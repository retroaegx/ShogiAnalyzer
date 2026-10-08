"""Version check against the latest GitHub release (same approach as NImageManager).

- current version: <app>/VERSION
- latest version : https://api.github.com/repos/<repo>/releases/latest (tag_name, e.g. v1.0.1)
- checked at startup (in the background) and every SHOGI_ANALYZER_UPDATE_CHECK_INTERVAL_HOURS
- the last result is kept in server/data/update_status.json so it is shown right after a restart
- .env: SHOGI_ANALYZER_UPDATE_CHECK=TRUE/FALSE, SHOGI_ANALYZER_UPDATE_CHECK_INTERVAL_HOURS=24,
        SHOGI_ANALYZER_UPDATE_REPO=owner/repo
"""

from __future__ import annotations

import calendar
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from ..paths import data_dir

ROOT_DIR = Path(__file__).resolve().parents[3]
VERSION_FILE = ROOT_DIR / "VERSION"
DEFAULT_REPO = "retroaegx/ShogiAnalyzer"
DEFAULT_INTERVAL_HOURS = 24.0
TIMEOUT_SEC = 5.0
STALE_AFTER_SEC = 3600.0  # re-check on page connect when the last check is older than this
SEMVER_RE = re.compile(r"^v?(?P<core>\d+(?:\.\d+){0,3})(?:-(?P<pre>[0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$")


def _tr(ja: str, en: str) -> str:
    return ja if (os.environ.get("SHOGI_ANALYZER_LANG") or "ja").lower().startswith("ja") else en


def _utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def read_current_version() -> str:
    try:
        raw = VERSION_FILE.read_text(encoding="utf-8", errors="ignore").strip()
    except OSError:
        raw = ""
    return raw or "0.0.0"


def _parse(value: str | None):
    m = SEMVER_RE.match(str(value or "").strip())
    if not m:
        return None
    core = tuple(int(p) for p in m.group("core").split("."))
    pre = m.group("pre")
    pre_key = None if not pre else tuple((0, int(t)) if t.isdigit() else (1, t.lower()) for t in pre.split("."))
    return core, pre_key


def compare_versions(current: str | None, latest: str | None) -> int:
    """-1: current is older, 0: same, 1: current is newer (semver; "v" prefix allowed)."""
    a, b = _parse(current), _parse(latest)
    if a is None or b is None:
        return 0 if a == b else (-1 if a is None else 1)
    (ac, ap), (bc, bp) = a, b
    width = max(len(ac), len(bc))
    ac, bc = ac + (0,) * (width - len(ac)), bc + (0,) * (width - len(bc))
    if ac != bc:
        return -1 if ac < bc else 1
    if ap == bp:
        return 0
    if ap is None:  # 1.0.0 > 1.0.0-beta
        return 1
    if bp is None:
        return -1
    return -1 if ap < bp else 1


