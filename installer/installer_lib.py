from __future__ import annotations

import hashlib
import json
import os
import re
import platform as py_platform
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

try:
    import cpuinfo  # type: ignore
except Exception:
    cpuinfo = None


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


# ---------- console language ----------
def _ui_is_japanese() -> bool:
    """Japanese Windows display language / ja locale -> Japanese console messages, else English."""
    forced = (os.environ.get("SHOGI_ANALYZER_LANG") or "").strip().lower()
    if forced:
        return forced.startswith("ja")
    if os.name == "nt":
        try:
            import ctypes

            return (ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF) == 0x11  # LANG_JAPANESE
        except Exception:
            pass
    for key in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(key)
        if value:
            return value.lower().startswith("ja")
    try:
        import locale

        return (locale.getlocale()[0] or "").lower().startswith(("ja", "japanese"))
    except Exception:
        return False


UI_JA = _ui_is_japanese()
# the server (started from run.py) prints in the same language
os.environ.setdefault("SHOGI_ANALYZER_LANG", "ja" if UI_JA else "en")


def tr(ja: str, en: str) -> str:
    return ja if UI_JA else en


def run_streamed(cmd: list[str], cwd: str | None = None, env: dict[str, str] | None = None) -> int:
    """Run a command and forward its output line by line through sys.stdout.

    Child processes write to the console directly, so without this their output
    would bypass the console log (sys.stdout is tee'd to console.log by run.py).
    """
    if env is None:
        env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")  # read as UTF-8 below
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        sys.stdout.write(line)
    return proc.wait()


def runtime_home() -> Path:
    """Folder the generated/downloaded files go under (.venv, engines/, tools/, server/data/, .env).

    The repository folder itself, as in the original layout; everything generated is
    listed in .gitignore.
    """
    return repo_root()


def _server_data_dir(root: Path) -> Path:
    return root / "server" / "data"


# ---------- settings file (.env) ----------
# keys whose relative values are resolved against the folder of the .env file
_ENV_PATH_KEYS = {"SHOGI_ANALYZER_ENGINE_PATH", "SHOGI_ANALYZER_ENGINE_EVAL_DIR"}


def portable_path(path: str | Path, base: Path) -> str:
    """Path to store in .env / engine_config.json: relative to base (with "/") when it lies
    inside base, so the whole folder can be moved; otherwise absolute (with "/")."""
    if not str(path).strip():
        return ""
    p = Path(path).expanduser()
    try:
        return p.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return p.resolve().as_posix()


def resolve_portable(value: str, base: Path) -> str:
    """Inverse of portable_path: relative values are taken from base."""
    if not (value or "").strip():
        return ""
    p = Path(value).expanduser()
    return str(p if p.is_absolute() else (base / p).resolve())


def env_file_path() -> Path:
    """<repo>/.env (ignored by git)."""
    return runtime_home() / ".env"


def ensure_env_file(root: Path) -> tuple[Path, bool]:
    """Create <runtime>/.env from .env.template on first run. Returns (path, created)."""
    path = env_file_path()
    if path.exists():
        return path, False
    template = root / ".env.template"
    path.parent.mkdir(parents=True, exist_ok=True)
    if template.exists():
        shutil.copyfile(template, path)
    else:
        path.write_text("# ShogiAnalyzer settings\n", encoding="utf-8")
    return path, True


def read_env_value(path: Path, key: str) -> str:
    """Value of KEY in the settings file ("" when missing or empty)."""
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return ""
    for raw in lines:
        line = raw.strip()
        if line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() == key:
            return v.strip().strip("'\"")
    return ""


def fill_env_value(path: Path, key: str, value: str) -> bool:
    """Write KEY=value into the settings file if KEY is missing or empty there.

    Values the user typed are never overwritten. Returns True when the file changed.
    """
    if not value or read_env_value(path, key):
        return False
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        lines = []
    for i, raw in enumerate(lines):
        line = raw.strip()
        if not line.startswith("#") and "=" in line and line.split("=", 1)[0].strip() == key:
            lines[i] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def load_env_file(path: Path) -> dict[str, str]:
    """Apply KEY=VALUE lines from the settings file to os.environ.

    - variables already set in the real environment win
    - empty values are ignored (= use the default / automatic setting)
    - relative paths are taken from the folder of the .env file
    """
    applied: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        return applied
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        if not key or not value or key in os.environ:
            continue
        if key in _ENV_PATH_KEYS:
            p = Path(value).expanduser()
            if not p.is_absolute():
                p = (path.parent / p).resolve()
            value = str(p)
        os.environ[key] = value
        applied[key] = value
    return applied


