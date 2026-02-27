from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import time
import venv

from installer_lib import (
    ensure_cloudflared,
    ensure_engine_config,
    ensure_requirements,
    find_existing_cloudflared_config,
    list_existing_tunnels,
    parse_cloudflared_config,
    repo_root,
    run_quick_tunnel,
)


PORT = 31145


def _enable_windows_ansi() -> bool:
    """Enable ANSI escape sequences on Windows console (best-effort)."""

    if os.name != "nt":
        return True
    if not sys.stdout.isatty():
        return False
    try:
        import ctypes  # type: ignore

        kernel32 = ctypes.windll.kernel32
        h = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(h, ctypes.byref(mode)) == 0:
            return False
        # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        if kernel32.SetConsoleMode(h, mode.value | 0x0004) == 0:
            return False
        return True
    except Exception:
        return False


def _red(text: str, enabled: bool) -> str:
    if not enabled:
        return text
    return f"\x1b[31m{text}\x1b[0m"


def _venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _ensure_venv(root: Path) -> Path:
    venv_dir = root / ".venv"
    py = _venv_python(venv_dir)
    if py.exists():
        return py
    print(f"[installer] Creating virtual environment: {venv_dir}")
    venv.EnvBuilder(with_pip=True, clear=False, upgrade=False).create(venv_dir)
    return py


def _is_running_in_venv(root: Path) -> bool:
    venv_dir = root / ".venv"
    py = _venv_python(venv_dir)
    try:
        return Path(sys.executable).resolve() == py.resolve()
    except Exception:
        return False


def _rerun_in_venv(py: Path) -> int:
    # Re-exec the same entry inside the venv so imports/pip target the venv.
    args = [str(py), str(Path(__file__).resolve())] + sys.argv[1:]
    return subprocess.call(args, cwd=str(repo_root()))


def _run_server(env: dict[str, str]) -> subprocess.Popen:
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "server.app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(PORT),
        # Keep the console clean: suppress INFO logs and HTTP access logs.
        "--log-level",
        (os.environ.get("SHOGI_ANALYZER_SERVER_LOGLEVEL") or "warning"),
        "--no-access-log",
        "--no-use-colors",
    ]
    if os.environ.get("SHOGI_ANALYZER_RELOAD", "").strip().lower() in {"1", "true", "yes", "on"}:
        cmd.append("--reload")
    merged = os.environ.copy()
    merged.update(env)
    print(f"[installer] Starting server: http://localhost:{PORT}")
    return subprocess.Popen(cmd, cwd=str(repo_root()), env=merged)


def main() -> int:
    root = repo_root()
    ansi_ok = _enable_windows_ansi()
    py = _ensure_venv(root)
    if not py.exists():
        print(f"[installer] ERROR: venv python not found: {py}")
        return 1

    if not _is_running_in_venv(root):
        return _rerun_in_venv(py)

    # 1) Python deps (WS含む) は起動時に必ず整える。
    if not ensure_requirements(root):
        print("[installer] FATAL: could not prepare python environment")
        return 2

    # 2) cloudflared を準備（Quick Tunnel を動かすため）
    cloudflared = ensure_cloudflared(root)

    if cloudflared:
        # If the user already has a locally-managed tunnel set up, show hostnames as well.
        # (Quick Tunnel uses trycloudflare.com; existing tunnels may map to the user's domain.)
        cfg_paths = find_existing_cloudflared_config()
        for p in cfg_paths:
            try:
                info = parse_cloudflared_config(p)
            except Exception:
                continue
            hostnames = info.get("hostnames") or []
            tunnel_name = info.get("tunnel")
            if hostnames:
                print("\n[installer] Existing Cloudflare Tunnel config found")
                print(f"  config : {p}")
                if tunnel_name:
                    print(f"  tunnel : {tunnel_name}")
                print("  hostnames:")
                for h in hostnames:
                    print(f"    https://{h}")

        existing = list_existing_tunnels(cloudflared)
        if existing:
            print("\n[installer] Existing Cloudflare Tunnels (logged-in)")
            print(existing)

    # 3) エンジン未設定なら、ここでセットアップ（manifest or manual path）
    try:
        env = ensure_engine_config(root)
    except RuntimeError as exc:
        print(f"\n[installer] {exc}")
        return 3

    if env.get("SHOGI_ANALYZER_ENGINE_CMD") or env.get("SHOGI_ANALYZER_ENGINE_PATH"):
        print("\n[installer] Engine config")
        if env.get("SHOGI_ANALYZER_ENGINE_CMD"):
            print(f"  cmd : {env['SHOGI_ANALYZER_ENGINE_CMD']}")
        if env.get("SHOGI_ANALYZER_ENGINE_PATH"):
            print(f"  path: {env['SHOGI_ANALYZER_ENGINE_PATH']}")
        if env.get("SHOGI_ANALYZER_ENGINE_EVAL_DIR"):
            print(f"  eval: {env['SHOGI_ANALYZER_ENGINE_EVAL_DIR']}")

    # 4) サーバ起動
    server = _run_server(env)
    time.sleep(0.4)

    # 5) Quick Tunnel（既定: ON。止めたい場合は SHOGI_ANALYZER_TUNNEL=0）
    tunnel_flag = (os.environ.get("SHOGI_ANALYZER_TUNNEL") or "1").strip().lower()
    want_tunnel = tunnel_flag not in {"0", "false", "no", "off"}
    tunnel_proc = None
    public_url = None
    if want_tunnel and cloudflared:
        tunnel_proc, public_url = run_quick_tunnel(cloudflared, PORT)

    print("\n[installer] URLs")
    print(f"  local : {_red(f'http://localhost:{PORT}', ansi_ok)}")
    if public_url:
        print(f"  public: {_red(public_url, ansi_ok)}")
    elif want_tunnel:
        print(
            "  public: (failed)  ※ cloudflared が失敗しました。\n"
            "          ログ: server/data/cloudflared_quick_tunnel.log\n"
            "          UDP禁止環境などでは --protocol http2 が必要なことがあります。\n"
            "          また、既存の ~/.cloudflared/config.yml(config.yaml) がある環境では Quick Tunnel が動かないことがあります。"
        )

    # 6) keep
    try:
        rc = server.wait()
        if tunnel_proc and tunnel_proc.poll() is None:
            tunnel_proc.terminate()
        return int(rc or 0)
    except KeyboardInterrupt:
        print("\n[installer] stopping...")
        server.terminate()
        if tunnel_proc and tunnel_proc.poll() is None:
            tunnel_proc.terminate()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
