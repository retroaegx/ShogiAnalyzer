import { parseSfen } from "/js/vendor/sfen.js";
import { buildUsiDrop, buildUsiMove } from "/js/vendor/usi.js";
import { loadBoardTheme, loadBoardThemeConfig, THEME_LS_KEYS } from "/js/vendor/themeLoader.js";
import {
  HAND_ORDER,
  PIECE_JA,
  FILE_LABEL,
  RANK_LABEL,
  canPromote,
  formatScore,
  legalDrops,
  legalMovesFrom,
  kifMove,
  kifPv,
  moveTarget,
  mustPromote,
  promotedTypeOf,
  senteScore,
  winRate,
} from "/js/shogi.js";

/*
 * Board geometry: the background image is shown at --bs px, and the 9x9 grid is
 * placed over the theme's board_region using the same scale, so pieces always
 * line up with the lines drawn in the image regardless of window size.
 */

const $ = (id) => document.getElementById(id);

const THEME_NAMES = {
  "theme.bg.wood": "木目",
  "theme.bg.classic_carbon": "カーボン",
  "theme.bg.ice_blue": "アイスブルー",
  "theme.bg.neon_night": "ネオンナイト",
  "theme.bg.white_gold": "ホワイトゴールド",
  "theme.piece.standard": "標準",
  "theme.piece.dark": "写真",
  "theme.piece.black": "黒文字",
  "theme.piece.matrix": "マトリックス",
  "theme.piece.neon": "ネオン",
  "theme.piece.white": "白地",
};

const LS_OPTS = "shogi_analyzer_view_opts";

// Chrome / Edge (Android) announce that the app can be installed; keep the event for our own button.
// Registered at load time: the event can fire before the rest of the page is set up.
let installEvent = null;
window.addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault();
  installEvent = e;
});

const els = {
  wsStatus: $("wsStatus"),
  engineStatus: $("engineStatus"),
  titleInput: $("titleInput"),
  titleLabel: $("titleLabel"),
  titleEditBtn: $("titleEditBtn"),
  titleSave: $("titleSave"),
  dlgTitle: $("dlgTitle"),

  boardArea: $("boardArea"),
  boardStage: $("boardStage"),
  boardFrame: $("boardFrame"),
  board: $("board"),
  boardBg: $("boardBg"),
  boardGrid: $("boardGrid"),
  boardOverlay: $("boardOverlay"),
  dragGhost: $("dragGhost"),
  coordFiles: $("coordFiles"),
  coordRanks: $("coordRanks"),
  standTop: $("standTop"),
  standBottom: $("standBottom"),
  handTop: $("handTop"),
  handBottom: $("handBottom"),
  standTopMark: $("standTopMark"),
  standTopName: $("standTopName"),
  standBottomMark: $("standBottomMark"),
  standBottomName: $("standBottomName"),
  evalBar: $("evalBar"),
  evalBarFill: $("evalBarFill"),
  evalBarText: $("evalBarText"),

  btnStart: $("btnStart"),
  btnPrev: $("btnPrev"),
  btnNext: $("btnNext"),
  btnEnd: $("btnEnd"),
  flipBtn: $("flipBtn"),
  plySlider: $("plySlider"),
  plyNow: $("plyNow"),
  plyMax: $("plyMax"),
  turnChip: $("turnChip"),

  multipvSeg: $("multipvSeg"),
  analysisOnOff: $("analysisOnOff"),
  engineSettingsBtn: $("engineSettingsBtn"),
  analyzeAllBtn: $("analyzeAllBtn"),
  batchProgress: $("batchProgress"),
  batchBar: $("batchBar"),
  batchText: $("batchText"),
  evalScore: $("evalScore"),
  evalVerdict: $("evalVerdict"),
  evalMeta: $("evalMeta"),
  pvList: $("pvList"),
  evalGraph: $("evalGraph"),

  kifuSub: $("kifuSub"),
  moveList: $("moveList"),
  variations: $("variations"),
  varTitle: $("varTitle"),
  varChips: $("varChips"),
  commentInput: $("commentInput"),

  newGameBtn: $("newGameBtn"),
  openBtn: $("openBtn"),
  importBtn: $("importBtn"),
  exportBtn: $("exportBtn"),
  saveBtn: $("saveBtn"),
  settingsBtn: $("settingsBtn"),
  menuBtn: $("menuBtn"),
  miniOnOff: $("miniOnOff"),
  miniScore: $("miniScore"),
  miniDepth: $("miniDepth"),
  miniVerdict: $("miniVerdict"),
  miniBest: $("miniBest"),
  dlgMenu: $("dlgMenu"),
  kifuCard: $("kifuCard"),
  kifuDrawerBtn: $("kifuDrawerBtn"),
  kifuDrawerClose: $("kifuDrawerClose"),
  kifuBackdrop: $("kifuBackdrop"),
  connOverlay: $("connOverlay"),
  connTitle: $("connTitle"),
  connMsg: $("connMsg"),
  optArrowLabels: $("optArrowLabels"),

  dialogHost: $("dialogHost"),
  dlgOpen: $("dlgOpen"),
  gameFilter: $("gameFilter"),
  gameList: $("gameList"),
  dlgImport: $("dlgImport"),
  dropzone: $("dropzone"),
  importFile: $("importFile"),
  pasteBtn: $("pasteBtn"),
  kifuCopyBtn: $("kifuCopyBtn"),
  dlgPaste: $("dlgPaste"),
  pasteTarget: $("pasteTarget"),
  dlgExport: $("dlgExport"),
  exportSeg: $("exportSeg"),
  exportPreview: $("exportPreview"),
  exportCopy: $("exportCopy"),
  exportDownload: $("exportDownload"),
  dlgSettings: $("dlgSettings"),
  bgChoices: $("bgChoices"),
  pieceChoices: $("pieceChoices"),
  optCoordsSeg: $("optCoordsSeg"),
  optEvalBar: $("optEvalBar"),
  optLegal: $("optLegal"),
  dlgEngine: $("dlgEngine"),
  engineName: $("engineName"),
  engineLoading: $("engineLoading"),
  engineForm: $("engineForm"),
  threadsRow: $("threadsRow"),
  threadsRange: $("threadsRange"),
  threadsNum: $("threadsNum"),
  threadsLimit: $("threadsLimit"),
  threadsDefault: $("threadsDefault"),
  hashRow: $("hashRow"),
  hashRange: $("hashRange"),
  hashNum: $("hashNum"),
  hashLimit: $("hashLimit"),
  hashDefault: $("hashDefault"),
  hashOptName: $("hashOptName"),
  batchSeconds: $("batchSeconds"),
  winRate: $("winRate"),
  wrSente: $("wrSente"),
  wrGote: $("wrGote"),
  wrFill: $("wrFill"),
  pvHead: $("pvHead"),
  autoStopSel: $("autoStopSel"),
  engineOptions: $("engineOptions"),
  engineResetAll: $("engineResetAll"),
  engineSave: $("engineSave"),
  dlgConfirm: $("dlgConfirm"),
  dlgConfirmTitle: $("dlgConfirmTitle"),
  dlgConfirmMsg: $("dlgConfirmMsg"),
  dlgConfirmActions: $("dlgConfirmActions"),

  toastHost: $("toastHost"),
};

const state = {
  ws: null,
  isOwner: false,
  sessionId: null,
  ownerToken: null,
  flip: false,
  opts: { coords: "overlay", evalBar: true, legal: true, lastMove: true, bestMove: true, nextMove: true, arrowLabels: true },

  theme: null,
  geom: null, // {natW, natH, rx, ry, rw, rh} in image px

  game: null,
  parsed: null,
  nodeMap: new Map(),
  mainLine: [], // node ids from root following the current path then first children

  selection: null, // {kind:"board"|"hand", owner, pieceType, fromRow?, fromCol?}
  legal: [],
  drag: null,

  analysis: {
    available: false,
    enabled: false,
    multipv: 1,
    status: "stopped",
    nodeId: null,
    elapsedMs: 0,
    lines: [],
  },
  engine: null,
  batch: null, // {index, total, node_id} while 全解析 runs
  evals: new Map(), // node_id -> {score_type, score_value, depth}
  evalsGameId: null,

  exportFormat: "kif",
};

// ---------- utilities ----------
const clamp = (n, a, b) => Math.min(b, Math.max(a, n));

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

function icon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "ico");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", `#i-${name}`);
  svg.appendChild(use);
  return svg;
}

function toast(level, message, timeoutMs = 3000) {
  const div = el("div", `toast ${level || "info"}`, String(message || ""));
  els.toastHost.appendChild(div);
  setTimeout(() => {
    div.classList.add("out");
    setTimeout(() => div.remove(), 220);
  }, timeoutMs);
}

function lsGet(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}
function lsSet(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // storage unavailable: settings just won't persist
  }
}

function loadOpts() {
  try {
    const raw = JSON.parse(lsGet(LS_OPTS) || "{}");
    Object.assign(state.opts, raw || {});
    // coordinates used to be on/off: on -> the new default (on the board frame), off -> hidden
    if (state.opts.coords === true) state.opts.coords = "overlay";
    if (state.opts.coords === false) state.opts.coords = "off";
    if (!["overlay", "outside", "off"].includes(state.opts.coords)) state.opts.coords = "overlay";
  } catch {
    // ignore
  }
}

function fmtNum(n) {
  n = Number(n || 0);
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)}G`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(0)}k`;
  return String(n);
}

function fmtDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const p = (x) => String(x).padStart(2, "0");
  return `${d.getFullYear()}/${p(d.getMonth() + 1)}/${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

// ---------- dialogs ----------
let openDialogEl = null;
let dialogResolve = null;

function showDialog(dlg) {
  closeDialog(null);
  els.dialogHost.hidden = false;
  dlg.hidden = false;
  openDialogEl = dlg;
  const focusable = dlg.querySelector("input:not([hidden]), textarea, .btn.primary, button");
  if (focusable) setTimeout(() => focusable.focus(), 30);
}

function closeDialog(value) {
  if (openDialogEl) openDialogEl.hidden = true;
  openDialogEl = null;
  els.dialogHost.hidden = true;
  if (dialogResolve) {
    const r = dialogResolve;
    dialogResolve = null;
    r(value);
  }
}

/** actions: [{label, value, primary?, img?}] -> resolves with value (null on dismiss). */
function confirmDialog({ title, message, actions }) {
  els.dlgConfirmTitle.textContent = title || "";
  els.dlgConfirmMsg.textContent = message || "";
  els.dlgConfirmMsg.hidden = !message;
  els.dlgConfirmActions.innerHTML = "";
  for (const a of actions || [{ label: "OK", value: true, primary: true }]) {
    const b = el("button", `btn${a.primary ? " primary" : ""}${a.danger ? " danger" : ""}${a.img ? " piece-choice" : ""}`);
    b.type = "button";
    if (a.img) {
      const img = el("img");
      img.src = a.img;
      img.alt = "";
      b.appendChild(img);
    }
    b.appendChild(el("span", null, a.label));
    b.addEventListener("click", () => closeDialog(a.value));
    els.dlgConfirmActions.appendChild(b);
  }
  showDialog(els.dlgConfirm);
  return new Promise((resolve) => {
    dialogResolve = resolve;
  });
}

// ---------- websocket ----------
// one id per browser tab: when this tab reconnects, the server hands the session straight back
// (no 「別の画面で操作中」 prompt) even if it has not noticed the old connection is gone yet
const TAB_ID = (() => {
  try {
    let id = sessionStorage.getItem("shogi_analyzer_tab");
    if (!id) {
      id = Math.random().toString(36).slice(2) + Date.now().toString(36);
      sessionStorage.setItem("shogi_analyzer_tab", id);
    }
    return id;
  } catch {
    return Math.random().toString(36).slice(2);
  }
})();

function wsUrl() {
  return `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/ws?tab=${encodeURIComponent(TAB_ID)}`;
}

// reconnect quickly: first retry almost at once, then back off a little
const WS_RETRY_MS = [150, 500, 1000, 2000, 3000];
let wsRetry = 0;
let wsRetryTimer = null;
let wsConnectTimer = null;
let wsPingTimer = null;

function scheduleReconnect(delay) {
  clearTimeout(wsRetryTimer);
  wsRetryTimer = setTimeout(connectWs, delay ?? WS_RETRY_MS[Math.min(wsRetry, WS_RETRY_MS.length - 1)]);
  wsRetry += 1;
}

/** Make sure the socket is really alive (after the phone wakes up, the network returns, …):
 * a closed socket reconnects at once, an open one must answer a ping quickly. */
function checkConnection() {
  const ws = state.ws;
  if (!ws || ws.readyState === WebSocket.CLOSED || ws.readyState === WebSocket.CLOSING) {
    wsRetry = 0;
    scheduleReconnect(0);
    return;
  }
  if (ws.readyState !== WebSocket.OPEN) return; // still connecting
  const sentAt = Date.now();
  try {
    ws.send(JSON.stringify({ type: "ping" }));
  } catch {
    scheduleReconnect(0);
    return;
  }
  clearTimeout(wsPingTimer);
  wsPingTimer = setTimeout(() => {
    // no answer: the connection is dead even if the browser has not noticed; start a new one
    if (state.ws === ws && (state.wsLastSeen || 0) < sentAt) {
      wsRetry = 0;
      connectWs();
    }
  }, 3000);
}

function sendWs(type, payload = {}) {
  const ws = state.ws;
  if (!ws || ws.readyState !== WebSocket.OPEN) return false;
  const msg = { type, payload };
  if (state.sessionId) msg.session_id = state.sessionId;
  if (state.ownerToken) msg.owner_token = state.ownerToken;
  ws.send(JSON.stringify(msg));
  return true;
}

function setConn(stateName, text) {
  els.wsStatus.dataset.state = stateName;
  els.wsStatus.querySelector(".status-text").textContent = text;
  els.wsStatus.title = text;
}

function resetSession() {
  state.isOwner = false;
  state.sessionId = null;
  state.ownerToken = null;
  clearSelection();
}

function connectWs() {
  clearTimeout(wsRetryTimer);
  clearTimeout(wsConnectTimer);
  clearTimeout(wsPingTimer);
  const old = state.ws;
  setConn("connecting", "接続中");
  const ws = new WebSocket(wsUrl());
  state.ws = ws;
  if (old && old.readyState <= WebSocket.OPEN) {
    try {
      old.close(); // replaced: its events are ignored from now on
    } catch {
      // already gone
    }
  }
  // a connection attempt that hangs (bad network) is abandoned and retried
  wsConnectTimer = setTimeout(() => {
    if (state.ws === ws && ws.readyState === WebSocket.CONNECTING) {
      try {
        ws.close();
      } catch {
        // ignore
      }
      scheduleReconnect();
    }
  }, 6000);

  ws.addEventListener("open", () => {
    if (state.ws !== ws) return;
    clearTimeout(wsConnectTimer);
    wsRetry = 0;
    state.wsLastSeen = Date.now();
    setConn("connected", "接続済み");
    showConnRestored();
  });
  ws.addEventListener("close", (ev) => {
    if (state.ws !== ws) return; // an old socket we already replaced
    clearTimeout(wsConnectTimer);
    if (ev.code === 4401) {
      // password protection is on and this browser is not logged in (or the login expired)
      location.replace("/login");
      return;
    }
    if (ev.code === 4409) {
      // another page with the same tab id (a duplicated tab) took the session: stay read-only
      toast("warning", "他の画面にセッションが引き継がれました");
      setConn("busy", "閲覧のみ");
      resetSession();
      renderControls();
      loadReadOnlyState();
      return;
    }
    setConn("error", "切断 — 再接続中");
    showConnLost();
    resetSession();
    renderControls();
    scheduleReconnect();
  });

  ws.addEventListener("message", async (ev) => {
    if (state.ws !== ws) return;
    state.wsLastSeen = Date.now();
    let msg;
    try {
      msg = JSON.parse(ev.data);
    } catch {
      return;
    }
    const type = String(msg?.type || "");
    const payload = msg?.payload || {};

    switch (type) {
      case "pong":
        clearTimeout(wsPingTimer);
        return;

      case "toast":
        toast(payload.level || "info", payload.message || "");
        return;

      case "session:busy": {
        setConn("busy", "他の接続が操作中");
        resetSession();
        loadReadOnlyState();
        const ans = await confirmDialog({
          title: "別の画面で操作中です",
          message: "このセッションは他のブラウザ/タブで使用されています。こちらに引き継ぎますか？",
          actions: [
            { label: "閲覧のみ", value: null },
            { label: "引き継ぐ", value: "takeover", primary: true },
          ],
        });
        if (ans === "takeover") sendWs("session:takeover", {});
        return;
      }

      case "session:kicked":
        toast("warning", "他の画面にセッションが引き継がれました");
        setConn("busy", "閲覧のみ");
        resetSession();
        loadReadOnlyState();
        return;

      case "session:stale":
        toast("warning", "セッションが古くなったため再接続します");
        resetSession();
        try {
          ws.close();
        } catch {
          // ignore
        }
        return;

      case "session:granted": {
        setConn("connected", "接続済み");
        state.isOwner = true;
        state.sessionId = payload.session_id || null;
        state.ownerToken = payload.owner_token || null;
        state.analysis.available = Boolean(payload.server_capabilities?.analysis);
        state.analysis.enabled = Boolean(payload.analysis_state?.enabled);
        state.analysis.multipv = clamp(Number(payload.analysis_state?.multipv || 1) || 1, 1, 5);
        state.engine = payload.engine_status || null;
        state.batch = state.engine?.batch || null;
        if (state.engine?.last_error) toast("error", String(state.engine.last_error));
        setGame(payload.game || null);
        return;
      }

      case "analysis:batch": {
        if (payload.state === "running") {
          state.batch = { index: payload.index, total: payload.total, node_id: payload.node_id, line: payload.line };
        } else {
          state.batch = null;
          if (payload.state === "done") toast("info", `全解析が完了しました（${payload.total}局面）`);
          else if (payload.state === "cancelled") toast("warning", "全解析を中止しました");
          refetchEvals();
        }
        if (state.game) {
          state.mainLine = computeMainLine(state.game);
          renderMoveList();
          renderVariations();
        }
        renderAnalysis();
        renderEvalGraph();
        renderControls();
        return;
      }

      case "game:deleted": {
        toast("info", `「${pendingDeleteTitle || "棋譜"}」を削除しました${payload.was_current ? "（新しい棋譜を開きました）" : ""}`);
        pendingDeleteTitle = "";
        openGameList(); // show the updated list
        return;
      }

      case "game:state":
        setGame(payload.game || null);
        return;

      case "analysis:update": {
        const a = state.analysis;
        a.nodeId = payload.node_id || state.game?.current_node_id || null;
        a.elapsedMs = Number(payload.elapsed_ms || 0);
        a.lines = Array.isArray(payload.lines) ? payload.lines : [];
        a.status = "running";
        const best = payload.bestline || a.lines[0];
        if (best && a.nodeId && (best.score_type === "cp" || best.score_type === "mate")) {
          const prev = state.evals.get(a.nodeId);
          if (!prev || (best.depth || 0) >= (prev.depth || 0)) {
            // keep the candidate lines too, so they can be shown later (analysis OFF / revisits)
            state.evals.set(a.nodeId, { score_type: best.score_type, score_value: best.score_value, depth: best.depth || 0, lines: a.lines });
          }
        }
        renderAnalysis();
        renderEvalGraph();
        updateMoveEvals();
        return;
      }

      case "analysis:stopped": {
        const reason = String(payload.reason || "stopped");
        // "idle": nobody moved for the auto-stop time; 常時解析 stays ON, the lines stay shown
        state.analysis.status = reason === "idle" ? "idle" : "stopped";
        // the batch keeps streaming other positions; don't keep showing their lines
        if (reason === "batch finished") state.analysis.lines = [];
        if (/(failed|timeout|not configured|exited|error)/i.test(reason)) toast("error", reason);
        renderAnalysis();
        return;
      }

      default:
        return;
    }
  });
}

// Non-owner connections get no game:state pushes; show a snapshot so the board isn't empty.
async function loadReadOnlyState() {
  try {
    const res = await fetch("/api/current", { cache: "no-store" });
    const json = await res.json();
    if (!state.isOwner && json.game) setGame(json.game);
  } catch {
    renderControls();
  }
}

// ---------- game state ----------
function setGame(game) {
  const prevNode = state.game?.current_node_id;
  const prevGame = state.game?.game_id;
  state.game = game;
  if (!game) return;

  state.nodeMap = new Map((game.nodes || []).map((n) => [n.node_id, n]));
  state.parsed = parseSfen(game.current_position_sfen);

  const ui = game.ui_state || {};
  if ("analysis_enabled" in ui) state.analysis.enabled = Boolean(ui.analysis_enabled);
  if (ui.analysis_multipv) state.analysis.multipv = clamp(Number(ui.analysis_multipv) || 1, 1, 5);

  if (prevNode !== game.current_node_id || prevGame !== game.game_id) {
    if (closePromotion) closePromotion(null);
    clearSelection(false);
    state.analysis.lines = [];
    state.analysis.elapsedMs = 0;
    state.analysis.nodeId = null;
    if (state.analysis.enabled) state.analysis.status = "starting";
  }

  state.mainLine = computeMainLine(game);

  if (state.evalsGameId !== game.game_id) {
    state.evals = new Map();
    state.evalsGameId = game.game_id;
    fetchEvals(game.game_id);
  }

  renderAll();
}

async function fetchEvals(gameId) {
  try {
    const res = await fetch(`/api/games/${encodeURIComponent(gameId)}/evals`, { cache: "no-store" });
    if (!res.ok) return;
    const json = await res.json();
    if (state.evalsGameId !== gameId) return;
    for (const [nodeId, ev] of Object.entries(json.items || {})) {
      const cur = state.evals.get(nodeId);
      if (!cur || (ev.depth || 0) >= (cur.depth || 0)) state.evals.set(nodeId, ev);
    }
    renderEvalGraph();
    updateMoveEvals();
    renderAnalysis();
  } catch {
    // graph just stays sparse
  }
}

// Line shown in the kifu list / slider / graph (and analysed by 全解析): path to the current
// position, then onward. Going back inside the line shown so far (also to before a branch
// point) keeps following that line; otherwise the first child onward. While 全解析 runs it is
// exactly the line being analysed.
function computeMainLine(game) {
  const line = state.batch?.line;
  if (Array.isArray(line) && line.includes(game.current_node_id)) return [...line];
  const kids = (id) => game.children_index?.[id] || [];
  const path = [...(game.current_path_node_ids || [])];
  const prev = state.mainLine || [];
  const at = prev.indexOf(game.current_node_id);
  if (at >= 0 && at + 1 === path.length && path.every((id, i) => prev[i] === id)) {
    for (let i = at + 1; i < prev.length && kids(path[path.length - 1]).includes(prev[i]); i++) path.push(prev[i]);
  }
  for (let next = kids(path[path.length - 1])[0]; next; next = kids(next)[0]) path.push(next);
  return path;
}

function refetchEvals() {
  if (state.game?.game_id) fetchEvals(state.game.game_id);
}

const node = (id) => state.nodeMap.get(id) || null;
function children(id) {
  const ids = state.game?.children_index?.[id];
  return Array.isArray(ids) ? ids.map(node).filter(Boolean) : [];
}
function firstChild(id) {
  const ids = state.game?.children_index?.[id];
  return Array.isArray(ids) && ids.length ? ids[0] : null;
}
function sideToMoveOf(n) {
  if (!n) return "sente";
  const parts = String(n.position_sfen || "").split(/\s+/);
  return parts[1] === "w" ? "gote" : "sente";
}
function curPly() {
  return Math.max(0, (state.game?.current_path_node_ids?.length || 1) - 1);
}

// While 全解析 runs, the server moves the position itself and the kifu is read-only.
let lockToastAt = 0;
function kifuLocked() {
  if (!state.batch) return false;
  if (Date.now() - lockToastAt > 2500) {
    lockToastAt = Date.now();
    toast("warning", "全解析中は棋譜を操作できません（中止すると操作できます）");
  }
  return true;
}

function jump(nodeId) {
  if (!nodeId || nodeId === state.game?.current_node_id || kifuLocked()) return;
  sendWs("node:jump", { node_id: nodeId });
}

function nodeLabel(n) {
  if (!n?.move_usi) return "";
  const parent = n.parent_id ? node(n.parent_id) : null;
  if (!parent) return n.move_usi;
  const prevTo = parent.move_usi ? moveTarget(parent.move_usi) : null;
  return kifMove(parent.position_sfen, n.move_usi, prevTo);
}

// ---------- theme / geometry ----------
async function loadTheme() {
  state.theme = await loadBoardTheme();
  const t = state.theme || {};
  const reg = t.board_region;
  els.boardBg.src = t.background || "";
  try {
    await els.boardBg.decode();
  } catch {
    // fall back to defaults below
  }
  const natW = els.boardBg.naturalWidth || 1000;
  const natH = els.boardBg.naturalHeight || 1000;
  // Grid line positions (image px). The drawn lines in the board images are not
  // perfectly uniform, so themes carry measured `grid_lines`; fall back to an even split.
  const even = (a, b) => Array.from({ length: 10 }, (_, i) => a + ((b - a) * i) / 9);
  const valid = (v) => Array.isArray(v) && v.length === 10 && v.every((n) => Number.isFinite(Number(n)));
  let xs;
  let ys;
  if (valid(t.grid_lines?.x) && valid(t.grid_lines?.y)) {
    xs = t.grid_lines.x.map(Number);
    ys = t.grid_lines.y.map(Number);
  } else if (reg?.start && reg?.end) {
    xs = even(Number(reg.start.x || 0), Number(reg.end.x || natW));
    ys = even(Number(reg.start.y || 0), Number(reg.end.y || natH));
  } else {
    xs = even(0, natW);
    ys = even(0, natH);
  }
  state.geom = { natW, natH, xs, ys, rx: xs[0], ry: ys[0], rw: xs[9] - xs[0], rh: ys[9] - ys[0] };
  const tracks = (v) => v.slice(1).map((n, i) => `${(n - v[i]).toFixed(2)}fr`).join(" ");
  els.boardGrid.style.gridTemplateColumns = tracks(xs);
  els.boardGrid.style.gridTemplateRows = tracks(ys);
  els.coordFiles.style.gridTemplateColumns = tracks(xs);
  els.coordRanks.style.gridTemplateRows = tracks(ys);
  els.boardOverlay.setAttribute("viewBox", `0 0 ${state.geom.rw} ${state.geom.rh}`);
  const grid = t.grid || {};
  els.boardGrid.classList.toggle("draw-lines", Boolean(grid.show));
  if (grid.color) els.boardGrid.style.setProperty("--grid-color", grid.color);
  const coordColor = t.coordinates?.color;
  void coordColor; // coordinates are drawn outside the board in UI colors
  layoutBoard();
}

function isMobile() {
  return window.matchMedia("(max-width: 900px)").matches;
}

function layoutBoard() {
  const g = state.geom;
  if (!g) return;
  const root = document.documentElement;
  const frac = g.rw / g.natW; // region width relative to image
  const cellPerBs = frac / 9;
  const mobile = isMobile();
  // coordinate band: a fraction of a square, clamped (slimmer on phones)
  const coordRatio = mobile ? 0.34 : 0.42;
  const coordMin = mobile ? 11 : 14;
  const coordMax = mobile ? 16 : 26;
  // only "outside" reserves a band next to the board; "overlay" draws on the board frame
  const coordsOutside = state.opts.coords === "outside";
  const coordK = coordsOutside ? cellPerBs * coordRatio : 0;

  const area = els.boardArea.getBoundingClientRect();
  const nav = els.boardArea.querySelector(".navbar").getBoundingClientRect().height || 54;
  let bs;
  if (mobile) {
    // Phone (no page scroll): the board comes first and takes the full width when the height
    // allows it. Below it only a minimum is reserved (候補手/全解析 row + a small graph); the
    // graph then grows into whatever height the board leaves.
    const main = els.boardArea.parentElement;
    const ms = getComputedStyle(main);
    const mainH = main.clientHeight - parseFloat(ms.paddingTop) - parseFloat(ms.paddingBottom);
    const gap = parseFloat(ms.rowGap) || 6;
    const ctlH = document.querySelector(".analysis-card")?.offsetHeight || 40;
    // short screens (iPhone SE…): the graph gives way first so the stands can stay above / below
    const graphMin = window.innerHeight < 640 ? 40 : 60;
    const availW = area.width;
    const availH = mainH - nav - 4 - (ctlH + gap + graphMin + gap);
    const coordPx = coordsOutside ? Math.max(coordMin, Math.min(coordMax, (availW * cellPerBs * coordRatio) / (1 + coordK))) : 0;
    // stands always above / below the board (rows fixed at 0.82 of a square, see app.css):
    // beside the board they were too narrow to tap and could not show many captured pieces
    els.boardStage.classList.remove("stands-side");
    bs = Math.min(availW - coordPx, (availH - 8 - coordPx) / (g.natH / g.natW + 2 * cellPerBs * 0.82));
  } else {
    els.boardStage.classList.remove("stands-side");
    const standK = cellPerBs * 1.9; // matches --stand-w (fixed 2-column stands)
    const fixedW = (state.opts.evalBar ? 12 : 0) + 3 * 12;
    const bsW = (area.width - fixedW) / (1 + 2 * standK + coordK);
    const bsH = (area.height - nav - 14) / (1 + coordK);
    bs = Math.min(bsW, bsH);
  }
  bs = Math.floor(clamp(bs, mobile ? 160 : 220, 1400)); // phones: never larger than the space left
  const scale = bs / g.natW;
  const cell = (g.rw * scale) / 9;
  const coord = coordsOutside ? Math.round(clamp(cell * coordRatio, coordMin, coordMax)) : 0;
  // overlay: font from the square size; strips at least as wide as the text
  const covFont = Math.round(clamp(cell * 0.22, 9, 14));
  const rightMargin = bs - (g.rx + g.rw) * scale;
  root.style.setProperty("--cov-font", `${covFont}px`);
  // strips a little narrower than the frame margin: the text sits slightly toward the outer edge
  root.style.setProperty("--cov-x", `${Math.max(rightMargin * 0.84, covFont * 1.1)}px`);
  root.style.setProperty("--cov-y", `${Math.max(g.ry * scale * 0.84, covFont * 1.05)}px`);
  root.style.setProperty("--bs", `${bs}px`);
  root.style.setProperty("--cell", `${cell}px`);
  root.style.setProperty("--coord", `${coord}px`);
  root.style.setProperty("--rl", `${g.rx * scale}px`);
  root.style.setProperty("--rt", `${g.ry * scale}px`);
  root.style.setProperty("--rw", `${g.rw * scale}px`);
  root.style.setProperty("--rh", `${g.rh * scale}px`);
  els.board.style.height = `${Math.round(g.natH * scale)}px`;
}

// ---------- board rendering ----------
let squares = null; // [vr][vc]

function ensureSquares() {
  if (squares) return;
  squares = [];
  els.boardGrid.innerHTML = "";
  for (let vr = 0; vr < 9; vr++) {
    const row = [];
    for (let vc = 0; vc < 9; vc++) {
      const sq = el("div", "sq");
      sq.dataset.vr = String(vr);
      sq.dataset.vc = String(vc);
      els.boardGrid.appendChild(sq);
      row.push(sq);
    }
    squares.push(row);
  }
}

const toView = (r, c) => (state.flip ? { vr: 8 - r, vc: 8 - c } : { vr: r, vc: c });
const toInternal = (vr, vc) => (state.flip ? { row: 8 - vr, col: 8 - vc } : { row: vr, col: vc });

// Pieces of the side sitting at the top of the board are drawn upside down.
const upsideDown = (owner) => (owner === "gote") !== state.flip;

function pieceUrl(type, owner) {
  const p = state.theme?.pieces || {};
  if (p.sente || p.gote) return p[owner]?.[type] || p.sente?.[type] || null;
  return p[type] || null;
}

function makePieceEl(type, owner, cls) {
  const url = pieceUrl(type, owner);
  if (url) {
    const img = el("img", `${cls} ${upsideDown(owner) ? "gote" : ""}`.trim());
    img.src = url;
    img.alt = PIECE_JA[type] || type;
    img.draggable = false;
    return img;
  }
  return el("span", `piece-token ${upsideDown(owner) ? "gote" : ""}`.trim(), (PIECE_JA[type] || "?").slice(-1));
}

function renderCoords() {
  els.boardFrame.classList.toggle("no-coords", state.opts.coords === "off");
  els.boardFrame.classList.toggle("coords-overlay", state.opts.coords === "overlay");
  els.coordFiles.innerHTML = "";
  els.coordRanks.innerHTML = "";
  for (let i = 0; i < 9; i++) {
    const file = state.flip ? i + 1 : 9 - i;
    const rank = state.flip ? 9 - i : i + 1;
    els.coordFiles.appendChild(el("span", null, String(file)));
    els.coordRanks.appendChild(el("span", null, RANK_LABEL(rank)));
  }
}

function renderBoard() {
  ensureSquares();
  const parsed = state.parsed;
  const board = parsed?.board;
  const cur = node(state.game?.current_node_id);
  const last = cur?.move_usi ? moveTarget(cur.move_usi) : null;
  const turn = parsed?.currentPlayer;

  const showLast = state.opts.lastMove;
  for (let r = 0; r < 9; r++) {
    for (let c = 0; c < 9; c++) {
      const { vr, vc } = toView(r, c);
      const sq = squares[vr][vc];
      sq.className = "sq";
      sq.innerHTML = "";
      const p = board?.[r]?.[c];
      const isLastTo = showLast && last && last.row === r && last.col === c;
      if (isLastTo) sq.classList.add("last-to");
      if (showLast && last && last.fromRow === r && last.fromCol === c) sq.appendChild(el("div", "ind ind-from"));
      if (!p) continue;
      if (p.owner === turn) sq.classList.add("mine");
      const pe = isLastTo ? makeLastMovePiece(p.piece, p.owner) : makePieceEl(p.piece, p.owner, "piece");
      const d = state.drag;
      if (d?.active && d.kind === "board" && d.fromRow === r && d.fromCol === c) pe.classList.add("lifted");
      sq.appendChild(pe);
    }
  }
  els.boardGrid.classList.toggle("can-move", state.isOwner);
  applyHighlights();
  renderOverlay();
}

// Last moved piece: outline + ripple layers (falls back to the plain piece for text tokens).
function makeLastMovePiece(type, owner) {
  const url = pieceUrl(type, owner);
  if (!url) return makePieceEl(type, owner, "piece");
  const wrap = el("span", `piece-wrap${upsideDown(owner) ? " gote" : ""}`);
  for (const cls of ["ripple", "outline"]) {
    const img = el("img", cls);
    img.src = url;
    img.alt = cls === "outline" ? PIECE_JA[type] || type : "";
    img.draggable = false;
    wrap.appendChild(img);
  }
  return wrap;
}

// ---------- board overlay (computer moves / next move / branches) ----------
const SVG_NS = "http://www.w3.org/2000/svg";

function svgEl(tag, attrs) {
  const e = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, String(v));
  return e;
}

// Center of a *visual* square in overlay (image px, relative to the first grid line).
function cellCenter(vr, vc) {
  const { xs, ys } = state.geom;
  return { x: (xs[vc] + xs[vc + 1]) / 2 - xs[0], y: (ys[vr] + ys[vr + 1]) / 2 - ys[0] };
}

// on-screen px per overlay unit (the overlay viewBox is in board-image pixels)
function overlayPxPerUnit() {
  const rw = state.geom.rw;
  return (els.boardOverlay.getBoundingClientRect().width || rw) / rw;
}

// rough text width: CJK ~1em, ASCII ~0.56em
function textWidth(text, fs) {
  let w = 0;
  for (const ch of text) w += /[\u0000-\u007f]/.test(ch) ? 0.56 : 1.0;
  return w * fs;
}

// label boxes placed in the current overlay render (to keep labels from overlapping)
let overlayLabels = [];
// boxes along every arrow / marker drawn in this render ({x, y, w, h, owner}): labels keep off them
let overlayObstacles = [];
const boxesOverlap = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;

/** Arrow sizes for a move (shared by the drawing and the label avoidance). */
function arrowSize(weight) {
  const cell = state.geom.rw / 9;
  const s = Math.max(weight, 0.7);
  return { shaftW: cell * 0.085 * s, headW: cell * 0.32 * s, headL: cell * 0.32 * s };
}

/** Register the area an arrow (or drop marker) covers, as a row of small boxes along it. */
function addArrowObstacles(usi, weight, owner) {
  const t = moveTarget(usi);
  if (!t || !state.geom) return;
  const cell = state.geom.rw / 9;
  const to = toView(t.row, t.col);
  const p1 = cellCenter(to.vr, to.vc);
  if (t.fromRow == null) {
    const r = cell * 0.34 * Math.max(weight, 0.8);
    overlayObstacles.push({ x: p1.x - r, y: p1.y - r, w: 2 * r, h: 2 * r, owner });
    return;
  }
  const fr = toView(t.fromRow, t.fromCol);
  const p0 = cellCenter(fr.vr, fr.vc);
  const { shaftW, headW } = arrowSize(weight);
  const dist = Math.hypot(p1.x - p0.x, p1.y - p0.y);
  const steps = Math.max(2, Math.ceil(dist / (cell * 0.25)));
  for (let k = 0; k <= steps; k++) {
    const f = k / steps;
    const half = (f > 0.75 ? headW : shaftW * 1.6) / 2;
    const x = p0.x + (p1.x - p0.x) * f;
    const y = p0.y + (p1.y - p0.y) * f;
    overlayObstacles.push({ x: x - half, y: y - half, w: 2 * half, h: 2 * half, owner });
  }
}

/**
 * Small pill label beside a move ("候補手 -134" / "指し手" ...), nudged away from other labels.
 * score: optional {text, cls} shown after the name in the same pill (one pill per move,
 * so the name and the evaluation can never collide).
 */
function moveLabel(anchor, normal, dist, text, cls, primary, score = null, owner = null, along = null) {
  const { rw, rh } = state.geom;
  const cell = rw / 9;
  const fs = Math.max(cell * (primary ? 0.17 : 0.15), (primary ? 9.5 : 8.5) / overlayPxPerUnit());
  const sfs = fs * 1.12;
  const gap = fs * 0.35;
  const pfs = fs * 0.78;
  const promoW = score?.promo ? gap * 0.6 + textWidth(score.promo, pfs) : 0;
  const w = textWidth(text, fs) + (score ? (text ? gap : 0) + textWidth(score.text, sfs) * 0.92 + promoW : 0) + fs * 0.9;
  const h = fs * 1.5;
  // distance from the arrow to the pill's centre: half the pill's extent along the normal
  // (its width for vertical arrows, its height for horizontal ones), so it never covers the arrow
  const base = dist + Math.abs(normal.x) * (w / 2) + Math.abs(normal.y) * (h / 2);
  // beside the arrow first, then further out, then slid along it; never on another label or arrow
  const slide = along ? [0, 0.9, -0.9, 1.6, -1.6].map((v) => v * cell) : [0];
  let box = null;
  let first = null;
  search: for (const sl of slide) {
    for (const k of [1, -1, 1.9, -1.9, 2.8, -2.8]) {
      const cx = clamp(anchor.x + normal.x * base * k + (along?.x || 0) * sl, w / 2, rw - w / 2);
      const cy = clamp(anchor.y + normal.y * base * k + (along?.y || 0) * sl, h / 2, rh - h / 2);
      box = { x: cx - w / 2, y: cy - h / 2, w, h };
      first ??= box;
      // keep a small gap between pills, not just "not overlapping"
      const m = h * 0.2;
      const padded = { x: box.x - m, y: box.y - m, w: w + 2 * m, h: h + 2 * m };
      if (!overlayLabels.some((b) => boxesOverlap(b, padded)) && !overlayObstacles.some((o) => o.owner !== owner && boxesOverlap(o, padded))) break search;
      box = null;
    }
  }
  box ??= first;
  overlayLabels.push(box);
  const g = svgEl("g", { class: `mv-label ${cls}` });
  g.appendChild(svgEl("rect", { x: box.x, y: box.y, width: w, height: h, rx: h * 0.35, "stroke-width": cell * 0.016 }));
  const t = svgEl("text", { x: box.x + w / 2, y: box.y + h / 2, "font-size": fs });
  const name = svgEl("tspan", {});
  name.textContent = text;
  t.appendChild(name);
  if (score) {
    const sc = svgEl("tspan", { class: `lab-score ${score.cls || ""}`.trim(), dx: text ? gap : 0, "font-size": sfs });
    sc.textContent = score.text;
    t.appendChild(sc);
    if (score.promo) {
      const pr = svgEl("tspan", { class: "lab-promo", dx: gap * 0.6, "font-size": pfs });
      pr.textContent = score.promo;
      t.appendChild(pr);
    }
  }
  g.appendChild(t);
  return g;
}

/**
 * Arrow (shaft + head) for a move, or a marker for a drop, with a small label.
 * kind: "best" | "best sub" | "next" | "branch"; score: optional {text, cls} for candidates
 */
function overlayShape(usi, kind, weight = 1, labelText = "", score = null, owner = null) {
  const t = moveTarget(usi);
  if (!t || !state.geom) return null;
  const cell = state.geom.rw / 9;
  const to = toView(t.row, t.col);
  const p1 = cellCenter(to.vr, to.vc);
  const g = svgEl("g", { class: kind });
  const labelCls = `lab-${kind.split(" ")[0]}${kind.includes("sub") ? " lab-sub" : ""}`;
  const primary = kind === "best" || kind === "next";

  if (t.fromRow == null) {
    // drop: a marker with the dropped piece's character at the destination
    const type = String(usi[0] || "");
    const name = { P: "歩", L: "香", N: "桂", S: "銀", G: "金", B: "角", R: "飛" }[type] || "打";
    const r = cell * 0.34 * Math.max(weight, 0.8);
    g.setAttribute("class", `mk ${kind}`);
    g.appendChild(svgEl("circle", { cx: p1.x, cy: p1.y, r, "stroke-width": cell * 0.05 }));
    const text = svgEl("text", { x: p1.x, y: p1.y, "font-size": r * 1.2, "stroke-width": cell * 0.045 });
    // oriented like the dropping side's pieces (upside down for the side at the top)
    if (upsideDown(state.parsed?.currentPlayer || "sente")) text.setAttribute("transform", `rotate(180 ${p1.x} ${p1.y})`);
    text.textContent = name;
    g.appendChild(text);
    if (labelText || score) g.appendChild(moveLabel(p1, { x: 0, y: -1 }, r + cell * 0.04, labelText, labelCls, primary, score, owner));
    return g;
  }

  const fr = toView(t.fromRow, t.fromCol);
  const p0 = cellCenter(fr.vr, fr.vc);
  const dist = Math.hypot(p1.x - p0.x, p1.y - p0.y);
  if (dist < 1) return null;
  const u = { x: (p1.x - p0.x) / dist, y: (p1.y - p0.y) / dist };
  const n = { x: -u.y, y: u.x };
  const size = arrowSize(weight);
  const shaftW = size.shaftW;
  const headW = size.headW;
  const start = { x: p0.x + u.x * cell * 0.22, y: p0.y + u.y * cell * 0.22 };
  const tip = { x: p1.x + u.x * cell * 0.04, y: p1.y + u.y * cell * 0.04 };
  const len = Math.hypot(tip.x - start.x, tip.y - start.y);
  const headL = Math.min(size.headL, len * 0.6);
  const base = { x: tip.x - u.x * headL, y: tip.y - u.y * headL };
  const P = (p, k) => `${(p.x + n.x * k).toFixed(1)} ${(p.y + n.y * k).toFixed(1)}`;
  const d = [
    `M ${P(start, shaftW / 2)}`,
    `L ${P(base, shaftW / 2)}`,
    `L ${P(base, headW / 2)}`,
    `L ${tip.x.toFixed(1)} ${tip.y.toFixed(1)}`,
    `L ${P(base, -headW / 2)}`,
    `L ${P(base, -shaftW / 2)}`,
    `L ${P(start, -shaftW / 2)}`,
    "Z",
  ].join(" ");
  g.appendChild(
    svgEl("path", {
      class: "arrow",
      d,
      "stroke-width": cell * 0.03,
      ...(kind === "branch" ? { "stroke-dasharray": `${cell * 0.1} ${cell * 0.07}` } : {}),
    }),
  );

  if (labelText || score) {
    // beside the middle of the shaft, on the upper side (right side for vertical moves)
    let ln = n;
    if (ln.y > 0.2 || (Math.abs(ln.y) <= 0.2 && ln.x < 0)) ln = { x: -n.x, y: -n.y };
    const mid = { x: (start.x + base.x) / 2, y: (start.y + base.y) / 2 };
    g.appendChild(moveLabel(mid, ln, shaftW / 2 + cell * 0.08, labelText, labelCls, primary, score, owner, u));
  }
  return g;
}

function renderOverlay() {
  const svg = els.boardOverlay;
  if (!svg) return;
  svg.innerHTML = "";
  overlayLabels = [];
  overlayObstacles = [];
  if (!state.game || !state.geom) return;
  const cur = state.game.current_node_id;
  // collect every arrow first, so each label can keep off all of them
  const specs = []; // [usi, kind, weight, name, score]

  // next moves stored in the kifu: the next move of the displayed line (指し手) + other branches
  if (state.opts.nextMove) {
    const i = state.mainLine.indexOf(cur);
    const nextId = i >= 0 ? state.mainLine[i + 1] : firstChild(cur);
    children(cur).forEach((n) => {
      if (!n.move_usi) return;
      const isNext = n.node_id === nextId;
      const name = state.opts.arrowLabels ? (isNext ? "指し手" : "分岐") : "";
      specs.push([n.move_usi, isNext ? "next" : "branch", isNext ? 1 : 0.7, name, null]);
    });
  }

  // computer: best move (and weaker lines for the other candidates)
  const shown = shownLines(); // live, or the last saved analysis of this position
  if (state.opts.bestMove && shown.lines.length) {
    const side = sideToMoveOf(node(cur));
    const seen = new Set();
    shown.lines.forEach((line, i) => {
      const first = line.pv_usi?.[0];
      if (!first || seen.has(first)) return;
      seen.add(first);
      // the evaluation goes in the same pill as the name ("候補手 -134")
      const cp = senteScore(line, side);
      const score = { text: formatScore(line, side), cls: cp == null ? "" : cp >= 0 ? "plus" : "minus" };
      // 成 / 不成 of the engine's move, small beside the evaluation
      score.promo = promotionMark(first);
      // with labels OFF the pill keeps only the evaluation
      const name = state.opts.arrowLabels ? (i === 0 ? "候補手" : `候補${seen.size}`) : "";
      specs.push([first, i === 0 ? "best" : "best sub", i === 0 ? 1 : 0.6, name, score]);
    });
  }

  specs.forEach(([usi, kind, weight], i) => addArrowObstacles(usi, weight, i));
  const shapes = specs.map(([usi, kind, weight, name, score], i) => overlayShape(usi, kind, weight, name, score, i));

  // draw weaker shapes first so the best move / main line stay on top
  const order = { "best sub": 0, branch: 1, next: 2, best: 3 };
  shapes
    .filter(Boolean)
    .sort((x, y) => (order[x.getAttribute("class").replace(/^mk /, "")] ?? 0) - (order[y.getAttribute("class").replace(/^mk /, "")] ?? 0))
    .forEach((s) => svg.appendChild(s));
  // labels on top of every arrow
  svg.querySelectorAll(".mv-label").forEach((l) => svg.appendChild(l));
}

/** "成" / "不成" for a board move that could promote in the shown position ("" otherwise). */
function promotionMark(usi) {
  const m = /^([1-9])([a-i])([1-9])([a-i])(\+?)$/.exec(String(usi || ""));
  const board = state.parsed?.board;
  if (!m || !board) return "";
  const fromRow = m[2].charCodeAt(0) - 97;
  const toRow = m[4].charCodeAt(0) - 97;
  const piece = board[fromRow]?.[9 - Number(m[1])];
  if (!piece) return "";
  if (m[5]) return "成";
  return canPromote(piece, fromRow, toRow) ? "不成" : "";
}

function applyHighlights() {
  if (!squares) return;
  for (const row of squares) {
    for (const sq of row) {
      sq.classList.remove("sel");
      sq.querySelector(".ind-move")?.remove();
    }
  }
  const sel = state.selection;
  if (sel?.kind === "board") {
    const { vr, vc } = toView(sel.fromRow, sel.fromCol);
    squares[vr][vc].classList.add("sel");
  }
  if (!state.opts.legal) return;
  for (const m of state.legal) {
    const { vr, vc } = toView(m.row, m.col);
    squares[vr][vc].appendChild(el("div", "ind ind-move"));
  }
}

function renderStands() {
  const parsed = state.parsed;
  const cap = parsed?.capturedPieces || { sente: {}, gote: {} };
  const turn = parsed?.currentPlayer;
  const topOwner = state.flip ? "sente" : "gote";
  const bottomOwner = state.flip ? "gote" : "sente";

  els.standTopMark.textContent = topOwner === "sente" ? "☗" : "☖";
  els.standTopName.textContent = topOwner === "sente" ? "先手" : "後手";
  els.standBottomMark.textContent = bottomOwner === "sente" ? "☗" : "☖";
  els.standBottomName.textContent = bottomOwner === "sente" ? "先手" : "後手";
  els.standTop.classList.toggle("to-move", turn === topOwner);
  els.standBottom.classList.toggle("to-move", turn === bottomOwner);

  const fill = (root, owner) => {
    root.innerHTML = "";
    let any = false;
    for (const t of HAND_ORDER) {
      const n = Number(cap?.[owner]?.[t] || 0);
      if (!n) continue;
      any = true;
      const b = el("button", `hand-piece${upsideDown(owner) ? " gote" : ""}`);
      b.type = "button";
      b.dataset.owner = owner;
      b.dataset.type = t;
      b.title = `${PIECE_JA[t]} ×${n}`;
      b.disabled = !state.isOwner || owner !== turn;
      if (state.selection?.kind === "hand" && state.selection.owner === owner && state.selection.pieceType === t) b.classList.add("selected");
      const url = pieceUrl(t, owner);
      if (url) {
        const img = el("img");
        img.src = url;
        img.alt = PIECE_JA[t];
        img.draggable = false;
        b.appendChild(img);
      } else {
        b.appendChild(el("span", "tok", PIECE_JA[t]));
      }
      if (n > 1) b.appendChild(el("span", "cnt", String(n)));
      b.addEventListener("pointerdown", (e) => onHandPointerDown(e, owner, t));
      root.appendChild(b);
    }
    if (!any) root.appendChild(el("div", "stand-empty", "なし"));
  };
  fill(els.handTop, topOwner);
  fill(els.handBottom, bottomOwner);
}

// ---------- selection / moves ----------
function clearSelection(render = true) {
  state.selection = null;
  state.legal = [];
  if (state.drag) endDragVisual();
  state.drag = null;
  if (render && squares) {
    applyHighlights();
    for (const b of document.querySelectorAll(".hand-piece.selected")) b.classList.remove("selected");
  }
}

function selectBoard(row, col) {
  const p = state.parsed?.board?.[row]?.[col];
  if (!p || !state.isOwner || p.owner !== state.parsed.currentPlayer) return false;
  state.selection = { kind: "board", owner: p.owner, pieceType: p.piece, fromRow: row, fromCol: col };
  state.legal = legalMovesFrom(state.parsed.board, row, col, p);
  applyHighlights();
  return true;
}

function selectHand(owner, type) {
  if (!state.isOwner || owner !== state.parsed?.currentPlayer) return false;
  state.selection = { kind: "hand", owner, pieceType: type };
  state.legal = legalDrops(state.parsed.board, type, owner);
  applyHighlights();
  for (const b of document.querySelectorAll(".hand-piece")) {
    b.classList.toggle("selected", b.dataset.owner === owner && b.dataset.type === type);
  }
  return true;
}

async function commitMove(toRow, toCol) {
  const sel = state.selection;
  const parsed = state.parsed;
  if (!sel || !parsed || !state.game?.current_node_id) return;
  if (!state.legal.some((m) => m.row === toRow && m.col === toCol)) return;

  let usi = null;
  if (sel.kind === "board") {
    const piece = parsed.board[sel.fromRow][sel.fromCol];
    if (!piece) return;
    let promote = false;
    if (canPromote(piece, sel.fromRow, toRow)) {
      if (mustPromote(piece, toRow)) {
        promote = true;
      } else {
        const ans = await pickPromotion(toRow, toCol, piece);
        if (ans == null) {
          clearSelection();
          return;
        }
        promote = ans;
      }
    }
    usi = buildUsiMove({ fromRow: sel.fromRow, fromCol: sel.fromCol, toRow, toCol, promote });
  } else {
    usi = buildUsiDrop({ pieceType: sel.pieceType, toRow, toCol });
  }
  clearSelection();
  if (usi) playUsi(usi);
}

// Small 成/不成 picker anchored next to the destination square (above it when it fits,
// otherwise below), kept inside the 9x9 area. Resolves true / false, or null on cancel.
let closePromotion = null;

function pickPromotion(toRow, toCol, piece) {
  if (closePromotion) closePromotion(null);
  return new Promise((resolve) => {
    const { vr, vc } = toView(toRow, toCol);
    const boardRect = els.board.getBoundingClientRect();
    const gridRect = els.boardGrid.getBoundingClientRect();
    const sqRect = squares[vr][vc].getBoundingClientRect();
    const cell = gridRect.width / 9;
    const gap = Math.max(6, Math.floor(cell * 0.1));
    const opt = Math.max(44, Math.min(Math.floor(cell * 0.95), Math.floor((gridRect.width - gap) / 2)));
    const panelW = opt * 2 + 1;
    const panelH = Math.round(opt * 1.12);

    // geometry in grid coordinates, then shifted into the board element
    const sqL = sqRect.left - gridRect.left;
    const sqT = sqRect.top - gridRect.top;
    let left = clamp(sqL + (sqRect.width - panelW) / 2, 0, Math.max(0, gridRect.width - panelW));
    let top = sqT - panelH - gap;
    if (top < 0 && sqT + sqRect.height + gap + panelH <= gridRect.height) top = sqT + sqRect.height + gap;
    top = clamp(top, 0, Math.max(0, gridRect.height - panelH));
    const offX = gridRect.left - boardRect.left;
    const offY = gridRect.top - boardRect.top;

    const panel = el("div", "promo");
    panel.style.left = `${left + offX}px`;
    panel.style.top = `${top + offY}px`;
    panel.style.width = `${panelW}px`;
    panel.style.height = `${panelH}px`;
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-label", "成りの選択");

    const option = (type, label, value) => {
      const b = el("button", "promo-opt");
      b.type = "button";
      b.title = label;
      b.setAttribute("aria-label", label);
      // always upright in the picker, even for the side drawn upside down on the board
      const pe = makePieceEl(type, piece.owner, "promo-piece");
      pe.classList.remove("gote");
      b.appendChild(pe);
      b.appendChild(el("span", "promo-cap", label));
      b.addEventListener("pointerdown", (e) => e.stopPropagation());
      b.addEventListener("click", (e) => {
        e.stopPropagation();
        finish(value);
      });
      return b;
    };
    // 成 on the left (easier to hit on tablets), 不成 on the right — same as the reference board
    panel.append(option(promotedTypeOf(piece.piece), "成", true), el("div", "promo-sep"), option(piece.piece, "不成", false));
    panel.addEventListener("pointerdown", (e) => e.stopPropagation());
    els.board.appendChild(panel);
    panel.querySelector("button")?.focus({ preventScroll: true });
    const target = squares[vr][vc];
    target.classList.add("promo-target");

    const onOutside = (e) => {
      if (!panel.contains(e.target)) finish(null);
    };
    const onKey = (e) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        finish(null);
      }
    };
    function finish(value) {
      window.removeEventListener("pointerdown", onOutside, true);
      window.removeEventListener("keydown", onKey, true);
      panel.remove();
      target.classList.remove("promo-target");
      closePromotion = null;
      resolve(value);
    }
    closePromotion = finish;
    // register after the current pointer event so it does not cancel immediately
    setTimeout(() => {
      if (closePromotion !== finish) return;
      window.addEventListener("pointerdown", onOutside, true);
      window.addEventListener("keydown", onKey, true);
    }, 0);
  });
}

function playUsi(usi) {
  if (!state.game?.current_node_id || kifuLocked()) return;
  // If this move already exists as a child, just follow it.
  const existing = children(state.game.current_node_id).find((n) => n.move_usi === usi);
  if (existing) jump(existing.node_id);
  else sendWs("node:play_move", { from_node_id: state.game.current_node_id, move_usi: usi });
}

// ---------- pointer / drag ----------
function squareFromPoint(x, y) {
  const hit = document.elementFromPoint(x, y);
  const sq = hit?.closest?.(".sq");
  if (!sq || !els.boardGrid.contains(sq)) return null;
  return toInternal(Number(sq.dataset.vr), Number(sq.dataset.vc));
}

function onBoardPointerDown(e) {
  if (e.button !== 0 && e.pointerType === "mouse") return;
  if (!state.parsed || !state.isOwner || kifuLocked()) return;
  const sqEl = e.target.closest(".sq");
  if (!sqEl) return;
  const { row, col } = toInternal(Number(sqEl.dataset.vr), Number(sqEl.dataset.vc));
  const p = state.parsed.board?.[row]?.[col];

  if (state.selection && state.legal.some((m) => m.row === row && m.col === col)) {
    e.preventDefault();
    commitMove(row, col);
    return;
  }
  const sel = state.selection;
  if (sel?.kind === "board" && sel.fromRow === row && sel.fromCol === col) {
    // second tap on the same piece: keep selected but allow drag
  } else if (!p || p.owner !== state.parsed.currentPlayer) {
    clearSelection();
    return;
  } else {
    clearSelection();
    selectBoard(row, col);
  }
  e.preventDefault();
  state.drag = { pointerId: e.pointerId, kind: "board", owner: p.owner, pieceType: p.piece, fromRow: row, fromCol: col, x0: e.clientX, y0: e.clientY, active: false };
}

function onHandPointerDown(e, owner, type) {
  if (e.button !== 0 && e.pointerType === "mouse") return;
  if (!state.parsed || !state.isOwner || owner !== state.parsed.currentPlayer || kifuLocked()) return;
  e.preventDefault();
  const already = state.selection?.kind === "hand" && state.selection.owner === owner && state.selection.pieceType === type;
  if (!already) {
    clearSelection();
    selectHand(owner, type);
  }
  state.drag = { pointerId: e.pointerId, kind: "hand", owner, pieceType: type, x0: e.clientX, y0: e.clientY, active: false };
}

function onPointerMove(e) {
  const d = state.drag;
  if (!d || d.pointerId !== e.pointerId) return;
  if (!d.active) {
    if (Math.hypot(e.clientX - d.x0, e.clientY - d.y0) < 6) return;
    d.active = true;
    const url = pieceUrl(d.pieceType, d.owner);
    if (url) {
      els.dragGhost.src = url;
      els.dragGhost.classList.add("on");
    }
    if (d.kind === "board") {
      const { vr, vc } = toView(d.fromRow, d.fromCol);
      squares[vr][vc].querySelector(".piece, .piece-wrap")?.classList.add("lifted");
    }
  }
  e.preventDefault();
  const size = els.boardGrid.getBoundingClientRect().width / 9;
  const rot = upsideDown(d.owner) ? " rotate(180deg)" : "";
  els.dragGhost.style.width = `${size * 1.08}px`;
  els.dragGhost.style.height = `${size * 1.08}px`;
  els.dragGhost.style.transform = `translate(${e.clientX - size * 0.54}px, ${e.clientY - size * 0.62}px)${rot}`;

  for (const row of squares) for (const sq of row) sq.classList.remove("drop-target");
  const tgt = squareFromPoint(e.clientX, e.clientY);
  if (tgt && state.legal.some((m) => m.row === tgt.row && m.col === tgt.col)) {
    const { vr, vc } = toView(tgt.row, tgt.col);
    squares[vr][vc].classList.add("drop-target");
  }
}

function endDragVisual() {
  els.dragGhost.classList.remove("on");
  if (!squares) return;
  for (const row of squares) {
    for (const sq of row) {
      sq.classList.remove("drop-target");
      sq.querySelector(".lifted")?.classList.remove("lifted");
    }
  }
}

function onPointerUp(e) {
  const d = state.drag;
  if (!d || d.pointerId !== e.pointerId) return;
  state.drag = null;
  const wasActive = d.active;
  endDragVisual();
  if (!wasActive) return; // a tap: selection stays, next tap picks the destination
  const tgt = e.type === "pointercancel" ? null : squareFromPoint(e.clientX, e.clientY);
  if (tgt && state.legal.some((m) => m.row === tgt.row && m.col === tgt.col)) {
    commitMove(tgt.row, tgt.col);
  } else if (d.kind === "hand") {
    // keep the hand selection so the user can tap a square
  }
}

// ---------- analysis rendering ----------
function renderEngineStatus() {
  const es = state.engine || {};
  const a = state.analysis;
  let name = es.engine_name || String(es.command || "").split(/[\\/]/).pop() || "エンジン";
  name = name.replace(/\.exe$/i, "");
  let st = "idle";
  let text = name;
  if (!a.available) {
    st = "error";
    text = "エンジン未設定";
  } else if (a.enabled && a.status === "running") {
    st = "running";
    text = `${name} · 解析中`;
  } else if (a.enabled && a.status === "idle") {
    text = `${name} · 自動停止`;
  } else if (a.enabled) {
    text = `${name} · 待機`;
  }
  els.engineStatus.dataset.state = st;
  els.engineStatus.querySelector(".status-text").textContent = text;
  els.engineStatus.title = [es.command, es.eval_dir ? `eval: ${es.eval_dir}` : "", es.threads ? `threads ${es.threads} / hash ${es.hash_mb}MB` : ""].filter(Boolean).join("\n");
}

/**
 * Candidate lines to show for the current position: the engine's live output when it is
 * for this position, otherwise the last saved analysis of this position. Saved results
 * stay visible after 常時解析 is turned OFF and when coming back to analysed positions.
 */
function shownLines() {
  const a = state.analysis;
  const cur = state.game?.current_node_id;
  if (a.lines.length && (!a.nodeId || a.nodeId === cur)) {
    return { lines: a.lines, live: a.enabled && a.status === "running", saved: false };
  }
  const ev = cur ? state.evals.get(cur) : null;
  return { lines: Array.isArray(ev?.lines) ? ev.lines : [], live: false, saved: Boolean(ev) };
}

function currentBest() {
  const shown = shownLines();
  if (shown.lines.length) return shown.lines[0];
  const cur = state.game?.current_node_id;
  return (cur ? state.evals.get(cur) : null) || null;
}

function renderEvalBar() {
  els.boardStage.classList.toggle("no-eval", !state.opts.evalBar);
  const cur = node(state.game?.current_node_id);
  const best = currentBest();
  const cp = senteScore(best, sideToMoveOf(cur));
  const wr = winRate(cp);
  els.evalBarFill.style.height = `${(wr * 100).toFixed(1)}%`;
  els.evalBar.classList.toggle("flipped", state.flip);
  els.evalBar.classList.toggle("gote-ahead", (cp ?? 0) < 0 !== state.flip);
  if (cp == null) els.evalBarText.textContent = "";
  else if (Math.abs(cp) >= 30000) els.evalBarText.textContent = "詰";
  else els.evalBarText.textContent = (Math.abs(cp) / 100).toFixed(1);
}

function verdict(cp) {
  if (cp == null) return "";
  const a = Math.abs(cp);
  if (a >= 30000) return cp > 0 ? "先手勝ち" : "後手勝ち";
  const side = cp > 0 ? "先手" : "後手";
  if (a < 150) return "互角";
  if (a < 500) return `${side}やや有利`;
  if (a < 1200) return `${side}有利`;
  if (a < 2500) return `${side}優勢`;
  return `${side}勝勢`;
}

// Phone: one-line summary inside the sticky nav bar (score, verdict, engine's best move).
function renderMiniEval(best, cp, side) {
  const a = state.analysis;
  els.miniOnOff.classList.toggle("on", a.enabled);
  els.miniOnOff.querySelector("b").textContent = a.enabled ? "ON" : "OFF";
  els.miniOnOff.disabled = !a.available || !state.isOwner;
  els.miniScore.textContent = best ? formatScore(best, side) : "±0";
  els.miniScore.className = `mini-score ${cp == null ? "" : cp >= 0 ? "plus" : "minus"}`;
  els.miniScore.style.opacity = best ? "" : "0.4";
  const topLine = shownLines().lines[0];
  const depth = topLine?.depth ?? best?.depth;
  els.miniDepth.textContent = depth ? `${depth}/${topLine?.seldepth || "-"}` : "";
  els.miniVerdict.textContent = els.evalVerdict.textContent;
  els.miniVerdict.dataset.side = els.evalVerdict.dataset.side || "even";
  const cur = node(state.game?.current_node_id);
  const first = shownLines().lines[0]?.pv_usi?.[0];
  els.miniBest.textContent = "";
  if (state.batch) {
    els.miniBest.textContent = `全解析 ${Math.min(state.batch.index + 1, state.batch.total)}/${state.batch.total}`;
  } else if (first && state.game) {
    const text = kifPv([first], state.game.current_position_sfen, cur?.move_usi ? moveTarget(cur.move_usi) : null)[0]?.text || "";
    els.miniBest.append(el("small", null, "最善"), text);
  }
}

function renderAnalysis() {
  const a = state.analysis;
  const on = a.enabled;
  const canUse = a.available && state.isOwner;
  for (const b of els.analysisOnOff.querySelectorAll("button")) {
    const isOn = b.dataset.v === "on";
    b.classList.toggle("active", isOn === on);
    b.setAttribute("aria-pressed", String(isOn === on));
    b.disabled = !canUse;
  }
  for (const b of els.multipvSeg.querySelectorAll("button")) {
    b.classList.toggle("on", Number(b.dataset.v) === a.multipv);
    b.disabled = !canUse;
  }
  els.engineSettingsBtn.disabled = !a.available;

  // 全解析 progress / button
  const batch = state.batch;
  els.analyzeAllBtn.disabled = !canUse;
  els.analyzeAllBtn.classList.toggle("running", Boolean(batch));
  els.analyzeAllBtn.querySelector("span").textContent = batch ? "中止" : "全解析";
  els.batchProgress.hidden = !batch;
  if (batch) {
    const done = Math.min(batch.index, batch.total);
    els.batchBar.style.width = `${((done / Math.max(batch.total, 1)) * 100).toFixed(1)}%`;
    els.batchText.textContent = `全解析中 ${done + 1} / ${batch.total} 局面`;
  }

  const cur = node(state.game?.current_node_id);
  const side = sideToMoveOf(cur);
  const best = currentBest();
  const cp = senteScore(best, side);

  els.evalScore.textContent = best ? formatScore(best, side) : "±0";
  els.evalScore.style.opacity = best ? "" : "0.35";
  els.evalScore.className = `eval-score ${cp == null ? "" : cp >= 0 ? "plus" : "minus"}`;
  if (!a.available) els.evalVerdict.textContent = "エンジン未設定";
  else if (!on && !best) els.evalVerdict.textContent = "解析停止中";
  else if (on && !best) els.evalVerdict.textContent = a.status === "idle" ? "自動停止中" : "思考中…";
  else els.evalVerdict.textContent = verdict(cp);
  if (state.batch && !best) els.evalVerdict.textContent = "全解析中…";
  els.evalVerdict.dataset.side = !best || cp == null || Math.abs(cp) < 150 ? "even" : cp > 0 ? "sente" : "gote";
  renderMiniEval(best, cp, side);

  // 先手 / 後手 win rate (estimated from the evaluation, as the evaluation bar)
  const wr = cp == null ? 0.5 : winRate(cp);
  const sentePct = Math.round(wr * 100);
  els.wrSente.textContent = `${sentePct}%`;
  els.wrGote.textContent = `${100 - sentePct}%`;
  els.wrFill.style.width = `${(wr * 100).toFixed(1)}%`;
  els.winRate.classList.toggle("none", cp == null);

  const shown = shownLines();
  const top = shown.lines[0];
  els.evalMeta.innerHTML = "";
  if (top || best?.depth) {
    // 深さ 27/43 = depth / selective depth (as in ShogiGUI)
    const row = el("div", "meta-depth");
    row.append(el("small", null, "深さ"), el("b", null, String(top?.depth ?? best.depth ?? "-")), el("span", null, `/${top?.seldepth || "-"}`));
    if (shown.live) row.append(el("small", "meta-time", `${(a.elapsedMs / 1000).toFixed(1)}s`));
    else row.prepend(el("small", "meta-state", on && a.status === "idle" ? "自動停止" : shown.saved ? "保存済み" : "最終解析"));
    els.evalMeta.append(row);
    if (top?.nodes) els.evalMeta.append(el("div", null, shown.live ? `${fmtNum(top.nodes)} nodes · ${fmtNum(top.nps)} nps` : `${fmtNum(top.nodes)} nodes`));
  }

  els.pvList.innerHTML = "";
  const lines = shown.lines;
  els.pvHead.hidden = !lines.length;
  if (!lines.length) {
    const msg = !a.available ? "解析エンジンが設定されていません" : on ? "読み筋を計算中…" : "解析をONにすると候補手と読み筋を表示します";
    els.pvList.appendChild(el("li", "pv-empty", msg));
  } else {
    const prevTo = cur?.move_usi ? moveTarget(cur.move_usi) : null;
    for (const line of lines) {
      const li = el("li", "pv");
      const s = senteScore(line, side);
      li.appendChild(el("span", "pv-idx", String(line.pv_index ?? 1)));
      li.appendChild(el("span", `pv-score ${s == null ? "" : s >= 0 ? "plus" : "minus"}`, formatScore(line, side)));
      const moves = kifPv((line.pv_usi || []).slice(0, 14), state.game.current_position_sfen, prevTo);
      const mv = el("span", "pv-moves");
      if (moves.length) {
        mv.appendChild(el("b", null, moves[0].text));
        mv.appendChild(document.createTextNode(moves.slice(1).map((m) => m.text).join(" ")));
      }
      mv.title = moves.map((m) => m.text).join(" ");
      li.appendChild(mv);
      li.appendChild(el("span", "pv-depth", line.depth ? String(line.depth) : "-"));
      li.appendChild(el("span", "pv-nodes", line.nodes ? fmtNum(line.nodes) : "-"));
      const play = el("button", "pv-play");
      play.type = "button";
      play.title = "この手を指す";
      play.appendChild(icon("play"));
      li.appendChild(play);
      const first = line.pv_usi?.[0];
      li.addEventListener("click", () => {
        if (first && state.isOwner) playUsi(first);
      });
      els.pvList.appendChild(li);
    }
  }
  renderEngineStatus();
  renderEvalBar();
  renderOverlay();
}

// ---------- eval graph ----------
let graphGeom = null;

function renderEvalGraph() {
  const cv = els.evalGraph;
  const rect = cv.getBoundingClientRect();
  if (!rect.width) return;
  const dpr = window.devicePixelRatio || 1;
  cv.width = Math.round(rect.width * dpr);
  cv.height = Math.round(rect.height * dpr);
  const ctx = cv.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const W = rect.width;
  const H = rect.height;
  ctx.clearRect(0, 0, W, H);

  const css = getComputedStyle(document.documentElement);
  const accent = css.getPropertyValue("--accent").trim() || "#e3b25a";

  const line = state.mainLine;
  const n = Math.max(line.length - 1, 1);

  // evaluations along the main line (sente's view, centipawns; mate = huge)
  const evs = [];
  line.forEach((id, i) => {
    const ev = state.evals.get(id);
    if (!ev) return;
    const cp = senteScore(ev, sideToMoveOf(node(id)));
    if (cp != null) evs.push([i, cp]);
  });

  // symmetric scale: ±1000 at least, then in 500 steps up to ±3000; beyond that the line sticks to the edge
  const peak = evs.reduce((m, [, cp]) => Math.max(m, Math.abs(cp)), 0);
  const lim = clamp(Math.ceil(peak / 500) * 500, 1000, 3000);

  // text and margins follow the graph's size
  // very low graphs (short phones): only ±max and 0, no 先手/後手 captions, so nothing overlaps
  const compact = H < 56;
  const fs = compact ? 8 : clamp(Math.round(H * 0.08), 9, 12);
  const font = `${fs}px system-ui, sans-serif`;
  ctx.font = font;
  const fmt = (v) => (v > 0 ? `+${v}` : `${v}`);
  const gutter = Math.ceil(ctx.measureText(fmt(-lim)).width) + 8;
  const padY = Math.ceil(fs / 2) + 3;
  const x0 = gutter;
  const x1 = W - 6;
  const x = (i) => x0 + (i / n) * (x1 - x0);
  // move-number axis under the plot when there is room for it
  const showAxis = H >= 56;
  const yBottom = H - padY;
  const y = (cp) => padY + ((lim - clamp(cp, -lim, lim)) / (2 * lim)) * (yBottom - padY);
  graphGeom = { n, x0, x1 };

  // background: sente half, grid lines with values (±lim, ±lim/2, 0)
  ctx.fillStyle = "rgba(255,255,255,0.025)";
  ctx.fillRect(x0, padY, x1 - x0, y(0) - padY);
  ctx.lineWidth = 1;
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  for (const v of compact ? [lim, 0, -lim] : [lim, lim / 2, 0, -lim / 2, -lim]) {
    const gy = Math.round(y(v)) + 0.5;
    ctx.strokeStyle = v === 0 ? "rgba(227,178,90,0.32)" : "rgba(227,178,90,0.11)";
    ctx.beginPath();
    ctx.moveTo(x0, gy);
    ctx.lineTo(x1, gy);
    ctx.stroke();
    ctx.fillStyle = v === 0 ? "rgba(154,161,173,0.85)" : "rgba(154,161,173,0.7)";
    ctx.fillText(fmt(v), gutter - 5, gy);
  }
  ctx.textBaseline = "alphabetic";

  // points
  const pts = evs.map(([i, cp]) => [x(i), y(cp), i]);

  if (pts.length) {
    // area to the 50% line
    const mid = y(0);
    const grad = ctx.createLinearGradient(0, padY, 0, yBottom);
    const midStop = clamp((mid - padY) / Math.max(yBottom - padY, 1), 0, 1);
    grad.addColorStop(0, "rgba(240,198,116,0.46)");
    grad.addColorStop(midStop, "rgba(240,198,116,0.05)");
    grad.addColorStop(midStop, "rgba(130,155,230,0.05)");
    grad.addColorStop(1, "rgba(130,155,230,0.38)");
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.moveTo(pts[0][0], mid);
    for (const [px, py] of pts) ctx.lineTo(px, py);
    ctx.lineTo(pts[pts.length - 1][0], mid);
    ctx.closePath();
    ctx.fill();

    ctx.strokeStyle = "#f3cf86";
    ctx.lineWidth = 1.8;
    ctx.lineJoin = "round";
    ctx.shadowColor = "rgba(240,198,116,0.75)";
    ctx.shadowBlur = 8;
    ctx.beginPath();
    pts.forEach(([px, py], k) => (k ? ctx.lineTo(px, py) : ctx.moveTo(px, py)));
    ctx.stroke();
    ctx.shadowBlur = 0;
    if (pts.length < 40) {
      ctx.fillStyle = "#f6dc9c";
      for (const [px, py] of pts) {
        ctx.beginPath();
        ctx.arc(px, py, 1.8, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  } else {
    ctx.fillStyle = "rgba(154,161,173,0.7)";
    ctx.font = "12px system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.font = font;
    ctx.fillText("解析した局面の評価値がここに表示されます", (x0 + x1) / 2, y(lim / 4));
  }

  // current ply marker
  const cx = x(curPly());
  ctx.strokeStyle = accent;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(cx, padY);
  ctx.lineTo(cx, yBottom);
  ctx.stroke();
  const curPt = pts.find((p) => p[2] === curPly());
  if (curPt) {
    ctx.fillStyle = "rgba(240,198,116,0.28)";
    ctx.beginPath();
    ctx.arc(curPt[0], curPt[1], 8, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#fff1cf";
    ctx.strokeStyle = accent;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(curPt[0], curPt[1], 4, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
  }

  // labels
  ctx.fillStyle = "rgba(154,161,173,0.75)";
  ctx.font = font;
  ctx.textAlign = "left";
  if (!compact) {
    ctx.textBaseline = "top";
    ctx.fillText("☗先手", x0 + 4, padY + 2);
    ctx.textBaseline = "bottom";
    ctx.fillText("☖後手", x0 + 4, yBottom - 2);
  }
  if (showAxis) {
    // 0, 10, 20 … plies (step grows for long games)
    const step = n <= 60 ? 10 : n <= 150 ? 20 : 50;
    ctx.textBaseline = "bottom";
    ctx.textAlign = "center";
    ctx.fillStyle = "rgba(154,161,173,0.7)";
    ctx.font = `${Math.max(8, fs - 2)}px system-ui, sans-serif`;
    for (let i = step; i <= n; i += step) ctx.fillText(String(i), clamp(x(i), x0 + 8, x1 - 8), H);
  }
  ctx.textBaseline = "alphabetic";
}

function onGraphClick(e) {
  if (!graphGeom || !state.mainLine.length) return;
  const rect = els.evalGraph.getBoundingClientRect();
  const t = (e.clientX - rect.left - graphGeom.x0) / (graphGeom.x1 - graphGeom.x0);
  const i = clamp(Math.round(t * graphGeom.n), 0, state.mainLine.length - 1);
  jump(state.mainLine[i]);
}

// ---------- kifu ----------
function evalClass(cp) {
  return cp == null ? "" : cp >= 0 ? "plus" : "minus";
}

function renderMoveList() {
  const list = els.moveList;
  list.innerHTML = "";
  const cur = state.game?.current_node_id;
  const line = state.mainLine;
  line.forEach((id, i) => {
    const n = node(id);
    if (!n) return;
    const li = el("li", "mv");
    li.dataset.id = id;
    if (i === 0) {
      li.classList.add("root");
      li.appendChild(el("span"));
      li.appendChild(el("span", "mv-no", ""));
      li.appendChild(el("span", "mv-text", "開始局面"));
    } else {
      const del = el("button", "mv-del");
      del.type = "button";
      del.title = "この手を取り消す";
      del.setAttribute("aria-label", `${i}手目を取り消す`);
      del.appendChild(icon("close"));
      del.disabled = !state.isOwner || Boolean(state.batch);
      del.addEventListener("click", (e) => {
        e.stopPropagation();
        deleteMove(id, i);
      });
      li.appendChild(del);
      li.appendChild(el("span", "mv-no", String(i)));
      li.appendChild(el("span", "mv-text", nodeLabel(n)));
    }
    li.appendChild(el("span", "mv-eval"));
    const sibs = n.parent_id ? children(n.parent_id) : [];
    if (sibs.length > 1) {
      const b = icon("branch");
      b.classList.add("mv-branch");
      li.appendChild(b);
    } else {
      li.appendChild(el("span"));
    }
    if (id === cur) li.classList.add("cur");
    li.addEventListener("click", () => jump(id));
    list.appendChild(li);
  });
  updateMoveEvals();
  keepCurrentMoveVisible();
  els.kifuSub.textContent = `${Math.max(line.length - 1, 0)}手`;
}

/** × in the kifu: take back a move. Removing more than that one move (later moves / branches) asks first. */
async function deleteMove(id, ply) {
  if (!state.isOwner || state.batch) return;
  let count = 0;
  const stack = [id];
  while (stack.length) {
    const nid = stack.pop();
    count += 1;
    stack.push(...(state.game?.children_index?.[nid] || []));
  }
  if (count > 1) {
    const n = node(id);
    const ans = await confirmDialog({
      title: "まとめて取り消しますか？",
      message: `${ply}手目「${nodeLabel(n)}」以降の ${count} 手（分岐を含む）を取り消します。`,
      actions: [
        { label: "キャンセル", value: null },
        { label: `${count}手を取り消す`, value: true, primary: true, danger: true },
      ],
    });
    if (!ans) return;
  }
  sendWs("node:delete", { node_id: id });
}

/** Changes not saved yet: ask before replacing the kifu on screen. true = go on. */
async function confirmDiscard(what) {
  if (!state.game?.dirty) return true;
  const ans = await confirmDialog({
    title: "保存されていない変更があります",
    message: `表示中の棋譜「${state.game.title || "無題"}」には保存されていない変更があります。${what}と、その変更は失われます。`,
    actions: [
      { label: "キャンセル", value: null },
      { label: "保存せずに続ける", value: "discard", danger: true },
      { label: "保存して続ける", value: "save", primary: true },
    ],
  });
  if (ans === "save") sendWs("game:save", {}); // handled before the next message on the same socket
  return Boolean(ans);
}

// Scroll only the list (scrollIntoView would also scroll the page on mobile).
// Also called when the list is resized, e.g. the analysis card grows as PV rows arrive.
function keepCurrentMoveVisible() {
  const list = els.moveList;
  const curEl = list.querySelector(".mv.cur");
  if (!curEl) return;
  const top = curEl.offsetTop;
  const bottom = top + curEl.offsetHeight;
  if (top < list.scrollTop) list.scrollTop = top - 4;
  else if (bottom > list.scrollTop + list.clientHeight) list.scrollTop = bottom - list.clientHeight + 4;
}

function updateMoveEvals() {
  for (const li of els.moveList.querySelectorAll(".mv")) {
    const id = li.dataset.id;
    const ev = state.evals.get(id);
    const span = li.querySelector(".mv-eval");
    if (!span) continue;
    if (!ev) {
      span.textContent = "";
      span.className = "mv-eval";
      continue;
    }
    const n = node(id);
    const cp = senteScore(ev, sideToMoveOf(n));
    span.textContent = formatScore(ev, sideToMoveOf(n));
    let cls = evalClass(cp);
    // blunder mark: the side that just moved lost >= 800 compared to the previous position
    const parentEv = n?.parent_id ? state.evals.get(n.parent_id) : null;
    if (parentEv && cp != null) {
      const pcp = senteScore(parentEv, sideToMoveOf(node(n.parent_id)));
      const mover = sideToMoveOf(node(n.parent_id));
      const drop = mover === "sente" ? pcp - cp : cp - pcp;
      if (pcp != null && Math.abs(pcp) < 3000 && drop >= 800) cls = "bad";
    }
    span.className = `mv-eval ${cls}`;
  }
}

function renderVariations() {
  const cur = state.game?.current_node_id;
  const curNode = node(cur);
  els.varChips.innerHTML = "";
  const kids = children(cur);
  const sibs = curNode?.parent_id ? children(curNode.parent_id) : [];
  let items = [];
  let title = "";
  if (kids.length > 1) {
    title = "次の一手の変化";
    items = kids.map((k, i) => ({ n: k, on: i === 0 }));
  } else if (sibs.length > 1) {
    title = "この手の変化";
    items = sibs.map((k) => ({ n: k, on: k.node_id === cur }));
  }
  els.variations.hidden = !items.length;
  if (!items.length) return;
  els.varTitle.textContent = title;
  for (const it of items) {
    const b = el("button", `chip${it.on ? " on" : ""}`, nodeLabel(it.n));
    b.type = "button";
    b.addEventListener("click", () => jump(it.n.node_id));
    els.varChips.appendChild(b);
  }
}

function renderComment() {
  const cur = node(state.game?.current_node_id);
  if (document.activeElement !== els.commentInput) els.commentInput.value = cur?.comment || "";
  els.commentInput.disabled = !state.isOwner;
}

// ---------- controls ----------
function renderControls() {
  const owner = state.isOwner;
  const canNav = owner && !state.batch; // 全解析 drives the position
  const cur = state.game?.current_node_id;
  const hasPrev = Boolean(node(cur)?.parent_id);
  const hasNext = Boolean(firstChild(cur));
  els.btnStart.disabled = !canNav || !hasPrev;
  els.btnPrev.disabled = !canNav || !hasPrev;
  els.btnNext.disabled = !canNav || !hasNext;
  els.btnEnd.disabled = !canNav || !hasNext;
  els.saveBtn.disabled = !owner;
  els.saveBtn.classList.toggle("dirty", Boolean(state.game?.dirty));
  els.saveBtn.title = state.game?.dirty ? "保存されていない変更があります — サーバーに保存 (Ctrl+S)" : "サーバーに保存 (Ctrl+S)";
  for (const b of [els.newGameBtn, els.openBtn, els.importBtn, els.pasteBtn]) b.disabled = !canNav;
  els.plySlider.disabled = !canNav;
  document.body.classList.toggle("batch-lock", Boolean(state.batch));

  const max = Math.max(state.mainLine.length - 1, 0);
  const ply = curPly();
  els.plySlider.max = String(max);
  els.plySlider.value = String(ply);
  els.plySlider.style.setProperty("--p", `${max ? (ply / max) * 100 : 0}%`);
  els.plyNow.textContent = String(ply);
  els.plyMax.textContent = String(max);
  const turn = state.parsed?.currentPlayer;
  els.turnChip.textContent = turn === "gote" ? "☖後手番" : "☗先手番";
  els.turnChip.classList.toggle("gote", turn === "gote");
  els.flipBtn.classList.toggle("on", state.flip);

  if (state.game) {
    els.titleLabel.textContent = state.game.title || "無題の棋譜";
    els.titleLabel.title = state.game.title || "";
  }
  els.titleEditBtn.disabled = !owner;
}

function renderAll() {
  if (!state.game) return;
  renderCoords();
  renderStands();
  renderBoard();
  renderMoveList();
  renderVariations();
  renderComment();
  renderControls();
  renderAnalysis();
  renderEvalGraph();
}

// ---------- navigation ----------
function navPrev() {
  const p = node(state.game?.current_node_id)?.parent_id;
  if (p) jump(p);
}
function navNext() {
  // follow the displayed line (it keeps the branch played last), else the first child
  const cur = state.game?.current_node_id;
  const i = state.mainLine.indexOf(cur);
  const c = (i >= 0 && state.mainLine[i + 1]) || firstChild(cur);
  if (c) jump(c);
}
function navStart() {
  jump(state.game?.root_node_id);
}
function navEnd() {
  jump(state.mainLine[state.mainLine.length - 1]);
}

// ---------- menus ----------
async function openGameList() {
  showDialog(els.dlgOpen);
  els.gameList.innerHTML = "";
  els.gameList.appendChild(el("li", "empty", "読み込み中…"));
  try {
    const res = await fetch("/api/games?limit=200&offset=0", { cache: "no-store" });
    const json = await res.json();
    const items = Array.isArray(json.items) ? json.items : [];
    const draw = () => {
      const q = els.gameFilter.value.trim().toLowerCase();
      els.gameList.innerHTML = "";
      const shown = items.filter((g) => !q || String(g.title || "").toLowerCase().includes(q));
      if (!shown.length) els.gameList.appendChild(el("li", "empty", "棋譜がありません"));
      for (const g of shown) {
        const li = el("li", g.game_id === state.game?.game_id ? "cur" : "");
        const b = el("button");
        b.type = "button";
        b.appendChild(el("span", "g-title", g.title || "無題"));
        b.appendChild(el("span", "g-date", fmtDate(g.updated_at)));
        b.addEventListener("click", async () => {
          closeDialog(null);
          if (!(await confirmDiscard("別の棋譜を開く"))) return;
          sendWs("game:load", { game_id: g.game_id });
        });
        // small × next to each saved game: delete after a はい/いいえ confirmation
        const del = el("button", "g-delete");
        del.type = "button";
        del.title = "この棋譜を削除";
        del.setAttribute("aria-label", `「${g.title || "無題"}」を削除`);
        del.appendChild(icon("close"));
        del.disabled = !state.isOwner || Boolean(state.batch);
        del.addEventListener("click", () => confirmDeleteGame(g));
        li.append(b, del);
        els.gameList.appendChild(li);
      }
    };
    els.gameFilter.oninput = draw;
    draw();
  } catch (e) {
    els.gameList.innerHTML = "";
    els.gameList.appendChild(el("li", "empty", `一覧の取得に失敗しました: ${e}`));
  }
}

async function confirmDeleteGame(g) {
  const title = g.title || "無題";
  const isCurrent = g.game_id === state.game?.game_id;
  const ans = await confirmDialog({
    title: "削除しますか？",
    message: `「${title}」を削除します。この操作は元に戻せません。${isCurrent ? "\n（表示中の棋譜です。削除後は新しい棋譜に切り替わります）" : ""}`,
    actions: [
      { label: "いいえ", value: null },
      { label: "はい", value: true, primary: true, danger: true },
    ],
  });
  if (ans) {
    pendingDeleteTitle = title;
    sendWs("game:delete", { game_id: g.game_id });
  } else {
    openGameList(); // いいえ: back to the list
  }
}
let pendingDeleteTitle = "";

const FORMAT_NAMES = { kif: "KIF", kif2: "KI2", usi: "USI" };

/** Read a kifu as a NEW game. source: "file" (filename = title fallback) | "paste". */
async function importText(text, { source = "file", filename = "" } = {}) {
  if (!text || !text.trim()) {
    toast("warning", source === "paste" ? "クリップボードが空です" : "ファイルが空です");
    return false;
  }
  if (!(await confirmDiscard("棋譜を読み込む"))) return false;
  try {
    const res = await fetch("/api/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, source, filename }),
    });
    const json = await res.json().catch(() => ({}));
    if (json?.error === "format") {
      toast("error", json.detail || "形式が違います");
      return false;
    }
    if (!res.ok) throw new Error(json?.detail || `HTTP ${res.status}`);
    const how = source === "paste" ? "貼り付けました" : "読み込みました";
    toast("info", `${FORMAT_NAMES[json.format] || ""} 形式の棋譜を新しい棋譜として${how}`);
    // the new game is already current on the server (not in the saved list until 保存)
    if (json.game?.game_id) sendWs("game:refresh", {});
    return true;
  } catch (e) {
    toast("error", `読み込みに失敗しました: ${e.message || e}`);
    return false;
  }
}

/** Copy the current kifu as KIF text. The fetch is handed to the clipboard as a promise so the
 * copy still counts as part of the tap (Safari drops it after an await otherwise). */
async function copyKifuAsKif() {
  const id = state.game?.game_id;
  if (!id) return;
  const text = fetch(`/api/export/${encodeURIComponent(id)}?format=kif`, { cache: "no-store" }).then(async (r) => {
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.text();
  });
  try {
    if (window.ClipboardItem && navigator.clipboard?.write) {
      await navigator.clipboard.write([new ClipboardItem({ "text/plain": text.then((t) => new Blob([t], { type: "text/plain" })) })]);
    } else if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(await text);
    } else {
      throw new Error("no clipboard");
    }
    toast("info", "棋譜を KIF 形式でコピーしました");
  } catch {
    // http on the LAN etc.: classic copy through a hidden text area
    try {
      const ta = el("textarea");
      ta.value = await text;
      ta.style.cssText = "position:fixed;left:-9999px;top:0";
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      ta.remove();
      toast(ok ? "info" : "error", ok ? "棋譜を KIF 形式でコピーしました" : "コピーできませんでした（「書出」からコピーしてください）");
    } catch (e) {
      toast("error", `コピーできませんでした: ${e.message || e}`);
    }
  }
}

async function pasteFromClipboard() {
  let text = null;
  try {
    if (navigator.clipboard?.readText) text = await navigator.clipboard.readText();
  } catch {
    text = null; // permission denied / not a secure context
  }
  if (text === null) {
    // fallback: let the user paste into a small target (no text box to fill in)
    els.pasteTarget.textContent = "ここに貼り付け";
    showDialog(els.dlgPaste);
    setTimeout(() => els.pasteTarget.focus(), 40);
    return;
  }
  await importText(text, { source: "paste" });
}

const fileStem = (name) => String(name || "").replace(/\.usi\.txt$/i, "").replace(/\.[^.]+$/, "");

async function decodeFile(file) {
  const buf = await file.arrayBuffer();
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(buf);
  } catch {
    // KIF files are frequently Shift_JIS
    return new TextDecoder("shift_jis").decode(buf);
  }
}

async function refreshExport() {
  const id = state.game?.game_id;
  if (!id) return;
  for (const b of els.exportSeg.querySelectorAll("button")) b.classList.toggle("on", b.dataset.v === state.exportFormat);
  els.exportPreview.value = "生成中…";
  try {
    const res = await fetch(`/api/export/${encodeURIComponent(id)}?format=${state.exportFormat}`, { cache: "no-store" });
    const text = await res.text();
    if (!res.ok) throw new Error(text);
    els.exportPreview.value = text;
    const ext = { kif: "kifu", kif2: "ki2u", usi: "usi.txt" }[state.exportFormat]; // UTF-8 KIF / KI2 use .kifu / .ki2u
    const name = `${(state.game.title || "kifu").replace(/[\\/:*?"<>|]/g, "_")}.${ext}`;
    const old = els.exportDownload.href;
    if (old.startsWith("blob:")) URL.revokeObjectURL(old);
    els.exportDownload.href = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }));
    els.exportDownload.download = name;
  } catch (e) {
    els.exportPreview.value = `書き出しに失敗しました: ${e.message || e}`;
  }
}

