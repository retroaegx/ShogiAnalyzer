from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CandidateMove:
    from_row: int
    from_col: int


def _in_bounds(r: int, c: int) -> bool:
    return 0 <= r <= 8 and 0 <= c <= 8


def _owner(token: str) -> str:
    return "b" if token[-1].isupper() else "w"


def _normalize_token(token: str) -> str:
    if token.startswith("+"):
        return "+" + token[-1].upper()
    return token[-1].upper()


def _slide_ok(board, fr: int, fc: int, tr: int, tc: int, dr: int, dc: int) -> bool:
    r, c = fr + dr, fc + dc
    while (r, c) != (tr, tc):
        if not _in_bounds(r, c):
            return False
        if board[r][c] is not None:
            return False
        r += dr
        c += dc
    return True


def _step_ok(board, fr: int, fc: int, tr: int, tc: int, dr: int, dc: int) -> bool:
    return (fr + dr, fc + dc) == (tr, tc)


def _knight_ok(fr: int, fc: int, tr: int, tc: int, forward: int) -> bool:
    # forward: -1 for sente (towards decreasing row), +1 for gote
    return (fr + 2 * forward, fc - 1) == (tr, tc) or (fr + 2 * forward, fc + 1) == (tr, tc)


def candidates_for_piece(board, side: str, piece_norm: str, to_row: int, to_col: int) -> list[CandidateMove]:
    """Return candidate from-squares whose piece could move to (to_row,to_col).

    This is a pseudo-legal generator (ignores check). It is intended for KI2 parsing.
    """
    forward = -1 if side == "b" else 1

    def token_matches(tok: str) -> bool:
        if _owner(tok) != side:
            return False
        return _normalize_token(tok) == piece_norm

    out: list[CandidateMove] = []
    for fr in range(9):
        for fc in range(9):
            tok = board[fr][fc]
            if tok is None:
                continue
            if not token_matches(tok):
                continue
            # destination occupied by own piece is invalid
            dst = board[to_row][to_col]
            if dst is not None and _owner(dst) == side:
                continue

            norm = piece_norm
            if norm in {"P"}:
                if _step_ok(board, fr, fc, to_row, to_col, forward, 0):
                    out.append(CandidateMove(fr, fc))
            elif norm in {"L"}:
                if fc == to_col and ((to_row - fr) * forward) > 0:
                    dr = forward
                    if _slide_ok(board, fr, fc, to_row, to_col, dr, 0):
                        out.append(CandidateMove(fr, fc))
            elif norm in {"N"}:
                if _knight_ok(fr, fc, to_row, to_col, forward):
                    out.append(CandidateMove(fr, fc))
            elif norm in {"S"}:
                deltas = [
                    (forward, 0),
                    (forward, -1),
                    (forward, 1),
                    (-forward, -1),
                    (-forward, 1),
                ]
                if any(_step_ok(board, fr, fc, to_row, to_col, dr, dc) for dr, dc in deltas):
                    out.append(CandidateMove(fr, fc))
            elif norm in {"G", "+P", "+L", "+N", "+S"}:
                deltas = [
                    (forward, 0),
                    (forward, -1),
                    (forward, 1),
                    (0, -1),
                    (0, 1),
                    (-forward, 0),
                ]
                if any(_step_ok(board, fr, fc, to_row, to_col, dr, dc) for dr, dc in deltas):
                    out.append(CandidateMove(fr, fc))
            elif norm in {"K"}:
                deltas = [
                    (-1, -1),
                    (-1, 0),
                    (-1, 1),
                    (0, -1),
                    (0, 1),
                    (1, -1),
                    (1, 0),
                    (1, 1),
                ]
                if any(_step_ok(board, fr, fc, to_row, to_col, dr, dc) for dr, dc in deltas):
                    out.append(CandidateMove(fr, fc))
            elif norm in {"B", "+B"}:
                dr = to_row - fr
                dc = to_col - fc
                if abs(dr) == abs(dc) and dr != 0:
                    step_r = 1 if dr > 0 else -1
                    step_c = 1 if dc > 0 else -1
                    if _slide_ok(board, fr, fc, to_row, to_col, step_r, step_c):
                        out.append(CandidateMove(fr, fc))
                if norm == "+B":
                    # horse adds king orthogonal steps
                    if any(
                        _step_ok(board, fr, fc, to_row, to_col, sdr, sdc)
                        for sdr, sdc in [(-1, 0), (1, 0), (0, -1), (0, 1)]
                    ):
                        out.append(CandidateMove(fr, fc))
            elif norm in {"R", "+R"}:
                if fr == to_row and fc != to_col:
                    step = 1 if (to_col - fc) > 0 else -1
                    if _slide_ok(board, fr, fc, to_row, to_col, 0, step):
                        out.append(CandidateMove(fr, fc))
                if fc == to_col and fr != to_row:
                    step = 1 if (to_row - fr) > 0 else -1
                    if _slide_ok(board, fr, fc, to_row, to_col, step, 0):
                        out.append(CandidateMove(fr, fc))
                if norm == "+R":
                    # dragon adds king diagonal steps
                    if any(
                        _step_ok(board, fr, fc, to_row, to_col, sdr, sdc)
                        for sdr, sdc in [(-1, -1), (-1, 1), (1, -1), (1, 1)]
                    ):
                        out.append(CandidateMove(fr, fc))
    # de-dup (some promoted pieces can match via both slide and step)
    uniq = {(c.from_row, c.from_col): c for c in out}
    return list(uniq.values())


def filter_candidates_by_disambig(
    side: str,
    to_row: int,
    to_col: int,
    candidates: list[CandidateMove],
    disambig: list[str],
) -> list[CandidateMove]:
    if not disambig or not candidates:
        return candidates

    def file_of(c: CandidateMove) -> int:
        return 9 - c.from_col

    def rank_of(c: CandidateMove) -> int:
        return c.from_row + 1

    to_file = 9 - to_col
    to_rank = to_row + 1
    forward_is_up = side == "b"  # sente: forward = smaller rank

    filtered = candidates

    if "直" in disambig:
        filtered = [c for c in filtered if file_of(c) == to_file]

    if "寄" in disambig:
        filtered = [c for c in filtered if rank_of(c) == to_rank]

    if "上" in disambig:
        if forward_is_up:
            filtered = [c for c in filtered if rank_of(c) > to_rank]
        else:
            filtered = [c for c in filtered if rank_of(c) < to_rank]

    if "引" in disambig:
        if forward_is_up:
            filtered = [c for c in filtered if rank_of(c) < to_rank]
        else:
            filtered = [c for c in filtered if rank_of(c) > to_rank]

    if "右" in disambig:
        if side == "b":
            # sente right = smaller file number
            best = min((file_of(c) for c in filtered), default=None)
        else:
            best = max((file_of(c) for c in filtered), default=None)
        if best is not None:
            filtered = [c for c in filtered if file_of(c) == best]

    if "左" in disambig:
        if side == "b":
            best = max((file_of(c) for c in filtered), default=None)
        else:
            best = min((file_of(c) for c in filtered), default=None)
        if best is not None:
            filtered = [c for c in filtered if file_of(c) == best]

    return filtered
