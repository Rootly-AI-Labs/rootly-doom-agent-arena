#!/usr/bin/env python3
"""Smoke-test Doom Arena participant intent API endpoints."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request


def now_ms() -> int:
    return int(time.time() * 1000)


def request(
    server_url: str,
    method: str,
    path: str,
    body: bytes | None = None,
    content_type: str | None = None,
) -> tuple[int, bytes]:
    headers = {}
    if content_type is not None:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(
        server_url.rstrip("/") + path,
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def expect(status: int, allowed: set[int], label: str) -> None:
    if status not in allowed:
        raise RuntimeError(f"{label} returned HTTP {status}, expected {sorted(allowed)}")
    print(f"ok {label}: HTTP {status}")


def post_json(server_url: str, path: str, payload: object) -> tuple[int, bytes]:
    return request(
        server_url,
        "POST",
        path,
        json.dumps(payload).encode("utf-8"),
        "application/json",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test participant intent API.")
    parser.add_argument("--server-url", default="http://127.0.0.1:8001")
    args = parser.parse_args()
    server_url = args.server_url.rstrip("/")

    reset_payload = {
        "arena_mode": "duel",
        "player_1_model": "codex",
        "player_2_model": "claude",
        "round": 1,
        "seed": 42,
        "timeout_seconds": 120,
    }
    status, body = post_json(server_url, "/api/arena/reset", reset_payload)
    expect(status, {200}, "POST /api/arena/reset")
    reset = json.loads(body.decode("utf-8"))
    run_id = str(reset["run_id"])
    scenario_id = str(reset["scenario_id"])

    issued = now_ms()
    payload = {
        "run_id": run_id,
        "scenario_id": scenario_id,
        "participant_id": "player_1",
        "intent": "engage_opponent",
        "style": "balanced",
        "target_id": "player_2",
        "preferred_distance": 600,
        "aggression": 0.5,
        "duration_ms": 2000,
        "issued_at_ms": issued,
    }
    status, _ = post_json(server_url, "/api/arena/participant-intents", payload)
    expect(status, {200}, "POST old valid /api/arena/participant-intents")

    status, body = request(server_url, "GET", "/api/arena/participant-intents")
    expect(status, {200}, "GET /api/arena/participant-intents")
    text = body.decode("utf-8", errors="replace")
    if "engage_opponent" not in text or "player_1" not in text:
        raise RuntimeError("participant intent TSV did not contain valid intent")
    required_columns = {
        "strafe_direction",
        "movement_bias",
        "fire_policy",
        "distance_policy",
        "replan_if",
        "sequence_number",
        "decision_cadence_ms",
    }
    header_columns = set(text.splitlines()[0].split("\t"))
    missing_columns = sorted(required_columns - header_columns)
    if missing_columns:
        raise RuntimeError(f"participant intent TSV missing new columns: {missing_columns}")
    print("ok TSV includes tactical intent columns")

    extended_payload = {
        **payload,
        "participant_id": "player_2",
        "intent": "strafe_attack",
        "style": "aggressive",
        "target_id": "player_1",
        "strafe_direction": "alternate",
        "movement_bias": "circle",
        "fire_policy": "burst_when_aligned",
        "distance_policy": "kite",
        "replan_if": ["lost_los", "stuck", "low_health"],
        "sequence_number": 7,
        "decision_cadence_ms": 750,
        "issued_at_ms": now_ms(),
    }
    status, _ = post_json(server_url, "/api/arena/participant-intents", extended_payload)
    expect(status, {200}, "POST extended /api/arena/participant-intents")
    status, body = request(server_url, "GET", "/api/arena/participant-intents")
    expect(status, {200}, "GET extended /api/arena/participant-intents")
    extended_text = body.decode("utf-8", errors="replace")
    for expected in ("alternate", "circle", "burst_when_aligned", "kite", "lost_los,stuck,low_health", "\t7\t750"):
        if expected not in extended_text:
            raise RuntimeError(f"extended participant intent TSV missing {expected!r}")
    print("ok extended tactical payload persisted")

    invalid_cases = [
        ("invalid participant", {**payload, "participant_id": "player_3"}),
        ("invalid intent", {**payload, "intent": "teleport_attack"}),
        ("invalid style", {**payload, "style": "reckless"}),
        ("invalid strafe_direction", {**payload, "strafe_direction": "sideways"}),
        ("invalid movement_bias", {**payload, "movement_bias": "wander"}),
        ("invalid fire_policy", {**payload, "fire_policy": "spray"}),
        ("invalid distance_policy", {**payload, "distance_policy": "teleport"}),
        ("invalid replan_if", {**payload, "replan_if": ["lost_los", "hungry"]}),
        ("invalid decision_cadence_ms", {**payload, "decision_cadence_ms": 0}),
        ("expired intent", {**payload, "issued_at_ms": issued - 3000, "expires_at_ms": issued - 1000}),
    ]
    for label, invalid_payload in invalid_cases:
        status, _ = post_json(server_url, "/api/arena/participant-intents", invalid_payload)
        expect(status, {400}, f"POST {label}")

    status, _ = post_json(server_url, "/api/arena/reset", reset_payload)
    expect(status, {200}, "POST reset clears intents")

    status, body = request(server_url, "GET", "/api/arena/participant-intents")
    expect(status, {200}, "GET cleared /api/arena/participant-intents")
    cleared = body.decode("utf-8", errors="replace").splitlines()
    if len([line for line in cleared if line.strip()]) != 1:
        raise RuntimeError("participant intents were not cleared on reset")

    print("participant intent API smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
