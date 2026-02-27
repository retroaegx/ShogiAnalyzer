from __future__ import annotations

import re

from .gametree import GameTree
from .movegen import candidates_for_piece, filter_candidates_by_disambig
from .notation import JA_TO_BASE, parse_ki2_move_token
from .sfen_ops import DEFAULT_START_SFEN, parse_sfen, parse_usi_move


_HENKA_RE = re.compile(r"^\s*変化\s*：\s*(\d+)手")


def detect_kif2(text: str) -> bool:
    s = (text or "").strip()
    return "▲" in s or "△" in s


def _piece_norm_from_ja(piece_name: str) -> str:
    # Map to token-like normalization: 'P', '+P', ...
    if piece_name in {"と"}:
        return "+P"
    if piece_name in {"成香"}:
        return "+L"
    if piece_name in {"成桂"}:
        return "+N"
    if piece_name in {"成銀"}:
        return "+S"
    if piece_name in {"馬"}:
        return "+B"
    if piece_name in {"龍", "竜"}:
        return "+R"
    # base piece
    base = JA_TO_BASE.get(piece_name)
    if not base:
        raise ValueError(f"unknown piece name: {piece_name}")
    return base


def _side_from_mark(mark: str) -> str:
    return "b" if mark == "▲" else "w"


def _tokenize_ki2(text: str) -> list[str]:
    # Robust tokenization: each token starts with ▲/△ and continues until the next ▲/△.
    s = (text or "").replace("\r", "\n")
    tokens: list[str] = []
    for ln in s.split("\n"):
        if not ln.strip():
            continue
        if ln.strip().startswith("*"):
            continue
        for seg in re.findall(r"[▲△][^▲△]+", ln):
            t = seg.strip()
            if t:
                tokens.append(t)
    return tokens


def import_kif2_game(text: str, title: str | None = None) -> GameTree:
    raw_lines = (text or "").replace("\r", "\n").split("\n")
    # Variations are rarely used in KI2, but support the same '変化：N手' marker.
    in_var = False
    current_var_start = 0
    main_tokens: list[str] = []
    variations: list[tuple[int, list[str]]] = []
    cur_var_tokens: list[str] | None = None

    for ln in raw_lines:
        hm = _HENKA_RE.match(ln)
        if hm:
            in_var = True
            current_var_start = int(hm.group(1))
            cur_var_tokens = []
            variations.append((current_var_start, cur_var_tokens))
            continue
        toks = _tokenize_ki2(ln)
        if not toks:
            continue
        if in_var and cur_var_tokens is not None:
            cur_var_tokens.extend(toks)
        else:
            main_tokens.extend(toks)

    game = GameTree.new(title=(title or "Imported KI2").strip(), initial_sfen=DEFAULT_START_SFEN)

    def apply_tokens(base_node_id: str, tokens: list[str], *, prev_to_rc=None) -> str:
        cur = base_node_id
        cur_sfen = game.get_node(cur).position_sfen
        prev_to = prev_to_rc
        for tok in tokens:
            parsed, prev_to = parse_ki2_move_token(tok, prev_to_rc=prev_to)
            side = _side_from_mark(parsed["side_mark"])
            st = parse_sfen(cur_sfen)
            if st["side"] != side:
                # If the record side mark doesn't match SFEN, accept SFEN.
                side = st["side"]

            to_row = parsed["to_row"]
            to_col = parsed["to_col"]
            piece_norm = _piece_norm_from_ja(parsed["piece_name"])

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
        return cur

    # mainline
    end_node_id = apply_tokens(game.root_node_id, main_tokens)
    # remember mainline path
    main_path_nodes = [n.node_id for n in game.path_to_node(end_node_id)]

    # variations
    for start_n, toks in variations:
        if start_n < 1:
            continue
        base_idx = min(start_n - 1, len(main_path_nodes) - 1)
        base_node_id = main_path_nodes[base_idx]
        # previous destination for '同'
        prev_to = None
        node = game.get_node(base_node_id)
        if node.move_usi:
            try:
                mvu = parse_usi_move(node.move_usi)
                prev_to = (mvu.to_row, mvu.to_col)
            except Exception:
                prev_to = None
        apply_tokens(base_node_id, toks, prev_to_rc=prev_to)

    return game
