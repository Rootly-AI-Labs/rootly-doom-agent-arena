#!/usr/bin/env python3
"""Browser-backed MCP duel smoke test.

This script assumes the local arena server is running and the Doom/WASM browser
tab is open. It resets duel mode, waits for matching browser-exported state,
uses controller-token protected MCP helpers for both participants, sends normal
input commands, and verifies state advances.
"""

from __future__ import annotations

import argparse
import json
import secrets
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any

from doom_arena_mcp import DoomArenaClient, DoomArenaError


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_TOKENS_PATH = REPO_ROOT / "src" / "arena_controller_tokens.local.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Browser-backed MCP duel E2E smoke test.")
    parser.add_argument("--server-url", default="http://127.0.0.1:8001")
    parser.add_argument("--timeout-seconds", type=int, default=30)
    parser.add_argument("--open-browser", dest="open_browser", action="store_true")
    parser.add_argument("--no-open-browser", dest="open_browser", action="store_false")
    parser.set_defaults(open_browser=True)
    return parser.parse_args()


def request_text(server_url: str, path: str) -> tuple[int, str]:
    request = urllib.request.Request(server_url.rstrip("/") + path, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except OSError as exc:
        raise RuntimeError(f"Could not reach Doom Arena server at {server_url}: {exc}") from exc


def open_duel_page(server_url: str) -> None:
    webbrowser.open(server_url.rstrip("/") + "/?duel=1", new=1, autoraise=True)


def parse_tsv(text: str) -> list[dict[str, str]]:
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        return []
    header = lines[0].split("\t")
    return [dict(zip(header, line.split("\t"))) for line in lines[1:]]


def parse_json_object(label: str, text: str) -> dict[str, Any]:
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise RuntimeError(f"{label} did not return a JSON object")
    return parsed


def write_controller_tokens(run_id: str) -> dict[str, Any]:
    tokens = {
        "run_id": run_id,
        "player_1": {"model": "codex", "controller_token": secrets.token_urlsafe(18)},
        "player_2": {"model": "claude", "controller_token": secrets.token_urlsafe(18)},
        "enforce_controller_tokens": True,
    }
    CONTROLLER_TOKENS_PATH.write_text(json.dumps(tokens, indent=2) + "\n", encoding="utf-8")
    return tokens


def read_controller_tokens() -> dict[str, Any]:
    if not CONTROLLER_TOKENS_PATH.exists():
        raise RuntimeError(f"Token file does not exist: {CONTROLLER_TOKENS_PATH}")
    return parse_json_object("controller token file", CONTROLLER_TOKENS_PATH.read_text(encoding="utf-8"))


def run_metadata(server_url: str) -> dict[str, Any]:
    status, body = request_text(server_url, "/api/arena/run-metadata")
    if status != 200:
        return {"reachable": False, "status": status, "body": body}
    rows = parse_tsv(body)
    row = rows[0] if rows else {}
    return {"reachable": True, "status": status, "body": body, "row": row}


def latest_state_status(client: DoomArenaClient, run_id: str) -> dict[str, Any]:
    try:
        state = parse_json_object("get_arena_state", client.get_arena_state(run_id))
        return {"available": True, "state": state}
    except DoomArenaError as exc:
        return {"available": False, "error": str(exc)}


def wait_for_active_duel_metadata(server_url: str, requested_run_id: str, timeout_seconds: int) -> tuple[str, dict[str, Any], bool]:
    deadline = time.time() + timeout_seconds
    latest: dict[str, Any] = {}
    superseded_since = 0.0
    superseded_run_id = ""
    while time.time() < deadline:
        latest = run_metadata(server_url)
        row = latest.get("row", {})
        current_run_id = str(row.get("run_id", ""))
        if current_run_id == requested_run_id and row.get("arena_mode") == "duel":
            return requested_run_id, latest, False
        if current_run_id and current_run_id != requested_run_id and row.get("arena_mode") == "duel":
            if current_run_id != superseded_run_id:
                superseded_run_id = current_run_id
                superseded_since = time.time()
            elif time.time() - superseded_since >= 1.0:
                return current_run_id, latest, True
        time.sleep(0.25)
    raise RuntimeError(
        "Timed out waiting for duel run metadata.\n"
        f"  expected run_id: {requested_run_id}\n"
        f"  latest metadata: {json.dumps(latest, indent=2)}"
    )


def wait_for_state(client: DoomArenaClient, run_id: str, timeout_seconds: int) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    latest: dict[str, Any] = {}
    while time.time() < deadline:
        latest = latest_state_status(client, run_id)
        if latest.get("available"):
            state = latest["state"]
            if state.get("run_id") == run_id and state.get("player_1") and state.get("player_2"):
                return state
        time.sleep(0.25)
    raise RuntimeError(
        "Timed out waiting for browser/WASM state export.\n"
        f"  expected run_id: {run_id}\n"
        f"  latest state status: {json.dumps(latest, indent=2)}\n"
        "Open the Doom page in the browser, click Start Duel or let this reset load, "
        "and keep the tab open so arena_game_state.local.tsv is exported."
    )


def state_changed(before: dict[str, Any], after: dict[str, Any]) -> bool:
    if int(after.get("tick", 0) or 0) > int(before.get("tick", 0) or 0):
        return True
    for participant_id in ("player_1", "player_2"):
        before_player = before.get(participant_id, {})
        after_player = after.get(participant_id, {})
        for key in ("x", "y", "angle", "last_action"):
            if before_player.get(key) != after_player.get(key):
                return True
    return False


def wait_for_state_change(client: DoomArenaClient, run_id: str, before: dict[str, Any], timeout_seconds: int) -> tuple[bool, dict[str, Any]]:
    deadline = time.time() + timeout_seconds
    latest = before
    while time.time() < deadline:
        time.sleep(0.25)
        latest = parse_json_object("get_arena_state", client.get_arena_state(run_id))
        if state_changed(before, latest):
            return True, latest
    return False, latest


def main() -> int:
    args = parse_args()
    server_url = args.server_url.rstrip("/")
    diagnostics: dict[str, Any] = {"server_url": server_url}
    client = DoomArenaClient(server_url)

    try:
        status, body = request_text(server_url, "/api/arena/run-metadata")
        diagnostics["server_reachable"] = status == 200
        diagnostics["initial_run_metadata_status"] = status
        diagnostics["initial_run_metadata"] = body[:1000]

        reset = parse_json_object("reset_duel", client.reset_duel("codex", "claude", 1, 42, 120))
        requested_run_id = str(reset["run_id"])
        run_id = requested_run_id
        diagnostics["expected_run_id"] = requested_run_id
        diagnostics["reset"] = reset
        diagnostics["opened_browser"] = bool(args.open_browser)
        if args.open_browser:
            open_duel_page(server_url)

        metadata_run_id, metadata, superseded = wait_for_active_duel_metadata(server_url, requested_run_id, args.timeout_seconds)
        if superseded:
            diagnostics["superseded_reset"] = {
                "requested_run_id": requested_run_id,
                "active_run_id": metadata_run_id,
                "reason": "Another browser/client reset became the active duel run while smoke was waiting.",
            }
            run_id = metadata_run_id
        diagnostics["latest_run_metadata"] = metadata.get("row", {})

        tokens = write_controller_tokens(run_id)
        loaded_tokens = read_controller_tokens()
        diagnostics["token_file_exists"] = CONTROLLER_TOKENS_PATH.exists()
        diagnostics["token_file_run_id"] = loaded_tokens.get("run_id", "")
        diagnostics["active_run_id"] = run_id

        before = wait_for_state(client, run_id, args.timeout_seconds)
        diagnostics["initial_state"] = {
            "tick": before.get("tick", 0),
            "phase": before.get("phase", ""),
            "player_1": before.get("player_1", {}),
            "player_2": before.get("player_2", {}),
        }

        p1_token = loaded_tokens["player_1"]["controller_token"]
        p2_token = loaded_tokens["player_2"]["controller_token"]
        p1_obs = parse_json_object(
            "get_participant_observation(player_1)",
            client.get_participant_observation("player_1", controller_token=p1_token),
        )
        p2_obs = parse_json_object(
            "get_participant_observation(player_2)",
            client.get_participant_observation("player_2", controller_token=p2_token),
        )
        diagnostics["observations"] = {
            "player_1_ok": p1_obs.get("participant_id") == "player_1",
            "player_2_ok": p2_obs.get("participant_id") == "player_2",
        }

        p1_command = parse_json_object(
            "set_participant_input(player_1)",
            client.set_participant_input("player_1", forward=1, turn=1, duration_ms=750, controller_token=p1_token),
        )
        p2_command = parse_json_object(
            "set_participant_input(player_2)",
            client.set_participant_input("player_2", turn=-1, attack=True, duration_ms=750, controller_token=p2_token),
        )
        diagnostics["commands_accepted"] = {
            "player_1": bool(p1_command.get("accepted")),
            "player_2": bool(p2_command.get("accepted")),
            "player_1_command_id": p1_command.get("command_id", ""),
            "player_2_command_id": p2_command.get("command_id", ""),
        }

        changed, after = wait_for_state_change(client, run_id, before, min(args.timeout_seconds, 10))
        diagnostics["state_changed_after_commands"] = changed
        diagnostics["after_state"] = {
            "tick": after.get("tick", 0),
            "phase": after.get("phase", ""),
            "player_1": after.get("player_1", {}),
            "player_2": after.get("player_2", {}),
        }
        if not changed:
            raise RuntimeError("State did not advance/change after participant commands.")

        try:
            client.set_participant_input("player_2", forward=1, controller_token=p1_token)
        except DoomArenaError as exc:
            diagnostics["wrong_token_rejected"] = str(exc)
        else:
            raise RuntimeError("Wrong-token player_2 command unexpectedly succeeded.")

        result = parse_json_object("get_match_result", client.get_match_result(run_id))
        if "phase" not in result or "winner" not in result:
            raise RuntimeError("get_match_result missing phase/winner.")
        diagnostics["match_result"] = result
        diagnostics["ok"] = True
        print(json.dumps({"ok": True, "diagnostics": diagnostics}, indent=2))
        return 0
    except Exception as exc:
        diagnostics["ok"] = False
        diagnostics["error"] = str(exc)
        diagnostics["latest_run_metadata"] = run_metadata(server_url)
        diagnostics["latest_state_status"] = latest_state_status(
            client,
            str(diagnostics.get("active_run_id") or diagnostics.get("expected_run_id") or ""),
        )
        diagnostics["browser_hint"] = (
            "Open http://127.0.0.1:8001/?duel=1 in the browser, keep the Doom/WASM tab open, "
            "wait until the game is visible, and rerun this script. Use --no-open-browser only "
            "if you are managing the tab yourself."
        )
        print(json.dumps({"ok": False, "diagnostics": diagnostics}, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
