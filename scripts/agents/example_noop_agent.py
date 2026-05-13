#!/usr/bin/env python3
"""Example Doom Arena agent that always returns no-op."""

from __future__ import annotations

import json
import sys


def main() -> int:
    observation = json.load(sys.stdin)
    duration_ms = int(observation.get("decision_interval_ms", 750))
    action = {
        "participant_id": observation["participant_id"],
        "forward": 0,
        "strafe": 0,
        "turn": 0,
        "attack": False,
        "use": False,
        "duration_ms": duration_ms,
    }
    sys.stdout.write(json.dumps(action, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
