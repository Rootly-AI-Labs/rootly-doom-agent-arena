#!/usr/bin/env python3
"""Smoke-test the non-blocking rolling tactical control loop."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from doom_arena_mcp_duel_orchestrator import RollingTacticalController


REPO_ROOT = Path(__file__).resolve().parents[1]


class FakeDoomArenaClient:
    def __init__(self):
        self.records: list[dict[str, Any]] = []

    def set_participant_intent(
        self,
        participant_id: str,
        intent: str,
        style: str = "balanced",
        target_id: str | None = None,
        preferred_distance: int = 600,
        aggression: float = 0.5,
        duration_ms: int = 2500,
        controller_token: str | None = None,
        *,
        strafe_direction: str = "auto",
        movement_bias: str = "direct",
        fire_policy: str = "only_when_aligned",
        distance_policy: str = "maintain",
        replan_if: Any = None,
        sequence_number: Any = None,
        decision_cadence_ms: Any = None,
    ) -> str:
        record = {
            "sent_at_ms": int(time.time() * 1000),
            "participant_id": participant_id,
            "intent": intent,
            "style": style,
            "target_id": target_id,
            "preferred_distance": preferred_distance,
            "aggression": aggression,
            "duration_ms": duration_ms,
            "controller_token": controller_token,
            "strafe_direction": strafe_direction,
            "movement_bias": movement_bias,
            "fire_policy": fire_policy,
            "distance_policy": distance_policy,
            "replan_if": replan_if,
            "sequence_number": sequence_number,
            "decision_cadence_ms": decision_cadence_ms,
        }
        self.records.append(record)
        return json.dumps({"accepted": True, "normalized_intent": record})


def sample_state() -> dict[str, Any]:
    return {
        "run_id": "run_smoke",
        "scenario_id": "duel_e1m8",
        "phase": "combat",
        "tick": 1,
        "player_1": {
            "health": 100,
            "ammo": 50,
            "opponent_visible": True,
            "opponent_distance": 700,
            "opponent_relative_angle": 7,
        },
        "player_2": {
            "health": 100,
            "ammo": 50,
            "opponent_visible": True,
            "opponent_distance": 700,
            "opponent_relative_angle": -7,
        },
    }


def tokens() -> dict[str, Any]:
    return {
        "player_1": {"controller_token": "token_player_1"},
        "player_2": {"controller_token": "token_player_2"},
    }


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def run_latency_case(latency_ms: int) -> dict[str, Any]:
    client = FakeDoomArenaClient()
    events: list[dict[str, Any]] = []

    def provider(participant_id: str, state: dict[str, Any], request_id: int) -> dict[str, Any]:
        time.sleep(latency_ms / 1000.0)
        return {
            "intent": "strafe_attack",
            "style": "aggressive",
            "movement_bias": "circle",
            "fire_policy": "only_when_aligned",
            "distance_policy": "maintain",
            "aggression": 0.7,
        }

    controller = RollingTacticalController(
        client,
        tokens(),
        decision_cadence_ms=750,
        intent_duration_ms=2500,
        max_in_flight_decisions=1,
        fallback_intent="search",
        fallback_style="balanced",
        event_sink=events.append,
        decision_provider=provider,
    )
    controller.start(sample_state())
    runtime_seconds = max(4.0, (latency_ms / 1000.0) + 1.5)
    deadline = time.time() + runtime_seconds
    while time.time() < deadline:
        controller.update_state(sample_state())
        time.sleep(0.025)
    controller.stop()
    metrics = controller.metrics()

    assert_true(metrics["number_of_intents_sent"] >= 2, f"latency {latency_ms}ms did not send rolling intents")
    assert_true(
        metrics["percent_time_with_active_intent"] >= 98.0,
        f"latency {latency_ms}ms active intent coverage too low: {metrics}",
    )
    if latency_ms < 2500:
        assert_true(
            metrics["number_of_fallbacks"] == 0,
            f"latency {latency_ms}ms should not need fallback: {metrics}",
        )
    else:
        assert_true(
            metrics["number_of_fallbacks"] >= 1,
            f"latency {latency_ms}ms should send fallback after expiry: {metrics}",
        )

    print(
        f"ok simulated latency {latency_ms}ms: "
        f"active={metrics['percent_time_with_active_intent']}% "
        f"fallbacks={metrics['number_of_fallbacks']} "
        f"intents={metrics['number_of_intents_sent']}"
    )
    return {"latency_ms": latency_ms, "metrics": metrics, "events": events[-8:]}


def run_stale_response_case() -> dict[str, Any]:
    client = FakeDoomArenaClient()
    events: list[dict[str, Any]] = []

    def provider(participant_id: str, state: dict[str, Any], request_id: int) -> dict[str, Any]:
        if request_id % 2 == 1:
            time.sleep(0.24)
        else:
            time.sleep(0.04)
        return {
            "intent": "engage_opponent" if request_id % 2 else "strafe_attack",
            "style": "balanced",
            "movement_bias": "direct",
            "fire_policy": "only_when_aligned",
            "distance_policy": "maintain",
        }

    controller = RollingTacticalController(
        client,
        tokens(),
        decision_cadence_ms=50,
        intent_duration_ms=500,
        max_in_flight_decisions=2,
        fallback_intent="search",
        fallback_style="balanced",
        event_sink=events.append,
        decision_provider=provider,
    )
    controller.start(sample_state())
    deadline = time.time() + 1.2
    while time.time() < deadline:
        controller.update_state(sample_state())
        time.sleep(0.01)
    controller.stop()
    metrics = controller.metrics()
    assert_true(
        metrics["number_of_stale_responses_discarded"] >= 1,
        f"expected stale responses with max_in_flight_decisions=2: {metrics}",
    )
    for participant_id in ("player_1", "player_2"):
        sequence_numbers = [
            int(record["sequence_number"])
            for record in client.records
            if record.get("participant_id") == participant_id and record.get("sequence_number") is not None
        ]
        assert_true(
            sequence_numbers == sorted(sequence_numbers),
            f"{participant_id} sequence numbers were not monotonic: {sequence_numbers}",
        )
    print(
        "ok stale response discard: "
        f"stale={metrics['number_of_stale_responses_discarded']} "
        f"intents={metrics['number_of_intents_sent']}"
    )
    return {"metrics": metrics, "events": events[-8:]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test rolling tactical loop timing.")
    parser.add_argument("--json", action="store_true", help="Print full JSON details after ok lines.")
    args = parser.parse_args()

    results = {
        "latency_cases": [run_latency_case(latency) for latency in (100, 750, 1500, 3000)],
        "stale_response_case": run_stale_response_case(),
    }
    if args.json:
        print(json.dumps({"ok": True, "results": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
