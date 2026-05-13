#!/usr/bin/env python3
"""Smoke-test Doom Arena Codex/Claude hook wrappers without browser/WASM."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]


def sample_observation(participant_id: str, model: str) -> dict[str, Any]:
    opponent_id = "player_2" if participant_id == "player_1" else "player_1"
    return {
        "participant_id": participant_id,
        "opponent_id": opponent_id,
        "model": model,
        "state_mode": "shared_full",
        "decision_interval_ms": 750,
        "agent_timeout_ms": 10000,
        "state": {
            participant_id: {
                "opponent_relative_angle": 0,
                "opponent_distance": 300,
                "opponent_visible": True,
            },
            opponent_id: {
                "opponent_relative_angle": 12,
                "opponent_distance": 300,
                "opponent_visible": True,
            },
        },
        "allowed_actions": {
            "forward": [-1, 0, 1],
            "strafe": [-1, 0, 1],
            "turn": [-1, 0, 1],
            "attack": [True, False],
            "use": [True, False],
            "duration_ms": [100, 2000],
        },
        "instruction": "Return only one JSON action object. Do not include prose.",
    }


def run_hook(script: Path, observation: dict[str, Any], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(observation, separators=(",", ":")),
        text=True,
        capture_output=True,
        cwd=REPO_ROOT,
        env=env,
        check=False,
    )


def assert_action(stdout: str, participant_id: str) -> dict[str, Any]:
    action = json.loads(stdout)
    if not isinstance(action, dict):
        raise RuntimeError("hook did not return a JSON object")
    if action.get("participant_id") != participant_id:
        raise RuntimeError(f"expected participant_id {participant_id}, got {action.get('participant_id')}")
    for key in ("forward", "strafe", "turn", "attack", "use", "duration_ms"):
        if key not in action:
            raise RuntimeError(f"action missing {key}")
    return action


def main() -> int:
    env = os.environ.copy()
    env["CODEX_AGENT_CMD"] = f"{sys.executable} {REPO_ROOT / 'scripts' / 'agents' / 'example_chase_agent.py'}"
    env["CLAUDE_AGENT_CMD"] = f"{sys.executable} {REPO_ROOT / 'scripts' / 'agents' / 'example_noop_agent.py'}"

    codex = run_hook(
        REPO_ROOT / "scripts" / "agents" / "codex_agent_hook.py",
        sample_observation("player_1", "codex"),
        env,
    )
    if codex.returncode != 0:
        raise RuntimeError(f"codex hook failed: {codex.stderr}")
    codex_action = assert_action(codex.stdout, "player_1")

    claude = run_hook(
        REPO_ROOT / "scripts" / "agents" / "claude_agent_hook.py",
        sample_observation("player_2", "claude"),
        env,
    )
    if claude.returncode != 0:
        raise RuntimeError(f"claude hook failed: {claude.stderr}")
    claude_action = assert_action(claude.stdout, "player_2")

    missing_env = os.environ.copy()
    missing_env.pop("CODEX_AGENT_CMD", None)
    missing_env.pop("DOOM_ARENA_ALLOW_PLACEHOLDER_AGENT", None)
    missing = run_hook(
        REPO_ROOT / "scripts" / "agents" / "codex_agent_hook.py",
        sample_observation("player_1", "codex"),
        missing_env,
    )
    if missing.returncode == 0:
        raise RuntimeError("codex hook succeeded even though CODEX_AGENT_CMD was missing")
    if "CODEX_AGENT_CMD is not set" not in missing.stderr:
        raise RuntimeError("missing CODEX_AGENT_CMD error was not clear")

    print(json.dumps({
        "ok": True,
        "codex_action": codex_action,
        "claude_action": claude_action,
        "missing_env_failure": missing.stderr.strip(),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
