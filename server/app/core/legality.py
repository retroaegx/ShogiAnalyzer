"""Full legality check for a USI move (used for moves played from the UI).

Covers piece movement, promotion (only into/inside/out of the zone; forced for pieces that could
never move again), 二歩, drops on dead squares, leaving the own king in check (王手放置・自殺手)
and 打ち歩詰め. Positions without a king of the moving side skip the king-safety part.
"""

from __future__ import annotations

from .kifu_common import can_promote
from .movegen import candidates_for_piece
from .sfen_ops import SfenError, parse_sfen, parse_usi_move

_NORMS = ("P", "L", "N", "S", "G", "B", "R", "K", "+P", "+L", "+N", "+S", "+B", "+R")


def _owner(token: str) -> str:
    return "b" if token[-1].isupper() else "w"


def _norm(token: str) -> str:
    return ("+" if token.startswith("+") else "") + token[-1].upper()


def _other(side: str) -> str:
    return "w" if side == "b" else "b"


def _find_king(board, side: str):
    for r in range(9):
        for c in range(9):
            t = board[r][c]
            if t and _owner(t) == side and _norm(t) == "K":
                return r, c
    return None


def _attacked(board, row: int, col: int, by: str) -> bool:
    norms = {_norm(t) for line in board for t in line if t and _owner(t) == by}
    return any(candidates_for_piece(board, by, n, row, col) for n in norms)


def _king_safe(board, side: str) -> bool:
    k = _find_king(board, side)
    return k is None or not _attacked(board, k[0], k[1], _other(side))


def _dead_square(base: str, side: str, row: int) -> bool:
    """A piece of this kind could never move again from this row."""
    rel = row if side == "b" else 8 - row  # 0 = the far rank
    return (base in ("P", "L") and rel == 0) or (base == "N" and rel <= 1)


def _has_board_move(board, side: str) -> bool:
    norms = {_norm(t) for line in board for t in line if t and _owner(t) == side}
    for tr in range(9):
        for tc in range(9):
            for n in norms:
                for cand in candidates_for_piece(board, side, n, tr, tc):
                    nb = [line[:] for line in board]
                    nb[tr][tc] = nb[cand.from_row][cand.from_col]
                    nb[cand.from_row][cand.from_col] = None
                    if _king_safe(nb, side):
                        return True
    return False


def check_move(sfen: str, usi_move: str) -> None:
    """Raise SfenError with a Japanese reason when the move is not legal in this position."""
    state = parse_sfen(sfen)
    board = state["board"]
    side = state["side"]
    hands = state["hands"]
    mv = parse_usi_move(usi_move)
    tr, tc = mv.to_row, mv.to_col
    nb = [line[:] for line in board]

    if mv.is_drop:
        base = mv.drop_piece or ""
        if base == "K" or hands[side].get(base, 0) <= 0:
            raise SfenError("持ち駒にない駒は打てません")
        if board[tr][tc] is not None:
            raise SfenError("駒のあるマスには打てません")
        if _dead_square(base, side, tr):
            raise SfenError("行き所のない駒は打てません")
        if base == "P" and any(
            board[r][tc] and _owner(board[r][tc]) == side and _norm(board[r][tc]) == "P" for r in range(9)
        ):
            raise SfenError("二歩です")
        nb[tr][tc] = base if side == "b" else base.lower()
        if not _king_safe(nb, side):
            raise SfenError("王手を放置する手は指せません")
        if base == "P":
            enemy = _other(side)
            k = _find_king(board, enemy)
            forward = -1 if side == "b" else 1
            # a pawn check is adjacent, so only board moves can answer it
            if k == (tr + forward, tc) and not _has_board_move(nb, enemy):
                raise SfenError("打ち歩詰めです")
        return

    fr, fc = mv.from_row, mv.from_col
    piece = board[fr][fc]
    if piece is None or _owner(piece) != side:
        raise SfenError("動かせる駒がありません")
    if not any(
        (c.from_row, c.from_col) == (fr, fc) for c in candidates_for_piece(board, side, _norm(piece), tr, tc)
    ):
        raise SfenError("その駒はそこへ動けません")
    if mv.promote and not can_promote(piece, side, fr, tr):
        raise SfenError("成れない手です")
    if not mv.promote and not piece.startswith("+") and _dead_square(piece[-1].upper(), side, tr):
        raise SfenError("成らないと行き所のない駒になります")
    nb[tr][tc] = piece
    nb[fr][fc] = None
    if not _king_safe(nb, side):
        raise SfenError("王手を放置する手は指せません" if not _king_safe(board, side) else "玉を取られる手は指せません")
