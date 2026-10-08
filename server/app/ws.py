from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timezone
import json
import secrets
from urllib.parse import urlsplit
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from . import auth
from .core.legality import check_move
from .core.sfen_ops import SfenError


router = APIRouter()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


async def ws_send(ws: WebSocket, type_: str, payload: dict | None = None) -> None:
    lock = ws.scope.get("_send_lock")
    if lock is None:
        lock = asyncio.Lock()
        ws.scope["_send_lock"] = lock
    async with lock:
        await ws.send_json({"type": type_, "payload": payload or {}})


class SessionHub:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._owner: WebSocket | None = None
        self._owner_since: str | None = None
        self._owner_token: str | None = None
        self._session_id: str | None = None
        self._owner_tab: str | None = None

    async def try_grant(self, ws: WebSocket, tab: str | None = None) -> tuple[bool, dict, WebSocket | None]:
        """Grant the session when free. The same browser tab coming back (its old socket not
        yet noticed as dead, e.g. a phone waking up) also gets it back, without the
        「別の画面で操作中」 prompt; the replaced socket is returned so it can be closed."""
        async with self._lock:
            replaced: WebSocket | None = None
            if self._owner is not None and tab and tab == self._owner_tab:
                replaced = self._owner
                self._owner = None
            if self._owner is None:
                self._owner = ws
                self._owner_tab = tab
                self._owner_since = utc_now_iso()
                self._owner_token = secrets.token_urlsafe(12)
                self._session_id = secrets.token_urlsafe(12)
                return True, {
                    "owner_since": self._owner_since,
                    "owner_token": self._owner_token,
                    "session_id": self._session_id,
                }, replaced
            return False, {
                "owner_since": self._owner_since,
                "owner_hint": "another session is active",
            }, None

    async def takeover(self, ws: WebSocket) -> tuple[WebSocket | None, dict]:
        old_owner: WebSocket | None = None
        async with self._lock:
            if self._owner is ws:
                return None, {
                    "owner_since": self._owner_since,
                    "owner_token": self._owner_token,
                }
            old_owner = self._owner
            self._owner = ws
            self._owner_tab = None
            self._owner_since = utc_now_iso()
            self._owner_token = secrets.token_urlsafe(12)
            self._session_id = secrets.token_urlsafe(12)
            return old_owner, {
                "owner_since": self._owner_since,
                "owner_token": self._owner_token,
                "session_id": self._session_id,
            }

    async def is_owner(self, ws: WebSocket) -> bool:
        async with self._lock:
            return self._owner is ws

    async def owner_token(self, ws: WebSocket) -> str | None:
        async with self._lock:
            if self._owner is ws:
                return self._owner_token
            return None

    async def session_id(self, ws: WebSocket) -> str | None:
        async with self._lock:
            if self._owner is ws:
                return self._session_id
            return None

    async def release_if_owner(self, ws: WebSocket) -> bool:
        async with self._lock:
            if self._owner is not ws:
                return False
            self._owner = None
            self._owner_tab = None
            self._owner_since = None
            self._owner_token = None
            self._session_id = None
            return True


def _runtime_from_ws(ws: WebSocket):
    return ws.app.state.runtime


def _hub_from_ws(ws: WebSocket) -> SessionHub:
    return ws.app.state.session_hub


def _analysis_from_ws(ws: WebSocket):
    return ws.app.state.analysis


def _analysis_multipv_from_game(game: dict | Any) -> int:
    ui_state = getattr(game, "ui_state", None) or {}
    try:
        value = int(ui_state.get("analysis_multipv", 1))
    except Exception:
        value = 1
    return max(1, min(20, value))