async function setupThemeChoices() {
  let cfg;
  try {
    cfg = await loadBoardThemeConfig();
  } catch (e) {
    toast("warning", `テーマ設定を読み込めませんでした: ${e}`);
    return;
  }
  const bgSets = cfg.background_sets || [];
  const pieceSets = cfg.piece_sets || [];

  const draw = () => {
    const curBg = lsGet(THEME_LS_KEYS.backgroundSet) || bgSets[0]?.name;
    const curPs = lsGet(THEME_LS_KEYS.pieceSet) || pieceSets[0]?.name;
    els.bgChoices.innerHTML = "";
    for (const s of bgSets) {
      const b = el("button", `theme-opt${s.name === curBg ? " on" : ""}`);
      b.type = "button";
      const th = el("span", "thumb");
      th.style.backgroundImage = `url("${s.background}")`;
      b.append(th, el("span", null, THEME_NAMES[s.displayName] || s.name));
      b.addEventListener("click", async () => {
        lsSet(THEME_LS_KEYS.backgroundSet, s.name);
        await loadTheme();
        draw();
        renderAll();
      });
      els.bgChoices.appendChild(b);
    }
    els.pieceChoices.innerHTML = "";
    for (const s of pieceSets) {
      const b = el("button", `theme-opt${s.name === curPs ? " on" : ""}`);
      b.type = "button";
      const th = el("span", "thumb");
      const p = s.pieces || {};
      const url = (p.sente || p).king || (p.sente || p).rook;
      if (url) {
        const img = el("img");
        img.src = url;
        img.alt = "";
        th.appendChild(img);
      }
      b.append(th, el("span", null, THEME_NAMES[s.displayName] || s.name));
      b.addEventListener("click", async () => {
        lsSet(THEME_LS_KEYS.pieceSet, s.name);
        await loadTheme();
        draw();
        renderAll();
      });
      els.pieceChoices.appendChild(b);
    }
  };
  draw();
}

