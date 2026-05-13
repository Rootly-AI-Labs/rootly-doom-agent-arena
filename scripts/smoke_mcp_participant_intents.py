#!/usr/bin/env python3
"""Smoke-test MCP participant intent tools."""

from __future__ import annotations

import argparse
import json
import secrets
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from doom_arena_mcp import (
    CONTROLLER_TOKENS_PATH,
    EXPOSE_LOW_LEVEL_PARTICIPANT_MCP,
    DoomArenaClient,
    DoomArenaError,
    parse_participant_intent_rows,
    tool_definitions,
)
from doom_arena_duel_prompts import instructions as render_participant_instructions


REPO_ROOT = Path(__file__).resolve().parents[1]


def request(server_url: str, method: str, path: str) -> tuple[int, bytes]:
    req = urllib.request.Request(server_url.rstrip("/") + path, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def parse_json_object(label: str, text: str) -> dict[str, Any]:
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise AssertionError(f"{label} did not return a JSON object")
    return payload


def expect_doom_error(label: str, fn: Any) -> None:
    try:
        fn()
    except DoomArenaError as exc:
        print(f"ok {label}: {exc}")
        return
    raise AssertionError(f"{label} did not fail")


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test MCP participant intent tools.")
    parser.add_argument("--server-url", default="http://127.0.0.1:8001")
    args = parser.parse_args()

    tools = {tool["name"] for tool in tool_definitions()}
    for name in {
        "set_participant_ready",
        "wait_for_match_start",
        "set_participant_intent",
        "stop_participant_intent",
    }:
        if name not in tools:
            raise AssertionError(f"missing MCP tool: {name}")
    intent_tool = next(tool for tool in tool_definitions() if tool["name"] == "set_participant_intent")
    intent_properties = intent_tool["inputSchema"]["properties"]
    for name in {
        "strafe_direction",
        "movement_bias",
        "fire_policy",
        "distance_policy",
        "replan_if",
        "sequence_number",
        "decision_cadence_ms",
    }:
        if name not in intent_properties:
            raise AssertionError(f"set_participant_intent schema missing {name}")
    for name in {"set_participant_input", "stop_participant"}:
        if EXPOSE_LOW_LEVEL_PARTICIPANT_MCP:
            if name not in tools:
                raise AssertionError(f"missing debug MCP tool: {name}")
        elif name in tools:
            raise AssertionError(f"low-level participant MCP tool should be hidden by default: {name}")
    print("ok MCP tool definitions expose high-level participant intents only")

    instruction_text = render_participant_instructions(
        "player_1",
        "codex",
        "player_2",
        "token",
        True,
        decision_cadence_ms=750,
        intent_duration_ms=3000,
    )
    for snippet in (
        "set_participant_ready",
        "wait_for_match_start",
        "waiting_for_agents",
        "immediately observe again",
        "Do not call `Start-Sleep`",
        "sequence_number",
        "increment it on every decision",
        "Doom continues executing the latest valid policy",
    ):
        if snippet not in instruction_text:
            raise AssertionError(f"generated instructions missing snippet: {snippet}")
    print("ok generated instructions mention ready handshake, immediate chatbot loop, and sequence_number")

    client = DoomArenaClient(args.server_url)
    previous_tokens = CONTROLLER_TOKENS_PATH.read_bytes() if CONTROLLER_TOKENS_PATH.exists() else None
    try:
        reset = parse_json_object("reset_duel", client.reset_duel("codex", "claude", 1, 42, 120))
        run_id = str(reset["run_id"])
        p1_token = secrets.token_urlsafe(18)
        p2_token = secrets.token_urlsafe(18)
        CONTROLLER_TOKENS_PATH.write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "player_1": {"model": "codex", "controller_token": p1_token},
                    "player_2": {"model": "claude", "controller_token": p2_token},
                    "enforce_controller_tokens": True,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        p1_intent = parse_json_object(
            "set_participant_ready(player_1)",
            client.set_participant_ready("player_1", controller_token=p1_token),
        )
        if not p1_intent.get("accepted") or not p1_intent.get("ready"):
            raise AssertionError("player_1 ready signal was not accepted")
        p2_ready = parse_json_object(
            "set_participant_ready(player_2)",
            client.set_participant_ready("player_2", controller_token=p2_token),
        )
        if not p2_ready.get("accepted") or not p2_ready.get("ready"):
            raise AssertionError("player_2 ready signal was not accepted")
        status, ready_body = request(args.server_url, "GET", "/api/arena/participant-ready")
        if status != 200:
            raise AssertionError(f"GET /api/arena/participant-ready returned HTTP {status}")
        ready_text = ready_body.decode("utf-8", errors="replace")
        if "player_1" not in ready_text or "player_2" not in ready_text:
            raise AssertionError("participant ready TSV did not include both participants")
        print("ok participant ready MCP tools write durable ready state")

        wait_result = parse_json_object(
            "wait_for_match_start(player_1 short timeout)",
            client.wait_for_match_start("player_1", controller_token=p1_token, timeout_ms=100, poll_ms=50),
        )
        if "started" not in wait_result or "phase" not in wait_result:
            raise AssertionError("wait_for_match_start did not return start status")
        print("ok wait_for_match_start returns structured status")

        p1_intent = parse_json_object(
            "set_participant_intent(player_1)",
            client.set_participant_intent(
                "player_1",
                "engage_opponent",
                style="balanced",
                target_id="player_2",
                preferred_distance=600,
                aggression=0.5,
                duration_ms=2500,
                controller_token=p1_token,
                strafe_direction="auto",
                movement_bias="direct",
                fire_policy="only_when_aligned",
                distance_policy="maintain",
            ),
        )
        if not p1_intent.get("accepted") or p1_intent.get("participant_id") != "player_1":
            raise AssertionError("player_1 intent was not accepted")
        print("ok correct player_1 token can set intent")

        p2_intent = parse_json_object(
            "set_participant_intent(player_2 extended)",
            client.set_participant_intent(
                "player_2",
                "strafe_attack",
                style="aggressive",
                target_id="player_1",
                preferred_distance=500,
                aggression=0.8,
                duration_ms=3500,
                controller_token=p2_token,
                strafe_direction="alternate",
                movement_bias="circle",
                fire_policy="burst_when_aligned",
                distance_policy="kite",
                replan_if=["lost_los", "stuck"],
                sequence_number=3,
                decision_cadence_ms=750,
            ),
        )
        normalized = p2_intent.get("normalized_intent", {})
        if normalized.get("strafe_direction") != "alternate" or normalized.get("decision_cadence_ms") != 750:
            raise AssertionError("extended player_2 tactical intent fields were not normalized")
        print("ok correct player_2 token can set extended tactical intent")

        expect_doom_error(
            "wrong token rejected",
            lambda: client.set_participant_intent(
                "player_2",
                "hold",
                controller_token=p1_token,
            ),
        )
        expect_doom_error(
            "invalid participant rejected",
            lambda: client.set_participant_intent(
                "player_3",
                "hold",
                controller_token=p1_token,
            ),
        )
        expect_doom_error(
            "invalid intent rejected",
            lambda: client.set_participant_intent(
                "player_1",
                "teleport_attack",
                controller_token=p1_token,
            ),
        )
        expect_doom_error(
            "invalid style rejected",
            lambda: client.set_participant_intent(
                "player_1",
                "hold",
                style="reckless",
                controller_token=p1_token,
            ),
        )
        expect_doom_error(
            "invalid tactical enum rejected",
            lambda: client.set_participant_intent(
                "player_1",
                "hold",
                strafe_direction="sideways",
                controller_token=p1_token,
            ),
        )
        expect_doom_error(
            "invalid decision cadence rejected",
            lambda: client.set_participant_intent(
                "player_1",
                "hold",
                decision_cadence_ms=0,
                controller_token=p1_token,
            ),
        )

        stop_intent = parse_json_object(
            "stop_participant_intent(player_1)",
            client.stop_participant_intent("player_1", controller_token=p1_token),
        )
        if not stop_intent.get("accepted") or not stop_intent.get("cleared"):
            raise AssertionError("stop_participant_intent did not clear intent")
        status, body = request(args.server_url, "GET", "/api/arena/participant-intents")
        if status != 200:
            raise AssertionError(f"GET /api/arena/participant-intents returned HTTP {status}")
        remaining_rows = parse_participant_intent_rows(body.decode("utf-8", errors="replace"))
        if any(row.get("participant_id") == "player_1" for row in remaining_rows):
            raise AssertionError("player_1 intent was not cleared")
        print("ok stop_participant_intent clears only the active participant intent")

        p1_command = parse_json_object(
            "set_participant_input(player_1)",
            client.set_participant_input("player_1", forward=1, duration_ms=250, controller_token=p1_token),
        )
        if not p1_command.get("accepted"):
            raise AssertionError("existing set_participant_input was not accepted")
        print("ok internal set_participant_input path still works")

        p1_stop = parse_json_object(
            "stop_participant(player_1)",
            client.stop_participant("player_1", controller_token=p1_token),
        )
        if not p1_stop.get("accepted"):
            raise AssertionError("existing stop_participant was not accepted")
        print("ok internal stop_participant path still works")
    finally:
        if previous_tokens is None:
            CONTROLLER_TOKENS_PATH.unlink(missing_ok=True)
        else:
            CONTROLLER_TOKENS_PATH.write_bytes(previous_tokens)

    print("MCP participant intent smoke test passed")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    raise SystemExit(main())