async def _send_granted(ws: WebSocket) -> None:
    runtime = _runtime_from_ws(ws)
    hub = _hub_from_ws(ws)
    analysis = _analysis_from_ws(ws)
    token = await hub.owner_token(ws)
    session_id = await hub.session_id(ws)
    game = await runtime.current_game()
    game_wire = game.to_wire()
    capability_notes = []
    if not analysis.is_available():
        capability_notes.append(
            "USI engine analysis is disabled until SHOGI_ANALYZER_ENGINE_PATH or SHOGI_ANALYZER_ENGINE_CMD is set"
        )
    # KIF/KIF2 are supported; KI2 parsing is best-effort.
    payload = {
        "game": game_wire,
        "server_capabilities": {
            "analysis": analysis.is_available(),
            "analysis_controls": ["enable", "multipv", "start", "stop"] if analysis.is_available() else [],
            "import_formats": ["usi", "kif", "kif2"],
            "export_formats": ["usi", "kif", "kif2"],
            "notes": capability_notes,
        },
        "engine_status": analysis.status_wire(),
        "analysis_state": {
            "enabled": bool((game.ui_state or {}).get("analysis_enabled")),
            "multipv": _analysis_multipv_from_game(game),
        },
        "session_id": session_id,
        "owner_token": token,
    }
    await ws_send(ws, "session:granted", payload)


async def _send_state(ws: WebSocket) -> None:
    await ws_send(ws, "game:state", {"game": await _runtime_from_ws(ws).current_game_wire()})