// ---------- analysis ON/OFF, 全解析 ----------
async function setAnalysisEnabled(on) {
  const a = state.analysis;
  if (!a.available || !state.isOwner || a.enabled === on) return;
  if (on && state.batch) {
    const ans = await confirmDialog({
      title: "全解析を中止しますか？",
      message: "常時解析を ON にすると、実行中の全解析を中止します。解析済みの局面の評価値は残ります。",
      actions: [
        { label: "全解析を続ける", value: null },
        { label: "中止して常時解析", value: true, primary: true },
      ],
    });
    if (!ans || !state.batch) return;
  }
  a.enabled = on;
  a.status = on ? "starting" : "stopped";
  // turning OFF keeps the last lines on screen (score, candidates, arrows)
  renderAnalysis();
  sendWs("analysis:set_enabled", { enabled: on });
}

const LS_BATCH_SECONDS = "shogi_analyzer_batch_seconds";
function batchSeconds() {
  const v = Number(lsGet(LS_BATCH_SECONDS));
  return Number.isFinite(v) && v >= 0.5 ? clamp(v, 0.5, 120) : 3;
}

// ---------- engine settings dialog ----------
let engineSpec = null; // response of GET /api/engine/options
const engineInputs = new Map(); // option name -> () => value

const OPTION_HELP = {
  Threads: "探索に使うスレッド数",
  USI_Hash: "置換表のサイズ (MB)",
  USI_Ponder: "相手の手番中も考える",
  NetworkDelay: "通信遅延の見込み (ms)",
  NetworkDelay2: "秒読み時の通信遅延の見込み (ms)",
  MinimumThinkingTime: "最小思考時間 (ms)",
  SlowMover: "序盤の時間配分 (%)",
  MaxMovesToDraw: "引き分けとする手数 (0 = 無制限)",
  DepthLimit: "探索深さの上限 (0 = 無制限)",
  NodesLimit: "探索ノード数の上限 (0 = 無制限)",
  EvalDir: "評価関数のフォルダ",
  EnteringKingRule: "入玉ルール",
  LargePageEnable: "Large Pages を使う",
  USI_OwnBook: "定跡を使う",
  BookFile: "定跡ファイル",
  BookDir: "定跡フォルダ",
  ConsiderationMode: "検討モード（読み筋を最後まで出力）",
  DrawValueBlack: "先手の引き分けの評価値",
  DrawValueWhite: "後手の引き分けの評価値",
  PvInterval: "読み筋の出力間隔 (ms)",
  ResignValue: "投了する評価値",
};