def _flag(name: str, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    return default if not raw else raw not in {"0", "false", "no", "off"}


def _interval_hours() -> float:
    try:
        hours = float(os.environ.get("SHOGI_ANALYZER_UPDATE_CHECK_INTERVAL_HOURS") or DEFAULT_INTERVAL_HOURS)
    except ValueError:
        hours = DEFAULT_INTERVAL_HOURS
    return max(1.0, min(hours, 24.0 * 30))


def _repo() -> str:
    text = (os.environ.get("SHOGI_ANALYZER_UPDATE_REPO") or DEFAULT_REPO).strip().strip("/")
    text = re.sub(r"^https?://github\.com/", "", text, flags=re.I).removesuffix(".git").strip("/")
    return text if text.count("/") == 1 and all(text.split("/")) else DEFAULT_REPO


def _cache_file() -> Path:
    return data_dir() / "update_status.json"


def _base_state() -> dict[str, Any]:
    repo = _repo()
    page = f"https://github.com/{repo}/releases"
    return {
        "enabled": _flag("SHOGI_ANALYZER_UPDATE_CHECK", True),
        "repo": repo,
        "release_page_url": page,
        "current_version": read_current_version(),
        "latest_version": None,
        "release_name": None,
        "release_url": page,
        "published_at": None,
        "checked_at": None,
        "update_available": False,
        "error": None,
        "interval_hours": _interval_hours(),
    }


def _latest_release(repo: str) -> dict[str, Any]:
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "ShogiAnalyzer update checker", "X-GitHub-Api-Version": "2022-11-28"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
        data = json.loads(resp.read().decode(resp.headers.get_content_charset() or "utf-8", errors="replace"))
    if not isinstance(data, dict):
        raise RuntimeError("invalid release response")
    return data


class UpdateChecker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._state = _base_state()
        self._announced: str | None = None
        self._checking = threading.Event()

    def start(self) -> None:
        base = _base_state()
        try:
            cached = json.loads(_cache_file().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cached = {}
        state = {**(cached if isinstance(cached, dict) else {}), **{k: base[k] for k in ("enabled", "repo", "release_page_url", "current_version", "interval_hours")}}
        # the cached result was computed for the version that was installed then
        if state.get("latest_version"):
            state["update_available"] = compare_versions(state["current_version"], state["latest_version"]) < 0
        self._set(state)
        if not state["enabled"]:
            return
        self._stop.clear()
        # first check in the background: startup is never delayed by the network
        self._thread = threading.Thread(target=self._run, name="update-checker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def get_state(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def refresh_if_stale(self, max_age_sec: float = STALE_AFTER_SEC) -> dict[str, Any]:
        """When a page connects: check GitHub again in the background if the last check is older
        than max_age_sec (so a release made after the server started shows up without waiting
        for the daily check). Returns the current state with "checking": True while it runs."""
        state = self.get_state()
        if not state.get("enabled"):
            return state
        checked = _parse_iso(state.get("checked_at"))
        stale = checked is None or (time.time() - checked) > max_age_sec
        if stale and not self._checking.is_set():
            self._checking.set()

            def run() -> None:
                try:
                    self.check_now()
                finally:
                    self._checking.clear()

            threading.Thread(target=run, name="update-check-on-connect", daemon=True).start()
        state["checking"] = self._checking.is_set()
        return state

    def check_now(self) -> dict[str, Any]:
        state = {**self.get_state(), **_base_state()}
        state["checked_at"] = _utc_now_iso()
        if not state["enabled"]:
            state.update(update_available=False, error=None)
            self._set(state)
            return state
        try:
            rel = _latest_release(state["repo"])
            latest = str(rel.get("tag_name") or "").strip() or None
            state.update(
                latest_version=latest,
                release_name=str(rel.get("name") or "").strip() or latest,
                release_url=str(rel.get("html_url") or "").strip() or state["release_page_url"],
                published_at=str(rel.get("published_at") or "").strip() or None,
                error=None,
                update_available=bool(latest) and compare_versions(state["current_version"], latest) < 0,
            )
        except urllib.error.HTTPError as exc:
            state["update_available"] = False
            state["error"] = (
                _tr("GitHub のリリースがまだありません", "no GitHub release yet") if exc.code == 404
                else f"GitHub API error ({exc.code})"
            )
        except Exception as exc:  # offline etc.: keep the app running, just report it
            state["update_available"] = False
            state["error"] = f"update check failed: {exc.__class__.__name__}"
        self._set(state)
        self._announce(state)
        return state

    def _announce(self, state: dict[str, Any]) -> None:
        latest = state.get("latest_version")
        if state.get("update_available") and latest != self._announced:
            self._announced = latest
            print(_tr(
                f"[update] 新しいバージョン {latest} があります（現在 v{state['current_version']}）。更新方法: README の「更新」/ {state['release_url']}",
                f"[update] A new version {latest} is available (current v{state['current_version']}). How to update: README \"Update\" / {state['release_url']}",
            ), flush=True)

    def _set(self, state: dict[str, Any]) -> None:
        with self._lock:
            self._state = dict(state)
        try:
            path = _cache_file()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except OSError:
            pass

    def _run(self) -> None:
        while True:
            try:
                self.check_now()
            except Exception:
                pass
            if self._stop.wait(timeout=_interval_hours() * 3600.0):
                return


def _parse_iso(value: str | None) -> float | None:
    try:
        return calendar.timegm(time.strptime(str(value), "%Y-%m-%dT%H:%M:%SZ"))
    except (TypeError, ValueError):
        return None


_SERVICE = UpdateChecker()


def start_update_checker() -> None:
    _SERVICE.start()


def stop_update_checker() -> None:
    _SERVICE.stop()


def get_update_status() -> dict[str, Any]:
    return _SERVICE.refresh_if_stale()


def check_update_now() -> dict[str, Any]:
    return _SERVICE.check_now()
