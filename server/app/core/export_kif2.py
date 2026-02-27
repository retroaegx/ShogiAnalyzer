from __future__ import annotations

from .gametree import GameTree
from .notation import usi_to_kif2_label


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


def export_game_to_kif2(game: GameTree) -> str:
    lines: list[str] = []
    lines.append(f"▲{(game.title or 'Untitled').strip()}")
    lines.append("")

    main_nodes = _mainline_nodes(game)
    prev_to = None
    for i in range(1, len(main_nodes)):
        parent = game.get_node(main_nodes[i - 1])
        node = game.get_node(main_nodes[i])
        label = usi_to_kif2_label(parent.position_sfen, node.move_usi or "", prev_to_rc=prev_to)
        lines.append(label)
        if node.move_usi:
            try:
                from .sfen_ops import parse_usi_move

                mvu = parse_usi_move(node.move_usi)
                prev_to = (mvu.to_row, mvu.to_col)
            except Exception:
                prev_to = None

    # Variations branching from mainline.
    ply_by_node = {nid: idx for idx, nid in enumerate(main_nodes)}
    for parent_id in main_nodes:
        children = game.children_of(parent_id)
        if not children:
            continue
        for alt in children[1:]:
            start_ply = ply_by_node.get(parent_id, 0) + 1
            lines.append("")
            lines.append(f"変化：{start_ply}手")
            cur_parent = parent_id
            prev_to = None
            pnode = game.get_node(parent_id)
            if pnode.move_usi:
                try:
                    from .sfen_ops import parse_usi_move

                    mvu = parse_usi_move(pnode.move_usi)
                    prev_to = (mvu.to_row, mvu.to_col)
                except Exception:
                    prev_to = None
            cur = alt.node_id
            while True:
                par = game.get_node(cur_parent)
                nd = game.get_node(cur)
                lines.append(usi_to_kif2_label(par.position_sfen, nd.move_usi or "", prev_to_rc=prev_to))
                if nd.move_usi:
                    try:
                        from .sfen_ops import parse_usi_move

                        mvu = parse_usi_move(nd.move_usi)
                        prev_to = (mvu.to_row, mvu.to_col)
                    except Exception:
                        prev_to = None
                cur_parent = cur
                kids = game.children_of(cur)
                if not kids:
                    break
                cur = kids[0].node_id

    return "\n".join(lines).rstrip() + "\n"
