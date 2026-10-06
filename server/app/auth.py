"""Optional password protection, switched on/off with SHOGI_ANALYZER_PASSWORD in .env.

- OFF (default): no login. If a password had been saved before, it is deleted at startup.
- ON, no password yet: the first browser that connects is asked to set one. From this PC
  itself that works directly; from other devices (LAN / public address) the 6-digit setup
  code printed in the console is also required, so a stranger can't claim it first.
- ON, password set: every page / API / WebSocket needs a login cookie, valid for 30 days
  (also across server restarts).

<runtime>/data/auth.json holds the scrypt hash of the password (never the password) and a
random secret that signs the login cookies. No web-framework imports here.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any

from .paths import data_dir

COOKIE_NAME = "shogi_analyzer_auth"
LOGIN_DAYS = 30
LOGIN_SECONDS = LOGIN_DAYS * 24 * 60 * 60
MIN_LENGTH = 4

_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}

# one-time code for setting the password from another device (printed at startup)
setup_code: str | None = None


def required() -> bool:
    """SHOGI_ANALYZER_PASSWORD=TRUE in .env / environment (TRUE/FALSE, case-insensitive; 1/0 also accepted)."""
    raw = (os.environ.get("SHOGI_ANALYZER_PASSWORD") or "").strip().lower()
    return raw in {"true", "1", "yes", "on"}


def auth_file() -> Path:
    return data_dir() / "auth.json"


_cache: tuple[float, dict[str, Any] | None] | None = None


def load_auth() -> dict[str, Any] | None:
    """Saved password data, re-read only when the file changes."""
    global _cache
    path = auth_file()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        _cache = None
        return None
    if _cache and _cache[0] == mtime:
        return _cache[1]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = None
    data = data if isinstance(data, dict) and data.get("hash") and data.get("secret") else None
    _cache = (mtime, data)
    return data


def configured() -> bool:
    return load_auth() is not None


def setup_needed() -> bool:
    """ON but no password yet: the first connection must set one."""
    return required() and not configured()


def _tr(ja: str, en: str) -> str:
    # console language chosen by installer/run.py (Japanese UI -> "ja", otherwise English)
    return ja if (os.environ.get("SHOGI_ANALYZER_LANG") or "ja").lower().startswith("ja") else en


def apply_setting() -> str:
    """Called at server startup. Returns a console message ("" = nothing to say)."""
    global setup_code
    if not required():
        if auth_file().exists():
            auth_file().unlink()
            return _tr(
                "[auth] パスワード保護を OFF にしたため、保存されていたパスワード情報を削除しました",
                "[auth] Password protection is OFF: the saved password was deleted",
            )
        return ""
    if configured():
        return _tr(f"[auth] パスワード保護: ON（ログインは {LOGIN_DAYS} 日間有効）", f"[auth] Password protection: ON (logins last {LOGIN_DAYS} days)")
    setup_code = f"{secrets.randbelow(10**6):06d}"
    return _tr(
        "[auth] パスワード保護: ON / パスワードはまだ設定されていません\n"
        "       最初に接続した画面でパスワードを設定してください。\n"
        f"       この PC 以外（スマホ・公開アドレス）から設定する場合のセットアップコード: {setup_code}",
        "[auth] Password protection: ON / no password set yet\n"
        "       Set it on the first screen that connects.\n"
        f"       Setup code when setting it from another device (phone / public address): {setup_code}",
    )


def _hash(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, **_SCRYPT)


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def save_password(password: str) -> None:
    global setup_code
    salt = secrets.token_bytes(16)
    data = {
        "algo": "scrypt",
        "params": _SCRYPT,
        "salt": _b64(salt),
        "hash": _b64(_hash(password, salt)),
        # signs login cookies; a new password gets a new secret = all old logins end
        "secret": _b64(secrets.token_bytes(32)),
    }
    path = auth_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    setup_code = None


def verify_password(password: str) -> bool:
    data = load_auth()
    if not data:
        return False
    try:
        return hmac.compare_digest(_unb64(data["hash"]), _hash(password, _unb64(data["salt"])))
    except Exception:
        return False


def _sign(secret: bytes, payload: bytes) -> str:
    return _b64(hmac.new(secret, payload, hashlib.sha256).digest())


def issue_token() -> str:
    data = load_auth() or {}
    payload = json.dumps({"exp": int(time.time()) + LOGIN_SECONDS}, separators=(",", ":")).encode()
    return f"{_b64(payload)}.{_sign(_unb64(data.get('secret', '')), payload)}"


def token_valid(token: str | None) -> bool:
    """True when no login is needed, or the cookie is a valid, unexpired login."""
    if not required():
        return True
    data = load_auth()
    if not data or not token or "." not in token:
        return False
    try:
        body, sig = token.split(".", 1)
        payload = _unb64(body)
        if not hmac.compare_digest(sig, _sign(_unb64(data["secret"]), payload)):
            return False
        return int(json.loads(payload).get("exp", 0)) > time.time()
    except Exception:
        return False
