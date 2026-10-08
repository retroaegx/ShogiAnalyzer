"""Shared parts of the KIF / KI2 formats (Kakinoki 柿木将棋 notation).

- handicaps (手合割) <-> start SFEN, board diagrams (BOD 局面図) <-> SFEN
- header lines (key：value), comments (lines starting with "*"), game end (投了 / まで…)
- moves that may promote (for 「不成」)

The game result is kept in GameTree.meta under "_result" ({"term": "投了", "ply": 61}); keys
starting with "_" are internal and never written as KIF headers.
"""

from __future__ import annotations

import re
from datetime import datetime

from .sfen_ops import DEFAULT_START_SFEN, HAND_ORDER, PROMOTABLE, build_sfen, normalize_sfen, parse_sfen

_TAIL = "/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL w - 1"
HANDICAP_SFEN: dict[str, str] = {
    "平手": DEFAULT_START_SFEN,
    "香落ち": "lnsgkgsn1/1r5b1" + _TAIL,
    "右香落ち": "1nsgkgsnl/1r5b1" + _TAIL,
    "角落ち": "lnsgkgsnl/1r7" + _TAIL,
    "飛車落ち": "lnsgkgsnl/7b1" + _TAIL,
    "飛香落ち": "lnsgkgsn1/7b1" + _TAIL,
    "二枚落ち": "lnsgkgsnl/9" + _TAIL,
    "三枚落ち": "lnsgkgsn1/9" + _TAIL,
    "四枚落ち": "1nsgkgsn1/9" + _TAIL,
    "五枚落ち": "2sgkgsn1/9" + _TAIL,
    "左五枚落ち": "1nsgkgs2/9" + _TAIL,
    "六枚落ち": "2sgkgs2/9" + _TAIL,
    "左七枚落ち": "2sgkg3/9" + _TAIL,
    "右七枚落ち": "3gkgs2/9" + _TAIL,
    "八枚落ち": "3gkg3/9" + _TAIL,
    "十枚落ち": "4k4/9" + _TAIL,
}
HANDICAP_ALIASES = {"飛落ち": "飛車落ち", "飛車香落ち": "飛香落ち", "２枚落ち": "二枚落ち", "４枚落ち": "四枚落ち", "６枚落ち": "六枚落ち"}

END_TERMS = ("投了", "中断", "千日手", "持将棋", "詰み", "切れ負け", "反則勝ち", "反則負け", "入玉勝ち", "不詰", "不戦勝", "不戦敗")

KANJI_NUM = {1: "", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七", 8: "八", 9: "九", 10: "十",
             11: "十一", 12: "十二", 13: "十三", 14: "十四", 15: "十五", 16: "十六", 17: "十七", 18: "十八"}
_KANJI_DIGIT = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}

# BOD piece characters (promoted pieces are single characters)
_BOD_TO_TOKEN = {"歩": "P", "香": "L", "桂": "N", "銀": "S", "金": "G", "角": "B", "飛": "R", "玉": "K", "王": "K",
                 "と": "+P", "杏": "+L", "圭": "+N", "全": "+S", "馬": "+B", "龍": "+R", "竜": "+R"}
_TOKEN_TO_BOD = {"P": "歩", "L": "香", "N": "桂", "S": "銀", "G": "金", "B": "角", "R": "飛", "K": "玉",
                 "+P": "と", "+L": "杏", "+N": "圭", "+S": "全", "+B": "馬", "+R": "龍"}
_HAND_JA = {"R": "飛", "B": "角", "G": "金", "S": "銀", "N": "桂", "L": "香", "P": "歩"}

HEADER_ORDER = ("開始日時", "終了日時", "棋戦", "表題", "戦型", "場所", "持ち時間", "手合割", "先手", "下手", "後手", "上手")
_BOD_LINE_RE = re.compile(r"^\s*\|(.*)\|")


def handicap_sfen(name: str | None) -> str | None:
    n = (name or "").strip().replace("　", "")
    n = HANDICAP_ALIASES.get(n, n)
    return HANDICAP_SFEN.get(n)


