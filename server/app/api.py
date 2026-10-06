from __future__ import annotations

import asyncio
import hmac
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from . import auth
from .core.export_kif import export_game_to_kif
from .core.export_kif2 import export_game_to_kif2
from .core.export_usi import export_game_to_usi
from .core.import_kif import import_kif_game
from .core.import_kif2 import import_kif2_game
from .core.import_usi import detect_format, import_usi_game, normalize_usi_text
from .services.state_store import RuntimeState, StateStore, default_game_title
from .services.update_checker import check_update_now, get_update_status, read_current_version


router = APIRouter()


def _runtime(request: Request) -> RuntimeState:
    return request.app.state.runtime


def _store(request: Request) -> StateStore:
    return request.app.state.store


def _analysis(request: Request):
    return request.app.state.analysis


async def _read_json_or_empty(request: Request) -> dict[str, Any]:
    try:
        data = await request.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _logged_in(request: Request) -> bool:
    return auth.token_valid(request.cookies.get(auth.COOKIE_NAME))


def _client_ip(request: Request) -> str:
    # behind Cloudflare Tunnel every request comes from 127.0.0.1; the real address is in this header
    return request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "?")


# failed logins per client: (count, locked_until)
_failures: dict[str, tuple[int, float]] = {}


def _is_this_pc(request: Request) -> bool:
    """Opened on the server PC itself (not via LAN or the Cloudflare tunnel)."""
    host = request.client.host if request.client else ""
    via_proxy = any(h in request.headers for h in ("cf-connecting-ip", "x-forwarded-for", "cf-ray"))
    return host in {"127.0.0.1", "::1", "localhost"} and not via_proxy


def _login_response(request: Request) -> JSONResponse:
    resp = JSONResponse({"ok": True, "days": auth.LOGIN_DAYS})
    https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    resp.set_cookie(
        auth.COOKIE_NAME,
        auth.issue_token(),
        max_age=auth.LOGIN_SECONDS,
        httponly=True,
        samesite="lax",
        secure=https,
        path="/",
    )
    return resp


def _check_rate(ip: str) -> None:
    _, locked_until = _failures.get(ip, (0, 0.0))
    now = time.time()
    if locked_until > now:
        raise HTTPException(status_code=429, detail=f"しばらく待ってから再試行してください（{int(locked_until - now) + 1}秒）")


async def _fail(ip: str, message: str) -> None:
    count, _ = _failures.get(ip, (0, 0.0))
    count += 1
    # from the 5th failure on, wait 30s, 60s, 120s ... (max 15 min) before the next try
    lock = min(900, 30 * 2 ** (count - 5)) if count >= 5 else 0
    _failures[ip] = (count, time.time() + lock)
    await asyncio.sleep(0.8)  # slow down guessing
    raise HTTPException(status_code=401, detail=message)


@router.get("/api/auth/status")
async def auth_status(request: Request):
    return {
        "required": auth.required(),
        "configured": auth.configured(),
        "logged_in": auth.required() and auth.configured() and _logged_in(request),
        "setup_needs_code": auth.setup_needed() and not _is_this_pc(request),
        "min_length": auth.MIN_LENGTH,
        "days": auth.LOGIN_DAYS,
    }


@router.post("/api/auth/setup")
async def auth_setup(request: Request):
    """First connection after SHOGI_ANALYZER_PASSWORD=TRUE: set the password."""
    if not auth.setup_needed():
        raise HTTPException(status_code=409, detail="パスワードは設定済みです")
    ip = _client_ip(request)
    _check_rate(ip)
    data = await _read_json_or_empty(request)
    password = str(data.get("password") or "")
    if len(password) < auth.MIN_LENGTH:
        raise HTTPException(status_code=400, detail=f"パスワードは {auth.MIN_LENGTH} 文字以上にしてください")
    if not _is_this_pc(request):
        code = str(data.get("code") or "").strip()
        if not auth.setup_code or not hmac.compare_digest(code, auth.setup_code):
            await _fail(ip, "セットアップコードが違います（起動したコンソールに表示されています）")
    await asyncio.to_thread(auth.save_password, password)
    _failures.pop(ip, None)
    return _login_response(request)


@router.post("/api/login")
async def login(request: Request):
    if not auth.required():
        return {"ok": True}
    if auth.setup_needed():
        raise HTTPException(status_code=409, detail="先にパスワードを設定してください")
    ip = _client_ip(request)
    _check_rate(ip)
    data = await _read_json_or_empty(request)
    password = str(data.get("password") or "")
    if not password or not await asyncio.to_thread(auth.verify_password, password):
        await _fail(ip, "パスワードが違います")
    _failures.pop(ip, None)
    return _login_response(request)


@router.post("/api/logout")
async def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth.COOKIE_NAME, path="/")
    return resp


@router.get("/api/app/update_status")
async def app_update_status():
    """Current / latest version (GitHub release) for the update notice in the top bar."""
    return get_update_status()


@router.post("/api/app/update_check")
async def app_update_check():
    """「更新を確認」: ask GitHub now."""
    return await asyncio.to_thread(check_update_now)


@router.get("/api/app/version")
async def app_version():
    return {"version": read_current_version()}


@router.get("/healthz")
async def healthz(request: Request):
    if auth.required() and not _logged_in(request):
        return {"ok": True}  # no details for visitors who are not logged in
    runtime = _runtime(request)
    game = await runtime.current_game()
    return {
        "ok": True,
        "db": "ok",
        "engine": _analysis(request).status_wire(),
        "current_game_id": game.game_id,
    }


