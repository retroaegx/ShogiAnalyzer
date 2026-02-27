from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Callable
import uuid

from ..core.gametree import GameTree
from ..core.import_usi import import_usi_game
from ..db.session import connect_db, init_db


def _dumps(obj: Any) -> str:
    return json.dumps(obj or {}, ensure_ascii=False, separators=(",", ":"))


def _loads_dict(text: str | None) -> dict:
    if not text:
        return {}
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


class StateStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self._conn = connect_db(self.db_path)
        init_db(self._conn)

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    def list_games(self, limit: int = 50, offset: int = 0) -> list[dict]:
        limit = max(1, min(200, int(limit)))
        offset = max(0, int(offset))
        rows = self._conn.execute(
            """
            SELECT game_id, title, created_at, updated_at, initial_sfen, current_node_id
            FROM games
            ORDER BY updated_at DESC, created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]

    def save_game(self, game: GameTree) -> None:
        rec = game.to_game_record()
        node_records = game.to_node_records()
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO games (
                  game_id, title, created_at, updated_at, initial_sfen,
                  root_node_id, current_node_id, meta_json, ui_state_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(game_id) DO UPDATE SET
                  title=excluded.title,
                  updated_at=excluded.updated_at,
                  initial_sfen=excluded.initial_sfen,
                  root_node_id=excluded.root_node_id,
                  current_node_id=excluded.current_node_id,
                  meta_json=excluded.meta_json,
                  ui_state_json=excluded.ui_state_json
                """,
                (
                    rec["game_id"],
                    rec["title"],
                    rec["created_at"],
                    rec["updated_at"],
                    rec["initial_sfen"],
                    rec["root_node_id"],
                    rec["current_node_id"],
                    _dumps(rec["meta"]),
                    _dumps(rec["ui_state"]),
                ),
            )
            self._conn.execute("DELETE FROM nodes WHERE game_id = ?", (rec["game_id"],))
            self._conn.executemany(
                """
                INSERT INTO nodes (
                  node_id, game_id, parent_id, order_index, move_usi, move_label,
                  comment, position_sfen, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        n["node_id"],
                        n["game_id"],
                        n["parent_id"],
                        int(n["order_index"]),
                        n["move_usi"],
                        n["move_label"],
                        n["comment"],
                        n["position_sfen"],
                        n["created_at"],
                    )
                    for n in node_records
                ],
            )

    def load_game(self, game_id: str) -> GameTree | None:
        row = self._conn.execute(
            """
            SELECT game_id, title, created_at, updated_at, initial_sfen,
                   root_node_id, current_node_id, meta_json, ui_state_json
            FROM games WHERE game_id = ?
            """,
            (game_id,),
        ).fetchone()
        if row is None:
            return None
        node_rows = self._conn.execute(
            """
            SELECT node_id, game_id, parent_id, order_index, move_usi, move_label,
                   comment, position_sfen, created_at
            FROM nodes
            WHERE game_id = ?
            ORDER BY CASE WHEN parent_id IS NULL THEN 0 ELSE 1 END, parent_id, order_index, created_at, node_id
            """,
            (game_id,),
        ).fetchall()
        game_row = dict(row)
        game_row["meta"] = _loads_dict(game_row.pop("meta_json", None))
        game_row["ui_state"] = _loads_dict(game_row.pop("ui_state_json", None))
        return GameTree.from_rows(game_row, [dict(n) for n in node_rows])

    def update_game_fields(
        self,
        game: GameTree,
        *,
        title: str | None = None,
        meta: dict | None = None,
        ui_state: dict | None = None,
        current_node_id: str | None = None,
    ) -> GameTree:
        if title is not None:
            game.title = (str(title).strip() or game.title)
        if meta is not None and isinstance(meta, dict):
            game.meta = meta
        if ui_state is not None and isinstance(ui_state, dict):
            game.ui_state = ui_state
        if current_node_id is not None:
            game.jump(current_node_id)
        game.touch()
        self.save_game(game)
        return game

    def delete_game(self, game_id: str) -> bool:
        with self._conn:
            self._conn.execute("DELETE FROM nodes WHERE game_id = ?", (game_id,))
            cur = self._conn.execute("DELETE FROM games WHERE game_id = ?", (game_id,))
        if self.get_last_game_id() == game_id:
            self.set_last_game_id(None)
        return cur.rowcount > 0

    def get_last_game_id(self) -> str | None:
        row = self._conn.execute(
            "SELECT value_json FROM app_state WHERE key = 'last_game_id'"
        ).fetchone()
        if not row:
            return None
        try:
            value = json.loads(row["value_json"])
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, str) and value else None

    def set_last_game_id(self, game_id: str | None) -> None:
        value_json = json.dumps(game_id)
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO app_state(key, value_json) VALUES ('last_game_id', ?)
                ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json
                """,
                (value_json,),
            )

    def create_game(self, title: str | None = None, initial_sfen: str | None = None) -> GameTree:
        game = GameTree.new(title=title, initial_sfen=initial_sfen)
        self.save_game(game)
        self.set_last_game_id(game.game_id)
        return game

    def import_usi_text(self, text: str, title: str | None = None) -> GameTree:
        game = import_usi_game(text, title=title)
        self.save_game(game)
        self.set_last_game_id(game.game_id)
        return game

    def save_analysis_snapshot(
        self,
        *,
        node_id: str,
        elapsed_ms: int,
        multipv: int,
        lines: list[dict[str, Any]],
    ) -> str:
        snapshot_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO analysis_snapshots (
                  snapshot_id, node_id, elapsed_ms, multipv, lines_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    node_id,
                    max(0, int(elapsed_ms)),
                    max(1, int(multipv)),
                    json.dumps(lines or [], ensure_ascii=False, separators=(",", ":")),
                    created_at,
                ),
            )
        return snapshot_id

    def ensure_last_or_create(self) -> GameTree:
        last_id = self.get_last_game_id()
        if last_id:
            loaded = self.load_game(last_id)
            if loaded:
                return loaded
        return self.create_game(title="Recovered game")


