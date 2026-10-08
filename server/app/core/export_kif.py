"""KIF writer (柿木将棋 format, UTF-8 with the version 2.0 encoding line, i.e. a .kifu file).

Header (開始日時, 棋戦/表題, 手合割 or a board diagram, players), the move list with the time
columns, comments ("*" lines), the game end (「投了」 + 「まで○手で…」) and nested
variations in Kifu-for-Windows order.
"""

from __future__ import annotations

from .gametree import GameTree
from .kifu_common import comment_lines, header_lines, result_line
from .notation import usi_to_kif_move_text
from .sfen_ops import parse_usi_move

_TIME = "( 0:00/00:00:00)"


def _mainline_nodes(game: GameTree) -> list[str]:
    node_ids = [game.root_node_id]
    cur = game.root_node_id
    while True:
        children = game.children_of(cur)
        if not children:
            break
        nxt = children[0]
        node_ids.append(nxt.node_id)
        cur = nxt.node_id
    return node_ids


def _dest(move_usi: str | None):
    """Destination square of a move (for 「同」), or None."""
    if not move_usi:
        return None
    try:
        mvu = parse_usi_move(move_usi)
        return (mvu.to_row, mvu.to_col)
    except Exception:
        return None


def _line_from(game: GameTree, first_id: str, first_ply: int) -> list[tuple[int, str]]:
    """(ply, node_id) from first_id following the first child each time."""
    line = [(first_ply, first_id)]
    cur = first_id
    while True:
        kids = game.children_of(cur)
        if not kids:
            return line
        cur = kids[0].node_id
        line.append((line[-1][0] + 1, cur))


def _move_line(ply: int, body: str, has_variation: bool = False) -> str:
    # moves are padded so the time column lines up (full-width characters count as 2)
    width = sum(2 if ord(ch) > 0xFF else 1 for ch in body)
    return f"{ply:>4} {body}{' ' * max(1, 14 - width)}{_TIME}{'+' if has_variation else ''}"


def export_game_to_kif(game: GameTree) -> str:
    lines: list[str] = ["#KIF version=2.0 encoding=UTF-8"]
    lines += header_lines(game.meta or {}, game.title, game.created_at, game.initial_sfen)
    lines.append("手数----指手---------消費時間--")
    root = game.get_node(game.root_node_id)
    lines += comment_lines(root.comment)

    def write_moves(line: list[tuple[int, str]]) -> None:
        for ply, nid in line:
            node = game.get_node(nid)
            parent = game.get_node(node.parent_id)
            body = usi_to_kif_move_text(parent.position_sfen, node.move_usi or "", prev_to_rc=_dest(parent.move_usi))
            has_var = len(game.children_of(node.parent_id)) > 1
            lines.append(_move_line(ply, body, has_var))
            lines.extend(comment_lines(node.comment))

    def write_variations(line: list[tuple[int, str]]) -> None:
        # Kifu-for-Windows order: branch points from the end of the line backwards, each
        # variation followed right away by its own variations. A reader then finds the parent
        # of "変化：N手" as the most recently written line that has a move N (see import_kif.py).
        for ply, nid in reversed(line):
            for alt in game.children_of(nid)[1:]:
                sub = _line_from(game, alt.node_id, ply + 1)
                lines.append("")
                lines.append(f"変化：{ply + 1}手")
                write_moves(sub)
                write_variations(sub)

    main = _mainline_nodes(game)
    main_line = [(i, nid) for i, nid in enumerate(main)]
    write_moves(main_line[1:])

    # game end, when the stored result still matches the main line
    result = (game.meta or {}).get("_result") or {}
    played = len(main) - 1
    if result.get("term") and int(result.get("ply", -1)) == played:
        lines.append(_move_line(played + 1, result["term"]))
        lines.append(result_line(result["term"], played, game.get_node(main[-1]).position_sfen, game.initial_sfen))

    write_variations(main_line)  # includes the start position (alternatives to move 1)
    return "\n".join(lines).rstrip() + "\n"