@router.get("/api/games")
async def list_games(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    return {"items": _store(request).list_games(limit=limit, offset=offset), "limit": limit, "offset": offset}


@router.post("/api/games")
async def create_game(request: Request):
    data = await _read_json_or_empty(request)
    game = await _runtime(request).create_game(
        title=data.get("title"),
        initial_sfen=data.get("initial_sfen"),
    )
    return {"game": game.to_wire()}


@router.get("/api/games/{game_id}")
async def get_game(request: Request, game_id: str):
    game = _store(request).load_game(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="game not found")
    return {"game": game.to_wire()}


@router.get("/api/engine/options")
async def get_engine_options(request: Request):
    analysis = _analysis(request)
    if not analysis.is_available():
        raise HTTPException(status_code=400, detail="engine is not configured")
    try:
        return await analysis.options_wire()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"engine options unavailable: {exc}") from exc


@router.put("/api/engine/options")
async def put_engine_options(request: Request):
    analysis = _analysis(request)
    runtime = _runtime(request)
    data = await _read_json_or_empty(request)
    values = data.get("values")
    if not isinstance(values, dict):
        raise HTTPException(status_code=400, detail="values must be an object")
    try:
        await analysis.set_options(values)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    async def _resume():
        await analysis.restart_if_enabled_for_game(await runtime.current_game())

    # restart in the background with the new options (if analysis is ON)
    analysis.schedule_sync(_resume)
    return {"ok": True}


@router.get("/api/games/{game_id}/evals")
async def get_game_evals(request: Request, game_id: str):
    return {"items": _store(request).latest_evals(game_id)}


@router.put("/api/games/{game_id}")
async def update_game(request: Request, game_id: str):
    data = await _read_json_or_empty(request)
    runtime = _runtime(request)
    try:
        game = await runtime.load_game(game_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="game not found") from None

    def _mutate(g):
        g.title = (str(data.get("title")).strip() or g.title) if "title" in data else g.title
        if isinstance(data.get("meta"), dict):
            g.meta = data["meta"]
        if isinstance(data.get("ui_state"), dict):
            g.ui_state = data["ui_state"]
        if data.get("current_node_id"):
            g.jump(str(data["current_node_id"]))
        g.touch()

    game, _ = await runtime.mutate(_mutate)
    return {"game": game.to_wire()}


@router.delete("/api/games/{game_id}")
async def delete_game(request: Request, game_id: str):
    deleted = await _runtime(request).delete_game(game_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="game not found")
    return {"ok": True}


@router.post("/api/import")
async def import_game(request: Request):
    """Read a kifu (KIF / KI2 / USI) as a NEW game and make it current.

    source "paste": clipboard text; the game gets the automatic name (kif_YYYYMMDD_hhmmss), so
    the first save asks for a name. source "file": the KIF header title, else the file name.
    Anything that is not a supported kifu -> 415 {"error": "format"}.
    """
    content_type = (request.headers.get("content-type") or "").lower()
    text = ""
    title = None
    source = "file"
    filename = ""
    if "application/json" in content_type:
        data = await _read_json_or_empty(request)
        text = str(data.get("text") or "")
        title = data.get("title")
        source = str(data.get("source") or "file")
        filename = str(data.get("filename") or "")
    else:
        body = await request.body()
        text = body.decode("utf-8", errors="replace")

    wrong_format = JSONResponse(
        status_code=415,
        content={"error": "format", "detail": "形式が違います（対応: KIF / KI2 / USI）"},
    )
    if not text.strip():
        return JSONResponse(status_code=400, content={"error": "empty", "detail": "テキストが空です"})
    fmt = detect_format(text)
    if fmt == "unknown":
        return wrong_format
    if source == "paste":
        title = title or default_game_title()
    try:
        if fmt == "usi":
            game = import_usi_game(normalize_usi_text(text), title=title or filename or default_game_title())
        elif fmt == "kif":
            game = import_kif_game(text, title=title)
        else:
            game = import_kif2_game(text, title=title or filename or None)
    except Exception:
        return wrong_format
    if fmt == "kif2" and len(game.nodes) <= 1:
        return wrong_format  # "▲" somewhere in ordinary text, but no moves could be read
    if fmt == "kif" and game.title == "Imported KIF":
        game.title = filename or default_game_title()
    if fmt == "kif2" and game.title == "Imported KI2":
        game.title = default_game_title()
    await _runtime(request).set_current_game(game)
    return {"format": fmt, "game": game.to_wire()}


@router.get("/api/export/{game_id}")
async def export_game(request: Request, game_id: str, format: str = Query(default="usi")):
    game = _store(request).load_game(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="game not found")
    fmt = (format or "usi").lower()
    try:
        if fmt == "usi":
            text = export_game_to_usi(game)
            media_type = "text/plain; charset=utf-8"
            filename = f"{game_id}.usi.txt"
        elif fmt == "kif":
            text = export_game_to_kif(game)
            media_type = "text/plain; charset=utf-8"
            filename = f"{game_id}.kif"
        elif fmt in {"kif2", "ki2"}:
            text = export_game_to_kif2(game)
            media_type = "text/plain; charset=utf-8"
            filename = f"{game_id}.ki2"
        else:
            raise HTTPException(status_code=400, detail="format must be usi|kif|kif2")
    except NotImplementedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    resp = PlainTextResponse(text, media_type=media_type)
    resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


@router.get("/api/current")
async def current_game_state(request: Request):
    return {"game": await _runtime(request).current_game_wire()}
