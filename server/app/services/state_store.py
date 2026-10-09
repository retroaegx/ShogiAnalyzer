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


def default_game_title() -> str:
    """Title of a newly created game: kif_YYYYMMDD_hhmmss (local time)."""
    return datetime.now().strftime("kif_%Y%m%d_%H%M%S")


def _dumps(obj: Any) -> str:
    return json.dumps(obj or {}, ensure_ascii=False, separators=(",", ":"))


def content_signature(game: GameTree) -> str:
    """What 「保存」 keeps: title, start position, header and the move tree with comments
    (not the shown position or UI switches)."""
    nodes = sorted(
        (n.node_id, n.parent_id or "", int(n.order_index), n.move_usi or "", n.comment or "") for n in game.nodes.values()
    )
    return json.dumps([game.title, game.initial_sfen, game.meta, nodes], ensure_ascii=False, sort_keys=True, default=str)


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
            # analysis results of the game's positions go too (they reference node ids)
            self._conn.execute(
                "DELETE FROM analysis_snapshots WHERE node_id IN (SELECT node_id FROM nodes WHERE game_id = ?)",
                (game_id,),
            )
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

    # ---------- UI settings shared by every browser / device ----------
    def get_ui_settings(self) -> dict | None:
        """None until some browser has stored its settings for the first time."""
        row = self._conn.execute("SELECT value_json FROM app_state WHERE key = 'ui_settings'").fetchone()
        if not row:
            return None
        return _loads_dict(row["value_json"])

    def set_ui_settings(self, settings: dict) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO app_state(key, value_json) VALUES ('ui_settings', ?)
                ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json
                """,
                (_dumps(settings),),
            )

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
        game = GameTree.new(title=(title or "").strip() or default_game_title(), initial_sfen=initial_sfen)
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

    def latest_evals(self, game_id: str, node_ids: list[str] | None = None) -> dict[str, dict[str, Any]]:
        """Deepest snapshot per node: best score + all candidate lines (score is side-to-move perspective).

        The lines let the client keep showing candidate moves / arrows for positions that
        were analysed earlier, even when analysis is OFF. node_ids: the positions of the game
        being edited (its unsaved moves are not in the nodes table).
        """
        if node_ids is None:
            node_ids = [r["node_id"] for r in self._conn.execute("SELECT node_id FROM nodes WHERE game_id = ?", (game_id,))]
        rows = []
        for i in range(0, len(node_ids), 500):
            chunk = node_ids[i : i + 500]
            rows += self._conn.execute(
                f"SELECT node_id, lines_json, created_at FROM analysis_snapshots WHERE node_id IN ({','.join('?' * len(chunk))})",
                chunk,
            ).fetchall()
        rows.sort(key=lambda r: r["created_at"])
        out: dict[str, dict[str, Any]] = {}
        for r in rows:
            try:
                lines = json.loads(r["lines_json"] or "[]")
            except json.JSONDecodeError:
                continue
            best = next((l for l in lines if isinstance(l, dict) and int(l.get("pv_index") or 1) == 1), None)
            if not best or best.get("score_type") not in {"cp", "mate"}:
                continue
            depth = int(best.get("depth") or 0)
            prev = out.get(r["node_id"])
            # deeper wins; at equal depth prefer the snapshot with more candidate lines
            if prev and (prev["depth"] > depth or (prev["depth"] == depth and len(prev["lines"]) > len(lines))):
                continue
            out[r["node_id"]] = {
                "score_type": best["score_type"],
                "score_value": int(best.get("score_value") or 0),
                "depth": depth,
                "lines": [l for l in lines if isinstance(l, dict)],
            }
        return out

    def ensure_last_or_create(self) -> GameTree:
        last_id = self.get_last_game_id()
        if last_id:
            loaded = self.load_game(last_id)
            if loaded:
                return loaded
        return self.create_game()

    def game_exists(self, game_id: str) -> bool:
        return self._conn.execute("SELECT 1 FROM games WHERE game_id = ?", (game_id,)).fetchone() is not None

    # ---------- working copy (the kifu on screen, saved or not) ----------
    def save_working(self, game: GameTree, saved_sig: str | None) -> None:
        value = {"game": game.to_game_record(), "nodes": game.to_node_records(), "saved_sig": saved_sig}
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO app_state(key, value_json) VALUES ('working_game', ?)
                ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json
                """,
                (json.dumps(value, ensure_ascii=False, separators=(",", ":")),),
            )

    def load_working(self) -> tuple[GameTree, str | None] | None:
        row = self._conn.execute("SELECT value_json FROM app_state WHERE key = 'working_game'").fetchone()
        if not row:
            return None
        try:
            value = json.loads(row["value_json"])
            game = GameTree.from_rows(dict(value["game"]), [dict(n) for n in value["nodes"]])
        except Exception:
            return None
        sig = value.get("saved_sig")
        return game, sig if isinstance(sig, str) else None


