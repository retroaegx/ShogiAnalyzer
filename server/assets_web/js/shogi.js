// Shogi rules / notation helpers used by the UI (lightweight, enough for move input + display).
import { parseSfen } from "/js/vendor/sfen.js";
import { normalizeDropPieceType, parseUsi } from "/js/vendor/usi.js";

export const HAND_ORDER = ["rook", "bishop", "gold", "silver", "knight", "lance", "pawn"];

const FILE_ZENKAKU = ["", "１", "２", "３", "４", "５", "６", "７", "８", "９"];
const RANK_KANJI = ["", "一", "二", "三", "四", "五", "六", "七", "八", "九"];

export const PIECE_JA = {
  pawn: "歩",
  lance: "香",
  knight: "桂",
  silver: "銀",
  gold: "金",
  bishop: "角",
  rook: "飛",
  king: "玉",
  promoted_pawn: "と",
  promoted_lance: "成香",
  promoted_knight: "成桂",
  promoted_silver: "成銀",
  horse: "馬",
  dragon: "龍",
};

const PROMOTE_TYPE = {
  pawn: "promoted_pawn",
  lance: "promoted_lance",
  knight: "promoted_knight",
  silver: "promoted_silver",
  bishop: "horse",
  rook: "dragon",
};

// internal coords: row 0 = rank 一 (gote side), col 0 = file 9
export function fileOfCol(col) {
  return 9 - Number(col);
}
export function rankOfRow(row) {
  return Number(row) + 1;
}
export const FILE_LABEL = (file) => FILE_ZENKAKU[file] || String(file);
export const RANK_LABEL = (rank) => RANK_KANJI[rank] || String(rank);

function jaPiece(pieceType) {
  const t = String(pieceType || "");
  return PIECE_JA[t] || PIECE_JA[normalizeDropPieceType(t)] || "?";
}

export function moveTarget(moveUsi) {
  const mv = parseUsi(moveUsi);
  if (!mv?.ok) return null;
  return { row: mv.toRow, col: mv.toCol, fromRow: mv.isDrop ? null : mv.fromRow, fromCol: mv.isDrop ? null : mv.fromCol };
}

function cloneParsed(p) {
  return {
    ...p,
    board: p.board.map((row) => row.map((cell) => (cell ? { ...cell } : null))),
    capturedPieces: { sente: { ...(p.capturedPieces?.sente || {}) }, gote: { ...(p.capturedPieces?.gote || {}) } },
  };
}

/** KIF move text (without ▲△), e.g. "７六歩(77)", "同　銀", "５五角打". */
function kifBody(parsed, moveUsi, prevTo) {
  const mv = parseUsi(moveUsi);
  if (!mv?.ok) return moveUsi || "";
  const same = prevTo && prevTo.row === mv.toRow && prevTo.col === mv.toCol;
  const sq = same ? "同　" : `${FILE_LABEL(fileOfCol(mv.toCol))}${RANK_LABEL(rankOfRow(mv.toRow))}`;
  if (mv.isDrop) return `${sq}${jaPiece(mv.pieceType)}打`;
  const p = parsed?.board?.[mv.fromRow]?.[mv.fromCol] || null;
  return `${sq}${jaPiece(p?.piece)}${mv.promote ? "成" : ""}(${fileOfCol(mv.fromCol)}${rankOfRow(mv.fromRow)})`;
}

function applyMove(parsed, moveUsi) {
  const mv = parseUsi(moveUsi);
  if (!mv?.ok || !parsed?.board) return;
  const me = parsed.currentPlayer;
  if (mv.isDrop) {
    const t = normalizeDropPieceType(mv.pieceType) || mv.pieceType;
    parsed.board[mv.toRow][mv.toCol] = { owner: me, piece: t, promoted: false };
    const hand = parsed.capturedPieces[me];
    if (hand[t]) hand[t] -= 1;
  } else {
    const from = parsed.board[mv.fromRow][mv.fromCol];
    const cap = parsed.board[mv.toRow][mv.toCol];
    if (cap) {
      const base = baseType(cap.piece);
      parsed.capturedPieces[me][base] = (parsed.capturedPieces[me][base] || 0) + 1;
    }
    parsed.board[mv.fromRow][mv.fromCol] = null;
    const moved = from ? { ...from } : { owner: me, piece: "pawn", promoted: false };
    if (mv.promote && PROMOTE_TYPE[moved.piece]) {
      moved.piece = PROMOTE_TYPE[moved.piece];
      moved.promoted = true;
    }
    parsed.board[mv.toRow][mv.toCol] = moved;
  }
  parsed.currentPlayer = me === "sente" ? "gote" : "sente";
  parsed.turn = parsed.currentPlayer;
}