def _db_path(root: Path) -> Path:
    return _server_data_dir(root) / "app.db"


def load_manifest(root: Path) -> dict:
    p = root / "installer" / "manifest.json"
    return json.loads(p.read_text(encoding="utf-8"))


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _download(url: str, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".tmp")
    with urllib.request.urlopen(url) as r, tmp.open("wb") as f:
        shutil.copyfileobj(r, f)
    tmp.replace(dst)


def _log_installer_event(root: Path, *, kind: str, payload: dict) -> None:
    db_path = _db_path(root)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS installer_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              created_at TEXT NOT NULL,
              kind TEXT NOT NULL,
              payload_json TEXT NOT NULL
            );
            """
        )
        conn.execute(
            "INSERT INTO installer_events (created_at, kind, payload_json) VALUES (?,?,?)",
            (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), kind, json.dumps(payload, ensure_ascii=False)),
        )
        conn.commit()
    finally:
        conn.close()


def _platform_key() -> str:
    # This repo is currently Windows/Linux amd64 only.
    if os.name == "nt":
        return "windows_amd64"
    return "linux_amd64"


def ensure_requirements(root: Path) -> bool:
    """Install server requirements into the active venv (current python).

    run.bat は system python で起動され得るので、installer/run.py が venv python に
    リランしてから、この関数を呼ぶ前提。
    """
    req = root / "server" / "requirements.txt"
    if not req.exists():
        print(tr(f"[installer] エラー: requirements.txt が見つかりません: {req}", f"[installer] ERROR: requirements not found: {req}"))
        return False

    marker_dir = Path(sys.prefix)
    marker_dir.mkdir(parents=True, exist_ok=True)
    marker = marker_dir / ".requirements_sha256"
    want = _sha256_file(req)
    have = marker.read_text(encoding="utf-8").strip() if marker.exists() else ""
    if have == want:
        return True

    print(tr("[installer] Python のパッケージをインストールしています（.venv）...", "[installer] Installing Python requirements into .venv ..."))
    rc = run_streamed([sys.executable, "-m", "pip", "install", "-U", "pip"], cwd=str(root))
    if rc != 0:
        print(tr("[installer] エラー: pip の更新に失敗しました", "[installer] ERROR: pip upgrade failed"))
        return False
    # Always upgrade to ensure extras/websocket deps are installed even if uvicorn was previously installed without extras.
    rc = run_streamed([sys.executable, "-m", "pip", "install", "--upgrade", "-r", str(req)], cwd=str(root))
    if rc != 0:
        print(tr("[installer] エラー: Python パッケージのインストールに失敗しました", "[installer] ERROR: requirements install failed"))
        return False
    marker.write_text(want + "\n", encoding="utf-8")
    return True


def ensure_cloudflared(root: Path) -> Path | None:
    """Return path to cloudflared binary, downloading it if needed."""
    manifest = load_manifest(root)
    urls = manifest.get("cloudflared") or {}
    url = urls.get(f"{_platform_key()}_url")
    if not url:
        print(tr("[installer] cloudflared: この環境用のダウンロード先がないため Quick Tunnel は使えません", "[installer] cloudflared: manifest has no download url; Quick Tunnel disabled"))
        return None

    bin_dir = runtime_home() / "tools" / "cloudflared"
    bin_dir.mkdir(parents=True, exist_ok=True)
    exe_name = "cloudflared.exe" if os.name == "nt" else "cloudflared"
    dst = bin_dir / exe_name
    if dst.exists() and dst.stat().st_size > 0:
        return dst

    print(tr("[installer] cloudflared をダウンロードしています ...", "[installer] Downloading cloudflared ..."))
    try:
        _download(str(url), dst)
        if os.name != "nt":
            dst.chmod(dst.stat().st_mode | 0o111)
        _log_installer_event(root, kind="download", payload={"asset": "cloudflared", "url": url, "path": str(dst)})
        return dst
    except Exception as exc:
        print(tr(f"[installer] cloudflared のダウンロードに失敗しました: {exc}", f"[installer] cloudflared download failed: {exc}"))
        _log_installer_event(root, kind="download_error", payload={"asset": "cloudflared", "url": url, "error": str(exc)})
        return None


def list_existing_tunnels(cloudflared: Path) -> str | None:
    """Best-effort: list locally-managed tunnels (requires login)."""
    try:
        res = subprocess.run(
            [str(cloudflared), "tunnel", "list"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=6,
        )
        if res.returncode != 0:
            return None
        out = (res.stdout or "").strip()
        return out if out else None
    except Exception:
        return None


def _print_license(license_name: str, links: list[tuple[str, str]]) -> None:
    """License line + links (terms / license pages) of a third-party download."""
    print(tr(f"  ライセンス: {license_name or '配布元に明記なし'}", f"  license: {license_name or 'not stated by the distributor'}"))
    for label_ja_en, url in links:
        if url:
            ja, en = label_ja_en.split("|")
            print(tr(f"  {ja}: {url}", f"  {en}: {url}"))


def _prompt_consent(what_ja: str, what_en: str) -> bool:
    """y only when the user agrees to the distributor's terms / license (default: no)."""
    print(tr(
        f"  ※ {what_ja}の利用の範囲は、配布元の規約・ライセンス条項に従います。\n"
        "     上のリンク先の内容に同意する場合のみ y を入力してください（同意しない場合は Enter / n）。",
        f"  * Use of this {what_en} is governed by the distributor's terms and license.\n"
        "    Enter y only if you agree to them (see the links above); Enter / n to decline.",
    ))
    return _prompt_yes_no(tr(
        f"配布元の規約・ライセンスに同意して{what_ja}をダウンロードしますか？",
        f"Agree to the distributor's terms/license and download this {what_en}?",
    ))


