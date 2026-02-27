from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api import router as api_router
from .services.analysis_service import AnalysisService
from .services.state_store import RuntimeState, StateStore
from .ws import SessionHub, router as ws_router


def _server_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def create_app() -> FastAPI:
    app = FastAPI(title="Shogi Kifu Analyzer (Minimal)")

    data_dir = _server_dir() / "data"
    assets_dir = _server_dir() / "assets_web"
    data_dir.mkdir(parents=True, exist_ok=True)

    store = StateStore(data_dir / "app.db")
    runtime = RuntimeState(store)
    analysis = AnalysisService(store)
    app.state.store = store
    app.state.runtime = runtime
    app.state.analysis = analysis
    app.state.session_hub = SessionHub()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def _startup():
        await runtime.startup()

    @app.on_event("shutdown")
    async def _shutdown():
        await analysis.shutdown()
        store.close()

    app.include_router(api_router)
    app.include_router(ws_router)

    # Keep this mount last so /api/* and /ws remain reachable.
    app.mount("/", StaticFiles(directory=str(assets_dir), html=True), name="static")
    return app


app = create_app()