/** "▲７六歩(77)" for the move played from parentSfen. */
export function kifMove(parentSfen, moveUsi, prevTo) {
  const parsed = parseSfen(parentSfen);
  if (!parsed) return moveUsi || "";
  const mark = parsed.currentPlayer === "sente" ? "▲" : "△";
  return mark + kifBody(parsed, moveUsi, prevTo);
}

/** PV (USI list) -> [{usi, text}] with ▲△ marks. */
export function kifPv(pvUsi, startSfen, prevTo) {
  const list = Array.isArray(pvUsi) ? pvUsi : [];
  const p0 = parseSfen(startSfen);
  if (!p0) return list.map((u) => ({ usi: u, text: u }));
  const parsed = cloneParsed(p0);
  let prev = prevTo || null;
  return list.map((usi) => {
    const mark = parsed.currentPlayer === "sente" ? "▲" : "△";
    const text = mark + kifBody(parsed, usi, prev);
    const t = moveTarget(usi);
    prev = t ? { row: t.row, col: t.col } : null;
    applyMove(parsed, usi);
    return { usi, text };
  });
}

// ---------- movement ----------
export function isPromotedType(t) {
  return t === "dragon" || t === "horse" || String(t).startsWith("promoted_");
}

export function baseType(t) {
  return normalizeDropPieceType(t) || t;
}

function dir(owner) {
  return owner === "sente" ? -1 : 1;
}

function inBounds(r, c) {
  return r >= 0 && r < 9 && c >= 0 && c < 9;
}

export function getPossibleMoves(board, fromRow, fromCol, piece) {
  if (!piece) return [];
  const t = piece.piece;
  const owner = piece.owner;
  const d = dir(owner);
  const moves = [];
  const add = (r, c) => {
    if (!inBounds(r, c)) return;
    const dst = board[r][c];
    if (dst && dst.owner === owner) return;
    moves.push({ row: r, col: c });
  };
  const slide = (dr, dc) => {
    let r = fromRow + dr;
    let c = fromCol + dc;
    while (inBounds(r, c)) {
      const dst = board[r][c];
      if (dst) {
        if (dst.owner !== owner) moves.push({ row: r, col: c });
        break;
      }
      moves.push({ row: r, col: c });
      r += dr;
      c += dc;
    }
  };
  const gold = () => {
    add(fromRow + d, fromCol);
    add(fromRow + d, fromCol - 1);
    add(fromRow + d, fromCol + 1);
    add(fromRow, fromCol - 1);
    add(fromRow, fromCol + 1);
    add(fromRow - d, fromCol);
  };
  const rookSlides = () => [[1, 0], [-1, 0], [0, 1], [0, -1]].forEach(([a, b]) => slide(a, b));
  const bishopSlides = () => [[1, 1], [1, -1], [-1, 1], [-1, -1]].forEach(([a, b]) => slide(a, b));

  switch (t) {
    case "king":
      for (let dr = -1; dr <= 1; dr++) for (let dc = -1; dc <= 1; dc++) if (dr || dc) add(fromRow + dr, fromCol + dc);
      break;
    case "gold":
    case "promoted_pawn":
    case "promoted_lance":
    case "promoted_knight":
    case "promoted_silver":
      gold();
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
      slide(d, 0);
      break;
    case "pawn":
      add(fromRow + d, fromCol);
      break;
    case "rook":
      rookSlides();
      break;
    case "bishop":
      bishopSlides();
      break;
    case "dragon":
      rookSlides();
      [[1, 1], [1, -1], [-1, 1], [-1, -1]].forEach(([a, b]) => add(fromRow + a, fromCol + b));
      break;
    case "horse":
      bishopSlides();
      [[1, 0], [-1, 0], [0, 1], [0, -1]].forEach(([a, b]) => add(fromRow + a, fromCol + b));
      break;
    default:
      break;
  }
  return moves;
}

export function getDropMoves(board, pieceType, owner) {
  const t = baseType(pieceType);
  const out = [];
  for (let c = 0; c < 9; c++) {
    let nifu = false;
    if (t === "pawn") {
      for (let r = 0; r < 9; r++) {
        const p = board[r][c];
        if (p && p.owner === owner && p.piece === "pawn") nifu = true;
      }
    }
    if (nifu) continue;
    for (let r = 0; r < 9; r++) {
      if (board[r][c]) continue;
      if ((t === "pawn" || t === "lance") && (owner === "sente" ? r === 0 : r === 8)) continue;
      if (t === "knight" && (owner === "sente" ? r <= 1 : r >= 7)) continue;
      out.push({ row: r, col: c });
    }
  }
  return out;
}

