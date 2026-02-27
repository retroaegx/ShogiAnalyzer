from __future__ import annotations

import re
from dataclasses import dataclass

from .sfen_ops import ParsedUsiMove, parse_sfen, parse_usi_move, rc_to_square


FILE_ZENKAKU = {
    1: "１",
    2: "２",
    3: "３",
    4: "４",
    5: "５",
    6: "６",
    7: "７",
    8: "８",
    9: "９",
}

RANK_KANJI = {
    1: "一",
    2: "二",
    3: "三",
    4: "四",
    5: "五",
    6: "六",
    7: "七",
    8: "八",
    9: "九",
}


PIECE_JA = {
    "P": "歩",
    "L": "香",
    "N": "桂",
    "S": "銀",
    "G": "金",
    "B": "角",
    "R": "飛",
    "K": "玉",
    "+P": "と",
    "+L": "成香",
    "+N": "成桂",
    "+S": "成銀",
    "+B": "馬",
    "+R": "龍",
}


JA_TO_BASE = {
    "歩": "P",
    "香": "L",
    "桂": "N",
    "銀": "S",
    "金": "G",
    "角": "B",
    "飛": "R",
    "玉": "K",
    "王": "K",
    "と": "P",
    "成香": "L",
    "成桂": "N",
    "成銀": "S",
    "馬": "B",
    "龍": "R",
    "竜": "R",
}


def _file_rank_from_rc(row: int, col: int) -> tuple[int, int]:
    file_ = 9 - col
    rank = row + 1
    return file_, rank


def _rc_from_file_rank(file_: int, rank: int) -> tuple[int, int]:
    row = rank - 1
    col = 9 - file_
    if not (0 <= row <= 8 and 0 <= col <= 8):
        raise ValueError("square out of range")
    return row, col


def parse_kif_square(text: str) -> tuple[int, int]:
    s = (text or "").strip().replace("　", "")
    if len(s) < 2:
        raise ValueError(f"invalid square: {text}")
    file_ch = s[0]
    file_map = {**{str(i): i for i in range(1, 10)}, **{FILE_ZENKAKU[i]: i for i in range(1, 10)}}
    if file_ch not in file_map:
        raise ValueError(f"invalid file: {text}")
    file_ = file_map[file_ch]
    rank_ch = s[1]
    rank_map = {**{str(i): i for i in range(1, 10)}, **{RANK_KANJI[i]: i for i in range(1, 10)}}
    if rank_ch not in rank_map:
        raise ValueError(f"invalid rank: {text}")
    rank = rank_map[rank_ch]
    return _rc_from_file_rank(file_, rank)


def format_kif_square(row: int, col: int) -> str:
    file_, rank = _file_rank_from_rc(row, col)
    return f"{FILE_ZENKAKU[file_]}{RANK_KANJI[rank]}"


def format_from_paren(row: int, col: int) -> str:
    file_, rank = _file_rank_from_rc(row, col)
    return f"({file_}{rank})"


def side_mark(side: str) -> str:
    return "▲" if side == "b" else "△"


def _piece_token_from_board(board, row: int, col: int) -> str | None:
    try:
        return board[row][col]
    except Exception:
        return None


def _normalize_piece_token(token: str) -> str:
    # board tokens are like 'P', 'p', '+P', '+p'
    if not token:
        return token
    if token.startswith("+"):
        return "+" + token[-1].upper()
    return token[-1].upper()


def ja_piece_from_token(token: str) -> str:
    norm = _normalize_piece_token(token)
    return PIECE_JA.get(norm, norm)


def usi_to_kif2_label(parent_sfen: str, move_usi: str, *, prev_to_rc: tuple[int, int] | None = None) -> str:
    st = parse_sfen(parent_sfen)
    side = st["side"]
    board = st["board"]
    mv: ParsedUsiMove = parse_usi_move(move_usi)

    to_sq = format_kif_square(mv.to_row, mv.to_col)
    if prev_to_rc and prev_to_rc == (mv.to_row, mv.to_col):
        to_sq = "同　"

    if mv.is_drop:
        piece = PIECE_JA.get(mv.drop_piece or "", mv.drop_piece or "?")
        return f"{side_mark(side)}{to_sq}{piece}打"

    assert mv.from_row is not None and mv.from_col is not None
    token = _piece_token_from_board(board, mv.from_row, mv.from_col)
    piece = ja_piece_from_token(token or "?")
    suffix = "成" if mv.promote else ""
    return f"{side_mark(side)}{to_sq}{piece}{suffix}"


def usi_to_kif_move_text(parent_sfen: str, move_usi: str, *, prev_to_rc: tuple[int, int] | None = None) -> str:
    """KIF move body (no move number). Example: '７六歩(77)' / '同　歩(77)' / '７六歩打'."""
    st = parse_sfen(parent_sfen)
    board = st["board"]
    mv: ParsedUsiMove = parse_usi_move(move_usi)

    to_sq = format_kif_square(mv.to_row, mv.to_col)
    if prev_to_rc and prev_to_rc == (mv.to_row, mv.to_col):
        to_sq = "同　"

    if mv.is_drop:
        piece = PIECE_JA.get(mv.drop_piece or "", mv.drop_piece or "?")
        return f"{to_sq}{piece}打"

    assert mv.from_row is not None and mv.from_col is not None
    token = _piece_token_from_board(board, mv.from_row, mv.from_col)
    piece = ja_piece_from_token(token or "?")
    suffix = "成" if mv.promote else ""
    return f"{to_sq}{piece}{suffix}{format_from_paren(mv.from_row, mv.from_col)}"


