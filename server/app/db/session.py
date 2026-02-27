from __future__ import annotations

from pathlib import Path
import sqlite3


SCHEMA_SQL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS games (
  game_id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  initial_sfen TEXT NOT NULL,
  root_node_id TEXT NOT NULL,
  current_node_id TEXT NOT NULL,
  meta_json TEXT NOT NULL DEFAULT '{}',
  ui_state_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS nodes (
  node_id TEXT PRIMARY KEY,
  game_id TEXT NOT NULL,
  parent_id TEXT NULL,
  order_index INTEGER NOT NULL,
  move_usi TEXT NULL,
  move_label TEXT NOT NULL,
  comment TEXT NOT NULL DEFAULT '',
  position_sfen TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (game_id) REFERENCES games(game_id)
);

CREATE INDEX IF NOT EXISTS idx_nodes_game_parent_order
  ON nodes(game_id, parent_id, order_index);

CREATE TABLE IF NOT EXISTS analysis_snapshots (
  snapshot_id TEXT PRIMARY KEY,
  node_id TEXT NOT NULL,
  elapsed_ms INTEGER NOT NULL DEFAULT 0,
  multipv INTEGER NOT NULL DEFAULT 1,
  lines_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_state (
  key TEXT PRIMARY KEY,
  value_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS installer_downloads (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  asset_id TEXT NOT NULL,
  url TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  local_path TEXT NOT NULL,
  ok INTEGER NOT NULL,
  note TEXT NOT NULL
);
"""


def connect_db(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()