class RuntimeState:
    """The kifu on screen is a working copy: every change is kept (also over a restart) in
    app_state 'working_game', but the saved kifu list (games / nodes tables) only changes when
    the user presses 保存 (save()). dirty = the working copy differs from what was saved."""

    def __init__(self, store: StateStore):
        self.store = store
        self._lock = asyncio.Lock()
        self._current_game: GameTree | None = None
        self._saved_sig: str | None = None  # content signature at the last save/load (None: never saved)

    def _ensure_locked(self) -> GameTree:
        if self._current_game is None:
            working = self.store.load_working()
            if working:
                self._current_game, self._saved_sig = working
            else:
                last_id = self.store.get_last_game_id()
                loaded = self.store.load_game(last_id) if last_id else None
                if loaded:
                    self._current_game = loaded
                    self._saved_sig = content_signature(loaded)
                else:
                    self._set_new_locked(GameTree.new(title=default_game_title()))
        return self._current_game

    def _set_new_locked(self, game: GameTree) -> None:
        """A fresh, still empty game: nothing to lose, so it does not count as unsaved."""
        self._current_game = game
        self._saved_sig = content_signature(game)

    def _persist_locked(self) -> None:
        if self._current_game is not None:
            self.store.save_working(self._current_game, self._saved_sig)

    def is_dirty(self) -> bool:
        game = self._current_game
        return game is not None and content_signature(game) != self._saved_sig

    async def startup(self) -> None:
        async with self._lock:
            game = self._ensure_locked()
            # nobody is connected yet: analysis always starts OFF (also after a crash while ON)
            ui = dict(game.ui_state or {})
            if ui.get("analysis_enabled"):
                ui["analysis_enabled"] = False
                game.ui_state = ui
            self._persist_locked()

    async def current_game(self) -> GameTree:
        async with self._lock:
            return self._ensure_locked()

    async def current_game_wire(self) -> dict:
        async with self._lock:
            game = self._ensure_locked()
            return {**game.to_wire(), "dirty": self.is_dirty(), "saved": self._saved_sig is not None and self.store.game_exists(game.game_id)}

    async def set_current_game(self, game: GameTree) -> GameTree:
        """Show a newly built game (import): not in the saved list until 保存."""
        async with self._lock:
            self._current_game = game
            self._saved_sig = None
            self._persist_locked()
            return game

    async def mutate(self, fn: Callable[[GameTree], Any]) -> tuple[GameTree, Any]:
        async with self._lock:
            game = self._ensure_locked()
            result = fn(game)
            self._persist_locked()
            return game, result

    async def save(self, fn: Callable[[GameTree], Any] | None = None) -> tuple[GameTree, Any]:
        """保存: apply fn (title etc.) and write the working copy to the saved kifu list."""
        async with self._lock:
            game = self._ensure_locked()
            result = fn(game) if fn else None
            self.store.save_game(game)
            self.store.set_last_game_id(game.game_id)
            self._saved_sig = content_signature(game)
            self._persist_locked()
            return game, result

    async def load_game(self, game_id: str) -> GameTree:
        async with self._lock:
            loaded = self.store.load_game(game_id)
            if loaded is None:
                raise KeyError(f"game not found: {game_id}")
            self._current_game = loaded
            self._saved_sig = content_signature(loaded)
            self.store.set_last_game_id(game_id)
            self._persist_locked()
            return loaded

    async def create_game(self, title: str | None = None, initial_sfen: str | None = None) -> GameTree:
        async with self._lock:
            game = GameTree.new(title=(title or "").strip() or default_game_title(), initial_sfen=initial_sfen)
            self._set_new_locked(game)
            self._persist_locked()
            return game

    async def delete_game(self, game_id: str) -> bool:
        """Delete a saved game; if it is the one being shown, switch to a fresh game."""
        async with self._lock:
            deleted = self.store.delete_game(game_id)
            if deleted and self._current_game is not None and self._current_game.game_id == game_id:
                self._set_new_locked(GameTree.new(title=default_game_title()))
                self._persist_locked()
            return deleted

    async def import_usi_text(self, text: str, title: str | None = None) -> GameTree:
        return await self.set_current_game(import_usi_game(text, title=title))