async def _handle_owner_message(ws: WebSocket, msg: dict[str, Any]) -> None:
    runtime = _runtime_from_ws(ws)
    analysis = _analysis_from_ws(ws)
    msg_type = str(msg.get("type") or "")
    payload = msg.get("payload") or {}
    if not isinstance(payload, dict):
        payload = {}

    async def _sync_analysis_to_current_game() -> None:
        if analysis.batch_running:
            return  # 全解析 owns the engine; it resumes the current position when it ends
        game = await runtime.current_game()
        enabled = bool((game.ui_state or {}).get("analysis_enabled"))
        if enabled:
            ok, reason = await analysis.start_for_game(game)
            if not ok:
                await ws_send(ws, "toast", {"level": "warning", "message": reason})
            return
        if analysis.status_wire().get("analysis_running"):
            await analysis.stop("analysis disabled")

    # 全解析 drives the position itself; the kifu cannot be changed until it ends
    if analysis.batch_running and msg_type in {
        "game:new",
        "game:load",
        "game:delete",
        "game:import_text",
        "node:jump",
        "node:play_move",
        "node:reorder_children",
        "analysis:set_multipv",
    }:
        await ws_send(ws, "toast", {"level": "warning", "message": "全解析中は棋譜を操作できません"})
        await _send_state(ws)
        return

    if msg_type == "game:new":
        await runtime.create_game(title=payload.get("title"), initial_sfen=payload.get("initial_sfen"))
        await _send_state(ws)
        analysis.schedule_sync(_sync_analysis_to_current_game)
        return

    if msg_type == "game:load":
        game_id = str(payload.get("game_id") or "")
        if not game_id:
            await ws_send(ws, "toast", {"level": "error", "message": "game_id is required"})
            return
        try:
            await runtime.load_game(game_id)
            await _send_state(ws)
            analysis.schedule_sync(_sync_analysis_to_current_game)
        except KeyError:
            await ws_send(ws, "toast", {"level": "error", "message": "game not found"})
        return

    if msg_type == "game:delete":
        game_id = str(payload.get("game_id") or "")
        if not game_id:
            await ws_send(ws, "toast", {"level": "error", "message": "game_id is required"})
            return
        was_current = (await runtime.current_game()).game_id == game_id
        if not await runtime.delete_game(game_id):
            await ws_send(ws, "toast", {"level": "error", "message": "棋譜が見つかりませんでした"})
            return
        await ws_send(ws, "game:deleted", {"game_id": game_id, "was_current": was_current})
        if was_current:
            # the deleted game was on screen: show the fresh game that replaced it
            await _send_state(ws)
            analysis.schedule_sync(_sync_analysis_to_current_game)
        return

    if msg_type == "game:save":
        def _save_fields(g):
            if "title" in payload:
                title = str(payload.get("title") or "").strip()
                if title:
                    g.title = title
                    # the user chose this name (rename / first save): no save-name popup any more
                    g.ui_state = {**(g.ui_state or {}), "named": True}
            if isinstance(payload.get("meta"), dict):
                g.meta = payload["meta"]
            if isinstance(payload.get("ui_state"), dict):
                g.ui_state = payload["ui_state"]
            if payload.get("current_node_id"):
                g.jump(str(payload["current_node_id"]))
            g.touch()

        try:
            await runtime.mutate(_save_fields)
            await _send_state(ws)
            analysis.schedule_sync(_sync_analysis_to_current_game)
        except Exception as exc:
            await ws_send(ws, "toast", {"level": "error", "message": f"save failed: {exc}"})
        return

    if msg_type == "node:jump":
        node_id = str(payload.get("node_id") or "")
        if not node_id:
            await ws_send(ws, "toast", {"level": "error", "message": "node_id is required"})
            return

        def _jump(g):
            g.jump(node_id)

        try:
            await runtime.mutate(_jump)
            await _send_state(ws)
            analysis.schedule_sync(_sync_analysis_to_current_game)
        except Exception as exc:
            await ws_send(ws, "toast", {"level": "error", "message": f"jump failed: {exc}"})
        return

    if msg_type == "node:play_move":
        from_node_id = str(payload.get("from_node_id") or "")
        move_usi = str(payload.get("move_usi") or "").strip()
        if not from_node_id or not move_usi:
            await ws_send(
                ws,
                "toast",
                {"level": "error", "message": "from_node_id and move_usi are required"},
            )
            return

        def _play(g):
            # moves from the board must be legal; an illegal position must never be analyzed
            check_move(g.get_node(from_node_id).position_sfen, move_usi)
            g.play_move(from_node_id, move_usi)

        try:
            await runtime.mutate(_play)
            await _send_state(ws)
            analysis.schedule_sync(_sync_analysis_to_current_game)
        except SfenError as exc:
            await ws_send(ws, "toast", {"level": "error", "message": f"指せない手です: {exc}"})
            await _send_state(ws)
        except Exception as exc:
            await ws_send(ws, "toast", {"level": "error", "message": f"play_move failed: {exc}"})
        return

    if msg_type == "node:set_comment":
        node_id = str(payload.get("node_id") or "")
        comment = str(payload.get("comment") or "")
        if not node_id:
            await ws_send(ws, "toast", {"level": "error", "message": "node_id is required"})
            return

        def _set_comment(g):
            g.set_comment(node_id, comment)

        try:
            await runtime.mutate(_set_comment)
            await _send_state(ws)
        except Exception as exc:
            await ws_send(ws, "toast", {"level": "error", "message": f"set_comment failed: {exc}"})
        return

    if msg_type == "node:reorder_children":
        parent_id = str(payload.get("parent_id") or "")
        ordered_child_ids = payload.get("ordered_child_ids") or payload.get("ordered_child_ids[]") or []
        if not parent_id or not isinstance(ordered_child_ids, list):
            await ws_send(ws, "toast", {"level": "error", "message": "invalid reorder payload"})
            return

        def _reorder(g):
            g.reorder_children(parent_id, [str(x) for x in ordered_child_ids])

        try:
            await runtime.mutate(_reorder)
            await _send_state(ws)
        except Exception as exc:
            await ws_send(ws, "toast", {"level": "error", "message": f"reorder failed: {exc}"})
        return

    if msg_type == "analysis:set_enabled":
        enabled = bool(payload.get("enabled"))
        if enabled and not analysis.is_available():
            await ws_send(
                ws,
                "toast",
                {
                    "level": "warning",
                    "message": "analysis engine is not configured on the server",
                },
            )
            await ws_send(
                ws,
                "analysis:stopped",
                {"reason": "USI engine is not configured"},
            )
            return

        def _set_enabled(g):
            ui = dict(g.ui_state or {})
            ui["analysis_enabled"] = enabled
            ui["analysis_multipv"] = _analysis_multipv_from_game(g)
            g.ui_state = ui
            g.touch()

        await runtime.mutate(_set_enabled)
        await _send_state(ws)
        if enabled and analysis.batch_running:
            # 常時解析 ON stops 全解析 (the client asked the user first); the batch's
            # on_finish then starts analysis of the current position
            analysis.cancel_batch()
            return
        # background start/stop so the socket stays responsive (engine boot / isready can take seconds)
        analysis.schedule_sync(_sync_analysis_to_current_game)
        return

    if msg_type == "analysis:analyze_all":
        try:
            seconds = max(0.5, min(120.0, float(payload.get("seconds") or 3)))
        except (TypeError, ValueError):
            seconds = 3.0
        if analysis.batch_running:
            await ws_send(ws, "toast", {"level": "warning", "message": "全解析は実行中です"})
            return

        # 全解析 turns 常時解析 OFF
        def _disable(g):
            ui = dict(g.ui_state or {})
            ui["analysis_enabled"] = False
            g.ui_state = ui
            g.touch()

        game, _ = await runtime.mutate(_disable)
        wire = game.to_wire()
        # main line: path to the current position, then the first child onward
        node_ids = list(wire["current_path_node_ids"])
        children = wire["children_index"]
        while children.get(node_ids[-1]):
            node_ids.append(children[node_ids[-1]][0])

        async def _show(node_id: str) -> None:
            # the board starts from the initial position and follows the analysis
            await runtime.mutate(lambda g: g.jump(node_id))
            with contextlib.suppress(Exception):
                await _send_state(ws)

        ok, reason = analysis.start_batch(
            game, node_ids, seconds, on_finish=lambda: _sync_analysis_to_current_game(), on_step=_show
        )
        await _send_state(ws)
        if not ok:
            await ws_send(ws, "toast", {"level": "warning", "message": reason})
        return

    if msg_type == "analysis:batch_cancel":
        analysis.cancel_batch()
        return

    if msg_type == "analysis:set_multipv":
        if "multipv" not in payload:
            await ws_send(ws, "toast", {"level": "error", "message": "multipv is required"})
            return
        try:
            multipv = max(1, min(20, int(payload.get("multipv"))))
        except Exception:
            await ws_send(ws, "toast", {"level": "error", "message": "invalid multipv"})
            return

        def _set_multipv(g):
            ui = dict(g.ui_state or {})
            ui["analysis_multipv"] = multipv
            g.ui_state = ui
            g.touch()

        await runtime.mutate(_set_multipv)
        await _send_state(ws)
        analysis.schedule_sync(_sync_analysis_to_current_game)
        return

    if msg_type == "analysis:start":
        game = await runtime.current_game()
        node_id = str(payload.get("node_id") or "") or None
        ok, reason = await analysis.start_for_game(game, node_id=node_id)
        if not ok:
            await ws_send(ws, "toast", {"level": "warning", "message": reason})
        return

    if msg_type == "analysis:stop":
        await analysis.stop("stopped by user")
        return

    if msg_type == "game:import_text":
        text = str(payload.get("text") or "")
        title = payload.get("title")
        if not text.strip():
            await ws_send(ws, "toast", {"level": "error", "message": "text is required"})
            return
        from .core.import_usi import detect_format, import_usi_game
        from .core.import_kif import import_kif_game
        from .core.import_kif2 import import_kif2_game

        fmt = detect_format(text)
        if fmt == "usi":
            game_new = import_usi_game(text, title=title)
        elif fmt == "kif":
            game_new = import_kif_game(text, title=title)
        elif fmt == "kif2":
            game_new = import_kif2_game(text, title=title)
        else:
            await ws_send(ws, "toast", {"level": "error", "message": "unknown import format"})
            return
        await runtime.set_current_game(game_new)
        await _send_state(ws)
        analysis.schedule_sync(_sync_analysis_to_current_game)
        return

    if msg_type in {"session:takeover", ""}:
        return

    await ws_send(ws, "toast", {"level": "warning", "message": f"unknown message type: {msg_type}"})