async function openEngineSettings() {
  showDialog(els.dlgEngine);
  els.engineLoading.hidden = false;
  els.engineLoading.textContent = "エンジンから設定項目を読み込んでいます…";
  els.engineForm.hidden = true;
  els.engineSave.disabled = true;
  try {
    const res = await fetch("/api/engine/options", { cache: "no-store" });
    const json = await res.json();
    if (!res.ok) throw new Error(json?.detail || `HTTP ${res.status}`);
    engineSpec = json;
    renderEngineForm(false);
    els.engineLoading.hidden = true;
    els.engineForm.hidden = false;
    els.engineSave.disabled = false;
  } catch (e) {
    els.engineLoading.textContent = `設定を取得できませんでした: ${e.message || e}`;
  }
}

// value shown for an option: current value, or the engine default when resetting
function optionValue(o, useDefault) {
  return useDefault ? o.default : o.value ?? o.default;
}

function bindSlider(range, num, { min, max, value, def }, onChange) {
  range.min = num.min = String(min);
  range.max = num.max = String(max);
  const set = (v, from) => {
    v = Math.round(clamp(Number(v) || min, min, max));
    if (from !== range) range.value = String(v);
    if (from !== num) num.value = String(v);
    range.style.setProperty("--p", `${((v - min) / Math.max(max - min, 1)) * 100}%`);
    range.style.setProperty("--d", `${((clamp(def, min, max) - min) / Math.max(max - min, 1)) * 100}%`);
    onChange?.(v);
  };
  range.oninput = () => set(range.value, range);
  num.onchange = () => set(num.value, num);
  set(value);
  return () => Number(num.value);
}

