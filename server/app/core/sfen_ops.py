from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DEFAULT_START_SFEN = (
    "lnsgkgsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL b - 1"
)

PROMOTABLE = {"P", "L", "N", "S", "B", "R"}
HAND_ORDER = ["R", "B", "G", "S", "N", "L", "P"]


class SfenError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedUsiMove:
    is_drop: bool
    to_row: int
    to_col: int
    from_row: int | None = None
    from_col: int | None = None
    promote: bool = False
    drop_piece: str | None = None


def normalize_sfen(sfen: str | None) -> str:
    s = (sfen or "").strip()
    if not s or s == "startpos":
        return DEFAULT_START_SFEN
    parts = s.split()
    if len(parts) < 4:
        raise SfenError("SFEN must have 4 fields")
    return " ".join(parts[:4])


def square_to_rc(square: str) -> tuple[int, int]:
    if len(square) != 2:
        raise SfenError(f"invalid USI square: {square}")
    file_ch, rank_ch = square[0], square[1]
    if file_ch < "1" or file_ch > "9":
        raise SfenError(f"invalid file: {square}")
    if rank_ch < "a" or rank_ch > "i":
        raise SfenError(f"invalid rank: {square}")
    row = ord(rank_ch) - ord("a")
    col = 9 - int(file_ch)
    return row, col


def rc_to_square(row: int, col: int) -> str:
    if not (0 <= row <= 8 and 0 <= col <= 8):
        raise SfenError("row/col out of range")
    return f"{9 - col}{chr(ord('a') + row)}"


def parse_usi_move(usi: str) -> ParsedUsiMove:
    s = (usi or "").strip()
    if not s:
        raise SfenError("empty USI move")
    if len(s) == 4 and s[1] == "*":
        piece = s[0]
        if piece.upper() not in HAND_ORDER + ["K"]:
            raise SfenError(f"invalid drop piece: {piece}")
        to_row, to_col = square_to_rc(s[2:4])
        return ParsedUsiMove(
            is_drop=True,
            to_row=to_row,
            to_col=to_col,
            drop_piece=piece.upper(),
        )
    if len(s) not in (4, 5):
        raise SfenError(f"invalid USI move length: {s}")
    if len(s) == 5 and not s.endswith("+"):
        raise SfenError(f"invalid promotion suffix: {s}")
    from_row, from_col = square_to_rc(s[0:2])
    to_row, to_col = square_to_rc(s[2:4])
    return ParsedUsiMove(
        is_drop=False,
        from_row=from_row,
        from_col=from_col,
        to_row=to_row,
        to_col=to_col,
        promote=len(s) == 5,
    )


def _empty_board() -> list[list[str | None]]:
    return [[None for _ in range(9)] for _ in range(9)]


def _parse_board(board_part: str) -> list[list[str | None]]:
    ranks = board_part.split("/")
    if len(ranks) != 9:
        raise SfenError("board ranks must be 9")
    board = _empty_board()
    for r, rank in enumerate(ranks):
        c = 0
        i = 0
        while i < len(rank):
            ch = rank[i]
            if ch.isdigit():
                c += int(ch)
                i += 1
                continue
            token = ch
            if ch == "+":
                if i + 1 >= len(rank):
                    raise SfenError("dangling '+' in board")
                token = "+" + rank[i + 1]
                i += 1
            if c >= 9:
                raise SfenError("board rank overflow")
            piece_ch = token[-1]
            if piece_ch.upper() not in {"P", "L", "N", "S", "G", "B", "R", "K"}:
                raise SfenError(f"invalid piece token: {token}")
            board[r][c] = token
            c += 1
            i += 1
        if c != 9:
            raise SfenError("board rank width mismatch")
    return board


def _parse_hands(hands_part: str) -> dict[str, dict[str, int]]:
    hands = {"b": {k: 0 for k in HAND_ORDER}, "w": {k: 0 for k in HAND_ORDER}}
    if not hands_part or hands_part == "-":
        return hands
    num_buf = ""
    for ch in hands_part:
        if ch.isdigit():
            num_buf += ch
            continue
        base = ch.upper()
        if base not in HAND_ORDER:
            raise SfenError(f"invalid hand piece: {ch}")
        count = int(num_buf) if num_buf else 1
        num_buf = ""
        side = "b" if ch.isupper() else "w"
        hands[side][base] += count
    if num_buf:
        raise SfenError("dangling number in hands")
    return hands


