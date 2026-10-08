"""KI2 writer (柿木将棋 format, UTF-8 with the version 2.0 encoding line, i.e. a .ki2u file).

Header like KIF (手合割 or a board diagram), several moves per line (a line ends after a move
that has a comment), comments ("*"), the 「まで…」 result line and nested variations.
"""

from __future__ import annotations

from .gametree import GameTree
from .kifu_common import comment_lines, header_lines, result_line
from .notation import usi_to_kif2_label
from .sfen_ops import parse_usi_move

_PER_LINE = 6


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


def _line_from(game: GameTree, first_id: str) -> list[str]:
    line = [first_id]
    while True:
        kids = game.children_of(line[-1])
        if not kids:
            return line
        line.append(kids[0].node_id)


def _pad(label: str) -> str:
    # moves are padded to a common width (full-width characters count as 2)
    width = sum(2 if ord(ch) > 0xFF else 1 for ch in label)
    return label + " " * max(1, 14 - width)


def export_game_to_kif2(game: GameTree) -> str:
    lines: list[str] = ["#KI2 version=2.0 encoding=UTF-8"]
    lines += header_lines(game.meta or {}, game.title, game.created_at, game.initial_sfen)
    lines.append("")
    lines += comment_lines(game.get_node(game.root_node_id).comment)

    def write_moves(node_ids: list[str]) -> None:
        row: list[str] = []
        for nid in node_ids:
            node = game.get_node(nid)
            parent = game.get_node(node.parent_id)
            row.append(usi_to_kif2_label(parent.position_sfen, node.move_usi or "", prev_to_rc=_dest(parent.move_usi)))
            comments = comment_lines(node.comment)
            if len(row) == _PER_LINE or comments:
                lines.append("".join(_pad(x) for x in row).rstrip())
                row = []
                lines.extend(comments)
        if row:
            lines.append("".join(_pad(x) for x in row).rstrip())

    def variations(node_ids: list[str], first_ply: int) -> None:
        # same order as the KIF export: from the end of the line backwards, each variation
        # followed by its own variations (a reader takes the latest line that has move N)
        for offset in range(len(node_ids) - 1, -1, -1):
            ply = first_ply + offset
            for alt in game.children_of(node_ids[offset])[1:]:
                sub = _line_from(game, alt.node_id)
                lines.append("")
                lines.append(f"変化：{ply + 1}手")
                write_moves(sub)
                variations(sub, ply + 1)

    main = _mainline_nodes(game)
    write_moves(main[1:])
    result = (game.meta or {}).get("_result") or {}
    played = len(main) - 1
    if result.get("term") and int(result.get("ply", -1)) == played:
        lines.append(result_line(result["term"], played, game.get_node(main[-1]).position_sfen, game.initial_sfen))
    variations(main, 0)
    return "\n".join(lines).rstrip() + "\n"
