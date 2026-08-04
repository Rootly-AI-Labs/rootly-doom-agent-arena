#!/usr/bin/env python3
"""Supervise the automated Codex benchmark harness for the /automation dashboard.

The dashboard replaces the manual "paste each prompt into a chat client" flow
with a single Start Benchmark button. This module owns the harness subprocess
(`harness-test/run_doom_benchmark.py`), streams its output to a log file, and
exposes start/status/stop for the HTTP layer.

Only one benchmark may run at a time.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
HARNESS_DIR = REPO_ROOT / "harness-test"
HARNESS_SCRIPT = HARNESS_DIR / "run_doom_benchmark.py"
AUTOMATION_LOG = HARNESS_DIR / "automation_run.log"

IS_WINDOWS = sys.platform == "win32"

MATCHES_MIN = 1
MATCHES_MAX = 50
LOG_TAIL_LINES = 400

# The harness drives agents through an agent CLI, so the process that serves
# this endpoint must be able to see that binary. Inside the runtime Docker
# image it cannot, which is the single most common setup mistake.
AGENT_CLIS = ("claude", "codex")
DEFAULT_AGENT_CLI = "claude"

DEFAULT_MODELS = {
    "claude": ("claude-opus-5", "claude-sonnet-5"),
    "codex": ("gpt-5.5", "gpt-5.4"),
}


class AutomationError(RuntimeError):
    """Raised for conditions the dashboard should render as a plain message."""


def _running_in_container() -> bool:
    if os.environ.get("DOOM_ARENA_IN_CONTAINER"):
        return True
    if Path("/.dockerenv").exists():
        return True
    return False


def cli_available(agent_cli: str) -> bool:
    return shutil.which(agent_cli) is not None


def preflight(agent_cli: str = DEFAULT_AGENT_CLI) -> dict[str, Any]:
    """Report whether this process can actually launch a benchmark."""
    if agent_cli not in AGENT_CLIS:
        agent_cli = DEFAULT_AGENT_CLI
    has_cli = cli_available(agent_cli)
    has_harness = HARNESS_SCRIPT.is_file()
    in_container = _running_in_container()

    blockers: list[str] = []
    if not has_harness:
        blockers.append(f"Harness script is missing: {HARNESS_SCRIPT}")
    if not has_cli:
        if in_container:
            blockers.append(
                f"The {agent_cli} CLI is not available inside the arena container. "
                "Run the server on the host (python scripts/doom_arena_server.py "
                f"--port 8001) so it can launch {agent_cli}."
            )
        else:
            blockers.append(
                f"The {agent_cli} CLI was not found on PATH. Install it and confirm "
                f"`{agent_cli} --version` works, then reload this page."
            )

    return {
        "agent_cli": agent_cli,
        "cli_available": has_cli,
        "available_clis": {name: cli_available(name) for name in AGENT_CLIS},
        "default_models": {k: list(v) for k, v in DEFAULT_MODELS.items()},
        "harness_available": has_harness,
        "in_container": in_container,
        "ready": not blockers,
        "blockers": blockers,
    }


class BenchmarkRunner:
    """Owns at most one harness subprocess and its captured log."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None
        self._log_handle: Any = None
        self._started_at: float = 0.0
        self._finished_at: float = 0.0
        self._exit_code: int | None = None
        self._config: dict[str, Any] = {}
        self._stopping = False

    # -- internal helpers -------------------------------------------------

    def _poll_locked(self) -> None:
        """Reap the process if it has exited. Caller must hold the lock."""
        if self._process is None:
            return
        code = self._process.poll()
        if code is None:
            return
        self._exit_code = code
        self._finished_at = time.time()
        if self._log_handle is not None:
            try:
                self._log_handle.close()
            except OSError:
                pass
            self._log_handle = None
        self._process = None

    def _is_running_locked(self) -> bool:
        self._poll_locked()
        return self._process is not None

    def _build_command(self, config: dict[str, Any]) -> list[str]:
        command = [
            sys.executable,
            "-u",  # unbuffered, so the dashboard log tail updates live
            str(HARNESS_SCRIPT),
            "--matches",
            str(config["matches"]),
            "--player-1-model",
            str(config["player_1_model"]),
            "--player-2-model",
            str(config["player_2_model"]),
            "--scenario-id",
            str(config["scenario_id"]),
            "--weapon-pickups",
            "true" if config["enable_weapon_pickups"] else "false",
            "--agent-cli",
            str(config["agent_cli"]),
            # The dashboard is served by this backend; stopping it mid-flight
            # would kill the page the user is watching.
            "--keep-backend",
        ]
        if config["agent_cli"] == "claude":
            command.append(
                "--bypass-permissions"
                if config.get("bypass_permissions", True)
                else "--no-bypass-permissions"
            )
        if not config.get("open_browser", True):
            command.append("--no-browser")
        return command

    # -- public API -------------------------------------------------------

    def start(self, config: dict[str, Any]) -> dict[str, Any]:
        checks = preflight(config["agent_cli"])
        if not checks["ready"]:
            raise AutomationError(checks["blockers"][0])

        with self._lock:
            if self._is_running_locked():
                raise AutomationError(
                    "A benchmark is already running. Stop it before starting another."
                )

            command = self._build_command(config)
            try:
                log_handle = AUTOMATION_LOG.open("w", encoding="utf-8")
            except OSError as error:
                raise AutomationError(f"Could not open the automation log: {error}") from error

            header = (
                f"$ {' '.join(command)}\n"
                f"# started {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            )
            log_handle.write(header)
            log_handle.flush()

            creation: dict[str, Any] = {}
            if IS_WINDOWS:
                creation["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                creation["start_new_session"] = True

            try:
                process = subprocess.Popen(
                    command,
                    cwd=REPO_ROOT,
                    text=True,
                    stdin=subprocess.DEVNULL,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    **creation,
                )
            except OSError as error:
                log_handle.close()
                raise AutomationError(f"Could not launch the harness: {error}") from error

            self._process = process
            self._log_handle = log_handle
            self._started_at = time.time()
            self._finished_at = 0.0
            self._exit_code = None
            self._stopping = False
            self._config = dict(config)

            return {
                "pid": process.pid,
                "log_path": str(AUTOMATION_LOG),
                "command": command,
                "config": self._config,
            }

    def stop(self) -> dict[str, Any]:
        with self._lock:
            if not self._is_running_locked():
                return {"stopped": False, "reason": "No benchmark is running."}

            process = self._process
            assert process is not None
            self._stopping = True

            if IS_WINDOWS:
                # Kill the whole tree: the harness spawns two codex agents.
                subprocess.run(
                    ["taskkill", "/T", "/F", "/PID", str(process.pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            else:
                import signal

                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except (ProcessLookupError, OSError):
                    process.terminate()

            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

            self._poll_locked()
            return {"stopped": True, "pid": process.pid}

    def log_tail(self, limit: int = LOG_TAIL_LINES) -> str:
        try:
            text = AUTOMATION_LOG.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        lines = text.splitlines()
        if len(lines) <= limit:
            return "\n".join(lines)
        return "\n".join(lines[-limit:])

    def status(self) -> dict[str, Any]:
        with self._lock:
            running = self._is_running_locked()
            pid = self._process.pid if self._process is not None else None
            started_at = self._started_at
            finished_at = self._finished_at
            exit_code = self._exit_code
            config = dict(self._config)
            stopping = self._stopping

        log = self.log_tail()
        progress = _parse_progress(log)

        if running:
            state = "running"
        elif started_at == 0.0:
            state = "idle"
        elif stopping:
            state = "stopped"
        elif exit_code == 0:
            state = "completed"
        else:
            state = "failed"

        elapsed = 0.0
        if started_at:
            elapsed = (finished_at or time.time()) - started_at

        return {
            "state": state,
            "running": running,
            "pid": pid,
            "exit_code": exit_code,
            "started_at": started_at or None,
            "finished_at": finished_at or None,
            "elapsed_seconds": round(elapsed, 1),
            "config": config,
            "log": log,
            "log_path": str(AUTOMATION_LOG),
            **progress,
        }


def _parse_progress(log: str) -> dict[str, Any]:
    """Pull match progress and session id out of the harness stdout."""
    completed = 0
    total = 0
    session_id = ""
    for line in log.splitlines():
        stripped = line.strip()
        if stripped.startswith("Completed matches:"):
            fragment = stripped.split(":", 1)[1].strip()
            if "/" in fragment:
                left, _, right = fragment.partition("/")
                try:
                    completed = int(left.strip())
                    total = int(right.strip())
                except ValueError:
                    continue
        elif stripped.startswith("Created session "):
            parts = stripped.split()
            if len(parts) >= 3:
                session_id = parts[2]
    return {
        "completed_matches": completed,
        "total_matches": total,
        "duel_session_id": session_id,
    }


RUNNER = BenchmarkRunner()


def normalize_config(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate dashboard input into harness arguments."""
    try:
        matches = int(payload.get("matches", 1))
    except (TypeError, ValueError):
        raise AutomationError("matches must be a whole number") from None
    if matches < MATCHES_MIN or matches > MATCHES_MAX:
        raise AutomationError(f"matches must be between {MATCHES_MIN} and {MATCHES_MAX}")

    scenario_id = str(payload.get("scenario_id") or "duel_e1m8_blind_spawn").strip()
    if not scenario_id:
        raise AutomationError("scenario_id must not be empty")

    agent_cli = str(payload.get("agent_cli") or DEFAULT_AGENT_CLI).strip().lower()
    if agent_cli not in AGENT_CLIS:
        raise AutomationError(f"agent_cli must be one of: {', '.join(AGENT_CLIS)}")

    fallback_1, fallback_2 = DEFAULT_MODELS[agent_cli]
    player_1_model = str(payload.get("player_1_model") or fallback_1).strip()
    player_2_model = str(payload.get("player_2_model") or fallback_2).strip()
    if not player_1_model or not player_2_model:
        raise AutomationError("Both player models must be set")

    weapons = payload.get("enable_weapon_pickups", True)
    if isinstance(weapons, str):
        weapons = weapons.strip().lower() not in {"false", "0", "no"}

    bypass = payload.get("bypass_permissions", True)
    if isinstance(bypass, str):
        bypass = bypass.strip().lower() not in {"false", "0", "no"}

    return {
        "matches": matches,
        "scenario_id": scenario_id,
        "agent_cli": agent_cli,
        "player_1_model": player_1_model,
        "player_2_model": player_2_model,
        "enable_weapon_pickups": bool(weapons),
        "bypass_permissions": bool(bypass),
        "open_browser": bool(payload.get("open_browser", True)),
    }
