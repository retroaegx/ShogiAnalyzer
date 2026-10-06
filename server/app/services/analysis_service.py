from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import time
from collections import deque
from typing import Any, Awaitable, Callable

from ..core.gametree import GameTree
from ..core.sfen_ops import sfen_to_position_command
from .state_store import StateStore


SenderFn = Callable[[str, dict | None], Awaitable[None]]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _int_env(name: str, default: int, *, min_value: int, max_value: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(min_value, min(max_value, value))


def _float_env(name: str, default: float, *, min_value: float, max_value: float) -> float:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return max(min_value, min(max_value, value))


def _opt_int_env(name: str) -> int | None:
    raw = (os.environ.get(name) or "").strip()
    try:
        return int(raw) if raw else None
    except ValueError:
        return None


def system_memory_mb() -> int | None:
    try:
        import psutil  # type: ignore

        return int(psutil.virtual_memory().total // (1024 * 1024))
    except Exception:
        pass
    if os.name == "nt":
        try:
            import ctypes

            class _MemStatus(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            st = _MemStatus()
            st.dwLength = ctypes.sizeof(_MemStatus)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
                return int(st.ullTotalPhys // (1024 * 1024))
        except Exception:
            return None
        return None
    try:
        return int(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") // (1024 * 1024))
    except Exception:
        return None


def parse_usi_option(line: str) -> dict[str, Any] | None:
    """'option name X type spin default 4 min 1 max 1024' -> spec dict (names may contain spaces)."""
    tokens = line.split()
    if len(tokens) < 4 or tokens[0] != "option" or tokens[1] != "name":
        return None
    keywords = {"type", "default", "min", "max", "var"}
    spec: dict[str, Any] = {"name": "", "type": "string", "default": None, "min": None, "max": None, "vars": []}
    key = "name"
    buf: list[str] = []

    def flush() -> None:
        value = " ".join(buf)
        if key == "var":
            spec["vars"].append(value)
        elif key in {"min", "max"}:
            try:
                spec[key] = int(value)
            except ValueError:
                spec[key] = None
        else:
            spec[key] = value

    for tok in tokens[2:]:
        if tok in keywords and not (key == "name" and not buf):
            flush()
            key, buf = tok, []
        else:
            buf.append(tok)
    flush()
    if not spec["name"]:
        return None
    t = spec["type"]
    d = spec["default"]
    if t == "spin":
        try:
            spec["default"] = int(d) if d not in (None, "") else None
        except ValueError:
            spec["default"] = None
    elif t == "check":
        spec["default"] = str(d).lower() == "true"
    elif d is None:
        spec["default"] = ""
    return spec


def _engine_cmd_from_env() -> list[str] | None:
    cmd = (os.environ.get("SHOGI_ANALYZER_ENGINE_CMD") or "").strip()
    if cmd:
        return shlex.split(cmd, posix=(os.name != "nt"))
    path = (os.environ.get("SHOGI_ANALYZER_ENGINE_PATH") or "").strip()
    if path:
        return [path]
    return None


def _sanitize_multipv(value: Any, default: int = 1) -> int:
    try:
        n = int(value)
    except Exception:
        n = default
    return max(1, min(20, n))


def _jsonable_lines(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in lines:
        out.append(
            {
                "pv_index": int(line.get("pv_index", 1)),
                "score_type": str(line.get("score_type") or "unknown"),
                "score_value": int(line.get("score_value", 0)),
                "depth": int(line.get("depth", 0)),
                "seldepth": int(line.get("seldepth", 0)),
                "nodes": int(line.get("nodes", 0)),
                "nps": int(line.get("nps", 0)),
                "hashfull": int(line.get("hashfull", 0)),
                "pv_usi": [str(m) for m in (line.get("pv_usi") or [])],
            }
        )
    return out


class AnalysisService:
    def __init__(self, store: StateStore):
        self.store = store
        self._cmd = _engine_cmd_from_env()
        self._configured = bool(self._cmd)
        self._eval_dir = (os.environ.get("SHOGI_ANALYZER_ENGINE_EVAL_DIR") or "").strip() or None

        # USI handshake can take a while on first boot (NNUE weights / book load).
        self._usiok_timeout_s = _float_env("SHOGI_ANALYZER_USIOK_TIMEOUT_S", 12.0, min_value=1.0, max_value=120.0)
        self._readyok_timeout_s = _float_env("SHOGI_ANALYZER_READYOK_TIMEOUT_S", 45.0, min_value=2.0, max_value=300.0)
        self._post_setoption_readyok_timeout_s = _float_env(
            "SHOGI_ANALYZER_POST_SETOPTION_READYOK_TIMEOUT_S", 45.0, min_value=2.0, max_value=300.0
        )
        # Engine options use the engine's own defaults; only values the user changed in the
        # settings dialog (engine_options.json) or explicit env overrides are sent.
        self._env_threads = _opt_int_env("SHOGI_ANALYZER_ENGINE_THREADS")
        self._env_hash_mb = _opt_int_env("SHOGI_ANALYZER_ENGINE_HASH_MB")
        self._option_specs: dict[str, dict[str, Any]] = {}
        self._option_overrides: dict[str, Any] = self._load_overrides()

        # Whole-game analysis ("全解析")
        self._batch_task: asyncio.Task | None = None
        self._batch_cancel = False
        self._batch_progress: dict[str, Any] | None = None

        self._lock = asyncio.Lock()
        self._proc: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task | None = None
        self._ticker_task: asyncio.Task | None = None
        self._owner_sender: SenderFn | None = None

        self._usiok_event = asyncio.Event()
        self._readyok_event = asyncio.Event()
        self._bestmove_event = asyncio.Event()

        self._engine_name: str | None = None
        # (option specs live in self._option_specs, filled from "option name ..." lines)
        self._status = "idle" if self._configured else "not_configured"
        self._last_error: str | None = None

        # Keep last few lines for diagnostics (both outgoing commands and engine output).
        self._io_log: "deque[str]" = deque(maxlen=120)

        self._analysis_running = False
        self._analysis_node_id: str | None = None
        self._analysis_started_monotonic = 0.0
        self._active_multipv = 1
        self._latest_pv_by_index: dict[int, dict[str, Any]] = {}
        self._info_version = 0
        self._last_sent_info_version = -1
        self._last_sent_at_monotonic = 0.0
        self._last_snapshot_signature: str | None = None

        # MultiPV last sent to the running engine (None = unknown -> must send).
        self._applied_multipv: int | None = None
        # Coalesced background (re)start requests, so rapid navigation never blocks the WS loop.
        self._sync_task: asyncio.Task | None = None
        self._sync_pending: Callable[[], Awaitable[None]] | None = None

    def is_available(self) -> bool:
        return self._configured

    def capabilities_wire(self) -> dict[str, Any]:
        return {
            "analysis": self._configured,
            "analysis_controls": ["enable", "multipv", "start", "stop"] if self._configured else [],
        }

    def status_wire(self) -> dict[str, Any]:
        cmd_display = " ".join(self._cmd or [])
        return {
            "enabled": self._configured,
            "status": self._status,
            "engine_name": self._engine_name,
            "command": cmd_display,
            "eval_dir": self._eval_dir,
            "analysis_running": self._analysis_running,
            "node_id": self._analysis_node_id,
            "multipv": self._active_multipv,
            "threads": self._effective_option("Threads"),
            "hash_mb": self._effective_option("USI_Hash") or self._effective_option("Hash"),
            "last_error": self._last_error,
            "batch": self.batch_status(),
        }

    # ---------- engine options ----------
    def _overrides_path(self) -> Path:
        return Path(self.store.db_path).parent / "engine_options.json"

    def _engine_label(self) -> str:
        """Engine the saved options belong to (for reading the file); relative to the app folder when inside it."""
        parts = list(self._cmd or [])
        if parts:
            app_dir = Path(__file__).resolve().parents[3]
            try:
                parts[0] = Path(parts[0]).resolve().relative_to(app_dir).as_posix()
            except ValueError:
                pass
        return " ".join(parts)

    def _load_overrides(self) -> dict[str, Any]:
        try:
            raw = json.loads(self._overrides_path().read_text(encoding="utf-8"))
        except Exception:
            return {}
        values = raw.get("values") if isinstance(raw, dict) else None
        return dict(values) if isinstance(values, dict) else {}

    def _save_overrides(self) -> None:
        p = self._overrides_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps({"engine": self._engine_label(), "values": self._option_overrides}, ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )

    def _env_override(self, name: str) -> Any:
        if name == "Threads":
            return self._env_threads
        if name in {"USI_Hash", "Hash"}:
            return self._env_hash_mb
        return None

    def _effective_option(self, name: str) -> Any:
        if name in self._option_overrides:
            return self._option_overrides[name]
        env = self._env_override(name)
        if env is not None:
            return env
        if name == "EvalDir" and self._eval_dir:
            return self._eval_dir  # auto-detected folder actually sent at boot
        spec = self._option_specs.get(name)
        return spec["default"] if spec else None

    @staticmethod
    def hash_max_mb() -> int | None:
        mem = system_memory_mb()
        return max(1, mem // 2) if mem else None

    async def options_wire(self) -> dict[str, Any]:
        """Engine options with defaults reported by the engine itself (starts the engine if needed)."""
        if self._configured:
            async with self._lock:
                await self._ensure_engine_ready_locked()
        options = []
        for spec in self._option_specs.values():
            options.append({**spec, "value": self._effective_option(spec["name"]), "changed": spec["name"] in self._option_overrides})
        return {
            "engine_name": self._engine_name,
            "options": options,
            "system": {"memory_mb": system_memory_mb(), "hash_max_mb": self.hash_max_mb(), "cpus": os.cpu_count()},
        }

    def _coerce_option(self, spec: dict[str, Any], value: Any) -> Any:
        t = spec.get("type")
        if t == "spin":
            v = int(value)
            lo, hi = spec.get("min"), spec.get("max")
            if spec["name"] in {"USI_Hash", "Hash"} and self.hash_max_mb():
                hi = min(hi, self.hash_max_mb()) if hi is not None else self.hash_max_mb()
            if lo is not None:
                v = max(lo, v)
            if hi is not None:
                v = min(hi, v)
            return v
        if t == "check":
            return value if isinstance(value, bool) else str(value).lower() in {"true", "1", "on"}
        if t == "combo":
            v = str(value)
            if spec.get("vars") and v not in spec["vars"]:
                raise ValueError(f"{spec['name']}: '{v}' is not one of {spec['vars']}")
            return v
        return str(value)

    async def set_options(self, values: dict[str, Any]) -> None:
        """Store changed options (values equal to the engine default are dropped) and restart the engine."""
        if not self._option_specs:
            await self.options_wire()
        overrides: dict[str, Any] = {}
        for name, value in (values or {}).items():
            spec = self._option_specs.get(name)
            if not spec or spec.get("type") == "button" or name == "MultiPV":
                continue
            v = self._coerce_option(spec, value)
            if name == "EvalDir" and self._eval_dir and v == self._eval_dir and "EvalDir" not in self._option_overrides:
                continue  # unchanged auto-detected value, keep detecting it
            if v != spec.get("default"):
                overrides[name] = v
        self._option_overrides = overrides
        self._save_overrides()
        self._batch_cancel = True
        await self.shutdown()  # next analysis boots the engine with the new options

    def _option_value_text(self, value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    async def attach_owner_sender(self, sender: SenderFn) -> None:
        self._batch_cancel = True
        async with self._lock:
            self._owner_sender = sender
            if self._analysis_running:
                await self._stop_locked("owner changed", emit=True)

    async def clear_owner_sender(self) -> None:
        async with self._lock:
            self._owner_sender = None

    async def owner_disconnected(self) -> None:
        self._batch_cancel = True
        self._sync_pending = None  # a start queued just before the disconnect must not run
        async with self._lock:
            await self._stop_locked("owner disconnected", emit=True)
            self._owner_sender = None

    async def shutdown(self) -> None:
        async with self._lock:
            await self._stop_locked("server shutdown", emit=False)
            proc = self._proc
            self._proc = None
            reader = self._reader_task
            self._reader_task = None
            self._status = "idle" if self._configured else "not_configured"
        if proc and proc.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                proc.terminate()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            if proc.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    proc.kill()
        if reader and not reader.done():
            reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reader

    async def stop(self, reason: str = "stopped") -> None:
        async with self._lock:
            await self._stop_locked(reason, emit=True)

    async def start_for_game(
        self, game: GameTree, *, node_id: str | None = None, multipv: int | None = None
    ) -> tuple[bool, str]:
        target_node_id = node_id or game.current_node_id
        try:
            path = game.path_to_node(target_node_id)
        except Exception as exc:
            reason = f"invalid node for analysis: {exc}"
            await self._emit("analysis:stopped", {"reason": reason})
            return False, reason

        moves = [n.move_usi for n in path if n.move_usi]
        position_cmd = sfen_to_position_command(game.initial_sfen, moves)
        if multipv is None:
            multipv = _sanitize_multipv((game.ui_state or {}).get("analysis_multipv"), 1)

        async with self._lock:
            if self._owner_sender is None:
                # nobody is connected (session closed): never leave the engine searching unattended.
                # Also catches a start that was already waiting for the lock when the session ended.
                return False, "no active session"
            if not self._configured:
                self._status = "not_configured"
                reason = "USI engine is not configured (set SHOGI_ANALYZER_ENGINE_PATH)"
            else:
                try:
                    await self._ensure_engine_ready_locked()
                    if self._analysis_running:
                        await self._stop_locked("restarting", emit=False)
                    await self._apply_options_locked(multipv)
                    self._bestmove_event.clear()
                    self._latest_pv_by_index = {}
                    self._info_version += 1
                    self._last_sent_info_version = -1
                    self._last_sent_at_monotonic = 0.0
                    self._last_snapshot_signature = None
                    self._analysis_node_id = target_node_id
                    self._analysis_started_monotonic = asyncio.get_running_loop().time()
                    self._active_multipv = multipv
                    self._analysis_running = True
                    self._status = "analyzing"
                    await self._send_line_locked(position_cmd)
                    await self._send_line_locked("go infinite")
                    if self._ticker_task is None or self._ticker_task.done():
                        self._ticker_task = asyncio.create_task(self._ticker_loop())
                    return True, "started"
                except Exception as exc:
                    self._last_error = str(exc)
                    self._status = "error"
                    reason = f"analysis start failed: {exc}"
        await self._emit("analysis:stopped", {"reason": reason})
        return False, reason

    def schedule_sync(self, fn: Callable[[], Awaitable[None]]) -> None:
        """Run fn (an analysis start/stop for the current position) in the background.

        Requests made while one is running are coalesced: only the latest runs next,
        so stepping quickly through moves does not queue one engine restart per step.
        """
        self._sync_pending = fn
        if self._sync_task is None or self._sync_task.done():
            self._sync_task = asyncio.create_task(self._sync_runner())

    async def _sync_runner(self) -> None:
        while self._sync_pending is not None:
            fn = self._sync_pending
            self._sync_pending = None
            try:
                await fn()
            except Exception as exc:
                self._last_error = str(exc)

    # ---------- whole-game analysis ("全解析") ----------
    @property
    def batch_running(self) -> bool:
        return self._batch_task is not None and not self._batch_task.done()

    def batch_status(self) -> dict[str, Any] | None:
        return dict(self._batch_progress) if self.batch_running and self._batch_progress else None

    def start_batch(
        self,
        game: GameTree,
        node_ids: list[str],
        seconds: float,
        on_finish: Callable[[], Awaitable[None]] | None = None,
        on_step: Callable[[str], Awaitable[None]] | None = None,
    ) -> tuple[bool, str]:
        if not self._configured:
            return False, "USI engine is not configured"
        if self.batch_running:
            return False, "全解析は実行中です"
        if not node_ids:
            return False, "解析する局面がありません"
        self._batch_cancel = False
        self._batch_task = asyncio.create_task(self._batch_loop(game, node_ids, seconds, on_finish, on_step))
        return True, "started"

    def cancel_batch(self) -> None:
        self._batch_cancel = True

    async def _batch_loop(
        self,
        game: GameTree,
        node_ids: list[str],
        seconds: float,
        on_finish: Callable[[], Awaitable[None]] | None,
        on_step: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        total = len(node_ids)
        result = "done"
        loop = asyncio.get_running_loop()
        try:
            for i, nid in enumerate(node_ids):
                if self._batch_cancel:
                    result = "cancelled"
                    break
                # "line" lets the client show exactly the line being analysed
                self._batch_progress = {"index": i, "total": total, "node_id": nid, "seconds": seconds, "line": node_ids}
                if on_step:
                    # move the shown position along with the analysis
                    await on_step(nid)
                await self._emit("analysis:batch", {"state": "running", **self._batch_progress})
                # MultiPV 1: the whole budget goes into the best line
                ok, reason = await self.start_for_game(game, node_id=nid, multipv=1)
                if not ok:
                    result = "error"
                    await self._emit("toast", {"level": "error", "message": f"全解析を中断しました: {reason}"})
                    break
                end = loop.time() + seconds
                while loop.time() < end and not self._batch_cancel:
                    await asyncio.sleep(0.1)
                await self._flush_latest()
            async with self._lock:
                await self._stop_locked("batch finished", emit=True)
        except asyncio.CancelledError:
            result = "cancelled"
            raise
        except Exception as exc:
            result = "error"
            self._last_error = str(exc)
        finally:
            self._batch_progress = None
            await self._emit("analysis:batch", {"state": result, "total": total})
            if on_finish and result != "error":
                with contextlib.suppress(Exception):
                    await on_finish()

    async def _flush_latest(self) -> None:
        """Send + store the newest lines for the node being analysed (the ticker may lag ~1s)."""
        if not self._analysis_running or not self._analysis_node_id:
            return
        lines = [self._latest_pv_by_index[i] for i in sorted(self._latest_pv_by_index) if i <= self._active_multipv]
        if not lines:
            return
        lines_json = _jsonable_lines(lines)
        node_id = self._analysis_node_id
        elapsed_ms = max(0, int((asyncio.get_running_loop().time() - self._analysis_started_monotonic) * 1000))
        await self._emit(
            "analysis:update",
            {"node_id": node_id, "elapsed_ms": elapsed_ms, "multipv": self._active_multipv, "lines": lines_json, "bestline": lines_json[0]},
        )
        with contextlib.suppress(Exception):
            self.store.save_analysis_snapshot(node_id=node_id, elapsed_ms=elapsed_ms, multipv=self._active_multipv, lines=lines_json)

    async def restart_if_enabled_for_game(self, game: GameTree) -> None:
        enabled = bool((game.ui_state or {}).get("analysis_enabled"))
        if enabled:
            await self.start_for_game(game)
        else:
            await self.stop("analysis disabled")

    async def _emit(self, type_: str, payload: dict | None = None) -> None:
        sender = self._owner_sender
        if not sender:
            return
        try:
            await sender(type_, payload or {})
        except Exception:
            # WebSocket close/takeover races should not crash the server.
            pass

    async def _ensure_engine_ready_locked(self) -> None:
        if not self._configured:
            raise RuntimeError("engine not configured")

        if self._proc is not None and self._proc.returncode is not None:
            self._proc = None
            self._status = "idle"

        if self._proc is None:
            self._status = "starting"
            self._last_error = None
            self._usiok_event = asyncio.Event()
            self._readyok_event = asyncio.Event()
            self._bestmove_event = asyncio.Event()
            self._option_specs = {}
            self._applied_multipv = None
            self._engine_name = None
            self._io_log.clear()

            if not self._cmd:
                raise RuntimeError("missing engine command")

            cmd0 = self._cmd[0]
            if len(self._cmd) == 1:
                p0 = Path(cmd0)
                if not p0.exists():
                    raise RuntimeError(f"engine executable not found: {p0}")

            cwd = None
            if len(self._cmd) == 1:
                p = Path(cmd0)
                if p.parent and str(p.parent) not in {"", "."}:
                    cwd = str(p.parent)

            try:
                self._proc = await asyncio.create_subprocess_exec(
                    *self._cmd,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    cwd=cwd,
                )
            except FileNotFoundError as exc:
                raise RuntimeError(f"failed to start engine: {exc}") from exc
            self._reader_task = asyncio.create_task(self._reader_loop())

            await self._send_line_locked("usi")
            await self._wait_event(self._usiok_event, timeout=self._usiok_timeout_s, label="usiok")

            # Apply boot options BEFORE the first isready.
            await self._apply_boot_options_locked()

            self._readyok_event.clear()
            await self._send_line_locked("isready")
            await self._wait_event(self._readyok_event, timeout=self._readyok_timeout_s, label="readyok")

            await self._send_line_locked("usinewgame")
            self._status = "ready"

        elif not self._analysis_running:
            self._status = "ready"

    def _io_tail(self, limit: int = 40) -> str:
        items = list(self._io_log)
        if len(items) > limit:
            items = items[-limit:]
        return "\n".join(items)

    async def _wait_event(self, event: asyncio.Event, *, timeout: float, label: str) -> None:
        deadline = time.monotonic() + float(timeout)
        while True:
            if event.is_set():
                return
            if self._proc and self._proc.returncode is not None:
                tail = self._io_tail()
                raise RuntimeError(
                    f"engine process exited (rc={self._proc.returncode}) while waiting for {label}\n" + tail
                )
            now = time.monotonic()
            if now >= deadline:
                tail = self._io_tail()
                raise RuntimeError(f"timeout waiting for {label}\n" + tail)
            # Wait in small chunks so we can detect process exit promptly.
            try:
                await asyncio.wait_for(event.wait(), timeout=min(0.25, deadline - now))
            except asyncio.TimeoutError:
                pass

    async def _send_line_locked(self, line: str) -> None:
        if not self._proc or not self._proc.stdin:
            raise RuntimeError("engine stdin is not available")
        self._io_log.append("> " + line.strip())
        self._proc.stdin.write((line.strip() + "\n").encode("utf-8", errors="ignore"))
        await self._proc.stdin.drain()

    def _guess_eval_dir(self) -> str | None:
        """Infer eval directory from engine path when not explicitly configured."""
        if self._eval_dir:
            p = Path(self._eval_dir)
            if p.exists() and p.is_dir():
                return str(p)
        if not self._cmd:
            return None
        if len(self._cmd) != 1:
            return None
        exe = Path(self._cmd[0])
        candidates = [exe.parent / "eval", exe.parent.parent / "eval", exe.parent.parent.parent / "eval"]
        for d in candidates:
            try:
                if (d / "nn.bin").exists():
                    return str(d)
                if d.exists() and d.is_dir():
                    # fallback: any file in the dir
                    for p in d.iterdir():
                        if p.is_file():
                            return str(d)
            except Exception:
                continue
        return None

    async def _apply_boot_options_locked(self) -> None:
        """Options that should be set before the first isready."""
        values: dict[str, Any] = {}
        # EvalDir (NNUE weights location) unless the user set it explicitly
        if self._supports_option("EvalDir") and "EvalDir" not in self._option_overrides:
            guess = self._guess_eval_dir()
            if guess:
                self._eval_dir = guess
                values["EvalDir"] = guess
        # explicit env overrides (kept for compatibility); otherwise engine defaults stay
        if self._env_threads is not None and self._supports_option("Threads"):
            values["Threads"] = self._env_threads
        if self._env_hash_mb is not None:
            values["USI_Hash" if self._supports_option("USI_Hash") else "Hash"] = self._env_hash_mb
        # values changed in the settings dialog win
        for name, value in self._option_overrides.items():
            if self._supports_option(name) and name != "MultiPV":
                values[name] = value
        for name, value in values.items():
            await self._send_line_locked(f"setoption name {name} value {self._option_value_text(value)}")

    def _supports_option(self, name: str) -> bool:
        return name in self._option_specs

    async def _apply_options_locked(self, multipv: int) -> None:
        pairs: list[tuple[str, int]] = []
        # MultiPV is the one that changes most often; skip the setoption + isready
        # round trip when it is already applied (every move/jump restarts analysis).
        if self._supports_option("MultiPV") and multipv != self._applied_multipv:
            pairs.append(("MultiPV", multipv))

        for name, value in pairs:
            await self._send_line_locked(f"setoption name {name} value {value}")

        if pairs:
            self._readyok_event.clear()
            await self._send_line_locked("isready")
            await self._wait_event(
                self._readyok_event, timeout=self._post_setoption_readyok_timeout_s, label="readyok after setoption"
            )
            self._applied_multipv = multipv

    async def _stop_locked(self, reason: str, *, emit: bool) -> None:
        was_running = self._analysis_running
        self._analysis_running = False
        self._analysis_node_id = None
        self._latest_pv_by_index = {}
        self._last_sent_info_version = -1
        self._last_snapshot_signature = None

        ticker = self._ticker_task
        self._ticker_task = None

        if ticker and not ticker.done():
            ticker.cancel()

        if was_running and self._proc and self._proc.returncode is None:
            self._bestmove_event.clear()
            with contextlib.suppress(Exception):
                await self._send_line_locked("stop")
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._bestmove_event.wait(), timeout=2.0)

        if ticker and not ticker.done():
            with contextlib.suppress(asyncio.CancelledError):
                await ticker

        if self._configured:
            self._status = "ready" if self._proc and self._proc.returncode is None else "idle"
        else:
            self._status = "not_configured"

        if emit:
            await self._emit("analysis:stopped", {"reason": reason})

    async def _ticker_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(0.1)
                payload: dict[str, Any] | None = None
                snapshot_node_id: str | None = None
                snapshot_elapsed = 0
                snapshot_multipv = 1
                snapshot_lines: list[dict[str, Any]] = []

                async with self._lock:
                    if not self._analysis_running or not self._analysis_node_id:
                        return

                    now = asyncio.get_running_loop().time()
                    elapsed_ms = max(0, int((now - self._analysis_started_monotonic) * 1000))
                    interval_s = 0.5 if elapsed_ms < 5000 else 1.0
                    if (now - self._last_sent_at_monotonic) < interval_s:
                        continue
                    if self._info_version == self._last_sent_info_version:
                        continue

                    lines_sorted = [
                        self._latest_pv_by_index[idx]
                        for idx in sorted(self._latest_pv_by_index)
                        if idx <= self._active_multipv
                    ]
                    if not lines_sorted:
                        continue

                    lines_json = _jsonable_lines(lines_sorted)
                    payload = {
                        "node_id": self._analysis_node_id,
                        "elapsed_ms": elapsed_ms,
                        "multipv": self._active_multipv,
                        "lines": lines_json,
                        "bestline": lines_json[0] if lines_json else None,
                    }
                    self._last_sent_at_monotonic = now
                    self._last_sent_info_version = self._info_version

                    signature = repr(
                        (
                            self._analysis_node_id,
                            self._active_multipv,
                            [
                                (
                                    l["pv_index"],
                                    l["score_type"],
                                    l["score_value"],
                                    l["depth"],
                                    tuple(l["pv_usi"]),
                                )
                                for l in lines_json
                            ],
                        )
                    )
                    if signature != self._last_snapshot_signature:
                        self._last_snapshot_signature = signature
                        snapshot_node_id = self._analysis_node_id
                        snapshot_elapsed = elapsed_ms
                        snapshot_multipv = self._active_multipv
                        snapshot_lines = lines_json

                if payload:
                    await self._emit("analysis:update", payload)
                if snapshot_node_id and snapshot_lines:
                    with contextlib.suppress(Exception):
                        self.store.save_analysis_snapshot(
                            node_id=snapshot_node_id,
                            elapsed_ms=snapshot_elapsed,
                            multipv=snapshot_multipv,
                            lines=snapshot_lines,
                        )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            async with self._lock:
                self._last_error = str(exc)
                if self._configured:
                    self._status = "error"
            await self._emit("analysis:stopped", {"reason": f"analysis ticker error: {exc}"})

    async def _reader_loop(self) -> None:
        try:
            while True:
                proc = self._proc
                if not proc or not proc.stdout:
                    return
                raw = await proc.stdout.readline()
                if not raw:
                    return
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                # Keep tail log for troubleshooting (timeouts / missing eval, etc).
                try:
                    self._io_log.append("< " + line)
                except Exception:
                    pass
                await self._handle_engine_line(line)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            async with self._lock:
                self._last_error = str(exc)
                if self._configured:
                    self._status = "error"
            await self._emit("analysis:stopped", {"reason": f"engine reader error: {exc}"})
        finally:
            emit_reason: str | None = None
            async with self._lock:
                if self._proc and self._proc.returncode is None:
                    # If stdout closed unexpectedly, wait() will update returncode later.
                    pass
                if self._analysis_running:
                    self._analysis_running = False
                    self._analysis_node_id = None
                    self._latest_pv_by_index = {}
                    emit_reason = "engine process exited"
                self._proc = None
                if self._configured:
                    self._status = "idle"
            if emit_reason:
                await self._emit("analysis:stopped", {"reason": emit_reason})

    async def _handle_engine_line(self, line: str) -> None:
        if line == "usiok":
            self._usiok_event.set()
            return
        if line == "readyok":
            self._readyok_event.set()
            return
        if line.startswith("bestmove "):
            self._bestmove_event.set()
            return
        if line.startswith("id name "):
            self._engine_name = line[len("id name ") :].strip() or self._engine_name
            return
        if line.startswith("option name "):
            spec = parse_usi_option(line)
            if spec:
                self._option_specs[spec["name"]] = spec
            return
        if not line.startswith("info "):
            return
        parsed = self._parse_info_line(line)
        if not parsed:
            return
        # No lock here: this update has no await, so it is atomic on the event loop.
        # Taking self._lock would deadlock the reader while stop/start hold the lock
        # and wait for "bestmove"/"readyok" lines queued behind this info line.
        if not self._analysis_running or not self._analysis_node_id:
            return
        pv_index = int(parsed.get("pv_index", 1))
        self._latest_pv_by_index[pv_index] = parsed
        self._info_version += 1

    @staticmethod
    def _parse_info_line(line: str) -> dict[str, Any] | None:
        tokens = line.split()
        if not tokens or tokens[0] != "info":
            return None

        data: dict[str, Any] = {
            "pv_index": 1,
            "score_type": "unknown",
            "score_value": 0,
            "depth": 0,
            "seldepth": 0,
            "nodes": 0,
            "nps": 0,
            "hashfull": 0,
            "pv_usi": [],
        }

        i = 1
        while i < len(tokens):
            tok = tokens[i]
            if tok == "pv":
                data["pv_usi"] = tokens[i + 1 :]
                break
            if tok in {"depth", "seldepth", "multipv", "nodes", "nps", "hashfull"}:
                if i + 1 < len(tokens):
                    try:
                        value = int(tokens[i + 1])
                    except ValueError:
                        value = 0
                    if tok == "multipv":
                        data["pv_index"] = max(1, value)
                    else:
                        data[tok] = value
                    i += 2
                    continue
            if tok == "score":
                if i + 2 < len(tokens):
                    score_type = tokens[i + 1]
                    try:
                        score_value = int(tokens[i + 2])
                    except ValueError:
                        score_value = 0
                    if score_type in {"cp", "mate"}:
                        data["score_type"] = score_type
                        data["score_value"] = score_value
                    i += 3
                    # Skip optional bounds token(s) if present.
                    while i < len(tokens) and tokens[i] in {"upperbound", "lowerbound"}:
                        i += 1
                    continue
            i += 1

        pv = data.get("pv_usi") or []
        if not isinstance(pv, list) or not pv:
            return None
        return data
