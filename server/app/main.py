from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import auth
from .api import router as api_router
from .paths import data_dir as runtime_data_dir
from .services.update_checker import start_update_checker, stop_update_checker
from .services.analysis_service import AnalysisService
from .services.state_store import RuntimeState, StateStore
from .ws import SessionHub, router as ws_router


# served by StaticFiles; Python does not know this extension on every OS
mimetypes.add_type("application/manifest+json", ".webmanifest")


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
    open_paths = {"/login", "/api/login", "/api/auth/status", "/api/auth/setup", "/healthz",
                  # app install (PWA): the browser fetches these without the login cookie
                  "/manifest.webmanifest", "/sw.js"}

    @app.middleware("http")
    async def _require_login(request, call_next):
        path = request.url.path
        if not auth.required() or path in open_paths or path.startswith("/icons/") or auth.token_valid(request.cookies.get(auth.COOKIE_NAME)):
            return await call_next(request)
        if path.startswith("/api/"):
            return JSONResponse({"detail": "login required"}, status_code=401)
        if request.method == "GET" and (path == "/" or path.endswith(".html")):
            return RedirectResponse("/login", status_code=303)
        return PlainTextResponse("login required", status_code=401)

    @app.get("/login", include_in_schema=False)
    async def _login_page():
        return FileResponse(assets_dir / "login.html", headers={"Cache-Control": "no-store"})

    def _asset_token() -> str:
        """Changes whenever a script or the stylesheet changes (cache busting for app.js / app.css)."""
        files = [assets_dir / "app.css", *sorted((assets_dir / "js").rglob("*.js"))]
        stamp = "|".join(f"{f.name}:{f.stat().st_mtime_ns}:{f.stat().st_size}" for f in files if f.exists())
        return hashlib.sha1(stamp.encode()).hexdigest()[:10]

    @app.get("/", include_in_schema=False)
    @app.get("/index.html", include_in_schema=False)
    async def _index_page():
        # Proxies/CDNs in front (e.g. Cloudflare) may keep .js/.css for hours whatever we send;
        # versioned URLs make every update load the matching script and stylesheet.
        token = _asset_token()
        html = (assets_dir / "index.html").read_text(encoding="utf-8")
        html = html.replace('href="/app.css"', f'href="/app.css?v={token}"').replace('src="/js/app.js"', f'src="/js/app.js?v={token}"')
        return HTMLResponse(html, headers={"Cache-Control": "no-store"})

    @app.middleware("http")
    async def _revalidate_assets(request, call_next):
        # Without a Cache-Control header browsers cache index.html / app.js heuristically and
        # can mix an old page with a new script after an update. "no-cache" makes them
        # revalidate every load (a cheap 304 via ETag); board/piece images may be cached.
        response = await call_next(request)
        path = request.url.path
        if not path.startswith("/api/") and "cache-control" not in response.headers:
            if path.startswith(("/board-theme/images/", "/icons/")):
                response.headers["Cache-Control"] = "public, max-age=86400"
            elif path.endswith((".js", ".css", ".html", ".webmanifest")) or path == "/":
                # scripts / styles must always match the page: not stored by browsers or CDNs
                response.headers["Cache-Control"] = "no-store"
            else:
                response.headers["Cache-Control"] = "no-cache"
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
