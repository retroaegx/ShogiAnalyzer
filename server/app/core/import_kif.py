"""KIF reader (柿木将棋 format).

Supports: header lines (key：value), 手合割 incl. handicaps, board diagrams (BOD), comments
("*" lines -> the comment of the move above, or of the start position before move 1),
game end lines (投了 etc. -> meta["_result"]), times / variation markers on move lines and
nested variations ("変化：N手").
"""

from __future__ import annotations

import re

from .gametree import GameTree
from .kifu_common import end_term_in, parse_headers, start_position
from .notation import parse_kif_move_text
from .sfen_ops import parse_usi_move

_MOVE_LINE_RE = re.compile(r"^\s*(\d+)\s+(.*)$")
_HENKA_RE = re.compile(r"^\s*変化\s*[：:]\s*(\d+)手")
_TIME_RE = re.compile(r"\(\s*\d+:\d+\s*/\s*(\d+:)?\d+:\d+\s*\)")


def detect_kif(text: str) -> bool:
    s = (text or "").strip()
    return "手数----指手" in s or "手合割" in s


def _dest(move_usi: str | None):
    if not move_usi:
        return None
    try:
        mvu = parse_usi_move(move_usi)
        return (mvu.to_row, mvu.to_col)
    except Exception:
        return None


def import_kif_game(text: str, title: str | None = None) -> GameTree:
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    meta = parse_headers(lines)
    initial_sfen = start_position(meta, lines)

    game_title = (title or meta.get("棋戦") or meta.get("表題") or meta.get("タイトル") or "Imported KIF").strip()
    game = GameTree.new(title=game_title, initial_sfen=initial_sfen)
    game.meta = dict(meta)

    # segments: the main line, then each 「変化」 in file order
    # move = [body, [comment lines]]
    segments: list[dict] = [{"start": 1, "moves": [], "end": None, "lead": []}]
    in_moves = False
    for line in lines:
        s = line.strip()
        if not in_moves:
            if "手数----指手" in s:
                in_moves = True
            elif s.startswith("*") and not segments[0]["moves"]:
                segments[0]["lead"].append(s[1:])  # comment of the start position
            continue
        if not s or s.startswith(("#", "&")) or s.startswith("まで"):
            continue
        seg = segments[-1]
        if s.startswith("*"):
            if seg["moves"]:
                seg["moves"][-1][1].append(s[1:])
            else:
                seg["lead"].append(s[1:])
            continue
        hm = _HENKA_RE.match(line)
        if hm:
            segments.append({"start": int(hm.group(1)), "moves": [], "end": None, "lead": []})
            continue
        m = _MOVE_LINE_RE.match(line)
        if not m or seg["end"]:
            continue
        body = _TIME_RE.sub("", m.group(2) or "").strip().rstrip("+").strip()
        if not body:
            continue
        term = end_term_in(body)
        if term:
            seg["end"] = term
            continue
        seg["moves"].append([body, []])

    def play(base_node_id: str, moves: list, start_ply: int, line: dict[int, str]) -> None:
        cur = base_node_id
        prev_to = _dest(game.get_node(base_node_id).move_usi)
        for i, (body, comments) in enumerate(moves):
            parsed, prev_to = parse_kif_move_text(body, prev_to_rc=prev_to)
            mv_usi = parsed.to_usi()
            parse_usi_move(mv_usi)
            cur = game.play_move(cur, mv_usi).node_id
            line[start_ply + i] = cur
            if comments:
                game.set_comment(cur, "\n".join(comments))

    main = segments[0]
    if main["lead"]:
        game.set_comment(game.root_node_id, "\n".join(main["lead"]))
    main_line = {0: game.root_node_id}
    play(game.root_node_id, main["moves"], 1, main_line)
    if main["end"]:
        game.meta["_result"] = {"term": main["end"], "ply": len(main["moves"])}

    # 「変化：N手」 is another move N for the line written most recently that has a move N
    # (variations can branch off earlier variations, not only the main line)
    lines_seen = [main_line]
    for seg in segments[1:]:
        start_n = seg["start"]
        if start_n < 1:
            continue
        parent = next((ln for ln in reversed(lines_seen) if start_n in ln), main_line)
        base_ply = min(start_n - 1, max(parent))
        line = {p: nid for p, nid in parent.items() if p <= base_ply}
        lines_seen.append(line)
        moves = seg["moves"]
        if seg["lead"] and moves:
            moves[0][1][:0] = seg["lead"]
        play(parent[base_ply], moves, base_ply + 1, line)

    return game
