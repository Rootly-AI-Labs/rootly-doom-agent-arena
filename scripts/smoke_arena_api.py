#!/usr/bin/env python3
"""Smoke-test the local Doom Agent Arena API."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test Doom Agent Arena API.")
    parser.add_argument("--server-url", default="http://127.0.0.1:8001")
    return parser.parse_args()


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


def main() -> int:
    args = parse_args()
    server_url = args.server_url.rstrip("/")
    issued = int(time.time() * 1000)

    status, _ = request(server_url, "GET", "/api/arena/state")
    expect(status, {200, 404}, "GET /api/arena/state")

    player_payload = {
        "command_id": f"smoke_player_{issued}",
        "issued_at_ms": issued,
        "expires_at_ms": issued + 250,
        "duration_ms": 250,
        "forward": 1,
        "strafe": 0,
        "turn": 0,
        "attack": False,
        "use": False,
    }
    status, _ = request(
        server_url,
        "POST",
        "/api/arena/player-command",
        json.dumps(player_payload).encode("utf-8"),
        "application/json",
    )
    expect(status, {200}, "POST /api/arena/player-command")

    status, body = request(server_url, "GET", "/api/arena/player-command")
    expect(status, {200}, "GET /api/arena/player-command")
    if b"smoke_player_" not in body:
        raise RuntimeError("player command TSV did not contain smoke command_id")

    enemy_tsv = (
        "run_id\tscenario_id\tcommand_id\tissued_at_ms\texpires_at_ms\t"
        "target_type\ttarget\tcommand\targ1\targ2\n"
        f"smoke_run\te1m8_arena\tsmoke_enemy_{issued}\t{issued}\t"
        f"{issued + 1000}\tteam\tenemy\thold\t\t\n"
    ).encode("utf-8")
    status, _ = request(
        server_url,
        "POST",
        "/api/arena/enemy-commands",
        enemy_tsv,
        "text/tab-separated-values",
    )
    expect(status, {200}, "POST /api/arena/enemy-commands")

    status, body = request(server_url, "GET", "/api/arena/enemy-commands")
    expect(status, {200}, "GET /api/arena/enemy-commands")
    if b"smoke_enemy_" not in body:
        raise RuntimeError("enemy command TSV did not contain smoke command_id")

    status, body = request(server_url, "POST", "/api/arena/reset", b"", "application/json")
    expect(status, {200}, "POST /api/arena/reset")
    reset_payload = json.loads(body.decode("utf-8"))
    if not reset_payload.get("run_id") or not reset_payload.get("reset_requested"):
        raise RuntimeError("reset response did not include run_id/reset_requested")

    status, body = request(server_url, "GET", "/api/arena/run-metadata")
    expect(status, {200}, "GET /api/arena/run-metadata")
    if reset_payload["run_id"].encode("utf-8") not in body:
        raise RuntimeError("run metadata did not contain reset run_id")

    print("arena API smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
