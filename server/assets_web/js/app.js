import { parseSfen } from "/js/vendor/sfen.js";
import { buildUsiDrop, buildUsiMove, normalizeDropPieceType } from "/js/vendor/usi.js";
import { loadBoardTheme, loadBoardThemeConfig, THEME_LS_KEYS } from "/js/vendor/themeLoader.js";

/**
 * UI 方針:
 * - 盤のドラッグは HTML Drag & Drop を使わず Pointer Events で実装（タッチ対応を安定させる）
 * - 盤画像(theme.background)の board_region を基準にスケールして、余白はクロップして盤を最大化
 */

const HAND_ORDER = ["rook", "bishop", "gold", "silver", "knight", "lance", "pawn"];
const PIECE_LABEL = {
  king: "K",
  rook: "R",
  bishop: "B",
  gold: "G",
  silver: "S",
  knight: "N",
  lance: "L",
  pawn: "P",
  dragon: "+R",
  horse: "+B",
  promoted_silver: "+S",
  promoted_knight: "+N",
  promoted_lance: "+L",
  promoted_pawn: "+P",
};

// ---------- DOM ----------
const $ = (id) => document.getElementById(id);

const els = {
  toastHost: $("toastHost"),
  modalHost: $("modalHost"),

  wsStatus: $("wsStatus"),
  engineStatus: $("engineStatus"),

  menuBtn: $("menuBtn"),
  drawer: $("drawer"),
  drawerBackdrop: $("drawerBackdrop"),
  drawerClose: $("drawerClose"),

  // board
  boardWrap: $("boardWrap"),
  boardGrid: $("boardGrid"),
  dragGhost: $("dragGhost"),
  goteHand: $("goteHand"),
  senteHand: $("senteHand"),
  flipBtn: $("flipBtn"),

  // nav
  btnStart: $("btnStart"),
  btnPrev: $("btnPrev"),
  btnNext: $("btnNext"),
  btnEnd: $("btnEnd"),

  // meta
  currentSfen: $("currentSfen"),
  turnText: $("turnText"),

  // game
  titleInput: $("titleInput"),
  saveBtn: $("saveBtn"),
  moveList: $("moveList"),
  treeList: $("treeList"),

  // analysis
  analysisToggle: $("analysisToggle"),
  analysisMultipv: $("analysisMultipv"),
  analysisStatus: $("analysisStatus"),
  analysisGraph: $("analysisGraph"),
  analysisLines: $("analysisLines"),

  // menu actions
  newGameBtn: $("newGameBtn"),
  importFileBtn: $("importFileBtn"),
  importPasteBtn: $("importPasteBtn"),
  importFile: $("importFile"),
  importText: $("importText"),
  importBtn: $("importBtn"),

  exportFormat: $("exportFormat"),
  exportLink: $("exportLink"),

  gameList: $("gameList"),
  loadSelectedBtn: $("loadSelectedBtn"),
  refreshListBtn: $("refreshListBtn"),

  bgSet: $("bgSet"),
  pieceSet: $("pieceSet"),
};

// ---------- state ----------
const state = {
  ws: null,
  hasGranted: false,
  isOwner: false,
  sessionId: null,
  ownerToken: null,
  flip: false,

  theme: null,
  themeMeta: {
    bgNatural: null, // {w,h}
    region: null, // {startX,startY,endX,endY}
    layout: null, // computed for current boardPx {bgW,bgH,offX,offY,scale,boardPx}
  },

  game: null,

  // board interaction
  selection: null, // {kind:"board"|"hand", owner, pieceType, fromRow?,fromCol?, pointerId?}
  legal: [], // internal coords: [{row,col}]
  drag: null, // {pointerId, kind, owner, pieceType, fromRow?,fromCol?, startX,startY, active}
  lastBoardParsed: null, // parseSfen result

  analysis: {
    available: false,
    enabled: false,
    multipv: 1,
    statusText: "stopped",
    elapsedMs: 0,
    nodeId: null,
    lines: [],
    history: [], // [{t, v}] v:cp like
    engineStatus: null,
  },
};

// ---------- small helpers ----------
function toast(level, message, timeoutMs = 3200) {
  if (!els.toastHost) return;
  const div = document.createElement("div");
  div.className = `toast ${level || "info"}`.trim();
  div.textContent = String(message || "");
  els.toastHost.appendChild(div);
  window.setTimeout(() => {
    div.remove();
  }, timeoutMs);
}

function showModal({ title, message, actions }) {
  // actions: [{label, value, kind?}]
  if (!els.modalHost) return Promise.resolve(null);
  els.modalHost.hidden = false;
  els.modalHost.innerHTML = "";
  const wrap = document.createElement("div");
  wrap.className = "modal";

  const card = document.createElement("div");
  card.className = "modal-card";

  const t = document.createElement("div");
  t.className = "modal-title";
  t.textContent = title || "";

  const msg = document.createElement("div");
  msg.className = "modal-msg";
  msg.textContent = message || "";

  const btnRow = document.createElement("div");
  btnRow.className = "modal-actions";

  card.appendChild(t);
  card.appendChild(msg);
  card.appendChild(btnRow);
  wrap.appendChild(card);
  els.modalHost.appendChild(wrap);

  return new Promise((resolve) => {
    const close = (val) => {
      els.modalHost.hidden = true;
      els.modalHost.innerHTML = "";
      resolve(val);
    };

    (actions || [{ label: "OK", value: true }]).forEach((a) => {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = a.label;
      b.addEventListener("click", () => close(a.value));
      btnRow.appendChild(b);
    });

    wrap.addEventListener("click", (e) => {
      if (e.target === wrap) close(null);
    });
  });
}

