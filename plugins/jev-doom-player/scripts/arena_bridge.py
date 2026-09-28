"""Load and safely reuse the Doom Arena client from its source repository."""

from __future__ import annotations

import importlib
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any


ALLOWED_ENV_NAMES = {
    "OPENROUTER_API_KEY",
    "OPENROUTER_BASE_URL",
    "OPENROUTER_DECISIONS_URL",
    "OPENROUTER_MODEL",
    "DOOM_ARENA_BASE_URL",
}


class ArenaBridgeError(RuntimeError):
    """Raised when the trusted local Doom Arena dependency is unavailable."""


def _looks_like_repo_root(path: Path) -> bool:
    return (
        path.is_dir()
        and (path / "scripts" / "doom_arena_mcp.py").is_file()
        and (path / "scripts" / "doom_arena_map_blueprints.py").is_file()
        and (path / "src").is_dir()
    )


def resolve_repo_root(explicit: str | Path | None = None) -> Path:
    """Resolve the arena repository without embedding an absolute machine path."""

    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    configured = os.environ.get("DOOM_ARENA_REPO_ROOT", "").strip()
    if configured:
        candidates.append(Path(configured))

    for origin in (Path(__file__).resolve(), Path.cwd().resolve()):
        candidates.extend([origin, *origin.parents])

    seen: set[Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.expanduser().resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        if _looks_like_repo_root(resolved):
            return resolved

    raise ArenaBridgeError(
        "Could not locate rootly-doom-agent-arena. Set DOOM_ARENA_REPO_ROOT to the repository root."
    )


def load_repo_env(repo_root: Path, *, override: bool = False) -> set[str]:
    """Load only the sidecar's allowlisted names from the ignored repository .env."""

    path = repo_root / ".env"
    if not path.is_file():
        return set()
    loaded: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if name not in ALLOWED_ENV_NAMES:
            continue
        value = value.strip()
        if value and (override or not os.environ.get(name)):
            os.environ[name] = value
            loaded.add(name)
    return loaded


def load_arena_module(repo_root: Path | None = None) -> ModuleType:
    root = resolve_repo_root(repo_root)
    scripts_dir = root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    module = importlib.import_module("doom_arena_mcp")
    module_root = Path(module.REPO_ROOT).resolve()
    if module_root != root:
        raise ArenaBridgeError(
            "doom_arena_mcp was imported from a different repository; restart the plugin process."
        )
    return module


def load_controller_token(arena: ModuleType, client: Any, participant_id: str) -> str:
    """Strictly load the selected participant token without returning other secrets."""

    client._sync_run_metadata()
    if not client.run_id or client.run_id == "run_unknown":
        raise ArenaBridgeError("Arena run metadata is unavailable.")

    token_path = Path(arena.CONTROLLER_TOKENS_PATH)
    try:
        payload = json.loads(token_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ArenaBridgeError("The active run controller token file is missing.") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ArenaBridgeError("The active run controller token file is invalid.") from exc
    if not isinstance(payload, Mapping):
        raise ArenaBridgeError("The active run controller token payload is invalid.")
    if not bool(payload.get("enforce_controller_tokens")):
        raise ArenaBridgeError("The active run does not enforce participant controller tokens.")
    token_run_id = str(payload.get("run_id", ""))
    if token_run_id != client.run_id:
        raise ArenaBridgeError("The controller token file belongs to a different arena run.")
    participant = payload.get(participant_id)
    if not isinstance(participant, Mapping):
        raise ArenaBridgeError(f"No controller token is configured for {participant_id}.")
    token = str(participant.get("controller_token", ""))
    if not token:
        raise ArenaBridgeError(f"The controller token for {participant_id} is empty.")
    client._verify_controller_token(participant_id, token)
    return token


def read_filtered_observation(arena: ModuleType, client: Any, participant_id: str) -> dict[str, Any]:
    rows = arena.parse_state(client._request("GET", "/api/arena/state"))
    observation = arena.make_participant_observation(rows, participant_id)
    if not isinstance(observation, dict):
        raise ArenaBridgeError("Arena returned an invalid participant observation.")
    return observation


def recover_next_sequence(client: Any, participant_id: str) -> int:
    """Allocate above active and historical sequences for this run/participant."""

    client._sync_run_metadata()
    highest = 0
    for row in client._read_participant_intent_rows():
        if row.get("run_id") != client.run_id or row.get("participant_id") != participant_id:
            continue
        try:
            highest = max(highest, int(row.get("sequence_number") or 0))
        except (TypeError, ValueError):
            continue

    # The active intent endpoint intentionally omits expired and cleared rows.
    # Run stats retain the accepted intent lifecycle, which keeps sequence
    # allocation monotonic across sidecar restart and stop/reprepare cycles.
    request = getattr(client, "_request", None)
    if callable(request):
        try:
            stats = json.loads(request("GET", "/api/arena/run-stats"))
        except (OSError, TypeError, ValueError, RuntimeError):
            stats = {}
    else:
        stats = {}
    lifecycles = stats.get("intent_lifecycles", []) if isinstance(stats, Mapping) else []
    if isinstance(lifecycles, list):
        for row in lifecycles:
            if not isinstance(row, Mapping):
                continue
            if row.get("run_id") != client.run_id or row.get("participant_id") != participant_id:
                continue
            try:
                highest = max(highest, int(row.get("sequence_number") or 0))
            except (TypeError, ValueError):
                continue
    return highest + 1


def verify_active_sequence(client: Any, participant_id: str, sequence_number: int) -> bool:
    for row in client._read_participant_intent_rows():
        if row.get("run_id") != client.run_id or row.get("participant_id") != participant_id:
            continue
        try:
            return int(row.get("sequence_number") or 0) == sequence_number
        except (TypeError, ValueError):
            return False
    return False