def _analysis_off(g) -> None:
    g.ui_state = {**(g.ui_state or {}), "analysis_enabled": False}
    g.touch()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    if auth.required():
        # login cookie required (also while the password is not set yet), and only from this app's own pages (blocks cross-site sockets)
        origin = ws.headers.get("origin") or ""
        same_origin = not origin or urlsplit(origin).netloc == (ws.headers.get("host") or "")
        if not same_origin or not auth.token_valid(ws.cookies.get(auth.COOKIE_NAME)):
            await ws.close(code=4401)
            return
    hub = _hub_from_ws(ws)
    runtime = _runtime_from_ws(ws)
    analysis = _analysis_from_ws(ws)

    async def _analysis_sender(type_: str, payload: dict | None = None) -> None:
        await ws_send(ws, type_, payload)

    tab = (ws.query_params.get("tab") or "").strip()[:64] or None
    granted, info, replaced = await hub.try_grant(ws, tab)
    if granted:
        if replaced is not None:
            # same tab reconnecting: its previous connection has ended (analysis OFF, as on a disconnect)
            with contextlib.suppress(Exception):
                await runtime.mutate(_analysis_off)
            with contextlib.suppress(Exception):
                # 4409 = replaced by the same tab id: a live page (e.g. a duplicated tab) stays
                # read-only instead of reconnecting and taking the session back again
                await replaced.close(code=4409)
        await analysis.attach_owner_sender(_analysis_sender)
        await _send_granted(ws)
    else:
        await ws_send(ws, "session:busy", info)

    try:
        while True:
            message = await ws.receive_text()
            try:
                msg = json.loads(message)
            except json.JSONDecodeError:
                await ws_send(ws, "toast", {"level": "error", "message": "invalid JSON"})
                continue
            if not isinstance(msg, dict):
                await ws_send(ws, "toast", {"level": "error", "message": "JSON object required"})
                continue

            if msg.get("type") == "ping":
                # connection check from the page (works for viewers too)
                await ws_send(ws, "pong", {})
                continue

            if not await hub.is_owner(ws):
                if str(msg.get("type") or "") != "session:takeover":
                    await ws_send(ws, "session:busy", {"owner_hint": "send session:takeover to claim session"})
                    continue
                old_owner, _ = await hub.takeover(ws)
                # the previous session ends here: 常時解析 / 全解析 turn OFF (as on a disconnect)
                await runtime.mutate(_analysis_off)
                if old_owner and old_owner is not ws:
                    try:
                        await ws_send(old_owner, "session:kicked", {"reason": "session takeover"})
                        await old_owner.close()
                    except Exception:
                        pass
                await analysis.attach_owner_sender(_analysis_sender)
                await _send_granted(ws)
                await ws_send(ws, "toast", {"level": "info", "message": "session takeover complete"})
                continue

            # Owner message freshness guard
            expected_session_id = await hub.session_id(ws)
            expected_owner_token = await hub.owner_token(ws)
            if (
                msg.get("session_id") != expected_session_id
                or msg.get("owner_token") != expected_owner_token
            ):
                await ws_send(
                    ws,
                    "session:stale",
                    {
                        "reason": "stale owner token/session",
                        "expected_session_id": expected_session_id,
                    },
                )
                continue

            await _handle_owner_message(ws, msg)
    except WebSocketDisconnect:
        pass
    finally:
        released = await hub.release_if_owner(ws)
        if released:
            # session closed: 常時解析 OFF first (so nothing restarts it), then stop the engine / 全解析
            with contextlib.suppress(Exception):
                await runtime.mutate(_analysis_off)
            await analysis.owner_disconnected()
