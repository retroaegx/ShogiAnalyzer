from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import auth
from .api import router as api_router
from .paths import data_dir as runtime_data_dir
from .services.update_checker import start_update_checker, stop_update_checker
from .services.analysis_service import AnalysisService
from .services.state_store import RuntimeState, StateStore
from .ws import SessionHub, router as ws_router


def _server_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def create_app() -> FastAPI:
    app = FastAPI(title="Shogi Kifu Analyzer (Minimal)")

    data_dir = runtime_data_dir()
    assets_dir = _server_dir() / "assets_web"
    data_dir.mkdir(parents=True, exist_ok=True)

    store = StateStore(data_dir / "app.db")
    runtime = RuntimeState(store)
    analysis = AnalysisService(store)
    app.state.store = store
    app.state.runtime = runtime
    app.state.analysis = analysis
    app.state.session_hub = SessionHub()

    # (no CORS: the UI is served from this same origin; a permissive CORS policy would let
    # other sites use the login cookie)

    # pages that must be reachable without logging in (login / first-time password setup)
    open_paths = {"/login", "/api/login", "/api/auth/status", "/api/auth/setup", "/healthz"}

    @app.middleware("http")
    async def _require_login(request, call_next):
        path = request.url.path
        if not auth.required() or path in open_paths or auth.token_valid(request.cookies.get(auth.COOKIE_NAME)):
            return await call_next(request)
        if path.startswith("/api/"):
            return JSONResponse({"detail": "login required"}, status_code=401)
        if request.method == "GET" and (path == "/" or path.endswith(".html")):
            return RedirectResponse("/login", status_code=303)
        return PlainTextResponse("login required", status_code=401)

    @app.get("/login", include_in_schema=False)
    async def _login_page():
        return FileResponse(assets_dir / "login.html", headers={"Cache-Control": "no-cache"})

    @app.middleware("http")
    async def _revalidate_assets(request, call_next):
        # Without a Cache-Control header browsers cache index.html / app.js heuristically and
        # can mix an old page with a new script after an update. "no-cache" makes them
        # revalidate every load (a cheap 304 via ETag); board/piece images may be cached.
        response = await call_next(request)
        path = request.url.path
        if not path.startswith("/api/") and "cache-control" not in response.headers:
            response.headers["Cache-Control"] = (
                "public, max-age=86400" if path.startswith("/board-theme/images/") else "no-cache"
            )
        return response

    @app.on_event("startup")
    async def _startup():
        # apply SHOGI_ANALYZER_PASSWORD (discard the saved password when FALSE, setup code when TRUE)
        message = auth.apply_setting()
        if message:
            print(message, flush=True)
        await runtime.startup()
        start_update_checker()

    @app.on_event("shutdown")
    async def _shutdown():
        stop_update_checker()
        await analysis.shutdown()
        store.close()

    app.include_router(api_router)
    app.include_router(ws_router)

    # Keep this mount last so /api/* and /ws remain reachable.
    app.mount("/", StaticFiles(directory=str(assets_dir), html=True), name="static")
    return app


app = create_app()