@dataclass
class ParsedKifLikeMove:
    to_row: int
    to_col: int
    is_drop: bool
    drop_piece: str | None
    from_row: int | None
    from_col: int | None
    promote: bool

    def to_usi(self) -> str:
        to_sq = rc_to_square(self.to_row, self.to_col)
        if self.is_drop:
            if not self.drop_piece:
                raise ValueError("drop piece missing")
            return f"{self.drop_piece}*{to_sq}"
        if self.from_row is None or self.from_col is None:
            raise ValueError("from square missing")
        from_sq = rc_to_square(self.from_row, self.from_col)
        return f"{from_sq}{to_sq}{'+' if self.promote else ''}"


_PAREN_RE = re.compile(r"\((\d)(\d)\)")


def parse_kif_move_text(move_text: str, *, prev_to_rc: tuple[int, int] | None = None) -> tuple[ParsedKifLikeMove, tuple[int, int] | None]:
    """Parse a KIF move body like '７六歩(77)' or '同　歩(77)' or '７六歩打'."""
    s = (move_text or "").strip()
    # Strip trailing time info like: '( 0:00/00:00:00)'
    s = re.sub(r"\(\s*\d+:\d+\s*/\s*\d+:\d+:\d+\s*\)\s*$", "", s)
    s = s.replace("　", " ")
    if not s:
        raise ValueError("empty move")
    if any(term in s for term in ("投了", "中断", "持将棋", "千日手", "詰み")):
        raise ValueError("game end")

    # destination
    to_row: int
    to_col: int
    rest = s
    if rest.startswith("同"):
        if not prev_to_rc:
            raise ValueError("'同' used but no previous destination")
        to_row, to_col = prev_to_rc
        # consume '同' and optional spaces
        rest = rest[1:]
        rest = rest.lstrip()
    else:
        to_row, to_col = parse_kif_square(rest[:2])
        rest = rest[2:]

    rest = rest.strip()

    # from (optional)
    m = _PAREN_RE.search(rest)
    from_row = from_col = None
    if m:
        file_ = int(m.group(1))
        rank = int(m.group(2))
        from_row, from_col = _rc_from_file_rank(file_, rank)
        rest_wo_paren = (rest[: m.start()] + rest[m.end() :]).strip()
    else:
        rest_wo_paren = rest

    is_drop = "打" in rest_wo_paren
    promote = ("成" in rest_wo_paren) and ("不成" not in rest_wo_paren)

    drop_piece = None
    if is_drop:
        # Identify piece by the first matching japanese name.
        candidates = sorted(JA_TO_BASE.keys(), key=len, reverse=True)
        found = None
        for name in candidates:
            if rest_wo_paren.startswith(name):
                found = name
                break
        if not found:
            raise ValueError(f"cannot detect drop piece: {move_text}")
        drop_piece = JA_TO_BASE[found]
        if drop_piece == "K":
            raise ValueError("king drop is invalid")
        return (
            ParsedKifLikeMove(
                to_row=to_row,
                to_col=to_col,
                is_drop=True,
                drop_piece=drop_piece,
                from_row=None,
                from_col=None,
                promote=False,
            ),
            (to_row, to_col),
        )

    return (
        ParsedKifLikeMove(
            to_row=to_row,
            to_col=to_col,
            is_drop=False,
            drop_piece=None,
            from_row=from_row,
            from_col=from_col,
            promote=promote,
        ),
        (to_row, to_col),
    )


def parse_ki2_move_token(token: str, *, prev_to_rc: tuple[int, int] | None = None) -> tuple[dict, tuple[int, int] | None]:
    """Parse a single KI2 token like '▲７六歩' or '△同　銀右'.

    Returns a dict with keys: side_mark, to_row, to_col, piece_name, is_drop, promote, disambig(list[str]).
    """
    t = (token or "").strip()
    if not t:
        raise ValueError("empty token")
    if t[0] not in {"▲", "△"}:
        raise ValueError("missing side mark")
    mark = t[0]
    rest = t[1:].replace("　", " ").strip()

    if any(term in rest for term in ("投了", "中断", "持将棋", "千日手", "詰み")):
        raise ValueError("game end")

    if rest.startswith("同"):
        if not prev_to_rc:
            raise ValueError("'同' used but no previous destination")
        to_row, to_col = prev_to_rc
        rest = rest[1:].lstrip()
    else:
        to_row, to_col = parse_kif_square(rest[:2])
        rest = rest[2:].strip()

    # piece name (longest match)
    piece_candidates = [
        "成銀",
        "成桂",
        "成香",
        "龍",
        "竜",
        "馬",
        "と",
        "玉",
        "王",
        "飛",
        "角",
        "金",
        "銀",
        "桂",
        "香",
        "歩",
    ]

    piece_name = None
    for name in piece_candidates:
        if rest.startswith(name):
            piece_name = name
            rest = rest[len(name) :]
            break
    if not piece_name:
        raise ValueError(f"cannot detect piece name: {token}")

    is_drop = "打" in rest
    promote = ("成" in rest) and ("不成" not in rest)

    disambig = []
    for ch in ("右", "左", "直", "上", "引", "寄"):
        if ch in rest:
            disambig.append(ch)

    return (
        {
            "side_mark": mark,
            "to_row": to_row,
            "to_col": to_col,
            "piece_name": piece_name,
            "is_drop": is_drop,
            "promote": promote,
            "disambig": disambig,
        },
        (to_row, to_col),
    )