function wsUrl() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${location.host}/ws`;
}

function setWsStatus(text, cls) {
  if (!els.wsStatus) return;
  els.wsStatus.textContent = text;
  els.wsStatus.className = `status-pill ${cls || ""}`.trim();
}

function setEngineStatus(text) {
  if (!els.engineStatus) return;
  els.engineStatus.textContent = text || "engine: -";
}

function sendWs(type, payload = {}) {
  const ws = state.ws;
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  // Owner messages must include freshness tokens (session_id + owner_token).
  // The server validates them to avoid stale tabs overriding the active session.
  const base = { type, payload };
  if (state.sessionId) base.session_id = state.sessionId;
  if (state.ownerToken) base.owner_token = state.ownerToken;
  ws.send(JSON.stringify(base));
}

function nodeById(id) {
  return state.game?.nodes?.find((n) => n.node_id === id) || null;
}

function childrenOf(nodeId) {
  const idx = state.game?.children_index?.[nodeId];
  if (!Array.isArray(idx)) return [];
  return idx.map((cid) => nodeById(cid)).filter(Boolean);
}

function parentOf(nodeId) {
  return nodeById(nodeId)?.parent_id || null;
}

function firstChildId(nodeId) {
  const idx = state.game?.children_index?.[nodeId];
  return Array.isArray(idx) && idx.length ? idx[0] : null;
}

function clamp(n, a, b) {
  return Math.min(b, Math.max(a, n));
}

function keyRC(r, c) {
  return `${r},${c}`;
}

// ---------- shogi movement (lightweight, enough for UI) ----------
const PLAYERS = { SENTE: "sente", GOTE: "gote" };

function isPromotedType(t) {
  return (
    t === "dragon" ||
    t === "horse" ||
    t === "promoted_pawn" ||
    t === "promoted_lance" ||
    t === "promoted_knight" ||
    t === "promoted_silver"
  );
}

function baseType(t) {
  const x = normalizeDropPieceType(t);
  return x || t;
}

function dir(owner) {
  // row 0 is gote side (rank a). Sente moves "up" => -1
  return owner === PLAYERS.SENTE ? -1 : 1;
}

function inBounds(r, c) {
  return r >= 0 && r < 9 && c >= 0 && c < 9;
}

function getPossibleMoves(board, fromRow, fromCol, piece) {
  if (!piece) return [];
  const t = piece.piece;
  const owner = piece.owner;
  const moves = [];
  const d = dir(owner);

  const add = (r, c) => {
    if (!inBounds(r, c)) return;
    const dst = board[r][c];
    if (dst && dst.owner === owner) return;
    moves.push({ row: r, col: c });
  };
  const addSlide = (dr, dc) => {
    let r = fromRow + dr;
    let c = fromCol + dc;
    while (inBounds(r, c)) {
      const dst = board[r][c];
      if (!dst) {
        moves.push({ row: r, col: c });
      } else {
        if (dst.owner !== owner) moves.push({ row: r, col: c });
        break;
      }
      r += dr;
      c += dc;
    }
  };

  // promoted pawn/lance/knight/silver act like gold
  if (t === "promoted_pawn" || t === "promoted_lance" || t === "promoted_knight" || t === "promoted_silver") {
    // gold
    add(fromRow + d, fromCol);
    add(fromRow + d, fromCol - 1);
    add(fromRow + d, fromCol + 1);
    add(fromRow, fromCol - 1);
    add(fromRow, fromCol + 1);
    add(fromRow - d, fromCol);
    return moves;
  }

  switch (t) {
    case "king":
      for (let dr = -1; dr <= 1; dr++) for (let dc = -1; dc <= 1; dc++) if (dr || dc) add(fromRow + dr, fromCol + dc);
      break;

    case "gold":
      add(fromRow + d, fromCol);
      add(fromRow + d, fromCol - 1);
      add(fromRow + d, fromCol + 1);
      add(fromRow, fromCol - 1);
      add(fromRow, fromCol + 1);
      add(fromRow - d, fromCol);
      break;

    case "silver":
      add(fromRow + d, fromCol);
      add(fromRow + d, fromCol - 1);
      add(fromRow + d, fromCol + 1);
      add(fromRow - d, fromCol - 1);
      add(fromRow - d, fromCol + 1);
      break;

    case "knight":
      add(fromRow + 2 * d, fromCol - 1);
      add(fromRow + 2 * d, fromCol + 1);
      break;

    case "lance":
      addSlide(d, 0);
      break;

    case "pawn":
      add(fromRow + d, fromCol);
      break;

    case "rook":
      addSlide(1, 0);
      addSlide(-1, 0);
      addSlide(0, 1);
      addSlide(0, -1);
      break;

    case "bishop":
      addSlide(1, 1);
      addSlide(1, -1);
      addSlide(-1, 1);
      addSlide(-1, -1);
      break;

    case "dragon": // rook + king diagonals
      addSlide(1, 0);
      addSlide(-1, 0);
      addSlide(0, 1);
      addSlide(0, -1);
      add(fromRow + 1, fromCol + 1);
      add(fromRow + 1, fromCol - 1);
      add(fromRow - 1, fromCol + 1);
      add(fromRow - 1, fromCol - 1);
      break;

    case "horse": // bishop + king orthogonals
      addSlide(1, 1);
      addSlide(1, -1);
      addSlide(-1, 1);
      addSlide(-1, -1);
      add(fromRow + 1, fromCol);
      add(fromRow - 1, fromCol);
      add(fromRow, fromCol + 1);
      add(fromRow, fromCol - 1);
      break;

    default:
      break;
  }
  return moves;
}

function wouldCreateNifu(board, row, col, owner) {
  for (let r = 0; r < 9; r++) {
    const p = board[r][col];
    if (p && p.owner === owner && p.piece === "pawn") return true;
  }
  return false;
}

function isDeadEndDrop(pieceType, row, owner) {
  const d = dir(owner);
  if (pieceType === "pawn" || pieceType === "lance") {
    return owner === PLAYERS.SENTE ? row === 0 : row === 8;
  }
  if (pieceType === "knight") {
    return owner === PLAYERS.SENTE ? row <= 1 : row >= 7;
  }
  return false;
}

function getDropMoves(board, pieceType, owner) {
  const t = baseType(pieceType);
  const out = [];
  for (let r = 0; r < 9; r++) {
    for (let c = 0; c < 9; c++) {
      if (board[r][c] !== null) continue;
      if (t === "pawn" && wouldCreateNifu(board, r, c, owner)) continue;
      if (isDeadEndDrop(t, r, owner)) continue;
      out.push({ row: r, col: c });
    }
  }
  return out;
}

const PROMOTABLE = new Set(["pawn", "lance", "knight", "silver", "bishop", "rook"]);
function canPromote(piece, fromRow, toRow) {
  const t = baseType(piece.piece);
  if (!PROMOTABLE.has(t)) return false;
  if (isPromotedType(piece.piece)) return false;
  if (piece.owner === PLAYERS.SENTE) return fromRow <= 2 || toRow <= 2;
  return fromRow >= 6 || toRow >= 6;
}
function mustPromote(piece, toRow) {
  const t = baseType(piece.piece);
  if (piece.owner === PLAYERS.SENTE) {
    if ((t === "pawn" || t === "lance") && toRow === 0) return true;
    if (t === "knight" && toRow <= 1) return true;
  } else {
    if ((t === "pawn" || t === "lance") && toRow === 8) return true;
    if (t === "knight" && toRow >= 7) return true;
  }
  return false;
}

// ---------- theme/layout ----------
async function ensureThemeLoaded() {
  state.theme = await loadBoardTheme();
  const bgUrl = state.theme?.background;
  const region = state.theme?.board_region;
  if (!bgUrl || !region?.start || !region?.end) {
    toast("warning", "テーマの board_region が読み取れませんでした（config.json を確認してね）");
    state.themeMeta.bgNatural = null;
    state.themeMeta.region = null;
    return;
  }
  state.themeMeta.region = {
    startX: Number(region.start.x || 0),
    startY: Number(region.start.y || 0),
    endX: Number(region.end.x || 0),
    endY: Number(region.end.y || 0),
  };

  // Ensure background image element exists inside the wrap.
  const bgEl = ensureBoardBgElement();
  bgEl.src = bgUrl;

  // load natural size (needed for accurate board_region mapping)
  try {
    const img = await waitImage(bgEl);
    state.themeMeta.bgNatural = { w: img.naturalWidth || img.width, h: img.naturalHeight || img.height };
  } catch {
    state.themeMeta.bgNatural = null;
  }
}

function ensureBoardBgElement() {
  if (els.boardBg) return els.boardBg;
  const wrap = els.boardWrap;
  if (!wrap) return null;
  const img = document.createElement("img");
  img.className = "board-bg";
  img.alt = "";
  img.draggable = false;
  wrap.insertBefore(img, wrap.firstChild);
  els.boardBg = img;

  // Re-apply layout when the image finishes loading.
  img.addEventListener("load", () => {
    state.themeMeta.bgNatural = { w: img.naturalWidth || img.width, h: img.naturalHeight || img.height };
    applyBoardLayout();
    if (state.lastBoardParsed) renderBoard(state.lastBoardParsed);
  });
  img.addEventListener("error", () => {
    state.themeMeta.bgNatural = null;
    applyBoardLayout();
  });
  return img;
}

function waitImage(img) {
  return new Promise((resolve, reject) => {
    if (!img) return reject(new Error("no image"));
    if (img.complete && (img.naturalWidth || img.width)) return resolve(img);
    const onLoad = () => {
      cleanup();
      resolve(img);
    };
    const onErr = (e) => {
      cleanup();
      reject(e || new Error("image load failed"));
    };
    const cleanup = () => {
      img.removeEventListener("load", onLoad);
      img.removeEventListener("error", onErr);
    };
    img.addEventListener("load", onLoad);
    img.addEventListener("error", onErr);
  });
}

function computeBoardLayout(edgeCap) {
  const nat = state.themeMeta.bgNatural;
  const reg = state.themeMeta.region;
  if (!nat || !reg) return null;
  const regW = reg.endX - reg.startX;
  const regH = reg.endY - reg.startY;
  if (regW <= 0 || regH <= 0) return null;

  // Make the board square using the smaller side of board_region, centered.
  const s = Math.min(regW, regH);
  const sx = reg.startX + (regW - s) / 2;
  const sy = reg.startY + (regH - s) / 2;

  // Fit full background within edgeCap.
  const scaleMax = edgeCap / Math.max(nat.w, nat.h);
  let boardPx = Math.floor((s * scaleMax) / 9) * 9;
  boardPx = clamp(boardPx, 270, edgeCap);
  const scale = boardPx / s;

  const bgW = nat.w * scale;
  const bgH = nat.h * scale;
  const boardLeft = sx * scale;
  const boardTop = sy * scale;

  return { bgW, bgH, boardLeft, boardTop, boardPx, scale };
}

function applyBoardLayout() {
  const wrap = els.boardWrap;
  if (!wrap) return;

  // available: board-col inner width and height (avoid hands & controls)
  const col = wrap.closest(".board-col");
  const colW = (col?.clientWidth || window.innerWidth) - 28;
  const h = window.innerHeight;
  const edgeCap = clamp(Math.floor(Math.min(colW, h - 290, 920)), 320, 920);

  const layout = computeBoardLayout(edgeCap);
  state.themeMeta.layout = layout;

  if (!layout) {
    // fallback: keep a reasonable square so the game is still usable
    wrap.style.width = `${edgeCap}px`;
    wrap.style.height = `${edgeCap}px`;
    els.boardGrid.style.left = "0px";
    els.boardGrid.style.top = "0px";
    els.boardGrid.style.width = "100%";
    els.boardGrid.style.height = "100%";
    return;
  }

  wrap.style.width = `${layout.bgW}px`;
  wrap.style.height = `${layout.bgH}px`;
  els.boardGrid.style.left = `${layout.boardLeft}px`;
  els.boardGrid.style.top = `${layout.boardTop}px`;
  els.boardGrid.style.width = `${layout.boardPx}px`;
  els.boardGrid.style.height = `${layout.boardPx}px`;
}

// ---------- render ----------
let squares = null; // 9x9 [viewR][viewC] => element

function ensureSquares() {
  if (squares) return;
  squares = Array.from({ length: 9 }, () => Array.from({ length: 9 }, () => null));
  els.boardGrid.innerHTML = "";
  for (let vr = 0; vr < 9; vr++) {
    for (let vc = 0; vc < 9; vc++) {
      const sq = document.createElement("div");
      sq.className = "sq";
      sq.dataset.vr = String(vr);
      sq.dataset.vc = String(vc);
      squares[vr][vc] = sq;
      els.boardGrid.appendChild(sq);
    }
  }
}

function viewToInternal(vr, vc) {
  const r = Number(vr);
  const c = Number(vc);
  if (!state.flip) return { row: r, col: c };
  return { row: 8 - r, col: 8 - c };
}
function internalToView(r, c) {
  if (!state.flip) return { vr: r, vc: c };
  return { vr: 8 - r, vc: 8 - c };
}

function pieceImgUrl(pieceType) {
  const m = state.theme?.pieces || {};
  const url = m[pieceType];
  return url || null;
}

function clearHighlights() {
  if (!squares) return;
  for (let vr = 0; vr < 9; vr++) {
    for (let vc = 0; vc < 9; vc++) {
      squares[vr][vc].classList.remove("hl", "legal");
    }
  }
}

function applyHighlights() {
  clearHighlights();
  const sel = state.selection;
  if (sel?.kind === "board" && typeof sel.fromRow === "number") {
    const { vr, vc } = internalToView(sel.fromRow, sel.fromCol);
    squares?.[vr]?.[vc]?.classList.add("hl");
  }
  const legal = state.legal || [];
  for (const m of legal) {
    const { vr, vc } = internalToView(m.row, m.col);
    squares?.[vr]?.[vc]?.classList.add("legal");
  }
}

function renderHands(parsed) {
  const cap = parsed?.capturedPieces || { sente: {}, gote: {} };
  const turn = parsed?.currentPlayer;

  const renderHand = (rootEl, owner) => {
    rootEl.innerHTML = "";
    for (const t of HAND_ORDER) {
      const n = Number(cap?.[owner]?.[t] || 0);
      if (!n) continue;

      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "hand-piece";
      btn.dataset.owner = owner;
      btn.dataset.pieceType = t;
      btn.title = `${owner}:${t}`;
      btn.disabled = owner !== turn || !state.isOwner; // only current turn and owner session

      const imgUrl = pieceImgUrl(t);
      if (imgUrl) {
        const img = document.createElement("img");
        img.src = imgUrl;
        img.alt = t;
        if (owner === "gote") img.style.transform = "rotate(180deg)";
        btn.appendChild(img);
      } else {
        const span = document.createElement("span");
        span.className = "piece-token";
        span.textContent = PIECE_LABEL[t] || t;
        btn.appendChild(span);
      }

      const count = document.createElement("span");
      count.className = "mini";
      count.textContent = `×${n}`;
      btn.appendChild(count);

      btn.addEventListener("click", () => {
        if (btn.disabled) return;
        selectHand(owner, t, parsed);
      });

      btn.addEventListener("pointerdown", (e) => {
        if (btn.disabled) return;
        if (!state.lastBoardParsed) return;
        e.preventDefault();
        selectHand(owner, t, parsed);
        state.drag = {
          pointerId: e.pointerId,
          kind: "hand",
          owner,
          pieceType: t,
          startX: e.clientX,
          startY: e.clientY,
          active: false,
        };
        try {
          btn.setPointerCapture(e.pointerId);
        } catch {
          // ignore
        }
      });

      rootEl.appendChild(btn);
    }
  };

  renderHand(els.goteHand, "gote");
  renderHand(els.senteHand, "sente");
}

function renderBoard(parsed) {
  ensureSquares();
  applyBoardLayout();

  // clear pieces
  for (let vr = 0; vr < 9; vr++) for (let vc = 0; vc < 9; vc++) squares[vr][vc].innerHTML = "";

  const board = parsed?.board;
  if (!board) return;

  for (let r = 0; r < 9; r++) {
    for (let c = 0; c < 9; c++) {
      const p = board[r][c];
      if (!p) continue;
      const { vr, vc } = internalToView(r, c);
      const sq = squares[vr][vc];

      const url = pieceImgUrl(p.piece);
      if (url) {
        const img = document.createElement("img");
        img.className = `piece ${p.owner === "gote" ? "gote" : ""}`.trim();
        img.src = url;
        img.alt = p.piece;
        img.draggable = false;
        img.dataset.owner = p.owner;
        img.dataset.pieceType = p.piece;
        img.dataset.vr = String(vr);
        img.dataset.vc = String(vc);
        sq.appendChild(img);
      } else {
        const span = document.createElement("div");
        span.className = "piece-token";
        span.textContent = PIECE_LABEL[p.piece] || p.piece;
        sq.appendChild(span);
      }
    }
  }

  applyHighlights();
}

function renderMoveList() {
  const list = els.moveList;
  if (!list) return;
  list.innerHTML = "";
  const ids = state.game?.current_path_node_ids || [];
  const curId = state.game?.current_node_id;
  // skip root
  for (let i = 1; i < ids.length; i++) {
    const id = ids[i];
    const node = nodeById(id);
    if (!node) continue;
    const li = document.createElement("li");
    li.textContent = `${Math.ceil(i / 2)}${i % 2 ? "▲" : "△"} ${node.move_usi || ""}`;
    if (id === curId) li.classList.add("current");
    li.addEventListener("click", () => sendWs("node:jump", { node_id: id }));
    list.appendChild(li);
  }
}

function renderTree() {
  const root = els.treeList;
  if (!root) return;
  root.innerHTML = "";
  const curId = state.game?.current_node_id;
  if (!curId) return;

  const addButton = (node, label, isCurrent) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = label;
    if (isCurrent) btn.classList.add("current");
    btn.addEventListener("click", () => sendWs("node:jump", { node_id: node.node_id }));
    root.appendChild(btn);
  };

  // show siblings (branch choices at parent)
  const parentId = parentOf(curId);
  if (parentId) {
    const sibs = childrenOf(parentId);
    if (sibs.length > 1) {
      const head = document.createElement("div");
      head.className = "mini";
      head.style.marginBottom = "6px";
      head.textContent = "分岐";
      root.appendChild(head);
      for (const n of sibs) addButton(n, n.move_usi || "(?)", n.node_id === curId);
      const hr = document.createElement("div");
      hr.style.height = "10px";
      root.appendChild(hr);
    }
  }

  // show next moves from current node
  const kids = childrenOf(curId);
  const head2 = document.createElement("div");
  head2.className = "mini";
  head2.style.marginBottom = "6px";
  head2.textContent = "次の手";
  root.appendChild(head2);
  if (!kids.length) {
    const empty = document.createElement("div");
    empty.className = "mini";
    empty.textContent = "（なし）";
    root.appendChild(empty);
    return;
  }
  for (const n of kids) addButton(n, n.move_usi || "(?)", false);
}

function syncMeta(parsed) {
  if (els.currentSfen) els.currentSfen.textContent = state.game?.current_position_sfen || "";
  if (els.turnText) {
    const ids = state.game?.current_path_node_ids || [];
    const ply = Math.max(0, ids.length - 1);
    const turn = parsed?.currentPlayer === "sente" ? "先手" : "後手";
    els.turnText.textContent = `${ply} 手目 / 手番: ${turn}`;
  }
  if (els.titleInput && state.game?.title && els.titleInput.value !== state.game.title) {
    els.titleInput.value = state.game.title;
  }
  if (els.exportLink && state.game?.game_id) {
    const fmt = String(els.exportFormat?.value || "usi");
    els.exportLink.href = `/api/export/${state.game.game_id}?format=${encodeURIComponent(fmt)}`;
  }
}

function scoreToCpLike(line) {
  if (!line) return null;
  if (line.score_type === "cp") return Number(line.score_value || 0);
  if (line.score_type === "mate") {
    const v = Number(line.score_value || 0);
    // mate in +N => huge, mate in -N => huge negative
    const sign = v >= 0 ? 1 : -1;
    return sign * 30000;
  }
  return null;
}

function formatScore(line) {
  if (!line) return "-";
  if (line.score_type === "cp") {
    const v = Number(line.score_value || 0);
    const s = v > 0 ? "+" : "";
    return `${s}${v} cp`;
  }
  if (line.score_type === "mate") {
    const v = Number(line.score_value || 0);
    const s = v > 0 ? "+" : "";
    return `mate ${s}${v}`;
  }
  return "unknown";
}

function renderAnalysis() {
  const a = state.analysis;

  if (els.analysisToggle) {
    els.analysisToggle.textContent = a.enabled ? "解析: ON" : "解析: OFF";
    els.analysisToggle.disabled = !a.available || !state.isOwner;
  }
  if (els.analysisMultipv) {
    const v = String(a.multipv || 1);
    if (els.analysisMultipv.value !== v) els.analysisMultipv.value = v;
    els.analysisMultipv.disabled = !a.available || !state.isOwner;
  }
  if (els.analysisStatus) {
    let s = a.statusText || "stopped";
    if (a.elapsedMs && a.lines?.length) s += ` (${(a.elapsedMs / 1000).toFixed(1)}s)`;
    els.analysisStatus.textContent = s;
  }

  renderAnalysisGraph();

  if (!els.analysisLines) return;
  els.analysisLines.innerHTML = "";
  if (!a.available) {
    const li = document.createElement("li");
    li.textContent = "解析エンジンが設定されていません";
    els.analysisLines.appendChild(li);
    return;
  }
  if (!a.lines?.length) {
    const li = document.createElement("li");
    li.textContent = "候補なし（解析ON → 局面を選ぶと更新）";
    els.analysisLines.appendChild(li);
    return;
  }

  for (const line of a.lines) {
    const li = document.createElement("li");

    const meta = document.createElement("div");
    meta.className = "meta";
    const pvIndex = document.createElement("span");
    pvIndex.textContent = `#${line.pv_index ?? 1}`;
    const score = document.createElement("span");
    score.className = "score";
    score.textContent = formatScore(line);
    const depth = document.createElement("span");
    depth.textContent = `d${line.depth ?? "-"}`;
    meta.appendChild(pvIndex);
    meta.appendChild(score);
    meta.appendChild(depth);

    const pv = document.createElement("div");
    pv.className = "pv";
    const pvUsi = Array.isArray(line.pv_usi) ? line.pv_usi.join(" ") : "";
    pv.textContent = pvUsi;

    const actRow = document.createElement("div");
    actRow.style.marginTop = "6px";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = "▶ PV先頭を指す";
    btn.addEventListener("click", () => {
      const first = Array.isArray(line.pv_usi) ? line.pv_usi[0] : null;
      if (!first || !state.game?.current_node_id) return;
      sendWs("node:play_move", { from_node_id: state.game.current_node_id, move_usi: first });
    });
    actRow.appendChild(btn);

    li.appendChild(meta);
    li.appendChild(pv);
    li.appendChild(actRow);
    els.analysisLines.appendChild(li);
  }
}

