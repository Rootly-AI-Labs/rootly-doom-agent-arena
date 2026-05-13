#!/usr/bin/env python3
"""Smoke-test Doom Arena MCP duel tool behavior without real Codex/Claude."""

from __future__ import annotations

import argparse
import json
import secrets
from pathlib import Path
from typing import Any

from doom_arena_mcp import DoomArenaClient, DoomArenaError, tool_definitions


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_TOKENS_PATH = REPO_ROOT / "src" / "arena_controller_tokens.local.json"

FORBIDDEN_TOOL_NAMES = {
    "kill_enemy",
    "kill_all_enemies",
    "teleport_player",
    "give_weapon",
    "set_player_angle",
    "set_enemy_health",
    "remove_enemy",
    "set_participant_health",
    "set_winner",
    "damage_participant",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test MCP duel tools.")
    parser.add_argument("--server-url", default="http://127.0.0.1:8001")
    parser.add_argument("--no-controller-tokens", action="store_true")
    return parser.parse_args()


def parse_json_object(label: str, text: str) -> dict[str, Any]:
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise AssertionError(f"{label} did not return a JSON object")
    return parsed


def main() -> int:
    args = parse_args()
    client = DoomArenaClient(args.server_url)
    tools = {tool["name"] for tool in tool_definitions()}
    forbidden = sorted(tools & FORBIDDEN_TOOL_NAMES)
    if forbidden:
        raise AssertionError(f"Forbidden direct-mutation tools exposed: {forbidden}")
    for name in {"set_participant_ready", "wait_for_match_start", "set_participant_intent"}:
        if name not in tools:
            raise AssertionError(f"missing expected MCP tool: {name}")

    reset = parse_json_object(
        "reset_duel",
        client.reset_duel("codex", "claude", 1, 42, 120),
    )
    if reset.get("arena_mode") != "duel" or not reset.get("run_id"):
        raise AssertionError("reset_duel did not return duel metadata")
    p1_token = secrets.token_urlsafe(18)
    p2_token = secrets.token_urlsafe(18)
    token_payload = {
        "run_id": reset["run_id"],
        "player_1": {"model": "codex", "controller_token": p1_token},
        "player_2": {"model": "claude", "controller_token": p2_token},
        "enforce_controller_tokens": not args.no_controller_tokens,
    }
    CONTROLLER_TOKENS_PATH.write_text(json.dumps(token_payload, indent=2) + "\n", encoding="utf-8")

    p1_ready = parse_json_object(
        "set_participant_ready(player_1)",
        client.set_participant_ready("player_1", controller_token=p1_token),
    )
    p2_ready = parse_json_object(
        "set_participant_ready(player_2)",
        client.set_participant_ready("player_2", controller_token=p2_token),
    )
    if not p1_ready.get("ready") or not p2_ready.get("ready"):
        raise AssertionError("participant ready signals were not accepted")

    p1_command = parse_json_object(
        "set_participant_intent(player_1)",
        client.set_participant_intent(
            "player_1",
            "engage_opponent",
            style="balanced",
            target_id="player_2",
            duration_ms=2500,
            controller_token=p1_token,
        ),
    )
    p2_command = parse_json_object(
        "set_participant_intent(player_2)",
        client.set_participant_intent(
            "player_2",
            "strafe_attack",
            style="aggressive",
            target_id="player_1",
            duration_ms=2500,
            controller_token=p2_token,
        ),
    )
    if not p1_command.get("accepted") or not p2_command.get("accepted"):
        raise AssertionError("participant intents were not accepted")

    wrong_token_checks: dict[str, str] = {}
    if not args.no_controller_tokens:
        for label, participant_id, token in [
            ("player_1_token_controls_player_2", "player_2", p1_token),
            ("player_2_token_controls_player_1", "player_1", p2_token),
            ("missing_token_controls_player_1", "player_1", None),
        ]:
            try:
                client.set_participant_intent(participant_id, "hold", controller_token=token)
            except DoomArenaError as exc:
                wrong_token_checks[label] = str(exc)
            else:
                raise AssertionError(f"{label} unexpectedly succeeded")

    p1_stop = parse_json_object("stop_participant_intent(player_1)", client.stop_participant_intent("player_1", controller_token=p1_token))
    p2_stop = parse_json_object("stop_participant_intent(player_2)", client.stop_participant_intent("player_2", controller_token=p2_token))
    if not p1_stop.get("accepted") or not p2_stop.get("accepted"):
        raise AssertionError("stop_participant_intent was not accepted")

    events = parse_json_object("get_duel_events", client.get_duel_events(reset["run_id"], 5))
    if "events" not in events:
        raise AssertionError("get_duel_events missing events")

    state_status: dict[str, Any]
    try:
        state = parse_json_object("get_arena_state", client.get_arena_state(reset["run_id"]))
        p1_obs = parse_json_object(
            "get_participant_observation(player_1)",
            client.get_participant_observation("player_1", controller_token=p1_token),
        )
        p2_obs = parse_json_object(
            "get_participant_observation(player_2)",
            client.get_participant_observation("player_2", controller_token=p2_token),
        )
        result = parse_json_object("get_match_result", client.get_match_result(reset["run_id"]))
        for label, payload in {"state": state, "p1_obs": p1_obs, "p2_obs": p2_obs, "result": result}.items():
            if not payload:
                raise AssertionError(f"{label} returned empty JSON")
        state_status = {"available": True, "phase": result.get("phase", ""), "run_id": state.get("run_id", "")}
    except DoomArenaError as exc:
        state_status = {
            "available": False,
            "reason": str(exc),
            "note": "Browser/WASM is probably not running, so arena_game_state.local.tsv is not exported yet.",
        }

    print(
        json.dumps(
            {
                "ok": True,
                "run_id": reset["run_id"],
                "forbidden_tools_exposed": forbidden,
                "participant_intents": [p1_command["intent_id"], p2_command["intent_id"]],
                "intent_stops": [p1_stop["participant_id"], p2_stop["participant_id"]],
                "controller_tokens_enforced": not args.no_controller_tokens,
                "wrong_token_checks": wrong_token_checks,
                "state_status": state_status,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
