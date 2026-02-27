from __future__ import annotations

from .gametree import GameTree
from .sfen_ops import sfen_to_position_command


def export_game_to_usi(game: GameTree) -> str:
    return sfen_to_position_command(game.initial_sfen, game.current_path_moves())

