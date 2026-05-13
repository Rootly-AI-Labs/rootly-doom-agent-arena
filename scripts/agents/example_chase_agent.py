#!/usr/bin/env python3
"""Example Doom Arena agent that turns toward the opponent and fires on LOS."""

from __future__ import annotations

import json
import sys


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def main() -> int:
    observation = json.load(sys.stdin)
    participant_id = observation["participant_id"]
    state = observation.get("state", {})
    self_state = state.get(participant_id, {})
    duration_ms = int(observation.get("decision_interval_ms", 750))
    relative_angle = int(self_state.get("opponent_relative_angle", 0) or 0)
    distance = int(self_state.get("opponent_distance", 9999) or 9999)
    visible = bool(self_state.get("opponent_visible", False))

    turn = 0
    if relative_angle > 8:
        turn = 1
    elif relative_angle < -8:
        turn = -1

    action = {
        "participant_id": participant_id,
        "forward": 1 if distance > 420 or not visible else 0,
        "strafe": 0,
        "turn": clamp(turn, -1, 1),
        "attack": visible and abs(relative_angle) <= 10,
        "use": False,
        "duration_ms": max(100, min(2000, duration_ms)),
    }
    sys.stdout.write(json.dumps(action, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