def parse_sfen(sfen: str | None) -> dict[str, Any]:
    normalized = normalize_sfen(sfen)
    board_part, side_part, hands_part, ply_part = normalized.split()
    if side_part not in {"b", "w"}:
        raise SfenError("side must be b/w")
    try:
        ply = int(ply_part)
    except ValueError as exc:
        raise SfenError("ply must be int") from exc
    return {
        "board": _parse_board(board_part),
        "side": side_part,
        "hands": _parse_hands(hands_part),
        "ply": max(1, ply),
    }


def _serialize_board(board: list[list[str | None]]) -> str:
    ranks: list[str] = []
    for row in board:
        empties = 0
        parts: list[str] = []
        for cell in row:
            if not cell:
                empties += 1
                continue
            if empties:
                parts.append(str(empties))
                empties = 0
            parts.append(cell)
        if empties:
            parts.append(str(empties))
        ranks.append("".join(parts) or "9")
    return "/".join(ranks)


def _serialize_hands(hands: dict[str, dict[str, int]]) -> str:
    parts: list[str] = []
    for side in ("b", "w"):
        for piece in HAND_ORDER:
            count = int(hands.get(side, {}).get(piece, 0))
            if count <= 0:
                continue
            ch = piece if side == "b" else piece.lower()
            if count > 1:
                parts.append(str(count))
            parts.append(ch)
    return "".join(parts) or "-"


def build_sfen(state: dict[str, Any]) -> str:
    board = state["board"]
    side = state["side"]
    hands = state["hands"]
    ply = int(state["ply"])
    if side not in {"b", "w"}:
        raise SfenError("side must be b/w")
    return f"{_serialize_board(board)} {side} {_serialize_hands(hands)} {max(1, ply)}"


def _owner_of_token(token: str) -> str:
    return "b" if token[-1].isupper() else "w"


def _promote_token(token: str) -> str:
    base = token[-1].upper()
    if base not in PROMOTABLE:
        return token
    if token.startswith("+"):
        return token
    promoted = "+" + base
    return promoted if token[-1].isupper() else promoted.lower()


def _unpromoted_base_letter(token: str) -> str:
    return token[-1].upper()


def apply_usi_move(sfen: str | None, usi_move: str) -> str:
    state = parse_sfen(sfen)
    mv = parse_usi_move(usi_move)
    board: list[list[str | None]] = state["board"]
    side: str = state["side"]
    hands: dict[str, dict[str, int]] = state["hands"]

    if mv.is_drop:
        if mv.drop_piece == "K":
            raise SfenError("king drop is invalid")
        if board[mv.to_row][mv.to_col] is not None:
            raise SfenError("drop destination occupied")
        if hands[side].get(mv.drop_piece or "", 0) <= 0:
            raise SfenError(f"piece not in hand: {mv.drop_piece}")
        hands[side][mv.drop_piece] -= 1  # type: ignore[index]
        token = mv.drop_piece if side == "b" else (mv.drop_piece or "").lower()
        board[mv.to_row][mv.to_col] = token
    else:
        if mv.from_row is None or mv.from_col is None:
            raise SfenError("missing from square")
        piece = board[mv.from_row][mv.from_col]
        if piece is None:
            raise SfenError("source square empty")
        if _owner_of_token(piece) != side:
            raise SfenError("moving opponent piece")
        captured = board[mv.to_row][mv.to_col]
        if captured is not None:
            if _owner_of_token(captured) == side:
                raise SfenError("destination occupied by own piece")
            base = _unpromoted_base_letter(captured)
            if base != "K":
                hands[side][base] = hands[side].get(base, 0) + 1
        board[mv.from_row][mv.from_col] = None
        if mv.promote:
            piece = _promote_token(piece)
        board[mv.to_row][mv.to_col] = piece

    state["side"] = "w" if side == "b" else "b"
    state["ply"] = int(state["ply"]) + 1
    return build_sfen(state)


def sfen_to_position_command(initial_sfen: str, moves: list[str]) -> str:
    if normalize_sfen(initial_sfen) == DEFAULT_START_SFEN:
        base = "position startpos"
    else:
        base = f"position sfen {normalize_sfen(initial_sfen)}"
    if moves:
        return f"{base} moves {' '.join(moves)}"
    return base

