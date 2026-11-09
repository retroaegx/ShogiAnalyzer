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
    import websockets
    from PIL import Image, ImageDraw, ImageFont
    from app_paths import resource_root, runtime_home
    from server.app.core.gametree import GameTree
    from server.app.services.state_store import StateStore
    from https_client import create_https_context
    import ssl
    https = create_https_context()
    if https.verify_mode != ssl.CERT_REQUIRED or not https.check_hostname:
        raise RuntimeError('HTTPS certificate / hostname verification is disabled')
    root = resource_root()
    import importlib
    library_paths = {}
    probes = {}
    for name in ('py7zr','bcj','inflate64','multivolumefile','pyppmd'):
        module = importlib.import_module(name)
        path = Path(module.__file__)
        if getattr(sys, 'frozen', False) and (not path.is_file() or path.suffix != '.py'):
            raise RuntimeError(f'Library is not externally replaceable: {name}: {path}')
        library_paths[name] = str(path)
        probes[name] = getattr(module, 'SHOGI_REPLACEMENT_PROBE', None)
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
        # Exercise extraction with the same library used by engine setup.
        sample = Path(temp) / 'sample.txt'
        sample.write_text('archive roundtrip', encoding='utf-8')
        archive = Path(temp) / 'check.7z'
        with py7zr.SevenZipFile(archive, 'w') as package:
            package.write(sample, 'sample.txt')
        with py7zr.SevenZipFile(archive, 'r') as package:
            package.extractall(Path(temp) / 'extracted')
        if (Path(temp) / 'extracted/sample.txt').read_text() != 'archive roundtrip':
            raise RuntimeError('7z roundtrip failed')
        flags = cpuinfo.get_cpu_info().get("flags", [])
    print(json.dumps({"ok": True, "version": (root / "VERSION").read_text().strip(),
        "resources": str(root), "runtime": str(runtime_home()), "cpu_flags": len(flags), "replaceable_libraries":library_paths, "replacement_probes":probes,
        "https_verification":True}))
    return 0


def main() -> int:
    # PyInstaller's isolated interpreter ignores PYTHONIOENCODING. The launcher
    # decodes server pipes as UTF-8, so configure the actual pipe writers here.
    # Leave native console streams alone; Python uses the Windows Unicode API.
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and not stream.isatty() and hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='backslashreplace', write_through=True)
    args = sys.argv[1:]
    if args and args[0] in ('--prepare-update', '--update-job', '--cleanup-update'):
        from installer.update import main as update_main
        return update_main(args)
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
        from app_paths import installation_root
        from installer.update_lock import installation_lock, InstallationBusy
        try:
            with installation_lock(installation_root(), shared=True):
                uvicorn.run("server.app.main:app", host=os.environ.get("SHOGI_ANALYZER_HOST", "127.0.0.1"),
                    port=int(os.environ.get("SHOGI_ANALYZER_PORT", "31145")),
                    log_level=os.environ.get("SHOGI_ANALYZER_SERVER_LOGLEVEL", "warning"),
                    access_log=False, use_colors=False, loop="asyncio", http="h11", ws="websockets")
        except InstallationBusy as exc:
            print(str(exc), file=sys.stderr); return 2
        return 0
    if args:
        raise SystemExit("Usage: ShogiAnalyzer [--serve | --self-check]")
    from installer.run import main as installer_main
    return installer_main()


if __name__ == "__main__":
    raise SystemExit(main())
