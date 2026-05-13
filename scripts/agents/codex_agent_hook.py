#!/usr/bin/env python3
"""Codex hook stub for Doom Arena duel runner.

Reads one observation JSON object from stdin and must write one action JSON
object to stdout. Wire CODEX_AGENT_CMD to a real local Codex wrapper command
that follows the same stdin/stdout contract.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys


def noop(observation: dict) -> dict:
    return {
        "participant_id": observation["participant_id"],
        "forward": 0,
        "strafe": 0,
        "turn": 0,
        "attack": False,
        "use": False,
        "duration_ms": int(observation.get("decision_interval_ms", 750)),
    }


def main() -> int:
    observation = json.load(sys.stdin)
    command = os.environ.get("CODEX_AGENT_CMD", "").strip()
    if os.environ.get("DOOM_ARENA_ALLOW_PLACEHOLDER_AGENT") == "1":
        sys.stdout.write(json.dumps(noop(observation), separators=(",", ":")) + "\n")
        return 0
    if not command:
        sys.stderr.write(
            "CODEX_AGENT_CMD is not set. Set it to a real Codex wrapper command, "
            "or set DOOM_ARENA_ALLOW_PLACEHOLDER_AGENT=1 for local no-op testing.\n"
        )
        return 2

    completed = subprocess.run(
        command,
        input=json.dumps(observation, separators=(",", ":")),
        text=True,
        capture_output=True,
        shell=True,
        check=False,
    )
    if completed.stderr:
        sys.stderr.write(completed.stderr)
    if completed.returncode != 0:
        return completed.returncode
    sys.stdout.write(completed.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