def ask_password_protection(env_path: Path) -> None:
    """First run: ask whether to turn password protection on; the answer goes into .env.

    Only the ON/OFF choice is made here. The password itself is set on the first browser
    screen that connects (see server/app/auth.py).
    """
    key = "SHOGI_ANALYZER_PASSWORD"
    if read_env_value(env_path, key):
        return  # already chosen (edit .env to change it)
    if (os.environ.get(key) or "").strip():
        return  # given as an OS environment variable
    if not sys.stdin.isatty():
        return  # cannot ask now: stays OFF and is asked on the next interactive start
    print(tr(
        "\n[installer] パスワード保護\n"
        "  公開アドレス（Quick Tunnel / 固定アドレス）で使う場合は、有効にすることをおすすめします。\n"
        "  有効にした場合、パスワードは最初にブラウザで接続した画面で設定します（ログインは 30 日間有効）。\n"
        "  あとから .env の SHOGI_ANALYZER_PASSWORD（TRUE / FALSE）で変更できます。",
        "\n[installer] Password protection\n"
        "  Recommended when you use a public address (Quick Tunnel / fixed address).\n"
        "  If enabled, you set the password on the first browser screen that connects (logins last 30 days).\n"
        "  You can change it later with SHOGI_ANALYZER_PASSWORD (TRUE / FALSE) in .env.",
    ))
    value = "TRUE" if _prompt_yes_no(tr("パスワード保護を有効にしますか？", "Enable password protection?")) else "FALSE"
    if fill_env_value(env_path, key, value):
        print(tr(f"[installer] .env に保存: {key}={value}", f"[installer] Saved in .env: {key}={value}"))
    os.environ[key] = value


