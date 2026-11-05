// SFEN <-> UI state helpers

// Canonical start position (hirate)
export const DEFAULT_START_SFEN =
  "lnsgkgsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL b - 1";

const PIECE_MAP = {
  P: "pawn",
  L: "lance",
  N: "knight",
  S: "silver",
  G: "gold",
  B: "bishop",
  R: "rook",
  K: "king",
};

const PROMOTE_MAP = {
  pawn: "promoted_pawn",
  lance: "promoted_lance",
  knight: "promoted_knight",
  silver: "promoted_silver",
  // UI uses special names for +B/+R
  bishop: "horse",
  rook: "dragon",
};

const HAND_ORDER = ["rook", "bishop", "gold", "silver", "knight", "lance", "pawn"];

function emptyBoard() {
  return Array.from({ length: 9 }, () => Array.from({ length: 9 }, () => null));
}

function ensure4Fields(sfen) {
  const s = (sfen || "").trim();
  if (!s) return null;
  // Allow "startpos" as a convenience.
  if (s === "startpos") return DEFAULT_START_SFEN;
  const parts = s.split(/\s+/);
  if (parts.length >= 4) return parts.slice(0, 4).join(" ");
  return null;
}

export function parseSfen(sfenInput) {
  const sfen = ensure4Fields(sfenInput);
  if (!sfen) return null;
  const parts = sfen.split(/\s+/);
  const [boardPart, sidePart, handsPart, plyPart] = parts;

  const board = emptyBoard();
  const ranks = (boardPart || "").split("/");
  if (ranks.length !== 9) return null;

  for (let r = 0; r < 9; r += 1) {
    const rank = ranks[r];
    let c = 0;
    for (let i = 0; i < rank.length; i += 1) {
      const ch = rank[i];
      if (ch >= "1" && ch <= "9") {
        c += Number(ch);
        continue;
      }
      let promoted = false;
      let pieceCh = ch;
      if (ch === "+") {
        promoted = true;
        i += 1;
        pieceCh = rank[i];
      }
      const upper = pieceCh.toUpperCase();
      const base = PIECE_MAP[upper];
      if (!base) return null;
      const owner = pieceCh === upper ? "sente" : "gote";
      const pieceName = promoted && PROMOTE_MAP[base] ? PROMOTE_MAP[base] : base;
      const isPromoted = !!promoted || pieceName.startsWith("promoted_") || pieceName === "horse" || pieceName === "dragon";
      board[r][c] = { owner, piece: pieceName, promoted: isPromoted };
      c += 1;
    }
    if (c !== 9) return null;
  }

  const capturedPieces = { sente: {}, gote: {} };
  if (handsPart && handsPart !== "-") {
    let numBuf = "";
    for (let i = 0; i < handsPart.length; i += 1) {
      const ch = handsPart[i];
      if (ch >= "0" && ch <= "9") {
        numBuf += ch;
        continue;
      }
      const upper = ch.toUpperCase();
      const base = PIECE_MAP[upper];
      if (!base || base === "king") {
        numBuf = "";
        continue;
      }
      const owner = ch === upper ? "sente" : "gote";
      const cnt = numBuf ? Number(numBuf) : 1;
      numBuf = "";
      capturedPieces[owner][base] = (capturedPieces[owner][base] || 0) + cnt;
    }
  }

  const currentPlayer = sidePart === "w" ? "gote" : "sente";
  const ply = Number(plyPart || 1) || 1;

  return { board, capturedPieces, currentPlayer, turn: currentPlayer, ply, sfen };
}

export function countsToList(counts) {
  const out = [];
  for (const p of HAND_ORDER) {
    const n = Number(counts?.[p] || 0);
    for (let i = 0; i < n; i += 1) out.push(p);
  }
  return out;
}

/** Serialize the same board/hand representation used by parseSfen. */
export function toSfen(position) {
  const codes = {king:'K',rook:'R',bishop:'B',gold:'G',silver:'S',knight:'N',lance:'L',pawn:'P',
    dragon:'+R',horse:'+B',promoted_silver:'+S',promoted_knight:'+N',promoted_lance:'+L',promoted_pawn:'+P'};
  const ranks = position.board.map(row => {
    let out = '', empty = 0;
    for (const piece of row) {
      if (!piece) { empty++; continue; }
      if (empty) { out += empty; empty = 0; }
      const code = codes[piece.piece];
      if (!code) throw new Error('Unknown piece: '+piece.piece);
      out += piece.owner === 'sente' ? code : code.toLowerCase();
    }
    return out + (empty || '');
  });
  let hand = '';
  for (const owner of ['sente','gote']) for (const type of ['rook','bishop','gold','silver','knight','lance','pawn']) {
    const count = position.capturedPieces[owner][type] || 0;
    if (count > 0) hand += (count > 1 ? count : '') + (owner === 'sente' ? codes[type] : codes[type].toLowerCase());
  }
  return `${ranks.join('/')} ${position.currentPlayer === 'sente' ? 'b' : 'w'} ${hand || '-'} ${position.ply || 1}`;
}