def handicap_name_of(sfen: str) -> str | None:
    s = normalize_sfen(sfen)
    for name, hs in HANDICAP_SFEN.items():
        if normalize_sfen(hs) == s:
            return name
    return None


def is_header_line(line: str) -> bool:
    return "：" in line and not line.lstrip().startswith(("*", "#", "&")) and not _BOD_LINE_RE.match(line)


def parse_headers(lines: list[str]) -> dict[str, str]:
    """key：value lines (until the move list / first move); BOD hand lines are not headers."""
    meta: dict[str, str] = {}
    for line in lines:
        s = line.strip()
        if "手数----指手" in s or s.startswith(("▲", "△")):
            break
        if not is_header_line(line):
            continue
        k, v = s.split("：", 1)
        k, v = k.strip(), v.strip()
        if not k or k.endswith("の持駒") or k == "手番":
            continue
        meta[k] = v
    return meta


def _kanji_count(text: str) -> int:
    t = text.strip()
    if not t:
        return 1
    if t.startswith("十"):
        return 10 + (_KANJI_DIGIT.get(t[1:], 0) if len(t) > 1 else 0)
    return _KANJI_DIGIT.get(t, 1)


def _parse_hand(text: str) -> dict[str, int]:
    out = {k: 0 for k in HAND_ORDER}
    t = (text or "").strip()
    if not t or t == "なし":
        return out
    for item in re.split(r"[　\s]+", t):
        if not item:
            continue
        base = _BOD_TO_TOKEN.get(item[0])
        if base and base in out:
            out[base] += _kanji_count(item[1:])
    return out


def parse_bod(lines: list[str]) -> str | None:
    """SFEN of a board diagram (局面図) in the header, or None when there is none."""
    rows: list[list[str | None]] = []
    hands = {"b": {k: 0 for k in HAND_ORDER}, "w": {k: 0 for k in HAND_ORDER}}
    side = "b"
    for line in lines:
        s = line.strip()
        if "手数----指手" in s:
            break
        m = _BOD_LINE_RE.match(line)
        if m and len(rows) < 9:
            body = m.group(1)
            row: list[str | None] = []
            i = 0
            while i < len(body) and len(row) < 9:
                owner_gote = body[i] == "v"
                ch = body[i + 1] if i + 1 < len(body) else " "
                tok = _BOD_TO_TOKEN.get(ch)
                if tok:
                    row.append(tok.lower() if owner_gote else tok)
                else:
                    row.append(None)  # " ・"
                i += 2
            while len(row) < 9:
                row.append(None)
            rows.append(row)
            continue
        if re.match(r"^(後手|上手)の持駒[：:]", s):
            hands["w"] = _parse_hand(re.split(r"[：:]", s, 1)[1])
        elif re.match(r"^(先手|下手)の持駒[：:]", s):
            hands["b"] = _parse_hand(re.split(r"[：:]", s, 1)[1])
        elif s.startswith(("後手番", "上手番")) or re.match(r"^手番[：:]\s*(後手|上手)", s):
            side = "w"
        elif s.startswith(("先手番", "下手番")) or re.match(r"^手番[：:]\s*(先手|下手)", s):
            side = "b"
    if len(rows) != 9:
        return None
    return build_sfen({"board": rows, "side": side, "hands": hands, "ply": 1})


def _format_hand(hand: dict[str, int]) -> str:
    items = [f"{_HAND_JA[p]}{KANJI_NUM[n]}" for p in HAND_ORDER if (n := int(hand.get(p, 0))) > 0]
    return "　".join(items) + "　" if items else "なし"


def format_bod(sfen: str, handicap_names: bool = False) -> list[str]:
    st = parse_sfen(sfen)
    top, bottom = ("上手", "下手") if handicap_names else ("後手", "先手")
    out = [f"{top}の持駒：{_format_hand(st['hands']['w'])}", "  ９ ８ ７ ６ ５ ４ ３ ２ １", "+---------------------------+"]
    ranks = "一二三四五六七八九"
    for r, row in enumerate(st["board"]):
        cells = []
        for tok in row:
            if not tok:
                cells.append(" ・")
                continue
            norm = ("+" + tok[-1].upper()) if tok.startswith("+") else tok.upper()
            cells.append(("v" if tok[-1].islower() else " ") + _TOKEN_TO_BOD[norm])
        out.append("|" + "".join(cells) + "|" + ranks[r])
    out.append("+---------------------------+")
    out.append(f"{bottom}の持駒：{_format_hand(st['hands']['b'])}")
    if st["side"] == "w":
        out.append(f"{top}番")
    return out


