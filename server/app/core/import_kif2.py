"""KI2 reader (柿木将棋 format).

Supports: header lines, 手合割 incl. handicaps, board diagrams (BOD), moves with 右・左・上・
引・寄・直 / 成・不成 / 打 (「打」 may be omitted when no board piece can go there), comments
("*" lines -> the move written before them, or the start position), the 「まで…」 result line
and nested variations ("変化：N手").
"""

from __future__ import annotations

import re

from .gametree import GameTree
from .kifu_common import is_header_line, parse_headers, result_from_text, start_position
from .movegen import candidates_for_piece, filter_candidates_by_disambig
from .notation import JA_TO_BASE, parse_ki2_move_token
from .sfen_ops import parse_sfen, parse_usi_move

_HENKA_RE = re.compile(r"^\s*変化\s*[：:]\s*(\d+)手")


def detect_kif2(text: str) -> bool:
    s = (text or "").strip()
    return "▲" in s or "△" in s


def _piece_norm_from_ja(piece_name: str) -> str:
    # Map to token-like normalization: 'P', '+P', ...
    promoted = {"と": "+P", "成香": "+L", "成桂": "+N", "成銀": "+S", "馬": "+B", "龍": "+R", "竜": "+R"}
    if piece_name in promoted:
        return promoted[piece_name]
    base = JA_TO_BASE.get(piece_name)
    if not base:
        raise ValueError(f"unknown piece name: {piece_name}")
    return base


def _tokenize_ki2(line: str) -> list[str]:
    # each token starts with ▲/△ and continues until the next ▲/△
    return [t for seg in re.findall(r"[▲△][^▲△]+", line or "") if (t := seg.strip())]


def _dest(move_usi: str | None):
    if not move_usi:
        return None
    try:
        mvu = parse_usi_move(move_usi)
        return (mvu.to_row, mvu.to_col)
    except Exception:
        return None


def import_kif2_game(text: str, title: str | None = None) -> GameTree:
    raw_lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    meta = parse_headers(raw_lines)
    initial_sfen = start_position(meta, raw_lines)

    # tokens are [move, [comment lines]]; comments ("*") belong to the move written before them
    main_tokens: list[list] = []
    main_lead: list[str] = []
    main_end: str | None = None
    variations: list[tuple[int, list[list]]] = []
    cur_tokens = main_tokens

    for ln in raw_lines:
        s = ln.strip()
        hm = _HENKA_RE.match(ln)
        if hm:
            cur_tokens = []
            variations.append((int(hm.group(1)), cur_tokens))
            continue
        if not s or s.startswith(("#", "&")):
            continue
        if s.startswith("*"):
            if cur_tokens:
                cur_tokens[-1][1].append(s[1:])
            elif cur_tokens is main_tokens:
                main_lead.append(s[1:])
            continue
        if s.startswith("まで"):
            if cur_tokens is main_tokens:
                main_end = result_from_text(s)
            continue
        if is_header_line(ln) and not s.startswith(("▲", "△")):
            continue
        cur_tokens.extend([t, []] for t in _tokenize_ki2(ln))

    game_title = (title or meta.get("棋戦") or meta.get("表題") or "Imported KI2").strip()
    game = GameTree.new(title=game_title, initial_sfen=initial_sfen)
    game.meta = dict(meta)
    if main_lead:
        game.set_comment(game.root_node_id, "\n".join(main_lead))

    def apply_tokens(base_node_id: str, tokens: list[list]) -> str:
        cur = base_node_id
        cur_sfen = game.get_node(cur).position_sfen
        prev_to = _dest(game.get_node(cur).move_usi)
        for tok, comments in tokens:
            try:
                parsed, prev_to = parse_ki2_move_token(tok, prev_to_rc=prev_to)
            except ValueError as exc:
                if str(exc) == "game end":
                    break
                raise
            st = parse_sfen(cur_sfen)
            side = st["side"]  # the position decides; the mark is only a hint
            to_row = parsed["to_row"]
            to_col = parsed["to_col"]
            piece_norm = _piece_norm_from_ja(parsed["piece_name"])

            # KI2 writes 「打」 only when a board piece could also go there: a move with no board
            # candidate but the piece in hand is a drop
            in_hand = st["hands"][side].get(piece_norm, 0) if not piece_norm.startswith("+") else 0
            if not parsed["is_drop"] and in_hand and not candidates_for_piece(st["board"], side, piece_norm, to_row, to_col):
                parsed["is_drop"] = True

            if parsed["is_drop"]:
                drop_base = JA_TO_BASE.get(parsed["piece_name"], None)
                if not drop_base:
                    raise ValueError(f"unknown drop piece: {parsed['piece_name']}")
                mv_usi = f"{drop_base}*{9 - to_col}{chr(ord('a') + to_row)}"
            else:
                cand = candidates_for_piece(st["board"], side, piece_norm, to_row, to_col)
                cand = filter_candidates_by_disambig(side, to_row, to_col, cand, parsed.get("disambig") or [])
                if len(cand) != 1:
                    raise ValueError(
                        f"ambiguous KI2 move '{tok}': candidates={[(c.from_row, c.from_col) for c in cand]}"
                    )
                c0 = cand[0]
                from_sq = f"{9 - c0.from_col}{chr(ord('a') + c0.from_row)}"
                to_sq = f"{9 - to_col}{chr(ord('a') + to_row)}"
                mv_usi = f"{from_sq}{to_sq}{'+' if parsed['promote'] else ''}"

            parse_usi_move(mv_usi)
            cur = game.play_move(cur, mv_usi).node_id
            cur_sfen = game.get_node(cur).position_sfen
            if comments:
                game.set_comment(cur, "\n".join(comments))
        return cur

    # mainline; lines as {ply: node_id}
    end_node_id = apply_tokens(game.root_node_id, main_tokens)
    main_line = {i: n.node_id for i, n in enumerate(game.path_to_node(end_node_id))}
    if main_end:
        game.meta["_result"] = {"term": main_end, "ply": len(main_line) - 1}
    lines_seen = [main_line]

    # variations may branch off earlier variations, not only the main line:
    # "変化：N手" belongs to the most recently written line that has a move N
    for start_n, toks in variations:
        if start_n < 1:
            continue
        parent = next((ln for ln in reversed(lines_seen) if start_n in ln), main_line)
        base_ply = min(start_n - 1, max(parent))
        end_id = apply_tokens(parent[base_ply], toks)
        line = {p: nid for p, nid in parent.items() if p <= base_ply}
        for i, n in enumerate(game.path_to_node(end_id)):
            if i > base_ply:
                line[i] = n.node_id
        lines_seen.append(line)

    return game
