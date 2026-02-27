from __future__ import annotations

import re

from .gametree import GameTree
from .notation import parse_kif_move_text
from .sfen_ops import DEFAULT_START_SFEN, parse_usi_move


_MOVE_LINE_RE = re.compile(r"^\s*(\d+)\s+(.*)$")
_HENKA_RE = re.compile(r"^\s*変化\s*：\s*(\d+)手")


def detect_kif(text: str) -> bool:
    s = (text or "").strip()
    return "手数----指手" in s or "手合割" in s


def _parse_header_meta(lines: list[str]) -> dict:
    meta: dict[str, str] = {}
    for line in lines:
        if "手数----指手" in line:
            break
        if "：" in line:
            k, v = line.split("：", 1)
            k = k.strip()
            v = v.strip()
            if k and v:
                meta[k] = v
    return meta


def _initial_sfen_from_meta(meta: dict) -> str:
    # Minimal: only supports standard start (平手)
    handicap = (meta.get("手合割") or "").strip()
    if not handicap or handicap in {"平手", "平手　"}:
        return DEFAULT_START_SFEN
    raise ValueError(f"unsupported handicap: {handicap}")


def import_kif_game(text: str, title: str | None = None) -> GameTree:
    raw_lines = (text or "").replace("\r", "\n").split("\n")
    lines = [ln.rstrip("\n") for ln in raw_lines]
    meta = _parse_header_meta(lines)
    initial_sfen = _initial_sfen_from_meta(meta)

    game_title = (title or meta.get("棋戦") or meta.get("表題") or meta.get("タイトル") or "Imported KIF").strip()
    game = GameTree.new(title=game_title, initial_sfen=initial_sfen)
    game.meta = meta

    in_moves = False
    main_moves: list[str] = []
    variations: list[tuple[int, list[str]]] = []
    current_var: tuple[int, list[str]] | None = None

    for line in lines:
        if not in_moves:
            if "手数----指手" in line:
                in_moves = True
            continue

        if line.strip().startswith("*"):
            # KIF comments: ignore for now (could be mapped to node comments)
            continue

        hm = _HENKA_RE.match(line)
        if hm:
            start_n = int(hm.group(1))
            current_var = (start_n, [])
            variations.append(current_var)
            continue

        m = _MOVE_LINE_RE.match(line)
        if not m:
            continue

        body = (m.group(2) or "").strip()
        if not body:
            continue

        # Stop on resignation etc.
        if any(term in body for term in ("投了", "中断", "持将棋", "千日手", "詰み")):
            break

        if current_var is None:
            main_moves.append(body)
        else:
            current_var[1].append(body)

    # Build mainline
    cur = game.root_node_id
    node_ids = [cur]
    prev_to_rc = None
    for mv_text in main_moves:
        parsed, prev_to_rc = parse_kif_move_text(mv_text, prev_to_rc=prev_to_rc)
        mv_usi = parsed.to_usi()
        # Validate move format early.
        parse_usi_move(mv_usi)
        cur = game.play_move(cur, mv_usi).node_id
        node_ids.append(cur)

    # Build variations branching from mainline.
    for start_n, moves in variations:
        if start_n < 1:
            continue
        base_index = min(start_n - 1, len(node_ids) - 1)
        base_node_id = node_ids[base_index]
        base_node = game.get_node(base_node_id)
        prev_to = None
        if base_node.move_usi:
            try:
                mvu = parse_usi_move(base_node.move_usi)
                prev_to = (mvu.to_row, mvu.to_col)
            except Exception:
                prev_to = None
        cur = base_node_id
        prev_to_rc = prev_to
        for mv_text in moves:
            try:
                parsed, prev_to_rc = parse_kif_move_text(mv_text, prev_to_rc=prev_to_rc)
            except ValueError as exc:
                if str(exc) == "game end":
                    break
                raise
            mv_usi = parsed.to_usi()
            parse_usi_move(mv_usi)
            cur = game.play_move(cur, mv_usi).node_id

    return game
