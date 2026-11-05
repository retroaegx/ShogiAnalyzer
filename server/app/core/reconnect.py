"""Compare a queued board operation with the current authoritative position.

Called inside RuntimeState.mutate's lock. Existing child reuse makes a move whose
reply was lost safe to repeat, without adding a second node or moving another game.
"""
from .gametree import GameTree


class ReconnectConflict(ValueError):
    pass


def check_step(game: GameTree, kind: str, payload: dict) -> None:
    if not payload.get('operation_id'):
        return  # compatibility with older pages until their next reload
    if game.game_id != payload.get('expected_game_id'):
        raise ReconnectConflict('棋譜が変更されたため、未同期の操作は反映していません')
    base = game.nodes.get(payload.get('expected_node_id'))
    if not base or base.position_sfen != payload.get('expected_sfen'):
        raise ReconnectConflict('元の局面が変更されたため、未同期の操作は反映していません')
    current = game.get_node(game.current_node_id)
    if kind == 'node:jump':
        target = game.get_node(str(payload.get('node_id') or ''))
        if payload.get('step_limited') and target.parent_id != base.node_id and base.parent_id != target.node_id:
            raise ReconnectConflict('再接続中に移動できるのは1手だけです')
        applied = current.node_id == target.node_id
    else:
        if payload.get('from_node_id') != base.node_id:
            raise ReconnectConflict('操作の開始局面が一致しません')
        applied = current.parent_id == base.node_id and current.move_usi == payload.get('move_usi')
    if current.node_id != base.node_id and not applied:
        raise ReconnectConflict('別の操作で局面が変更されたため、未同期の操作は反映していません')
