"""Entry point shared by native portable packages and source smoke checks."""
from __future__ import annotations

import multiprocessing
import os
from pathlib import Path
import sys

# Divert cpuinfo's multiprocessing workers before importing the installer.
if __name__ == "__main__":
    multiprocessing.freeze_support()

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def self_check() -> int:
    import json
    import tempfile
    import py7zr
    import cpuinfo
    import shogi
    import websockets
    from PIL import Image, ImageDraw, ImageFont
    from app_paths import resource_root, runtime_home
    from server.app.core.gametree import GameTree
    from server.app.services.state_store import StateStore
    root = resource_root()
    required = ["VERSION", ".env.template", "installer/manifest.json", "server/assets_web/index.html",
        "server/assets_web/js/app.js", "server/app/services/share_fonts/ShogiAnalyzerMaru.ttf"]
    for name in required:
        if not (root / name).is_file():
            raise RuntimeError(f"Missing bundled resource: {name}")
    with tempfile.TemporaryDirectory() as temp:
        store = StateStore(Path(temp) / "check.db")
        store.close()
        game = GameTree.new()
        game.play_move(game.current_node_id, "7g7f")
        # Force Pillow's native codec/font loading, not merely its import.
        image = Image.new("RGB", (160, 40))
        font = ImageFont.truetype(str(root / required[-1]), 18)
        ImageDraw.Draw(image).text((0, 0), "先手７六歩", font=font)
        image.save(Path(temp) / "check.png")
        flags = cpuinfo.get_cpu_info().get("flags", [])
    print(json.dumps({"ok": True, "version": (root / "VERSION").read_text().strip(),
        "resources": str(root), "runtime": str(runtime_home()), "cpu_flags": len(flags)}))
    return 0


def main() -> int:
    args = sys.argv[1:]
    if args == ["--self-check"]:
        return self_check()
    if args and args[0] == "--engine-python":
        # Upstream engine builds generate architecture headers with a Python script.
        # Use our embedded interpreter; this does not download or accept any terms.
        import runpy
        if len(args) < 2:
            raise SystemExit("--engine-python requires a local script path")
        sys.argv = args[1:]
        runpy.run_path(sys.argv[0], run_name="__main__")
        return 0
    if args == ["--serve"]:
        from installer.installer_lib import load_env_file, env_file_path
        from app_paths import runtime_home
        load_env_file(env_file_path())
        runtime_home().mkdir(parents=True, exist_ok=True)
        os.chdir(runtime_home())
        import uvicorn
        uvicorn.run("server.app.main:app", host=os.environ.get("SHOGI_ANALYZER_HOST", "127.0.0.1"),
            port=int(os.environ.get("SHOGI_ANALYZER_PORT", "31145")),
            log_level=os.environ.get("SHOGI_ANALYZER_SERVER_LOGLEVEL", "warning"),
            access_log=False, use_colors=False, loop="asyncio", http="h11", ws="websockets")
        return 0
    if args:
        raise SystemExit("Usage: ShogiAnalyzer [--serve | --self-check]")
    from installer.run import main as installer_main
    return installer_main()


if __name__ == "__main__":
    raise SystemExit(main())
