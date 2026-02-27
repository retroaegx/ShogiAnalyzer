from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid

from .sfen_ops import DEFAULT_START_SFEN, apply_usi_move, normalize_sfen
from .notation import usi_to_kif2_label


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


@dataclass
class Node:
    node_id: str
    game_id: str
    parent_id: str | None
    order_index: int
    move_usi: str | None
    move_label: str
    comment: str
    position_sfen: str
    created_at: str

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "game_id": self.game_id,
            "parent_id": self.parent_id,
            "order_index": self.order_index,
            "move_usi": self.move_usi,
            "move_label": self.move_label,
            "comment": self.comment,
            "position_sfen": self.position_sfen,
            "created_at": self.created_at,
        }


@dataclass
class GameTree:
    game_id: str
    title: str
    created_at: str
    updated_at: str
    initial_sfen: str
    root_node_id: str
    current_node_id: str
    meta: dict = field(default_factory=dict)
    ui_state: dict = field(default_factory=dict)
    nodes: dict[str, Node] = field(default_factory=dict)

    @classmethod
    def new(cls, title: str | None = None, initial_sfen: str | None = None) -> "GameTree":
        game_id = new_id()
        now = utc_now_iso()
        initial = normalize_sfen(initial_sfen or DEFAULT_START_SFEN)
        root_node_id = new_id()
        root = Node(
            node_id=root_node_id,
            game_id=game_id,
            parent_id=None,
            order_index=0,
            move_usi=None,
            move_label="root",
            comment="",
            position_sfen=initial,
            created_at=now,
        )
        return cls(
            game_id=game_id,
            title=(title or "Untitled game").strip() or "Untitled game",
            created_at=now,
            updated_at=now,
            initial_sfen=initial,
            root_node_id=root_node_id,
            current_node_id=root_node_id,
            nodes={root_node_id: root},
        )

    @classmethod
    def from_rows(cls, game_row: dict, node_rows: list[dict]) -> "GameTree":
        nodes: dict[str, Node] = {}
        for r in node_rows:
            node = Node(
                node_id=r["node_id"],
                game_id=r["game_id"],
                parent_id=r["parent_id"],
                order_index=int(r["order_index"]),
                move_usi=r["move_usi"],
                move_label=r["move_label"],
                comment=r["comment"] or "",
                position_sfen=r["position_sfen"],
                created_at=r["created_at"],
            )
            nodes[node.node_id] = node
        game = cls(
            game_id=game_row["game_id"],
            title=game_row["title"],
            created_at=game_row["created_at"],
            updated_at=game_row["updated_at"],
            initial_sfen=game_row["initial_sfen"],
            root_node_id=game_row["root_node_id"],
            current_node_id=game_row["current_node_id"],
            meta=game_row.get("meta", {}) or {},
            ui_state=game_row.get("ui_state", {}) or {},
            nodes=nodes,
        )
        if game.root_node_id not in game.nodes:
            raise ValueError("root node missing")
        if game.current_node_id not in game.nodes:
            game.current_node_id = game.root_node_id
        return game

    def touch(self) -> None:
        self.updated_at = utc_now_iso()

    def get_node(self, node_id: str) -> Node:
        try:
            return self.nodes[node_id]
        except KeyError as exc:
            raise KeyError(f"node not found: {node_id}") from exc

    def children_of(self, parent_id: str | None) -> list[Node]:
        out = [n for n in self.nodes.values() if n.parent_id == parent_id]
        out.sort(key=lambda n: (n.order_index, n.created_at, n.node_id))
        return out

    def _next_order_index(self, parent_id: str) -> int:
        children = self.children_of(parent_id)
        if not children:
            return 0
        return max(n.order_index for n in children) + 1

    def jump(self, node_id: str) -> Node:
        node = self.get_node(node_id)
        self.current_node_id = node.node_id
        self.touch()
        return node

    def play_move(self, from_node_id: str, move_usi: str) -> Node:
        parent = self.get_node(from_node_id)
        for child in self.children_of(parent.node_id):
            if child.move_usi == move_usi:
                self.current_node_id = child.node_id
                self.touch()
                return child
        position_sfen = apply_usi_move(parent.position_sfen, move_usi)
        now = utc_now_iso()
        # Japanese label for UI and KIF2 export.
        try:
            label = usi_to_kif2_label(parent.position_sfen, move_usi)
        except Exception:
            label = move_usi
        node = Node(
            node_id=new_id(),
            game_id=self.game_id,
            parent_id=parent.node_id,
            order_index=self._next_order_index(parent.node_id),
            move_usi=move_usi,
            move_label=label,
            comment="",
            position_sfen=position_sfen,
            created_at=now,
        )
        self.nodes[node.node_id] = node
        self.current_node_id = node.node_id
        self.touch()
        return node

    def set_comment(self, node_id: str, comment: str) -> None:
        node = self.get_node(node_id)
        node.comment = comment
        self.touch()

    def reorder_children(self, parent_id: str, ordered_child_ids: list[str]) -> None:
        children = self.children_of(parent_id)
        child_ids = {c.node_id for c in children}
        if set(ordered_child_ids) != child_ids:
            raise ValueError("ordered_child_ids must match child set")
        for idx, cid in enumerate(ordered_child_ids):
            self.nodes[cid].order_index = idx
        self.touch()

    def path_to_node(self, node_id: str | None = None) -> list[Node]:
        cur_id = node_id or self.current_node_id
        chain: list[Node] = []
        seen: set[str] = set()
        while cur_id:
            if cur_id in seen:
                raise ValueError("cycle detected in node tree")
            seen.add(cur_id)
            node = self.get_node(cur_id)
            chain.append(node)
            cur_id = node.parent_id
        chain.reverse()
        return chain

    def current_path_moves(self) -> list[str]:
        return [n.move_usi for n in self.path_to_node() if n.move_usi]

    def current_position_sfen(self) -> str:
        return self.get_node(self.current_node_id).position_sfen

    def to_game_record(self) -> dict:
        return {
            "game_id": self.game_id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "initial_sfen": self.initial_sfen,
            "root_node_id": self.root_node_id,
            "current_node_id": self.current_node_id,
            "meta": self.meta,
            "ui_state": self.ui_state,
        }

    def to_node_records(self) -> list[dict]:
        records = [n.to_dict() for n in self.nodes.values()]
        records.sort(
            key=lambda n: (
                0 if n["parent_id"] is None else 1,
                n["parent_id"] or "",
                int(n["order_index"]),
                n["created_at"],
                n["node_id"],
            )
        )
        return records

    def to_wire(self) -> dict:
        current = self.get_node(self.current_node_id)
        children_index: dict[str, list[str]] = {}
        for node in self.nodes.values():
            if node.parent_id is None:
                continue
            children_index.setdefault(node.parent_id, []).append(node.node_id)
        for parent_id, child_ids in children_index.items():
            child_ids.sort(
                key=lambda cid: (
                    self.nodes[cid].order_index,
                    self.nodes[cid].created_at,
                    self.nodes[cid].node_id,
                )
            )
        return {
            "game_id": self.game_id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "initial_sfen": self.initial_sfen,
            "root_node_id": self.root_node_id,
            "current_node_id": self.current_node_id,
            "current_position_sfen": current.position_sfen,
            "meta": self.meta,
            "ui_state": self.ui_state,
            "nodes": self.to_node_records(),
            "children_index": children_index,
            "current_path_node_ids": [n.node_id for n in self.path_to_node()],
            "current_path_moves": self.current_path_moves(),
        }