function renderEngineForm(useDefaults) {
  const spec = engineSpec;
  if (!spec) return;
  engineInputs.clear();
  els.engineName.textContent = spec.engine_name || "USI エンジン";
  const byName = new Map(spec.options.map((o) => [o.name, o]));
  const sys = spec.system || {};
  const fmtMb = (mb) => (mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${mb} MB`);

  // Threads: slider limited by the logical CPU count (and the engine's own max)
  const th = byName.get("Threads");
  els.threadsRow.hidden = !th;
  if (th) {
    const max = Math.max(1, Math.min(th.max ?? 512, sys.cpus || th.max || 64));
    const get = bindSlider(els.threadsRange, els.threadsNum, { min: th.min ?? 1, max, value: optionValue(th, useDefaults), def: th.default }, (v) => {
      els.threadsRow.classList.toggle("changed", v !== th.default);
    });
    els.threadsLimit.textContent = `上限 ${max}（論理CPU ${sys.cpus ?? "?"}）`;
    els.threadsDefault.textContent = `既定値 ${th.default}`;
    engineInputs.set("Threads", get);
  }

  // Hash: slider + number box, limited to half of the installed memory
  const hs = byName.get("USI_Hash") || byName.get("Hash");
  els.hashRow.hidden = !hs;
  if (hs) {
    const max = Math.max(hs.min ?? 1, Math.min(hs.max ?? Infinity, sys.hash_max_mb || hs.max || 4096));
    els.hashOptName.textContent = hs.name;
    const get = bindSlider(els.hashRange, els.hashNum, { min: hs.min ?? 1, max, value: optionValue(hs, useDefaults), def: hs.default }, (v) => {
      els.hashRow.classList.toggle("changed", v !== hs.default);
    });
    els.hashLimit.textContent = sys.memory_mb ? `上限 ${fmtMb(max)}（メモリ ${fmtMb(sys.memory_mb)} の½）` : `上限 ${fmtMb(max)}`;
    els.hashDefault.textContent = `既定値 ${fmtMb(hs.default)}`;
    engineInputs.set(hs.name, get);
  }

  els.batchSeconds.value = String(batchSeconds());

  // 常時解析の自動停止 (kept on the server; 0 = 上限なし)
  const fmtSec = (s) => (s === 0 ? "上限なし" : s < 60 ? `${s}秒` : `${s / 60}分`);
  els.autoStopSel.innerHTML = "";
  for (const s of spec.auto_stop_choices || [10, 20, 30, 60, 120, 180, 300, 600, 1200, 0]) {
    const opt = el("option", null, fmtSec(s) + (s === 60 ? "（既定）" : ""));
    opt.value = String(s);
    els.autoStopSel.append(opt);
  }
  els.autoStopSel.value = String(useDefaults ? 60 : spec.auto_stop_sec ?? 60);

  // everything else, generated from the engine's option list
  els.engineOptions.innerHTML = "";
  for (const o of spec.options) {
    if (["Threads", "USI_Hash", "Hash", "MultiPV"].includes(o.name) || o.type === "button") continue;
    const row = el("div", "eng-row");
    const label = el("div", "eng-label");
    label.appendChild(el("span", "eng-name", OPTION_HELP[o.name] || o.name));
    label.appendChild(el("small", null, o.name));
    const ctl = el("div", "eng-ctl");
    let input;
    let get;
    const v = optionValue(o, useDefaults);
    if (o.type === "check") {
      input = el("input");
      input.type = "checkbox";
      input.checked = Boolean(v);
      get = () => input.checked;
    } else if (o.type === "spin") {
      input = el("input", "field num");
      input.type = "number";
      if (o.min != null) input.min = String(o.min);
      if (o.max != null && Math.abs(o.max) < Number.MAX_SAFE_INTEGER) input.max = String(o.max);
      input.value = String(v ?? "");
      get = () => Number(input.value);
    } else if (o.type === "combo") {
      input = el("select", "field");
      for (const opt of o.vars || []) {
        const op = el("option", null, opt);
        op.value = opt;
        input.appendChild(op);
      }
      input.value = String(v ?? "");
      get = () => input.value;
    } else {
      input = el("input", "field");
      input.type = "text";
      input.value = String(v ?? "");
      input.spellcheck = false;
      get = () => input.value;
    }
    const def = o.type === "check" ? (o.default ? "ON" : "OFF") : String(o.default ?? "");
    const defEl = el("span", "eng-default", def === "" ? "既定値: (空)" : `既定値: ${def}`);
    const reset = el("button", "icon-btn reset", "↺");
    reset.type = "button";
    reset.title = "既定値に戻す";
    // "changed" = differs from what the engine runs with by default (auto-detected values like EvalDir count as default)
    const base = o.changed ? o.default : o.value;
    const mark = () => row.classList.toggle("changed", o.type === "spin" ? Number(get()) !== Number(base) : get() !== base);
    reset.addEventListener("click", () => {
      if (o.type === "check") input.checked = Boolean(o.default);
      else input.value = String(o.default ?? "");
      mark();
    });
    input.addEventListener("input", mark);
    input.addEventListener("change", mark);
    ctl.append(input, defEl, reset);
    row.append(label, ctl);
    els.engineOptions.appendChild(row);
    engineInputs.set(o.name, get);
    mark();
  }
}

async function saveEngineSettings() {
  const secs = Number(els.batchSeconds.value);
  if (Number.isFinite(secs) && secs >= 0.5) lsSet(LS_BATCH_SECONDS, String(clamp(secs, 0.5, 120)));
  const values = {};
  for (const [name, get] of engineInputs) values[name] = get();
  els.engineSave.disabled = true;
  try {
    const res = await fetch("/api/engine/options", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ values, auto_stop_sec: Number(els.autoStopSel.value) }),
    });
    const json = await res.json();
    if (!res.ok) throw new Error(json?.detail || `HTTP ${res.status}`);
    closeDialog(null);
    toast("info", "エンジン設定を保存しました。エンジンを再起動します");
  } catch (e) {
    toast("error", `保存できませんでした: ${e.message || e}`);
  } finally {
    els.engineSave.disabled = false;
  }
}

// ---------- phone: kifu drawer ----------
function setKifuDrawer(open) {
  open = Boolean(open) && isMobile();
  document.body.classList.toggle("kifu-open", open);
  els.kifuBackdrop.hidden = !open;
  els.kifuDrawerBtn.classList.toggle("on", open);
  els.kifuDrawerBtn.setAttribute("aria-expanded", String(open));
  if (open) requestAnimationFrame(keepCurrentMoveVisible);
}

// Swipe left from the right screen edge opens the drawer; swipe right on it closes it.
function wireDrawerSwipe() {
  let start = null;
  document.addEventListener(
    "touchstart",
    (e) => {
      if (!isMobile() || e.touches.length !== 1 || openDialogEl) return;
      const t = e.touches[0];
      const open = document.body.classList.contains("kifu-open");
      const fromEdge = !open && t.clientX > window.innerWidth - 24;
      const onDrawer = open && els.kifuCard.contains(e.target);
      start = fromEdge || onDrawer ? { x: t.clientX, y: t.clientY, open } : null;
    },
    { passive: true },
  );
  document.addEventListener(
    "touchmove",
    (e) => {
      if (!start) return;
      const t = e.touches[0];
      const dx = t.clientX - start.x;
      const dy = t.clientY - start.y;
      if (Math.abs(dy) > Math.abs(dx)) {
        if (Math.abs(dy) > 12) start = null; // vertical scroll of the move list wins
        return;
      }
      if (!start.open && dx < -40) {
        setKifuDrawer(true);
        start = null;
      } else if (start.open && dx > 60) {
        setKifuDrawer(false);
        start = null;
      }
    },
    { passive: true },
  );
  document.addEventListener("touchend", () => (start = null), { passive: true });
  window.addEventListener("resize", () => {
    if (!isMobile()) setKifuDrawer(false);
  });
}

// ---------- connection overlay ----------
let connHideTimer = null;
let connAttempts = 0;

function showConnLost() {
  clearTimeout(connHideTimer);
  connAttempts += 1;
  els.connOverlay.hidden = false;
  els.connOverlay.dataset.state = "lost";
  els.connTitle.textContent = "接続が切れました";
  els.connMsg.textContent = connAttempts > 1 ? `再接続しています…（${connAttempts}回目）` : "再接続しています…";
}

function showConnRestored() {
  if (els.connOverlay.hidden) return; // first connection: nothing to announce
  connAttempts = 0;
  els.connOverlay.dataset.state = "ok";
  els.connTitle.textContent = "接続されました";
  els.connMsg.textContent = "操作を再開できます";
  clearTimeout(connHideTimer);
  connHideTimer = setTimeout(() => {
    els.connOverlay.dataset.state = "hide";
    connHideTimer = setTimeout(() => (els.connOverlay.hidden = true), 260);
  }, 1100);
}

function saveOpts() {
  lsSet(LS_OPTS, JSON.stringify(state.opts));
}

// ---------- wiring ----------
function wire() {
  els.boardGrid.addEventListener("pointerdown", onBoardPointerDown);
  window.addEventListener("pointermove", onPointerMove, { passive: false });
  window.addEventListener("pointerup", onPointerUp);
  window.addEventListener("pointercancel", onPointerUp);
  els.board.addEventListener("contextmenu", (e) => {
    e.preventDefault();
    clearSelection();
  });

  els.btnStart.addEventListener("click", navStart);
  els.btnPrev.addEventListener("click", navPrev);
  els.btnNext.addEventListener("click", navNext);
  els.btnEnd.addEventListener("click", navEnd);
  els.flipBtn.addEventListener("click", () => {
    if (closePromotion) closePromotion(null);
    state.flip = !state.flip;
    clearSelection(false);
    renderAll();
  });
  els.plySlider.addEventListener("input", () => {
    const i = Number(els.plySlider.value);
    els.plySlider.style.setProperty("--p", `${(i / Math.max(Number(els.plySlider.max), 1)) * 100}%`);
    els.plyNow.textContent = String(i);
  });
  els.plySlider.addEventListener("change", () => jump(state.mainLine[Number(els.plySlider.value)]));

  els.analysisOnOff.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-v]");
    if (b && !b.disabled) setAnalysisEnabled(b.dataset.v === "on");
  });
  els.analyzeAllBtn.addEventListener("click", () => {
    if (!state.analysis.available || !state.isOwner) return;
    if (state.batch) {
      sendWs("analysis:batch_cancel", {});
      return;
    }
    const seconds = batchSeconds();
    const n = state.mainLine.length;
    clearSelection();
    state.batch = { index: 0, total: n };
    renderAnalysis();
    renderControls();
    sendWs("analysis:analyze_all", { seconds, line: state.mainLine });
    toast("info", `全解析を開始します（${n}局面 × ${seconds}秒 ≒ ${Math.ceil((n * seconds) / 60)}分）`);
  });
  els.engineSettingsBtn.addEventListener("click", openEngineSettings);
  els.miniOnOff.addEventListener("click", () => setAnalysisEnabled(!state.analysis.enabled));
  els.multipvSeg.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-v]");
    if (!b || b.disabled) return;
    const v = clamp(Number(b.dataset.v), 1, 5);
    if (v === state.analysis.multipv) return;
    state.analysis.multipv = v;
    state.analysis.lines = [];
    renderAnalysis();
    sendWs("analysis:set_multipv", { multipv: v });
  });

  els.evalGraph.addEventListener("click", onGraphClick);

  // title: label + pencil -> rename popup. The same popup asks for a name on the first save
  // of a kifu that still has its automatic name (kif_YYYYMMDD_hhmmss).
  let titleMode = "rename";
  const openTitleEdit = (mode = "rename") => {
    if (!state.game || !state.isOwner) return;
    titleMode = mode;
    $("dlgTitleTitle").textContent = mode === "save" ? "保存名を入力" : "棋譜名を変更";
    els.titleSave.textContent = mode === "save" ? "保存" : "変更";
    els.titleInput.value = state.game.title || "";
    showDialog(els.dlgTitle);
    setTimeout(() => els.titleInput.select(), 40);
  };
  const commitTitle = () => {
    const t = els.titleInput.value.trim();
    if (!state.game || !state.isOwner || !t) return;
    if (titleMode === "save") {
      if (sendWs("game:save", { title: t })) toast("info", "サーバーに保存しました");
    } else if (t !== state.game.title) {
      sendWs("game:rename", { title: t });
    }
    closeDialog(null);
  };
  const needsName = () => {
    const g = state.game;
    return Boolean(g) && !(g.ui_state || {}).named && /^kif_\d{8}_\d{6}$/.test(g.title || "");
  };
  els.titleEditBtn.addEventListener("click", () => openTitleEdit("rename"));
  els.titleLabel.addEventListener("dblclick", () => openTitleEdit("rename"));
  els.titleSave.addEventListener("click", commitTitle);
  els.titleInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.isComposing) {
      e.preventDefault();
      commitTitle();
    }
  });

  els.commentInput.addEventListener("change", () => {
    const id = state.game?.current_node_id;
    if (id && state.isOwner) sendWs("node:set_comment", { node_id: id, comment: els.commentInput.value });
  });

  els.saveBtn.addEventListener("click", () => {
    if (needsName()) return openTitleEdit("save");
    if (sendWs("game:save", {})) toast("info", "サーバーに保存しました");
  });
  els.newGameBtn.addEventListener("click", async () => {
    if (state.game?.dirty) {
      if (!(await confirmDiscard("新しい棋譜を作成する"))) return;
      sendWs("game:new", {});
      return;
    }
    const ans = await confirmDialog({
      title: "新しい棋譜を作成",
      message: "初期局面から新しい棋譜を作成します。",
      actions: [
        { label: "キャンセル", value: null },
        { label: "作成", value: true, primary: true },
      ],
    });
    if (ans) sendWs("game:new", {});
  });
  els.openBtn.addEventListener("click", openGameList);
  els.importBtn.addEventListener("click", () => showDialog(els.dlgImport));
  els.pasteBtn.addEventListener("click", pasteFromClipboard);
  els.kifuCopyBtn.addEventListener("click", copyKifuAsKif);
  els.pasteTarget.addEventListener("paste", async (e) => {
    e.preventDefault();
    const text = e.clipboardData?.getData("text/plain") || "";
    closeDialog(null);
    await importText(text, { source: "paste" });
  });
  els.pasteTarget.addEventListener("beforeinput", (e) => {
    if (e.inputType !== "insertFromPaste") e.preventDefault(); // nothing can be typed here
  });
  els.exportBtn.addEventListener("click", () => {
    showDialog(els.dlgExport);
    refreshExport();
  });
  els.settingsBtn.addEventListener("click", () => showDialog(els.dlgSettings));
  els.engineSave.addEventListener("click", saveEngineSettings);

  // phone: actions live in a bottom sheet; each entry forwards to the toolbar button
  els.menuBtn.addEventListener("click", () => showDialog(els.dlgMenu));
  els.dlgMenu.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-act]");
    if (!b) return;
    const target = $(b.dataset.act);
    closeDialog(null);
    if (!target || target.disabled) {
      toast("warning", state.batch ? "全解析中は操作できません" : "今は使えません");
      return;
    }
    target.click();
  });

  // phone: the kifu card is a drawer sliding in from the right
  els.kifuDrawerBtn.addEventListener("click", () => setKifuDrawer(!document.body.classList.contains("kifu-open")));
  els.kifuDrawerClose.addEventListener("click", () => setKifuDrawer(false));
  els.kifuBackdrop.addEventListener("click", () => setKifuDrawer(false));
  wireDrawerSwipe();
  els.engineResetAll.addEventListener("click", () => renderEngineForm(true));

  // dialogs
  els.dialogHost.addEventListener("click", (e) => {
    if (e.target.closest("[data-close]")) closeDialog(null);
  });
  els.importFile.addEventListener("change", async () => {
    const f = els.importFile.files?.[0];
    els.importFile.value = "";
    if (!f) return;
    if (await importText(await decodeFile(f), { filename: fileStem(f.name) })) closeDialog(null);
  });
  ["dragenter", "dragover"].forEach((t) =>
    els.dropzone.addEventListener(t, (e) => {
      e.preventDefault();
      els.dropzone.classList.add("over");
    }),
  );
  ["dragleave", "drop"].forEach((t) => els.dropzone.addEventListener(t, () => els.dropzone.classList.remove("over")));
  els.dropzone.addEventListener("drop", async (e) => {
    e.preventDefault();
    const f = e.dataTransfer?.files?.[0];
    if (f && (await importText(await decodeFile(f), { filename: fileStem(f.name) }))) closeDialog(null);
  });
  els.exportSeg.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-v]");
    if (!b) return;
    state.exportFormat = b.dataset.v;
    refreshExport();
  });
  els.exportCopy.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(els.exportPreview.value);
      toast("info", "クリップボードにコピーしました");
    } catch {
      els.exportPreview.select();
      document.execCommand("copy");
      toast("info", "コピーしました");
    }
  });

  // view options
  const markCoords = () => {
    for (const b of els.optCoordsSeg.querySelectorAll("button")) {
      b.classList.toggle("on", b.dataset.v === state.opts.coords);
      b.setAttribute("aria-checked", String(b.dataset.v === state.opts.coords));
    }
  };
  markCoords();
  els.optEvalBar.checked = state.opts.evalBar;
  els.optLegal.checked = state.opts.legal;
  els.optCoordsSeg.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-v]");
    if (!b) return;
    state.opts.coords = b.dataset.v;
    markCoords();
    saveOpts();
    layoutBoard();
    renderCoords();
  });
  els.optEvalBar.addEventListener("change", () => {
    state.opts.evalBar = els.optEvalBar.checked;
    saveOpts();
    renderEvalBar();
    layoutBoard();
  });
  for (const [key, id, fn] of [
    ["lastMove", "optLastMove", renderBoard],
    ["bestMove", "optBestMove", renderOverlay],
    ["nextMove", "optNextMove", renderOverlay],
    ["arrowLabels", "optArrowLabels", renderOverlay],
  ]) {
    const box = $(id);
    box.checked = state.opts[key];
    box.addEventListener("change", () => {
      state.opts[key] = box.checked;
      saveOpts();
      if (state.game) fn();
    });
  }
  els.optLegal.addEventListener("change", () => {
    state.opts.legal = els.optLegal.checked;
    saveOpts();
    applyHighlights();
  });

  // keyboard
  window.addEventListener("keydown", (e) => {
    if (openDialogEl) {
      if (e.key === "Escape") closeDialog(null);
      return;
    }
    const tag = (e.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || e.target.isContentEditable) return;
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
      e.preventDefault();
      els.saveBtn.click();
      return;
    }
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    switch (e.key) {
      case "ArrowLeft":
        e.preventDefault();
        navPrev();
        break;
      case "ArrowRight":
        e.preventDefault();
        navNext();
        break;
      case "Home":
        e.preventDefault();
        navStart();
        break;
      case "End":
        e.preventDefault();
        navEnd();
        break;
      case "f":
      case "F":
        els.flipBtn.click();
        break;
      case " ":
        e.preventDefault();
        setAnalysisEnabled(!state.analysis.enabled);
        break;
      case "Escape":
        clearSelection();
        setKifuDrawer(false);
        break;
      default:
        break;
    }
  });

  // wheel on board = step through moves
  let wheelAcc = 0;
  els.board.addEventListener(
    "wheel",
    (e) => {
      e.preventDefault();
      wheelAcc += e.deltaY;
      if (Math.abs(wheelAcc) < 60) return;
      if (wheelAcc > 0) navNext();
      else navPrev();
      wheelAcc = 0;
    },
    { passive: false },
  );

  const ro = new ResizeObserver(() => {
    layoutBoard();
    renderEvalGraph();
  });
  ro.observe(els.boardArea);
  ro.observe(els.evalGraph);
  new ResizeObserver(keepCurrentMoveVisible).observe(els.moveList);
}

// Logout buttons only when password protection is on (SHOGI_ANALYZER_PASSWORD=TRUE).
// ---------- version / update notice (GitHub releases) ----------
function renderUpdate(st) {
  if (!st) return;
  const cur = st.current_version ? `v${st.current_version}` : "—";
  $("versionText").textContent = cur;
  const status = $("versionStatus");
  status.classList.toggle("new", Boolean(st.update_available));
  const when = st.checked_at ? new Date(st.checked_at).toLocaleString("ja-JP", { dateStyle: "short", timeStyle: "short" }) : "";
  if (!st.enabled) status.textContent = "更新の確認はオフです（.env の SHOGI_ANALYZER_UPDATE_CHECK）";
  else if (st.update_available) status.textContent = `新しいバージョン ${st.latest_version} があります`;
  else if (st.error) status.textContent = `確認できませんでした: ${st.error}`;
  else if (st.latest_version) status.textContent = `最新です${when ? `（確認: ${when}）` : ""}`;
  else status.textContent = "まだ確認していません";

  $("updateNotice").hidden = !st.update_available;
  if (st.update_available) {
    $("updateBody").textContent = `${st.release_name || st.latest_version} が公開されています。`;
    $("updateMeta").textContent = `現在 ${cur} → 最新 ${st.latest_version}${when ? ` ・ 確認 ${when}` : ""}`;
    $("updateLink").href = st.release_url || st.release_page_url || "#";
  }
}

async function setupUpdateNotice() {
  const popup = $("updatePopup");
  const badge = $("updateBadge");
  // the top bar is its own stacking context (blur): keep the popup outside so it sits above the board
  document.body.appendChild(popup);
  const setOpen = (open) => {
    popup.hidden = !open;
    if (open) {
      // under the badge, but always fully on screen (phones)
      const r = badge.getBoundingClientRect();
      const w = popup.offsetWidth;
      const right = Math.round(window.innerWidth - r.right - 8);
      popup.style.top = `${Math.round(r.bottom + 10)}px`;
      popup.style.right = `${Math.max(12, Math.min(right, window.innerWidth - w - 12))}px`;
    }
    badge.setAttribute("aria-expanded", String(open));
  };
  badge.addEventListener("click", (e) => {
    e.stopPropagation();
    setOpen(popup.hidden);
  });
  document.addEventListener("click", (e) => {
    if (!popup.hidden && !e.target.closest("#updateNotice, #updatePopup")) setOpen(false);
  });
  $("updateCheckBtn").addEventListener("click", async () => {
    const btn = $("updateCheckBtn");
    btn.disabled = true;
    try {
      const st = await fetch("/api/app/update_check", { method: "POST" }).then((r) => r.json());
      renderUpdate(st);
      toast("info", st.update_available ? `新しいバージョン ${st.latest_version} があります` : st.error ? "更新を確認できませんでした" : "最新のバージョンです");
    } catch {
      toast("error", "更新を確認できませんでした");
    } finally {
      btn.disabled = false;
    }
  });
  const load = async () => {
    try {
      const st = await fetch("/api/app/update_status", { cache: "no-store" }).then((r) => r.json());
      renderUpdate(st);
      // the server is asking GitHub right now (stale result on connect): read the answer shortly
      if (st.checking) setTimeout(load, 4000);
    } catch {
      // optional
    }
  };
  await load();
  setTimeout(load, 15000); // the server's first check runs in the background right after startup
  setInterval(load, 60 * 60 * 1000);
}

// ---------- "add to home screen" suggestion (phones / tablets only) ----------
const LS_INSTALL = "shogi_analyzer_install_prompt"; // "never" or the time (ms) until which it stays hidden
const SHARE_ICON = '<svg class="share-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v12M8 7l4-4 4 4"/><path d="M6 11v9h12v-9"/></svg>';

function installHelp() {
  const ua = navigator.userAgent;
  const ios = /iPhone|iPad|iPod/.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const android = /Android/.test(ua);
  if (ios) {
    if (/CriOS/.test(ua)) return `アドレスバー右の <b>共有ボタン</b> ${SHARE_ICON} →「<b>ホーム画面に追加</b>」で、アイコンからアプリのように開けます。`;
    if (/FxiOS|EdgiOS/.test(ua)) return `メニューの <b>共有</b> ${SHARE_ICON} →「<b>ホーム画面に追加</b>」で、アイコンからアプリのように開けます。`;
    return `<b>共有ボタン</b> ${SHARE_ICON}（「…」の中にある場合も）→「<b>ホーム画面に追加</b>」で、アイコンからアプリのように開けます。`;
  }
  if (android && /Firefox/.test(ua)) return "メニュー <b>⋮</b> →「<b>インストール</b>」（または「ホーム画面に追加」）で、アイコンからアプリのように開けます。";
  return null; // Android Chrome / Edge: handled with the install button
}

function setupInstallSuggestion() {
  const card = $("installCard");
  const standalone = window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
  const phoneLike = window.matchMedia("(pointer: coarse)").matches && /Android|iPhone|iPad|iPod/.test(navigator.userAgent + (navigator.maxTouchPoints > 1 ? " iPad" : ""));
  const saved = lsGet(LS_INSTALL);
  if (standalone || !phoneLike || !window.isSecureContext || saved === "never" || Number(saved) > Date.now()) return;
  const hide = () => (card.hidden = true);
  $("installLater").addEventListener("click", () => {
    lsSet(LS_INSTALL, String(Date.now() + 14 * 24 * 3600 * 1000));
    hide();
  });
  $("installNever").addEventListener("click", () => {
    lsSet(LS_INSTALL, "never");
    hide();
  });
  $("installGo").addEventListener("click", async () => {
    if (!installEvent) return hide();
    installEvent.prompt();
    const choice = await installEvent.userChoice.catch(() => null);
    installEvent = null;
    if (choice?.outcome !== "accepted") lsSet(LS_INSTALL, String(Date.now() + 14 * 24 * 3600 * 1000));
    hide();
  });
  window.addEventListener("appinstalled", hide);
  // a few seconds after opening, so it does not get in the way right away; never on top of a dialog
  const show = () => {
    if (openDialogEl) return void setTimeout(show, 3000);
    if (installEvent) {
      $("installBody").textContent = "ホーム画面に追加すると、アイコンからアプリのように開けます。";
      $("installGo").hidden = false;
    } else {
      const help = installHelp();
      if (!help) return; // the browser does not offer installing (yet): say nothing
      $("installBody").innerHTML = help;
    }
    card.hidden = false;
  };
  setTimeout(show, 6000);
}

async function setupLogout() {
  try {
    const st = await fetch("/api/auth/status", { cache: "no-store" }).then((r) => r.json());
    const on = Boolean(st.required && st.configured);
    for (const e of document.querySelectorAll(".logout-item")) e.hidden = !on;
  } catch {
    // status unavailable: keep the buttons hidden
  }
  $("logoutBtn").addEventListener("click", async () => {
    try {
      await fetch("/api/logout", { method: "POST" });
    } finally {
      location.replace("/login");
    }
  });
}

async function main() {
  loadOpts();
  ensureSquares();
  renderCoords();
  wire();
  setupLogout();
  setupUpdateNotice();
  // installable as an app (PWA): needs https (public address) or localhost
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
  setupInstallSuggestion();
  await loadTheme();
  setupThemeChoices();
  connectWs();
  // back to the page / network back: check the connection right away instead of waiting for
  // the browser to notice a dead socket; while visible, check it every 20 seconds
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") checkConnection();
  });
  window.addEventListener("online", checkConnection);
  window.addEventListener("pageshow", (e) => {
    if (e.persisted) checkConnection();
  });
  window.addEventListener("focus", checkConnection);
  setInterval(() => {
    if (document.visibilityState === "visible") checkConnection();
  }, 20000);
}

main().catch((e) => {
  console.error(e);
  toast("error", String(e));
});