class RuntimeState:
    def __init__(self, store: StateStore):
        self.store = store
        self._lock = asyncio.Lock()
        self._current_game: GameTree | None = None

    async def startup(self) -> None:
        async with self._lock:
            self._current_game = self.store.ensure_last_or_create()

    async def current_game(self) -> GameTree:
        async with self._lock:
            if self._current_game is None:
                self._current_game = self.store.ensure_last_or_create()
            return self._current_game

    async def current_game_wire(self) -> dict:
        game = await self.current_game()
        return game.to_wire()

    async def set_current_game(self, game: GameTree) -> GameTree:
        async with self._lock:
            # Persist the game because callers may construct a new GameTree
            # (e.g., imports) without saving it yet.
            self.store.save_game(game)
            self._current_game = game
            self.store.set_last_game_id(game.game_id)
            return game

    async def mutate(self, fn: Callable[[GameTree], Any]) -> tuple[GameTree, Any]:
        async with self._lock:
            if self._current_game is None:
                self._current_game = self.store.ensure_last_or_create()
            result = fn(self._current_game)
            self.store.save_game(self._current_game)
            self.store.set_last_game_id(self._current_game.game_id)
            return self._current_game, result

    async def load_game(self, game_id: str) -> GameTree:
        async with self._lock:
            loaded = self.store.load_game(game_id)
            if loaded is None:
                raise KeyError(f"game not found: {game_id}")
            self._current_game = loaded
            self.store.set_last_game_id(game_id)
            return loaded

    async def create_game(self, title: str | None = None, initial_sfen: str | None = None) -> GameTree:
        async with self._lock:
            game = self.store.create_game(title=title, initial_sfen=initial_sfen)
            self._current_game = game
            return game

    async def import_usi_text(self, text: str, title: str | None = None) -> GameTree:
        async with self._lock:
            game = self.store.import_usi_text(text=text, title=title)
            self._current_game = game
            return game