function renderAnalysisGraph() {
  const canvas = els.analysisGraph;
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  ctx.lineWidth = 2;
  ctx.strokeStyle = "rgba(244,244,245,.92)";

  const hist = state.analysis.history || [];
  if (hist.length < 2) return;

  // normalize window: last 60 points
  const view = hist.slice(-60);
  const ys = view.map((p) => p.v).filter((v) => typeof v === "number");
  if (!ys.length) return;
  const maxAbs = clamp(Math.max(...ys.map((v) => Math.abs(v))), 200, 30000);

  const pad = 10;
  const x0 = pad;
  const y0 = pad;
  const x1 = w - pad;
  const y1 = h - pad;

  // center line
  ctx.save();
  ctx.globalAlpha = 0.28;
  ctx.lineWidth = 1;
  ctx.strokeStyle = "rgba(244,244,245,.45)";
  ctx.beginPath();
  ctx.moveTo(x0, (y0 + y1) / 2);
  ctx.lineTo(x1, (y0 + y1) / 2);
  ctx.stroke();
  ctx.restore();

  ctx.globalAlpha = 1.0;
  ctx.lineWidth = 2;
  ctx.strokeStyle = "rgba(244,244,245,.92)";
  ctx.beginPath();
  for (let i = 0; i < view.length; i++) {
    const p = view[i];
    const x = x0 + (i / (view.length - 1)) * (x1 - x0);
    const y = (y0 + y1) / 2 - (p.v / maxAbs) * ((y1 - y0) / 2);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.stroke();
}

// ---------- actions ----------
function clearSelection() {
  state.selection = null;
  state.legal = [];
  state.drag = null;
  if (els.dragGhost) {
    els.dragGhost.style.opacity = "0";
    els.dragGhost.style.width = "0";
    els.dragGhost.style.height = "0";
  }
  applyHighlights();
}

function selectBoardSquare(fromRow, fromCol, piece, parsed) {
  if (!state.isOwner) return;
  const turn = parsed?.currentPlayer;
  if (!turn || piece.owner !== turn) return;
  state.selection = { kind: "board", fromRow, fromCol, owner: piece.owner, pieceType: piece.piece };
  state.legal = getPossibleMoves(parsed.board, fromRow, fromCol, piece);
  applyHighlights();
}

function selectHand(owner, pieceType, parsed) {
  if (!state.isOwner) return;
  const turn = parsed?.currentPlayer;
  if (!turn || owner !== turn) return;
  state.selection = { kind: "hand", owner, pieceType };
  state.legal = getDropMoves(parsed.board, pieceType, owner);
  applyHighlights();
}

async function commitMove(toRow, toCol, parsed) {
  const sel = state.selection;
  if (!sel || !state.game?.current_node_id) return;

  // check legal
  const ok = state.legal.some((m) => m.row === toRow && m.col === toCol);
  if (!ok) return;

  if (sel.kind === "board") {
    const fromRow = sel.fromRow;
    const fromCol = sel.fromCol;
    const piece = parsed.board[fromRow][fromCol];
    if (!piece) return;

    let promote = false;
    if (canPromote(piece, fromRow, toRow)) {
      if (mustPromote(piece, toRow)) {
        promote = true;
      } else {
        const ans = await showModal({
          title: "成りますか？",
          message: "成りを選択できます。",
          actions: [
            { label: "成る", value: "promote" },
            { label: "成らない", value: "no" },
            { label: "キャンセル", value: null },
          ],
        });
        if (ans == null) return;
        promote = ans === "promote";
      }
    }

    const usi = buildUsiMove({ fromRow, fromCol, toRow, toCol, promote });
    if (!usi) return;
    sendWs("node:play_move", { from_node_id: state.game.current_node_id, move_usi: usi });
    clearSelection();
    return;
  }

  if (sel.kind === "hand") {
    const usi = buildUsiDrop({ pieceType: sel.pieceType, toRow, toCol });
    if (!usi) return;
    sendWs("node:play_move", { from_node_id: state.game.current_node_id, move_usi: usi });
    clearSelection();
  }
}

// ---------- pointer handling ----------
function onPointerDown(e) {
  if (!state.lastBoardParsed) return;
  if (!state.isOwner) return;

  const target = e.target;
  const pieceEl = target?.closest?.("img.piece");
  const sqEl = target?.closest?.(".sq");
  if (!sqEl) return;

  const vr = Number(sqEl.dataset.vr);
  const vc = Number(sqEl.dataset.vc);
  const { row, col } = viewToInternal(vr, vc);

  const parsed = state.lastBoardParsed;
  const board = parsed.board;
  const p = board?.[row]?.[col] || null;

  // If we already have a selection and clicked a legal destination => commit
  if (state.selection && state.legal?.length) {
    const isLegal = state.legal.some((m) => m.row === row && m.col === col);
    if (isLegal) {
      e.preventDefault();
      commitMove(row, col, parsed);
      return;
    }
  }

  // click empty cancels
  if (!p) {
    clearSelection();
    return;
  }

  // select own-turn piece
  if (p.owner !== parsed.currentPlayer) {
    clearSelection();
    return;
  }

  selectBoardSquare(row, col, p, parsed);

  // setup drag candidate if pointerdown on piece image
  if (pieceEl && els.dragGhost) {
    state.drag = {
      pointerId: e.pointerId,
      kind: "board",
      owner: p.owner,
      pieceType: p.piece,
      fromRow: row,
      fromCol: col,
      startX: e.clientX,
      startY: e.clientY,
      active: false,
    };
    try {
      (els.boardWrap || els.boardGrid).setPointerCapture(e.pointerId);
    } catch {
      // ignore
    }
  }
}

function onPointerMove(e) {
  const d = state.drag;
  if (!d || d.pointerId !== e.pointerId) return;
  if (!state.lastBoardParsed) return;

  e.preventDefault();

  const dx = e.clientX - d.startX;
  const dy = e.clientY - d.startY;
  const dist = Math.hypot(dx, dy);

  if (!d.active && dist < 6) return;
  d.active = true;

  const url = pieceImgUrl(d.pieceType);
  if (url && els.dragGhost) {
    els.dragGhost.src = url;
    els.dragGhost.style.opacity = "0.95";
    const cell = (els.boardGrid?.clientWidth || els.boardWrap?.clientWidth || 600) / 9;
    const size = cell * 0.95;
    els.dragGhost.style.width = `${size}px`;
    els.dragGhost.style.height = `${size}px`;
    els.dragGhost.style.left = `${e.clientX - els.boardWrap.getBoundingClientRect().left}px`;
    els.dragGhost.style.top = `${e.clientY - els.boardWrap.getBoundingClientRect().top}px`;
    if (d.owner === "gote") els.dragGhost.style.transform = "translate(-50%, -50%) rotate(180deg)";
    else els.dragGhost.style.transform = "translate(-50%, -50%)";
  }
}

function onPointerUp(e) {
  const d = state.drag;
  if (!d || d.pointerId !== e.pointerId) return;
  const wasActive = !!d.active;
  state.drag = null;

  if (els.dragGhost) {
    els.dragGhost.style.opacity = "0";
  }

  if (!state.lastBoardParsed) return;
  if (!wasActive) return; // pointer-down selection should remain if user didn't drag

  const hit = document.elementFromPoint(e.clientX, e.clientY);
  const sqEl = hit?.closest?.(".sq");
  if (!sqEl) return;

  const vr = Number(sqEl.dataset.vr);
  const vc = Number(sqEl.dataset.vc);
  const { row, col } = viewToInternal(vr, vc);

  // If dragging was active and destination legal => commit
  const isLegal = state.legal?.some((m) => m.row === row && m.col === col);
  if (isLegal) {
    e.preventDefault();
    commitMove(row, col, state.lastBoardParsed);
  }
}

// ---------- game/menu wiring ----------
async function refreshGameList() {
  try {
    const res = await fetch("/api/games?limit=100&offset=0", { cache: "no-store" });
    const json = await res.json();
    const items = Array.isArray(json.items) ? json.items : [];
    els.gameList.innerHTML = "";
    for (const g of items) {
      const opt = document.createElement("option");
      opt.value = g.game_id;
      opt.textContent = `${g.title} (${g.updated_at || ""})`;
      els.gameList.appendChild(opt);
    }
  } catch (e) {
    toast("error", `ゲーム一覧取得に失敗: ${e}`);
  }
}

function openDrawer() {
  els.drawer.hidden = false;
}
function closeDrawer() {
  els.drawer.hidden = true;
}

async function importText(text) {
  try {
    const res = await fetch("/api/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: String(text || "") }),
    });
    const json = await res.json();
    if (!res.ok) throw new Error(json?.detail || `HTTP ${res.status}`);
    toast("info", `インポート: ${json.format || ""}`);
    // server sets current game; ws state will arrive
  } catch (e) {
    toast("error", `インポート失敗: ${e}`);
  }
}