def _prompt_yes_no(msg: str, default_no: bool = True) -> bool:
    # NOTE: On some terminals (and on Windows in some launchers) isatty() can be false
    # even though input() works. Prefer to try prompting and gracefully fall back.
    if not sys.stdin.isatty():
        print(f"{msg} {'[y/N]' if default_no else '[Y/n]'} " + tr("（入力できない環境を検出）", "(non-interactive detected)"))
        # If stdin is truly non-interactive, input() will raise EOFError.
    suffix = "[y/N]" if default_no else "[Y/n]"
    try:
        ans = input(f"{msg} {suffix} ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False if default_no else True
    if not ans:
        return not default_no
    return ans in {"y", "yes"}


def find_existing_cloudflared_config() -> list[Path]:
    """Return candidate cloudflared config paths on this machine."""
    candidates: list[Path] = []
    try:
        home = Path(os.environ.get("USERPROFILE") or os.environ.get("HOME") or str(Path.home()))
    except Exception:
        home = Path.home()
    cfdir = home / ".cloudflared"
    for name in ("config.yml", "config.yaml"):
        p = cfdir / name
        if p.exists() and p.is_file():
            candidates.append(p)
    # project-local override
    for name in ("cloudflared.yml", "cloudflared.yaml", "config.yml", "config.yaml"):
        p = repo_root() / name
        if p.exists() and p.is_file() and p not in candidates:
            candidates.append(p)
    return candidates


def parse_cloudflared_config(config_path: Path) -> dict:
    """Best-effort YAML parsing without dependencies.

    We only need:
    - tunnel: <NAME or UUID>
    - credentials-file: <path>
    - ingress[].hostname
    """
    text = config_path.read_text(encoding="utf-8", errors="ignore")
    tunnel = None
    creds = None
    hostnames: list[str] = []

    # tunnel: xxx
    m = re.search(r"^\s*tunnel\s*:\s*([^#\n]+)", text, re.MULTILINE)
    if m:
        tunnel = m.group(1).strip().strip('"').strip("'")
    m = re.search(r"^\s*credentials-file\s*:\s*([^#\n]+)", text, re.MULTILINE)
    if m:
        creds = m.group(1).strip().strip('"').strip("'")

    for m in re.finditer(r"^\s*hostname\s*:\s*([^#\n]+)", text, re.MULTILINE):
        h = m.group(1).strip().strip('"').strip("'")
        if h and h not in hostnames:
            hostnames.append(h)

    return {
        "config_path": str(config_path),
        "tunnel": tunnel,
        "credentials_file": creds,
        "hostnames": hostnames,
    }


def _engine_config_path(root: Path) -> Path:
    return _server_data_dir(root) / "engine_config.json"


_CONFIG_PATH_KEYS = ("engine_path", "engine_eval_dir")


def _load_engine_config(root: Path) -> dict:
    """Saved engine choice; paths are stored relative to the app folder and returned absolute."""
    p = _engine_config_path(root)
    if not p.exists():
        return {}
    try:
        cfg = json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    if not isinstance(cfg, dict):
        return {}
    for key in _CONFIG_PATH_KEYS:
        if cfg.get(key):
            cfg[key] = resolve_portable(str(cfg[key]), root)
    return cfg


def _save_engine_config(root: Path, cfg: dict) -> None:
    p = _engine_config_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    out = dict(cfg)
    for key in _CONFIG_PATH_KEYS:
        if out.get(key):
            out[key] = portable_path(str(out[key]), root)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _pick_engine_variant(engine: dict) -> dict | None:
    platforms = engine.get("platforms") or []
    os_key = "windows" if os.name == "nt" else ("darwin" if sys.platform == "darwin" else "linux")
    arch = py_platform.machine().lower()
    arch_key = "arm64" if arch in {"arm64", "aarch64"} else "amd64"
    for v in platforms:
        if (v.get("os") or "").lower() == os_key and (v.get("arch") or "").lower() == arch_key:
            return v
    # fallback: match os only
    for v in platforms:
        if (v.get("os") or "").lower() == os_key:
            return v
    return platforms[0] if platforms else None


def _sha256_verify_if_present(path: Path, sha256_hex: str) -> None:
    sha256_hex = (sha256_hex or "").strip().lower()
    if not sha256_hex:
        return
    got = _sha256_file(path).lower()
    if got != sha256_hex:
        raise RuntimeError(f"sha256 mismatch for {path.name}: got {got} expected {sha256_hex}")


def _extract_archive(archive: Path, dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    suf = archive.suffix.lower()
    if suf == ".zip":
        with zipfile.ZipFile(archive) as z:
            z.extractall(dest_dir)
        return
    if suf == ".7z":
        try:
            import py7zr  # type: ignore
        except Exception as e:
            raise RuntimeError(
                "py7zr is required to extract .7z archives. It should be installed automatically; "
                "please re-run run.bat/run.sh."
            ) from e
        with py7zr.SevenZipFile(str(archive), mode="r") as z:
            z.extractall(path=str(dest_dir))
        return
    # fallback
    shutil.unpack_archive(str(archive), str(dest_dir))


def _cpu_flags() -> set[str]:
    flags: set[str] = set()
    try:
        if cpuinfo is None:
            return set()
        info = cpuinfo.get_cpu_info()  # type: ignore
        fl = info.get("flags") or []
        flags = set([str(f).lower() for f in fl])
    except Exception:
        flags = set()
    return flags


def _choose_best_engine_exe(engine_root: Path, type_hint: str = "") -> Path | None:
    flags = _cpu_flags()
    # collect candidates
    if os.name == "nt":
        candidates = list(engine_root.rglob("*.exe"))
    else:
        candidates = [p for p in engine_root.rglob("*") if p.is_file() and os.access(p, os.X_OK)]

    if type_hint:
        filtered = [p for p in candidates if type_hint.lower() in p.name.lower()]
        if filtered:
            candidates = filtered

    if not candidates:
        return None

    pref = [
        ("avx512vnni", "avx512vnni" in flags),
        ("avx512", "avx512" in flags),
        ("avxvnni", "avxvnni" in flags),
        ("avx2", "avx2" in flags),
        ("sse42", "sse4_2" in flags or "sse42" in flags),
        ("sse41", "sse4_1" in flags or "sse41" in flags),
    ]

    def score(p: Path) -> int:
        n = p.name.lower()
        for i, (tok, ok) in enumerate(pref):
            if ok and tok in n:
                return 1000 - i
        return 0

    candidates.sort(key=score, reverse=True)
    return candidates[0]


def guess_eval_dir_from_exe(exe_path: Path) -> Path | None:
    """Best-effort guess of eval directory for NNUE engines.

    This repo's installer extracts engine binaries under:
      engines/<engine_id>/_engine_extract/<exe>
    and places nn.bin under:
      engines/<engine_id>/eval/nn.bin

    Many USI engines also default to <exe_dir>/eval.
    """

    exe_path = Path(exe_path)
    candidates: list[Path] = []
    try:
        candidates.append(exe_path.parent / "eval")
        candidates.append(exe_path.parent.parent / "eval")
        candidates.append(exe_path.parent.parent.parent / "eval")
    except Exception:
        pass

    seen: set[str] = set()
    for d in candidates:
        try:
            key = str(d.resolve())
        except Exception:
            key = str(d)
        if key in seen:
            continue
        seen.add(key)

        try:
            if (d / "nn.bin").exists():
                return d
            if d.exists() and d.is_dir():
                # Any files under eval/ are acceptable as a directory hint.
                for p in d.iterdir():
                    if p.is_file():
                        return d
        except Exception:
            continue

    return None


def _download_eval_if_needed(root: Path, engine: dict, engines_dir: Path) -> Path | None:
    """Download and extract eval assets to engines_dir/eval, returning eval_dir."""
    eval_meta = engine.get("eval") or {}
    eval_id = (eval_meta.get("id") or "").strip()
    if not eval_id:
        return None

    manifest = load_manifest(root)
    evals = manifest.get("evals") or []
    item = next((e for e in evals if (e.get("id") or "").strip() == eval_id), None)
    if not item:
        return None

    url = (item.get("url") or "").strip()
    if not url:
        return None

    print(tr("\n[installer] 評価関数のダウンロード", "\n[installer] Evaluation download"))
    print(tr(f"  名前      : {item.get('name') or eval_id}", f"  name   : {item.get('name') or eval_id}"))
    if item.get("author"):
        print(tr(f"  作者      : {item.get('author')}", f"  author : {item.get('author')}"))
    _print_license(
        str(item.get("license") or ""),
        [("配布ページ|page", str(item.get("license_url") or "")), ("規約|terms", str(item.get("terms_url") or ""))],
    )
    print(tr(f"  ダウンロード元: {url}", f"  download: {url}"))
    if not _prompt_consent("評価関数", "evaluation file"):
        return None

    eval_dir = engines_dir / "eval"
    eval_dir.mkdir(parents=True, exist_ok=True)
    filename = Path(url.split("?")[0]).name or "eval.bin"
    dst = engines_dir / filename
    try:
        _download(url, dst)
        _sha256_verify_if_present(dst, str(item.get("sha256") or ""))
        _log_installer_event(root, kind="download", payload={"asset": "eval", "eval_id": eval_id, "url": url, "path": str(dst)})
    except Exception as exc:
        print(tr(f"[installer] 評価関数のダウンロードに失敗しました: {exc}", f"[installer] eval download failed: {exc}"))
        _log_installer_event(root, kind="download_error", payload={"asset": "eval", "eval_id": eval_id, "url": url, "error": str(exc)})
        return None

    # Extract if archive
    if dst.suffix.lower() in {".zip", ".7z"}:
        try:
            tmp = engines_dir / "_eval_extract"
            if tmp.exists():
                shutil.rmtree(tmp, ignore_errors=True)
            _extract_archive(dst, tmp)
            # find nn.bin
            nn = None
            for p in tmp.rglob("nn.bin"):
                if p.is_file():
                    nn = p
                    break
            if nn:
                shutil.copy2(nn, eval_dir / "nn.bin")
            shutil.rmtree(tmp, ignore_errors=True)
        except Exception as exc:
            print(tr(f"[installer] 評価関数の展開に失敗しました: {exc}", f"[installer] eval extract failed: {exc}"))
            return None
    else:
        # direct file: if it is nn.bin, put it
        if dst.name.lower() == "nn.bin":
            shutil.copy2(dst, eval_dir / "nn.bin")
    return eval_dir


def _download_engine_variant(root: Path, engine: dict) -> Path | None:
    variant = _pick_engine_variant(engine)
    if not variant:
        return None
    url = (variant.get("url") or "").strip()
    build = variant.get("build") or {}
    if not url and not build:
        return None

    name = (engine.get("name") or engine.get("id") or "engine").strip()
    lic = (engine.get("license_url") or "").strip()
    terms = (engine.get("terms_url") or "").strip()

    print(tr("\n[installer] エンジンのダウンロード", "\n[installer] Engine download"))
    print(tr(f"  名前      : {name}", f"  name   : {name}"))
    _print_license(str(engine.get("license") or ""), [("ライセンス条項|license text", lic), ("規約|terms", terms)])
    if url:
        print(tr(f"  ダウンロード元: {url}", f"  download: {url}"))
        if not _prompt_consent("エンジン", "engine"):
            return None
    else:
        # build flow
        print(tr("  （この環境向けのビルド済みファイルはありません）", "  (no prebuilt binary for this platform)"))
        git_url = (build.get("git") or "").strip()
        tag = (build.get("tag") or "").strip()
        if git_url:
            print(tr(f"  ソース   : {git_url} {tag or ''}", f"  source: {git_url} {tag or ''}"))
        if not _prompt_consent("エンジン（ソースからビルド）", "engine (built from source)"):
            return None

    engines_dir = runtime_home() / "engines" / (engine.get("id") or "engine")
    engines_dir.mkdir(parents=True, exist_ok=True)
    # download/extract or build
    extracted_root = engines_dir / "_engine_extract"
    if extracted_root.exists():
        shutil.rmtree(extracted_root, ignore_errors=True)

    if url:
        filename = Path(url.split("?")[0]).name or "engine.bin"
        dst = engines_dir / filename
        try:
            _download(url, dst)
            _sha256_verify_if_present(dst, str(variant.get("sha256") or ""))
            _log_installer_event(root, kind="download", payload={"asset": "engine", "engine_id": engine.get("id"), "url": url, "path": str(dst)})
        except Exception as exc:
            print(tr(f"[installer] エンジンのダウンロードに失敗しました: {exc}", f"[installer] engine download failed: {exc}"))
            _log_installer_event(root, kind="download_error", payload={"asset": "engine", "engine_id": engine.get("id"), "url": url, "error": str(exc)})
            return None

        if dst.suffix.lower() in {".zip", ".7z"}:
            try:
                _extract_archive(dst, extracted_root)
            except Exception as exc:
                print(tr(f"[installer] 展開に失敗しました: {exc}", f"[installer] extract failed: {exc}"))
                return None
        else:
            # treat as direct binary
            extracted_root.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dst, extracted_root / dst.name)
    else:
        # Build from source (linux only for now)
        git_url = (build.get("git") or "").strip()
        tag = (build.get("tag") or "").strip()
        if not git_url:
            return None
        src_dir = engines_dir / "_src"
        if src_dir.exists():
            shutil.rmtree(src_dir, ignore_errors=True)
        print(tr("[installer] エンジンのソースを取得しています ...", "[installer] Cloning engine source..."))
        rc = run_streamed(["git", "clone", "--depth", "1", "--branch", tag or "master", git_url, str(src_dir)])
        if rc != 0:
            print(tr("[installer] エラー: git clone に失敗しました", "[installer] ERROR: git clone failed"))
            return None
        # Follow upstream build guidance; choose CPU based on flags.
        flags = _cpu_flags()
        target = "AVX2" if "avx2" in flags else "SSE42"
        make_cmd = ["make", "-C", str(src_dir / "source"), "clean", "tournament", f"TARGET_CPU={target}", "YANEURAOU_EDITION=YANEURAOU_ENGINE_NNUE"]
        print(tr("[installer] エンジンをビルドしています（時間がかかります）...", "[installer] Building engine (this may take a while)..."))
        rc = run_streamed(make_cmd)
        if rc != 0:
            print(tr("[installer] エラー: make に失敗しました", "[installer] ERROR: make failed"))
            return None
        extracted_root.mkdir(parents=True, exist_ok=True)
        # Try to locate built binary
        built = None
        for p in (src_dir / "source").rglob("YaneuraOu*"):
            if p.is_file() and os.access(p, os.X_OK):
                built = p
                break
        if built:
            shutil.copy2(built, extracted_root / built.name)

    # download eval (best effort)
    _download_eval_if_needed(root, engine, engines_dir)

    # choose best engine exe
    type_hint = (variant.get("engine_type_hint") or "").strip()
    best = _choose_best_engine_exe(extracted_root if extracted_root.exists() else engines_dir, type_hint=type_hint)
    if best is None:
        # fallback: largest file
        files = [p for p in (extracted_root if extracted_root.exists() else engines_dir).rglob("*") if p.is_file()]
        if not files:
            return None
        files.sort(key=lambda p: p.stat().st_size, reverse=True)
        best = files[0]
    return best


def ensure_engine_config(root: Path) -> dict[str, str]:
    """Return env vars to pass to uvicorn process.

    - If env already has engine configured, do nothing.
    - Else, try persisted config (server/data/engine_config.json).
    - Else, interactive setup (manifest download or manual path).
    """
    if (os.environ.get("SHOGI_ANALYZER_ENGINE_CMD") or "").strip() or (os.environ.get("SHOGI_ANALYZER_ENGINE_PATH") or "").strip():
        return {}

    cfg = _load_engine_config(root)
    cmd = (cfg.get("engine_cmd") or "").strip()
    path = (cfg.get("engine_path") or "").strip()
    if cmd:
        return {"SHOGI_ANALYZER_ENGINE_CMD": cmd}
    eval_dir = (cfg.get("engine_eval_dir") or "").strip()
    if path and Path(path).exists():
        env = {"SHOGI_ANALYZER_ENGINE_PATH": path}
        if eval_dir and Path(eval_dir).exists():
            env["SHOGI_ANALYZER_ENGINE_EVAL_DIR"] = eval_dir
        else:
            guessed = guess_eval_dir_from_exe(Path(path))
            if guessed and guessed.exists():
                env["SHOGI_ANALYZER_ENGINE_EVAL_DIR"] = str(guessed)
                # Repair persisted config so subsequent runs work without guessing.
                try:
                    cfg["engine_eval_dir"] = str(guessed)
                    _save_engine_config(root, cfg)
                except Exception:
                    pass
        return env

    # No engine configured.
    manifest = load_manifest(root)
    engines = manifest.get("engines") or []
    if not sys.stdin.isatty():
        # 要件上、初回でエンジン/評価関数の同意とDLが必要。
        # 対話入力ができない場合は黙って解析無効にせず止める。
        raise RuntimeError(tr(
            "USIエンジン未設定です。対話入力ができない環境で起動されました。\n"
            "ターミナル/コンソールから run.bat / run.sh を実行して、エンジンDLの同意を行ってください。",
            "No USI engine is configured and this console cannot take input.\n"
            "Run run.bat / run.sh from a terminal and agree to the engine download.",
        ))

    print(tr("\n[installer] 解析エンジン（USI）が設定されていません。", "\n[installer] USI engine is not configured."))
    if engines:
        print(tr("[installer] ダウンロードできるエンジン（installer/manifest.json）:", "[installer] Download candidates (installer/manifest.json):"))
        for i, e in enumerate(engines, 1):
            print(f"  {i}) {e.get('name') or e.get('id')}")
        print(tr("  m) パスを入力して手持ちのエンジンを使う", "  m) manual path"))
        print(tr("  s) スキップ（解析なしで起動）", "  s) skip"))
        try:
            choice = input("> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            choice = "s"
        if not choice and engines:
            # クイックインストールの既定: 候補1を選ぶ（実際のDLは次の同意で確定）
            choice = "1"
        if choice == "s":
            return {}
        if choice == "m" or not choice:
            pass
        else:
            try:
                idx = int(choice)
                if 1 <= idx <= len(engines):
                    exe = _download_engine_variant(root, engines[idx - 1])
                    if exe and exe.exists():
                        # Prefer eval dir under the engine folder if present.
                        eval_dir = guess_eval_dir_from_exe(exe)
                        cfg = {"engine_path": str(exe)}
                        if eval_dir and eval_dir.exists():
                            cfg["engine_eval_dir"] = str(eval_dir)
                        _save_engine_config(root, cfg)
                        env = {"SHOGI_ANALYZER_ENGINE_PATH": str(exe)}
                        if eval_dir and eval_dir.exists():
                            env["SHOGI_ANALYZER_ENGINE_EVAL_DIR"] = str(eval_dir)
                        return env
            except Exception:
                pass

    # Manual path flow.
    try:
        manual = input(tr(
            "USIエンジン実行ファイルのパスを入力してください（例: C:\\path\\engine.exe）\n> ",
            "Path to the USI engine executable (e.g. C:\\path\\engine.exe)\n> ",
        )).strip().strip('"')
    except (EOFError, KeyboardInterrupt):
        manual = ""
    if manual and Path(manual).exists():
        eval_dir = guess_eval_dir_from_exe(Path(manual))
        cfg = {"engine_path": manual}
        if eval_dir and eval_dir.exists():
            cfg["engine_eval_dir"] = str(eval_dir)
        _save_engine_config(root, cfg)
        env = {"SHOGI_ANALYZER_ENGINE_PATH": manual}
        if eval_dir and eval_dir.exists():
            env["SHOGI_ANALYZER_ENGINE_EVAL_DIR"] = str(eval_dir)
        return env

    print(tr("[installer] エンジンは未設定のままです。解析は使えません", "[installer] Engine remains unconfigured. analysis disabled"))
    return {}


def run_quick_tunnel(cloudflared: Path, port: int) -> tuple[subprocess.Popen | None, str | None]:
    """Start Cloudflare Quick Tunnel and try to extract the issued URL."""

    def _start(args: list[str]) -> subprocess.Popen:
        # Avoid ~/.cloudflared/config.yml interference by isolating HOME.
        tmp_home = Path(tempfile.mkdtemp(prefix="shogi_cf_"))
        env = os.environ.copy()
        env["HOME"] = str(tmp_home)
        env["USERPROFILE"] = str(tmp_home)
        # quiet colors
        env["NO_COLOR"] = "1"
        return subprocess.Popen(
            [str(cloudflared), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(tmp_home),
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

    # Prefer 127.0.0.1 for Windows resolver edge cases.
    base_args = ["tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{port}"]
    log_dir = _server_data_dir(repo_root())
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "cloudflared_quick_tunnel.log"

    proc = _start(base_args)
    url = _read_tunnel_url(proc, timeout_s=60.0, tee_path=log_path)
    if url:
        return proc, url

    # Fallback: some networks block UDP/QUIC; try http2.
    try:
        proc.terminate()
    except Exception:
        pass
    proc2 = _start(["tunnel", "--no-autoupdate", "--protocol", "http2", "--url", f"http://127.0.0.1:{port}"])
    url2 = _read_tunnel_url(proc2, timeout_s=60.0, tee_path=log_path)
    return proc2, url2


def _read_tunnel_url(proc: subprocess.Popen, timeout_s: float, tee_path: Path | None = None) -> str | None:
    started = time.time()
    if not proc.stdout:
        return None

    # NOTE (Windows): proc.stdout.readline() can block forever if cloudflared is quiet,
    # prints without line breaks, or if output is on stderr in some builds/environments.
    # We therefore read in a daemon thread and poll with a timeout.
    import queue
    import threading

    q: "queue.Queue[str | Exception]" = queue.Queue()
    buf = ""

    tee_fh = None
    if tee_path is not None:
        try:
            tee_fh = open(tee_path, "w", encoding="utf-8", errors="ignore")
        except Exception:
            tee_fh = None

    def _reader() -> None:
        try:
            # iter(readline, '') blocks inside the thread, not the main thread.
            for line in iter(proc.stdout.readline, ""):
                q.put(line)
        except Exception as e:
            q.put(e)

    threading.Thread(target=_reader, daemon=True).start()

    pat = re.compile(r"https?://[a-z0-9-]+\.trycloudflare\.com", re.IGNORECASE)
    while time.time() - started < timeout_s:
        # If the process already exited, stop early.
        if proc.poll() is not None and q.empty():
            break
        try:
            item = q.get(timeout=0.1)
        except queue.Empty:
            continue

        if isinstance(item, Exception):
            break

        line = item
        if tee_fh:
            try:
                tee_fh.write(line)
                tee_fh.flush()
            except Exception:
                pass

        s = line.strip()
        if not s:
            continue
        buf += "\n" + s

        m = pat.search(s)
        if m:
            if tee_fh:
                try:
                    tee_fh.close()
                except Exception:
                    pass
            return m.group(0)

        # Sometimes it prints without a clean line split; search the growing buffer as well.
        m2 = pat.search(buf)
        if m2:
            if tee_fh:
                try:
                    tee_fh.close()
                except Exception:
                    pass
            return m2.group(0)

    if tee_fh:
        try:
            tee_fh.close()
        except Exception:
            pass
    return None