def start_position(meta: dict[str, str], lines: list[str]) -> str:
    """Start SFEN from a board diagram, else from 手合割 (unknown handicap -> error)."""
    bod = parse_bod(lines)
    if bod:
        return bod
    name = (meta.get("手合割") or "平手").strip()
    sfen = handicap_sfen(name)
    if sfen is None:
        raise ValueError(f"unsupported handicap: {name}")
    return sfen


def header_lines(meta: dict, title: str | None, created_at: str | None, initial_sfen: str) -> list[str]:
    """Header block: known keys in the usual order, then other imported keys; 手合割 or a BOD."""
    meta = {k: v for k, v in (meta or {}).items() if not str(k).startswith("_") and v not in (None, "")}
    if "開始日時" not in meta and created_at:
        try:
            meta["開始日時"] = datetime.fromisoformat(created_at.replace("Z", "+00:00")).astimezone().strftime("%Y/%m/%d %H:%M:%S")
        except ValueError:
            pass
    if title and "棋戦" not in meta and "表題" not in meta:
        meta["表題"] = title
    hc = handicap_name_of(initial_sfen)
    handicap_game = hc is not None and hc != "平手"
    if hc:
        meta["手合割"] = hc
    else:
        meta.pop("手合割", None)
    if handicap_game:  # players of a handicap game are 下手 (sente) / 上手 (gote)
        if "先手" in meta and "下手" not in meta:
            meta["下手"] = meta.pop("先手")
        if "後手" in meta and "上手" not in meta:
            meta["上手"] = meta.pop("後手")
    out: list[str] = []
    keys = [k for k in HEADER_ORDER if k in meta] + [k for k in meta if k not in HEADER_ORDER]
    for k in keys:
        if k == "手合割" and not hc:
            continue
        out.append(f"{k}：{meta[k]}")
    if not hc:
        out.extend(format_bod(initial_sfen))
    return out


def comment_lines(comment: str | None) -> list[str]:
    return [f"*{ln}" for ln in (comment or "").splitlines()] if (comment or "").strip() else []


def end_term_in(text: str) -> str | None:
    for term in END_TERMS:
        if term in text:
            return term
    return None


def player_names(initial_sfen: str) -> tuple[str, str]:
    """(name of sente, name of gote) for result lines: 先手/後手, or 下手/上手 in handicap games."""
    hc = handicap_name_of(initial_sfen)
    return ("下手", "上手") if hc and hc != "平手" else ("先手", "後手")


def result_line(term: str, ply: int, final_sfen: str, initial_sfen: str) -> str:
    """「まで61手で先手の勝ち」 etc. ply = number of moves played."""
    sente, gote = player_names(initial_sfen)
    to_move = parse_sfen(final_sfen)["side"]
    mover = gote if to_move == "b" else sente  # made the last move
    waiting = sente if to_move == "b" else gote
    if term in ("投了", "詰み", "切れ負け", "反則負け", "不戦敗"):
        return f"まで{ply}手で{mover}の勝ち"
    if term in ("入玉勝ち", "反則勝ち", "不戦勝"):
        return f"まで{ply}手で{waiting}の{term}"
    return f"まで{ply}手で{term}"


def result_from_text(text: str) -> str | None:
    """Term from a KI2 「まで…」 line."""
    if "の勝ち" in text:
        return "投了"
    return end_term_in(text)


def can_promote(token: str, side: str, from_row: int, to_row: int) -> bool:
    """Unpromoted piece entering, leaving or moving inside the promotion zone."""
    if not token or token.startswith("+") or token[-1].upper() not in PROMOTABLE:
        return False
    zone = range(0, 3) if side == "b" else range(6, 9)
    return from_row in zone or to_row in zone