async function setupThemeSelects() {
  try {
    const cfg = await loadBoardThemeConfig();
    const bg = Array.isArray(cfg.background_sets) ? cfg.background_sets : [];
    const ps = Array.isArray(cfg.piece_sets) ? cfg.piece_sets : [];

    const curBg = localStorage.getItem(THEME_LS_KEYS.backgroundSet) || "";
    const curPs = localStorage.getItem(THEME_LS_KEYS.pieceSet) || "";

    els.bgSet.innerHTML = "";
    for (const x of bg) {
      const opt = document.createElement("option");
      opt.value = x.name;
      opt.textContent = x.displayName || x.name;
      if (x.name === curBg) opt.selected = true;
      els.bgSet.appendChild(opt);
    }
    els.pieceSet.innerHTML = "";
    for (const x of ps) {
      const opt = document.createElement("option");
      opt.value = x.name;
      opt.textContent = x.displayName || x.name;
      if (x.name === curPs) opt.selected = true;
      els.pieceSet.appendChild(opt);
    }

    els.bgSet.addEventListener("change", async () => {
      localStorage.setItem(THEME_LS_KEYS.backgroundSet, els.bgSet.value);
      await ensureThemeLoaded();
      rerenderAll();
    });
    els.pieceSet.addEventListener("change", async () => {
      localStorage.setItem(THEME_LS_KEYS.pieceSet, els.pieceSet.value);
      await ensureThemeLoaded();
      rerenderAll();
    });
  } catch (e) {
    toast("warning", `テーマ選択の読み込みに失敗: ${e}`);
  }
}

