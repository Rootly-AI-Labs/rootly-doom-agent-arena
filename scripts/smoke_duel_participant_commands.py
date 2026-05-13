#!/usr/bin/env python3
"""Smoke test for Doom Arena duel participant command plumbing."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from typing import Any


PARTICIPANT_HEADER = (
    "run_id\tscenario_id\tcommand_id\tissued_at_ms\texpires_at_ms\t"
    "participant_id\tforward\tstrafe\tturn\tattack\tuse\tduration_ms\n"
)


def now_ms() -> int:
    return int(time.time() * 1000)


def request(
    server_url: str,
    method: str,
    path: str,
    data: bytes | None = None,
    content_type: str | None = None,
) -> tuple[int, bytes]:
    headers = {}
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(
        server_url.rstrip("/") + path,
        data=data,
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


def make_row(run_id: str, scenario_id: str, participant_id: str, forward: int, turn: int) -> str:
    issued = now_ms()
    duration = 750
    row = [
        run_id,
        scenario_id,
        f"{participant_id}_smoke_{issued}",
        str(issued),
        str(issued + duration),
        participant_id,
        str(forward),
        "0",
        str(turn),
        "false",
        "false",
        str(duration),
    ]
    return "\t".join(row) + "\n"


def parse_state(body: bytes) -> list[dict[str, str]]:
    lines = body.decode("utf-8", errors="replace").splitlines()
    if not lines:
        return []
    header = lines[0].split("\t")
    return [dict(zip(header, line.split("\t"))) for line in lines[1:] if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test duel participant command API.")
    parser.add_argument("--server-url", default="http://127.0.0.1:8001")
    args = parser.parse_args()

    reset_payload = {
        "arena_mode": "duel",
        "player_1_model": "codex",
        "player_2_model": "claude",
        "round": 1,
        "seed": 42,
        "timeout_seconds": 120,
    }
    status, body = request(
        args.server_url,
        "POST",
        "/api/arena/reset",
        json.dumps(reset_payload).encode("utf-8"),
        "application/json",
    )
    expect(status, {200}, "POST /api/arena/reset")
    reset = json.loads(body.decode("utf-8"))
    if reset.get("arena_mode") != "duel":
        raise RuntimeError("reset did not enter duel mode")

    run_id = str(reset["run_id"])
    scenario_id = str(reset["scenario_id"])
    commands = (
        PARTICIPANT_HEADER
        + make_row(run_id, scenario_id, "player_1", 1, 0)
        + make_row(run_id, scenario_id, "player_2", 0, 1)
    )

    status, _ = request(
        args.server_url,
        "POST",
        "/api/arena/participant-commands",
        commands.encode("utf-8"),
        "text/tab-separated-values",
    )
    expect(status, {200}, "POST /api/arena/participant-commands")

    status, body = request(args.server_url, "GET", "/api/arena/participant-commands")
    expect(status, {200}, "GET /api/arena/participant-commands")
    text = body.decode("utf-8", errors="replace")
    if "player_1" not in text or "player_2" not in text:
        raise RuntimeError("participant command TSV did not include both participants")

    status, state_body = request(args.server_url, "GET", "/api/arena/state")
    if status == 200:
        participants = [row for row in parse_state(state_body) if row.get("kind") == "participant"]
        print(f"state participants visible: {len(participants)}")
    else:
        print("state not available yet; browser/WASM may not be running")

    print("duel participant command smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
