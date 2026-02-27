from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from .core.export_kif import export_game_to_kif
from .core.export_kif2 import export_game_to_kif2
from .core.export_usi import export_game_to_usi
from .core.import_kif import import_kif_game
from .core.import_kif2 import import_kif2_game
from .core.import_usi import detect_format
from .services.state_store import RuntimeState, StateStore


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


@router.get("/healthz")
async def healthz(request: Request):
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
    deleted = _store(request).delete_game(game_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="game not found")
    return {"ok": True}


@router.post("/api/import")
async def import_game(request: Request):
    content_type = (request.headers.get("content-type") or "").lower()
    text = ""
    title = None
    if "application/json" in content_type:
        data = await _read_json_or_empty(request)
        text = str(data.get("text") or "")
        title = data.get("title")
    else:
        body = await request.body()
        text = body.decode("utf-8", errors="replace")

    fmt = detect_format(text)
    runtime = _runtime(request)
    try:
        if fmt == "usi":
            game = await runtime.import_usi_text(text=text, title=title)
        elif fmt == "kif":
            game = import_kif_game(text, title=title)
            await runtime.set_current_game(game)
        elif fmt == "kif2":
            game = import_kif2_game(text, title=title)
            await runtime.set_current_game(game)
        else:
            raise HTTPException(status_code=400, detail="Could not detect input format (USI/KIF/KIF2)")
    except NotImplementedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Import failed: {exc}") from exc
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