// ---------- ws handling ----------
function syncAnalysisFromGame() {
  const ui = state.game?.ui_state || {};
  state.analysis.enabled = Boolean(ui.analysis_enabled);
  const raw = Number(ui.analysis_multipv || 1);
  // UI requirement: 1..5 (step=1)
  state.analysis.multipv = clamp(raw, 1, 5);

  // when node changes, clear running history
  const curNode = state.game?.current_node_id || null;
  if (state.analysis.nodeId && curNode && state.analysis.nodeId !== curNode) {
    state.analysis.lines = [];
    state.analysis.elapsedMs = 0;
    state.analysis.history = [];
    state.analysis.statusText = state.analysis.enabled ? "starting..." : "stopped";
  }
}

function connectWs() {
  setWsStatus("connecting…");
  const ws = new WebSocket(wsUrl());
  state.ws = ws;

  ws.addEventListener("open", () => {
    setWsStatus("connected", "connected");
  });

  ws.addEventListener("close", () => {
    setWsStatus("disconnected", "error");
    state.hasGranted = false;
    state.isOwner = false;
    state.sessionId = null;
    state.ownerToken = null;
    // retry
    window.setTimeout(connectWs, 1000);
  });

  ws.addEventListener("message", async (ev) => {
    let msg = null;
    try {
      msg = JSON.parse(ev.data);
    } catch {
      return;
    }
    const type = String(msg?.type || "");
    const payload = msg?.payload || {};

    if (type === "toast") {
      toast(payload.level || "info", payload.message || "");
      return;
    }

    if (type === "session:busy") {
      setWsStatus("busy", "busy");
      state.hasGranted = false;
      state.isOwner = false;
      state.sessionId = null;
      state.ownerToken = null;
      const ans = await showModal({
        title: "セッション使用中",
        message: "既に別の接続が操作中です。切断して引き継ぎますか？",
        actions: [
          { label: "引き継ぐ", value: "takeover" },
          { label: "キャンセル", value: null },
        ],
      });
      if (ans === "takeover") sendWs("session:takeover", {});
      return;
    }

    if (type === "session:kicked") {
      toast("warning", "セッションが引き継がれました");
      state.hasGranted = false;
      state.isOwner = false;
      state.sessionId = null;
      state.ownerToken = null;
      clearSelection();
      return;
    }

    if (type === "session:stale") {
      // Our tokens are stale (e.g., another tab took over). Force reconnect.
      toast("warning", "セッションが古い状態です。再接続します。");
      state.hasGranted = false;
      state.isOwner = false;
      state.sessionId = null;
      state.ownerToken = null;
      clearSelection();
      try {
        ws.close();
      } catch {
        // ignore
      }
      return;
    }

    if (type === "session:granted") {
      state.hasGranted = true;
      state.isOwner = true;

      state.sessionId = payload.session_id || null;
      state.ownerToken = payload.owner_token || null;

      const caps = payload.server_capabilities || {};
      state.analysis.available = Boolean(caps.analysis);
      state.analysis.engineStatus = payload.engine_status || null;
      state.analysis.enabled = Boolean(payload.analysis_state?.enabled);
      const rawMultipv = Number(payload.analysis_state?.multipv || 1) || 1;
      state.analysis.multipv = clamp(rawMultipv, 1, 5);

      // Engine status line
      const es = payload.engine_status || {};
      const shortCmd = String(es.command || "").split(/[\\/]/).pop();
      const evalHint = es.eval_dir ? " (eval)" : "";
      setEngineStatus(`engine: ${es.engine_name || es.status || "-"}${shortCmd ? ` [${shortCmd}]` : ""}${evalHint}`);
      if (es.last_error) {
        toast("error", String(es.last_error));
      }

      state.game = payload.game || null;
      syncAnalysisFromGame();
      rerenderAll();

      // If older configs stored MultiPV > 5, normalize it once.
      if (state.analysis.available && state.isOwner && state.sessionId && rawMultipv !== state.analysis.multipv) {
        sendWs("analysis:set_multipv", { multipv: state.analysis.multipv });
      }
      return;
    }

    if (type === "game:state") {
      state.game = payload.game || null;
      syncAnalysisFromGame();
      rerenderAll();
      return;
    }

    if (type === "analysis:update") {
      state.analysis.nodeId = payload.node_id || state.game?.current_node_id || null;
      state.analysis.elapsedMs = Number(payload.elapsed_ms || 0);
      state.analysis.lines = Array.isArray(payload.lines) ? payload.lines : [];
      state.analysis.statusText = "running";

      const best = payload.bestline || (state.analysis.lines?.[0] || null);
      const cp = scoreToCpLike(best);
      if (typeof cp === "number") {
        state.analysis.history.push({ t: Date.now(), v: cp });
      }
      rerenderAnalysisOnly();
      return;
    }

    if (type === "analysis:stopped") {
      state.analysis.statusText = String(payload.reason || "stopped");
      const r = String(payload.reason || "");
      if (/(failed|timeout|not configured|exited|error)/i.test(r)) {
        toast("error", r);
      }
      rerenderAnalysisOnly();
      return;
    }
  });
}

