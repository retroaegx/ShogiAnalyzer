from __future__ import annotations

from .gametree import GameTree
from .sfen_ops import DEFAULT_START_SFEN, normalize_sfen, parse_usi_move


def detect_format(text: str) -> str:
    s = (text or "").strip()
    lower = s.lower()
    if lower.startswith("position "):
        return "usi"
    if "手合割" in s or "手数----指手" in s:
        return "kif"
    if "▲" in s or "△" in s:
        return "kif2"
    return "unknown"


def parse_usi_text(text: str) -> tuple[str, list[str]]:
    s = (text or "").strip()
    if not s:
        raise ValueError("empty text")
    tokens = s.replace("\r", "\n").split()
    if not tokens:
        raise ValueError("empty text")

    if tokens[0] != "position":
        moves = []
        for t in tokens:
            parse_usi_move(t)
            moves.append(t)
        return DEFAULT_START_SFEN, moves

    if len(tokens) < 2:
        raise ValueError("invalid position command")

    idx = 1
    if tokens[idx] == "startpos":
        initial_sfen = DEFAULT_START_SFEN
        idx += 1
    elif tokens[idx] == "sfen":
        if len(tokens) < idx + 5:
            raise ValueError("position sfen requires 4 SFEN fields")
        initial_sfen = normalize_sfen(" ".join(tokens[idx + 1 : idx + 5]))
        idx += 5
    else:
        raise ValueError("position must use startpos or sfen")

    moves: list[str] = []
    if idx < len(tokens):
        if tokens[idx] != "moves":
            raise ValueError("unexpected token after position base")
        idx += 1
        for t in tokens[idx:]:
            parse_usi_move(t)
            moves.append(t)

    return initial_sfen, moves


def import_usi_game(text: str, title: str | None = None) -> GameTree:
    initial_sfen, moves = parse_usi_text(text)
    game = GameTree.new(title=title or "Imported USI", initial_sfen=initial_sfen)
    cur = game.root_node_id
    for mv in moves:
        cur = game.play_move(cur, mv).node_id
    return game