// ---------- full legality (king safety, 打ち歩詰め) ----------
const otherSide = (owner) => (owner === "sente" ? "gote" : "sente");

function findKing(board, owner) {
  for (let r = 0; r < 9; r++) for (let c = 0; c < 9; c++) {
    const p = board[r][c];
    if (p && p.owner === owner && p.piece === "king") return { r, c };
  }
  return null;
}

function isAttacked(board, row, col, byOwner) {
  for (let r = 0; r < 9; r++) for (let c = 0; c < 9; c++) {
    const p = board[r][c];
    if (p && p.owner === byOwner && getPossibleMoves(board, r, c, p).some((m) => m.row === row && m.col === col)) return true;
  }
  return false;
}

function kingSafeAfter(board, owner, place) {
  const nb = board.map((row) => row.slice());
  place(nb);
  const k = findKing(nb, owner);
  return !k || !isAttacked(nb, k.r, k.c, otherSide(owner)); // no king (詰将棋の玉方など): nothing to protect
}

/** Board moves of one piece that do not leave the own king in check (王手放置・自殺手 are illegal). */
export function legalMovesFrom(board, row, col, piece) {
  return getPossibleMoves(board, row, col, piece).filter((m) =>
    kingSafeAfter(board, piece.owner, (nb) => {
      nb[m.row][m.col] = piece;
      nb[row][col] = null;
    }),
  );
}

function hasAnyBoardMove(board, owner) {
  for (let r = 0; r < 9; r++) for (let c = 0; c < 9; c++) {
    const p = board[r][c];
    if (p && p.owner === owner && legalMovesFrom(board, r, c, p).length) return true;
  }
  return false;
}

/** Drops that are legal: 二歩・行き所のない駒 (getDropMoves), the own king safe, and no 打ち歩詰め. */
export function legalDrops(board, pieceType, owner) {
  const t = baseType(pieceType);
  return getDropMoves(board, pieceType, owner).filter((m) => {
    const dropped = { piece: t, owner };
    if (!kingSafeAfter(board, owner, (nb) => (nb[m.row][m.col] = dropped))) return false;
    if (t !== "pawn") return true;
    const enemy = otherSide(owner);
    const k = findKing(board, enemy);
    if (!k || k.r !== m.row + dir(owner) || k.c !== m.col) return true; // the pawn gives no check
    // 打ち歩詰め: a checking pawn drop the enemy cannot answer (a pawn check is adjacent, so only
    // board moves — capturing it or moving the king — can answer it)
    const nb = board.map((row) => row.slice());
    nb[m.row][m.col] = dropped;
    return hasAnyBoardMove(nb, enemy);
  });
}

const PROMOTABLE = new Set(["pawn", "lance", "knight", "silver", "bishop", "rook"]);

export function canPromote(piece, fromRow, toRow) {
  if (!PROMOTABLE.has(piece.piece)) return false;
  if (piece.owner === "sente") return fromRow <= 2 || toRow <= 2;
  return fromRow >= 6 || toRow >= 6;
}

export function mustPromote(piece, toRow) {
  const t = piece.piece;
  if (piece.owner === "sente") return ((t === "pawn" || t === "lance") && toRow === 0) || (t === "knight" && toRow <= 1);
  return ((t === "pawn" || t === "lance") && toRow === 8) || (t === "knight" && toRow >= 7);
}

export function promotedTypeOf(t) {
  return PROMOTE_TYPE[t] || t;
}

// ---------- evaluation ----------
/** USI score (side-to-move perspective) -> sente-perspective centipawn-like number. */
export function senteScore(line, sideToMove) {
  if (!line || (line.score_type !== "cp" && line.score_type !== "mate")) return null;
  const v = Number(line.score_value || 0);
  let cp;
  if (line.score_type === "mate") cp = (v > 0 || Object.is(v, 0) ? 1 : -1) * (32000 - Math.min(Math.abs(v), 999));
  else cp = v;
  return sideToMove === "gote" ? -cp : cp;
}

/** Winning probability for sente in [0,1]. */
export function winRate(cp) {
  if (cp == null) return 0.5;
  return 1 / (1 + Math.exp(-cp / 600));
}

export function formatScore(line, sideToMove) {
  if (!line) return "—";
  const v = Number(line.score_value || 0);
  const s = sideToMove === "gote" ? -1 : 1;
  if (line.score_type === "mate") {
    const senteWins = (v > 0 || Object.is(v, 0)) === (s > 0);
    return `${senteWins ? "▲" : "△"}詰${Math.abs(v) || ""}`;
  }
  if (line.score_type === "cp") {
    const x = v * s;
    return `${x > 0 ? "+" : ""}${x}`;
  }
  return "—";
}