// ---------- rerender ----------
function rerenderAll() {
  if (!state.game) return;
  const parsed = parseSfen(state.game.current_position_sfen);
  state.lastBoardParsed = parsed;

  syncMeta(parsed);
  renderHands(parsed);
  renderBoard(parsed);
  renderMoveList();
  renderTree();
  renderAnalysis();

  // buttons enabled state
  els.saveBtn.disabled = !state.isOwner;
  els.btnStart.disabled = !state.isOwner;
  els.btnPrev.disabled = !state.isOwner;
  els.btnNext.disabled = !state.isOwner;
  els.btnEnd.disabled = !state.isOwner;
}

function rerenderAnalysisOnly() {
  renderAnalysis();
}

// ---------- init ----------
function wireUi() {
  // board pointer events
  els.boardGrid.addEventListener("pointerdown", onPointerDown);
  // pointermove/up are bound to window so dragging from "hand" also works
  window.addEventListener("pointermove", onPointerMove, { passive: false });
  window.addEventListener("pointerup", onPointerUp, { passive: false });
  window.addEventListener("pointercancel", onPointerUp, { passive: false });

  // flip
  els.flipBtn.addEventListener("click", () => {
    state.flip = !state.flip;
    rerenderAll();
  });

  // nav
  els.btnStart.addEventListener("click", () => {
    if (!state.game?.root_node_id) return;
    sendWs("node:jump", { node_id: state.game.root_node_id });
  });
  els.btnPrev.addEventListener("click", () => {
    const cur = state.game?.current_node_id;
    if (!cur) return;
    const p = parentOf(cur);
    if (p) sendWs("node:jump", { node_id: p });
  });
  els.btnNext.addEventListener("click", () => {
    const cur = state.game?.current_node_id;
    if (!cur) return;
    const c = firstChildId(cur);
    if (c) sendWs("node:jump", { node_id: c });
  });
  els.btnEnd.addEventListener("click", () => {
    let cur = state.game?.current_node_id;
    if (!cur) return;
    let next = firstChildId(cur);
    while (next) {
      cur = next;
      next = firstChildId(cur);
    }
    sendWs("node:jump", { node_id: cur });
  });

  // analysis controls
  els.analysisToggle.addEventListener("click", () => {
    if (!state.analysis.available) return;
    const next = !state.analysis.enabled;
    // optimistic UI (server echo will finalize)
    state.analysis.enabled = next;
    state.analysis.statusText = next ? "starting..." : "stopped";
    rerenderAnalysisOnly();
    sendWs("analysis:set_enabled", { enabled: next });
  });
  els.analysisMultipv.addEventListener("change", () => {
    const v = clamp(Number(els.analysisMultipv.value || 1), 1, 5);
    // keep UI in sync even before server echo
    els.analysisMultipv.value = String(v);
    sendWs("analysis:set_multipv", { multipv: v });
  });

  // title/save
  els.saveBtn.addEventListener("click", () => {
    const title = String(els.titleInput.value || "").trim();
    sendWs("game:save", { title });
    toast("info", "保存しました");
  });

  // drawer
  els.menuBtn.addEventListener("click", openDrawer);
  els.drawerBackdrop.addEventListener("click", closeDrawer);
  els.drawerClose.addEventListener("click", closeDrawer);

  // menu actions
  els.newGameBtn.addEventListener("click", () => {
    sendWs("game:new", {});
    closeDrawer();
  });

  els.importFileBtn.addEventListener("click", () => els.importFile.click());
  els.importFile.addEventListener("change", async () => {
    const f = els.importFile.files?.[0];
    if (!f) return;
    const text = await f.text();
    await importText(text);
    els.importFile.value = "";
    closeDrawer();
  });

  els.importPasteBtn.addEventListener("click", () => {
    els.importText.focus();
  });
  els.importBtn.addEventListener("click", async () => {
    const text = String(els.importText.value || "");
    await importText(text);
    closeDrawer();
  });

  els.exportFormat.addEventListener("change", () => {
    if (state.game?.game_id) {
      els.exportLink.href = `/api/export/${state.game.game_id}?format=${encodeURIComponent(els.exportFormat.value)}`;
    }
  });

  els.refreshListBtn.addEventListener("click", refreshGameList);
  els.loadSelectedBtn.addEventListener("click", () => {
    const id = els.gameList.value;
    if (id) sendWs("game:load", { game_id: id });
    closeDrawer();
  });

  // resize => re-layout
  window.addEventListener("resize", () => {
    if (state.game) {
      applyBoardLayout();
    }
  });
}

async function main() {
  ensureSquares();
  wireUi();
  await setupThemeSelects();
  await ensureThemeLoaded();
  applyBoardLayout();
  refreshGameList();
  connectWs();
}

main().catch((e) => {
  console.error(e);
  toast("error", String(e));
});
