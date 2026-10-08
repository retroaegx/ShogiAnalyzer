from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import threading
import time
import venv

from installer_lib import (
    ensure_cloudflared,
    ensure_engine_config,
    ensure_env_file,
    ask_password_protection,
    ensure_requirements,
    fill_env_value,
    guess_eval_dir_from_exe,
    find_existing_cloudflared_config,
    list_existing_tunnels,
    load_env_file,
    portable_path,
    parse_cloudflared_config,
    repo_root,
    run_quick_tunnel,
    runtime_home,
    tr,
)


# engine paths that are filled into .env automatically when left empty
_ENGINE_KEYS = ("SHOGI_ANALYZER_ENGINE_PATH", "SHOGI_ANALYZER_ENGINE_EVAL_DIR")

# set in main() after the settings file (.env) has been read
PORT = 31145
HOST = "127.0.0.1"


def _env_flag(name: str, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw not in {"0", "false", "no", "off"}


def _lan_addresses() -> list[str]:
    """IPv4 addresses other devices on the LAN can use to reach this PC."""
    found: list[str] = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and ip not in found:
                found.append(ip)
    except OSError:
        pass
    return found

def _port_in_use(host: str, port: int) -> bool:
    """True when another program (e.g. ShogiAnalyzer already running) holds the port."""
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as s:
        if os.name == "nt":
            s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            # like uvicorn: connections left in TIME_WAIT after a restart must not count as "in use"
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
        except OSError:
            return True
    return False

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


class _Tee:
    """Write to the console and append to the console log (timestamped, ANSI stripped)."""

    def __init__(self, stream, fh):
        self._stream = stream
        self._fh = fh
        self._at_line_start = True
        self._lock = threading.Lock()

    def write(self, s: str) -> int:
        with self._lock:
            try:
                self._stream.write(s)
            except Exception:
                pass
            text = _ANSI.sub("", s).replace("\r\n", "\n")
            out = []
            for part in text.splitlines(keepends=True):
                if self._at_line_start:
                    out.append(datetime.now().strftime("[%H:%M:%S] "))
                out.append(part)
                self._at_line_start = part.endswith("\n")
            self._fh.write("".join(out))
            self._fh.flush()
        return len(s)

    def flush(self) -> None:
        try:
            self._stream.flush()
        except Exception:
            pass
        self._fh.flush()

    def isatty(self) -> bool:
        return self._stream.isatty()

    @property
    def encoding(self):
        return getattr(self._stream, "encoding", "utf-8")


def console_log_path() -> Path:
    return runtime_home() / "server" / "data" / "console.log"


def _setup_console_log() -> Path:
    """Mirror everything shown in the run.bat window into <runtime>/console.log.

    The first (system python) process starts a fresh log for this launch; the venv
    re-run and its children append to the same file.
    """
    path = Path(os.environ.get("SHOGI_ANALYZER_CONSOLE_LOG") or console_log_path())
    fresh = "SHOGI_ANALYZER_CONSOLE_LOG" not in os.environ
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(path, "w" if fresh else "a", encoding="utf-8", errors="replace")
    if fresh:
        version = (repo_root() / "VERSION").read_text(encoding="utf-8").strip() if (repo_root() / "VERSION").exists() else "?"
        fh.write(f"===== ShogiAnalyzer v{version}  {datetime.now():%Y-%m-%d %H:%M:%S} =====\n")
        fh.flush()
    os.environ["SHOGI_ANALYZER_CONSOLE_LOG"] = str(path)
    sys.stdout = _Tee(sys.stdout, fh)
    sys.stderr = _Tee(sys.stderr, fh)
    return path


def _pump(stream) -> None:
    # forward a child's output through the tee'd sys.stdout
    for line in stream:
        sys.stdout.write(line)


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


def _venv_dir() -> Path:
    return runtime_home() / ".venv"


def _ensure_venv() -> Path:
    venv_dir = _venv_dir()
    py = _venv_python(venv_dir)
    if py.exists():
        return py
    print(tr(f"[installer] Python の仮想環境を作成しています: {venv_dir}", f"[installer] Creating virtual environment: {venv_dir}"))
    venv.EnvBuilder(with_pip=True, clear=False, upgrade=False).create(venv_dir)
    return py


def _is_running_in_venv() -> bool:
    # Compare the environment prefix, not the executable: on Linux .venv/bin/python is a
    # symlink to the system python, so resolving both paths made the system python look
    # like the venv (pip then hit "externally-managed-environment").
    try:
        return Path(sys.prefix).resolve() == _venv_dir().resolve()
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
        HOST,
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
    # values from the environment / .env win over the saved engine config
    merged = dict(env)
    merged.update(os.environ)
    merged["PYTHONUNBUFFERED"] = "1"
    # the server's output is read as UTF-8 (Windows would otherwise send cp932 -> garbled text)
    merged["PYTHONIOENCODING"] = "utf-8"
    print(tr(f"[installer] サーバーを起動しています: http://localhost:{PORT}", f"[installer] Starting server: http://localhost:{PORT}"))
    proc = subprocess.Popen(
        cmd,
        cwd=str(repo_root()),
        env=merged,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    # server warnings/errors go to the window and console.log
    threading.Thread(target=_pump, args=(proc.stdout,), daemon=True).start()
    return proc


def main() -> int:
    global PORT, HOST
    root = repo_root()
    ansi_ok = _enable_windows_ansi()
    log_path = _setup_console_log()

    # settings file: <runtime>/.env (created from .env.template on first run)
    env_path, env_created = ensure_env_file(root)
    # the first (system python) process creates it; tell the venv re-run so it can say so
    if env_created:
        os.environ["SHOGI_ANALYZER_ENV_CREATED"] = "1"
    env_created = env_created or os.environ.get("SHOGI_ANALYZER_ENV_CREATED") == "1"
    # engine keys given as real OS environment variables (not from .env): never copied into .env
    from_env_file = set(filter(None, (os.environ.get("SHOGI_ANALYZER_ENV_LOADED") or "").split(",")))
    os_engine_keys = {k for k in _ENGINE_KEYS if os.environ.get(k) and k not in from_env_file}
    applied = load_env_file(env_path)
    # the venv re-run inherits the parent's .env values; remember which keys those were
    os.environ["SHOGI_ANALYZER_ENV_LOADED"] = ",".join(sorted(from_env_file | set(applied)))
    PORT = int(os.environ.get("SHOGI_ANALYZER_PORT") or 31145)
    HOST = (os.environ.get("SHOGI_ANALYZER_HOST") or "127.0.0.1").strip()
    public_url = (os.environ.get("SHOGI_ANALYZER_PUBLIC_URL") or "").strip().rstrip("/")

    if _is_running_in_venv():
        version_file = repo_root() / "VERSION"
        version = version_file.read_text(encoding="utf-8").strip() if version_file.exists() else "?"
        print(f"[installer] ShogiAnalyzer v{version}")
        print(tr(f"[installer] ログ  : {log_path}", f"[installer] Console log: {log_path}"))
        created = tr("  （新規作成）", "  (created)") if env_created else ""
        print(tr(f"[installer] 設定  : {env_path}{created}", f"[installer] Settings   : {env_path}{created}"))
    py = _ensure_venv()
    if not py.exists():
        print(tr(f"[installer] エラー: 仮想環境の Python が見つかりません: {py}", f"[installer] ERROR: venv python not found: {py}"))
        return 1

    if not _is_running_in_venv():
        return _rerun_in_venv(py)

    # stop here with a clear message instead of a bind error after all the setup
    if _port_in_use(HOST, PORT):
        print(tr(
            f"\n[installer] エラー: ポート {PORT} はすでに使われています。\n"
            "       ShogiAnalyzer がすでに起動しているか、別のアプリが使っています。\n"
            "       起動中のものを終了するか、.env の SHOGI_ANALYZER_PORT を別の番号にしてから起動し直してください。",
            f"\n[installer] ERROR: port {PORT} is already in use.\n"
            "       ShogiAnalyzer may already be running, or another app uses the port.\n"
            "       Stop it, or set another SHOGI_ANALYZER_PORT in .env, then start again.",
        ))
        return 4

    # first run: password protection ON/OFF (the password itself is set in the browser)
    ask_password_protection(env_path)

    # 1) Python deps (WS含む) は起動時に必ず整える。
    if not ensure_requirements(root):
        print(tr("[installer] 致命的エラー: Python 環境を準備できませんでした", "[installer] FATAL: could not prepare python environment"))
        return 2

    # 2) Quick Tunnel は「固定アドレス未設定」かつ「TUNNEL=TRUE」のときだけ使う
    want_tunnel = not public_url and _env_flag("SHOGI_ANALYZER_TUNNEL", True)
    cloudflared = ensure_cloudflared(root) if want_tunnel else None

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
                print(tr("\n[installer] 既存の Cloudflare Tunnel 設定があります", "\n[installer] Existing Cloudflare Tunnel config found"))
                print(tr(f"  設定     : {p}", f"  config : {p}"))
                if tunnel_name:
                    print(tr(f"  トンネル : {tunnel_name}", f"  tunnel : {tunnel_name}"))
                print(tr("  ホスト名:", "  hostnames:"))
                for h in hostnames:
                    print(f"    https://{h}")

        existing = list_existing_tunnels(cloudflared)
        if existing:
            print(tr("\n[installer] ログイン済みの Cloudflare Tunnel", "\n[installer] Existing Cloudflare Tunnels (logged-in)"))
            print(existing)

    # 3) エンジン未設定なら、ここでセットアップ（manifest or manual path）
    try:
        env = ensure_engine_config(root)
    except RuntimeError as exc:
        print(f"\n[installer] {exc}")
        return 3

    effective = {**env, **{k: v for k, v in os.environ.items() if k.startswith("SHOGI_ANALYZER_ENGINE_")}}
    # the evaluation folder the server would auto-detect next to the exe
    if effective.get("SHOGI_ANALYZER_ENGINE_PATH") and not effective.get("SHOGI_ANALYZER_ENGINE_EVAL_DIR"):
        guessed = guess_eval_dir_from_exe(Path(effective["SHOGI_ANALYZER_ENGINE_PATH"]))
        if guessed and guessed.exists():
            effective["SHOGI_ANALYZER_ENGINE_EVAL_DIR"] = str(guessed)

    # empty engine entries in .env get the paths actually in use (visible and editable there);
    # values typed by the user or given as OS environment variables are left alone
    for key in _ENGINE_KEYS:
        # relative to the .env folder when inside it, so the folder can be moved as a whole
        value = portable_path(effective.get(key) or "", env_path.parent)
        if key not in os_engine_keys and fill_env_value(env_path, key, value):
            print(tr(f"[installer] .env に自動設定: {key}={value}", f"[installer] Filled in .env: {key}={value}"))

    if effective.get("SHOGI_ANALYZER_ENGINE_CMD") or effective.get("SHOGI_ANALYZER_ENGINE_PATH"):
        print(tr("\n[installer] 解析エンジン", "\n[installer] Engine config"))
        if effective.get("SHOGI_ANALYZER_ENGINE_CMD"):
            print(tr(f"  コマンド: {effective['SHOGI_ANALYZER_ENGINE_CMD']}", f"  cmd : {effective['SHOGI_ANALYZER_ENGINE_CMD']}"))
        if effective.get("SHOGI_ANALYZER_ENGINE_PATH"):
            print(tr(f"  本体    : {effective['SHOGI_ANALYZER_ENGINE_PATH']}", f"  path: {effective['SHOGI_ANALYZER_ENGINE_PATH']}"))
        if effective.get("SHOGI_ANALYZER_ENGINE_EVAL_DIR"):
            print(tr(f"  評価関数: {effective['SHOGI_ANALYZER_ENGINE_EVAL_DIR']}", f"  eval: {effective['SHOGI_ANALYZER_ENGINE_EVAL_DIR']}"))

    # 4) サーバ起動
    server = _run_server(env)
    time.sleep(1.5)
    if server.poll() is not None:
        # the reason (bind error etc.) was printed just above by the server
        print(tr("\n[installer] エラー: サーバーの起動に失敗しました（上のメッセージを確認してください）",
                 "\n[installer] ERROR: the server failed to start (see the message above)"))
        return 5

    # 5) Quick Tunnel（固定アドレスが無く、SHOGI_ANALYZER_TUNNEL=TRUE のとき）
    tunnel_proc = None
    tunnel_url = None
    if want_tunnel and cloudflared:
        tunnel_proc, tunnel_url = run_quick_tunnel(cloudflared, PORT)

    print(tr("\n[installer] アドレス", "\n[installer] URLs"))
    print(f"  local : {_red(f'http://localhost:{PORT}', ansi_ok)}")
    if HOST in {"0.0.0.0", "::"}:
        for ip in _lan_addresses():
            print(f"  lan   : http://{ip}:{PORT}")
    if public_url:
        print(f"  public: {_red(public_url, ansi_ok)}  " + tr("（固定アドレス / .env の SHOGI_ANALYZER_PUBLIC_URL）", "(fixed address / SHOGI_ANALYZER_PUBLIC_URL in .env)"))
    elif tunnel_url:
        print(f"  public: {_red(tunnel_url, ansi_ok)}  " + tr("（Quick Tunnel: 起動ごとに変わります）", "(Quick Tunnel: changes on every start)"))
    elif want_tunnel:
        tunnel_log = runtime_home() / "server" / "data" / "cloudflared_quick_tunnel.log"
        print(tr(
            "  public: (失敗)  ※ cloudflared が失敗しました。\n"
            f"          ログ: {tunnel_log}\n"
            "          UDP禁止環境などでは --protocol http2 が必要なことがあります。\n"
            "          また、既存の ~/.cloudflared/config.yml(config.yaml) がある環境では Quick Tunnel が動かないことがあります。",
            "  public: (failed)  * cloudflared failed.\n"
            f"          log: {tunnel_log}\n"
            "          Networks that block UDP may need --protocol http2.\n"
            "          Quick Tunnel may not work when ~/.cloudflared/config.yml (config.yaml) exists.",
        ))
    else:
        print(tr("  public: (なし)  ※ .env で SHOGI_ANALYZER_TUNNEL=FALSE", "  public: (none)  * SHOGI_ANALYZER_TUNNEL=FALSE in .env"))
    print(tr(f"  ログ  : {log_path}", f"  log   : {log_path}"))
    print(tr(f"  設定  : {env_path}", f"  settings: {env_path}"))

    # 6) keep
    try:
        rc = server.wait()
        if tunnel_proc and tunnel_proc.poll() is None:
            tunnel_proc.terminate()
        return int(rc or 0)
    except KeyboardInterrupt:
        print(tr("\n[installer] 停止しています ...", "\n[installer] stopping..."))
        server.terminate()
        if tunnel_proc and tunnel_proc.poll() is None:
            tunnel_proc.terminate()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
