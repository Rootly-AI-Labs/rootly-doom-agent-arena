#!/usr/bin/env python3
"""Browser-backed smoke test for Doom Arena duel autopilot intents."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any

from doom_arena_mcp import CONTROLLER_TOKENS_PATH, DoomArenaClient, DoomArenaError


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TIMEOUT_SECONDS = 60


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test browser-backed duel autopilot intents.")
    parser.add_argument("--server-url", default="http://127.0.0.1:8001")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument(
        "--browser-mode",
        choices=("headless", "system", "none"),
        default="headless",
        help="How to load the Doom/WASM page. Use none only when a browser tab is already running.",
    )
    parser.add_argument("--chrome-path", default=os.environ.get("DOOM_ARENA_BROWSER", ""))
    parser.add_argument("--keep-browser", action="store_true", help="Leave a launched headless browser running for debugging.")
    return parser.parse_args()


def log_ok(message: str) -> None:
    print(f"ok {message}", flush=True)


def request_text(server_url: str, path: str, timeout: float = 5.0) -> tuple[int, str]:
    request = urllib.request.Request(server_url.rstrip("/") + path, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def server_reachable(server_url: str) -> bool:
    try:
        status, _ = request_text(server_url, "/api/arena/mcp-config", timeout=1.0)
        return 200 <= status < 500
    except OSError:
        return False


def start_server_if_needed(server_url: str) -> tuple[subprocess.Popen[str] | None, Any | None]:
    if server_reachable(server_url):
        log_ok(f"server reachable at {server_url}")
        return None, None

    parsed = urllib.parse.urlparse(server_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8001
    if host not in {"127.0.0.1", "localhost"}:
        raise RuntimeError(f"Server is not reachable and cannot be auto-started for non-local host: {server_url}")

    command = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "doom_arena_server.py"),
        "--host",
        host,
        "--port",
        str(port),
    ]
    server_log = tempfile.NamedTemporaryFile(
        prefix="doom_arena_autopilot_server_",
        suffix=".log",
        mode="w+",
        encoding="utf-8",
        delete=False,
    )
    process = subprocess.Popen(
        command,
        cwd=str(REPO_ROOT),
        stdout=server_log,
        stderr=subprocess.STDOUT,
        text=True,
    )
    deadline = time.time() + 15
    while time.time() < deadline:
        if server_reachable(server_url):
            log_ok(f"started local arena server at {server_url}")
            return process, server_log
        if process.poll() is not None:
            server_log.flush()
            server_log.seek(0)
            output = server_log.read()
            raise RuntimeError(f"Arena server exited before becoming ready:\n{output}")
        time.sleep(0.25)

    process.terminate()
    raise RuntimeError(f"Timed out starting Doom Arena server at {server_url}")


def chrome_candidates() -> list[str]:
    candidates: list[str] = []
    for name in ("chrome", "chrome.exe", "msedge", "msedge.exe"):
        found = shutil.which(name)
        if found:
            candidates.append(found)

    env_program_files = [
        os.environ.get("PROGRAMFILES", ""),
        os.environ.get("PROGRAMFILES(X86)", ""),
        os.environ.get("LOCALAPPDATA", ""),
    ]
    suffixes = [
        r"Google\Chrome\Application\chrome.exe",
        r"Microsoft\Edge\Application\msedge.exe",
    ]
    for base in env_program_files:
        if not base:
            continue
        for suffix in suffixes:
            path = str(Path(base) / suffix)
            if Path(path).exists():
                candidates.append(path)

    deduped: list[str] = []
    for candidate in candidates:
        if candidate not in deduped:
            deduped.append(candidate)
    return deduped


def launch_browser(server_url: str, mode: str, chrome_path: str, timeout_seconds: int) -> tuple[subprocess.Popen[str] | None, tempfile.TemporaryDirectory[str] | None]:
    url = server_url.rstrip("/") + "/?duel=1&autoStart=1"
    if mode == "none":
        log_ok("using existing browser/WASM tab")
        return None, None

    if mode == "system":
        webbrowser.open(url, new=1, autoraise=True)
        log_ok(f"opened system browser at {url}")
        return None, None

    browser = chrome_path or (chrome_candidates()[0] if chrome_candidates() else "")
    if not browser:
        raise RuntimeError(
            "Could not find Chrome or Edge for headless browser mode. "
            "Pass --chrome-path, set DOOM_ARENA_BROWSER, or use --browser-mode system."
        )

    user_data_dir = tempfile.TemporaryDirectory(prefix="doom_arena_chrome_")
    command = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--mute-audio",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--autoplay-policy=no-user-gesture-required",
        f"--user-data-dir={user_data_dir.name}",
        url,
    ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    time.sleep(0.5)
    if process.poll() is not None:
        user_data_dir.cleanup()
        raise RuntimeError(f"Headless browser exited immediately: {browser}")
    log_ok(f"opened headless browser at {url}")
    return process, user_data_dir


def parse_json_object(label: str, text: str) -> dict[str, Any]:
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise RuntimeError(f"{label} did not return a JSON object")
    return parsed


def write_controller_tokens(run_id: str) -> tuple[str, str]:
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
    return p1_token, p2_token


def get_state(client: DoomArenaClient, run_id: str) -> dict[str, Any]:
    return parse_json_object("get_arena_state", client.get_arena_state(run_id))


def wait_for_state(client: DoomArenaClient, run_id: str, timeout_seconds: int) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_error = ""
    while time.time() < deadline:
        try:
            state = get_state(client, run_id)
            if state.get("run_id") == run_id and state.get("player_1") and state.get("player_2"):
                log_ok(f"browser/WASM state available for {run_id}")
                return state
        except DoomArenaError as exc:
            last_error = str(exc)
        time.sleep(0.25)
    raise RuntimeError(
        "Timed out waiting for browser/WASM state export.\n"
        f"  expected run_id: {run_id}\n"
        f"  last_error: {last_error}\n"
        "Make sure the Doom page is loaded and the browser process is allowed to run WASM."
    )


def wait_for(predicate: Any, label: str, timeout_seconds: int, poll_seconds: float = 0.25) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last: dict[str, Any] = {}
    while time.time() < deadline:
        last = predicate()
        if last.get("_ok"):
            log_ok(label)
            return last["state"]
        time.sleep(poll_seconds)
    raise RuntimeError(f"Timed out waiting for {label}; last={json.dumps(last, indent=2)}")


def participant_motion_changed(before: dict[str, Any], after: dict[str, Any]) -> bool:
    for participant_id in ("player_1", "player_2"):
        before_player = before.get(participant_id, {})
        after_player = after.get(participant_id, {})
        for key in ("x", "y", "angle"):
            if before_player.get(key) != after_player.get(key):
                return True
    return False


def participant_has_active_autopilot(player: dict[str, Any], expected_intent: str) -> bool:
    return (
        player.get("controller_mode") == "autopilot"
        and player.get("intent") == expected_intent
        and player.get("intent_status") == "active"
        and bool(player.get("intent_id"))
        and bool(player.get("intent_style"))
        and bool(player.get("autopilot_action"))
        and bool(player.get("autopilot_reason"))
    )


def active_autopilot_check(client: DoomArenaClient, run_id: str, p1_intent: str, p2_intent: str) -> dict[str, Any]:
    state = get_state(client, run_id)
    return {
        "_ok": participant_has_active_autopilot(state.get("player_1", {}), p1_intent)
        and participant_has_active_autopilot(state.get("player_2", {}), p2_intent),
        "state": state,
    }


def fallback_check(client: DoomArenaClient, run_id: str) -> dict[str, Any]:
    state = get_state(client, run_id)
    return {
        "_ok": (
            state.get("player_1", {}).get("controller_mode") == "low_level_command"
            and state.get("player_2", {}).get("controller_mode") == "low_level_command"
            and state.get("player_1", {}).get("intent") == "none"
            and state.get("player_2", {}).get("intent") == "none"
            and state.get("player_1", {}).get("intent_status") == "inactive"
            and state.get("player_2", {}).get("intent_status") == "inactive"
        ),
        "state": state,
    }


def motion_check(client: DoomArenaClient, run_id: str, before: dict[str, Any]) -> dict[str, Any]:
    state = get_state(client, run_id)
    return {"_ok": participant_motion_changed(before, state), "state": state}


def low_level_check(client: DoomArenaClient, run_id: str, before_tick: int) -> dict[str, Any]:
    state = get_state(client, run_id)
    return {
        "_ok": (
            int(state.get("tick", 0) or 0) > before_tick
            and state.get("player_1", {}).get("command_status") == "valid"
            and state.get("player_2", {}).get("command_status") == "valid"
        ),
        "state": state,
    }


def wait_for_events(client: DoomArenaClient, run_id: str, timeout_seconds: int) -> list[dict[str, Any]]:
    deadline = time.time() + timeout_seconds
    latest: list[dict[str, Any]] = []
    seen_text = ""
    while time.time() < deadline:
        latest = parse_json_object("get_duel_events", client.get_duel_events(run_id, 100)).get("events", [])
        event_text = "\n".join(str(event.get("event", "")) for event in latest)
        seen_text += "\n" + event_text
        if (
            "intent_set:" in seen_text
            and "autopilot_action:" in seen_text
            and "intent_expired:" in seen_text
        ):
            log_ok("event log includes intent_set, autopilot_action, and intent_expired")
            return latest
        time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for autopilot events; latest={json.dumps(latest[-20:], indent=2)}")


def main() -> int:
    args = parse_args()
    server_url = args.server_url.rstrip("/")
    server_process: subprocess.Popen[str] | None = None
    server_log: Any | None = None
    browser_process: subprocess.Popen[str] | None = None
    browser_temp_dir: tempfile.TemporaryDirectory[str] | None = None
    previous_tokens = CONTROLLER_TOKENS_PATH.read_bytes() if CONTROLLER_TOKENS_PATH.exists() else None

    try:
        server_process, server_log = start_server_if_needed(server_url)
        client = DoomArenaClient(server_url)
        reset = parse_json_object("reset_duel", client.reset_duel("codex", "claude", 1, 42, 120))
        run_id = str(reset["run_id"])
        if reset.get("arena_mode") != "duel":
            raise RuntimeError(f"reset did not enter duel mode: {reset}")
        log_ok(f"duel reset/start works: {run_id}")

        p1_token, p2_token = write_controller_tokens(run_id)
        browser_process, browser_temp_dir = launch_browser(
            server_url,
            args.browser_mode,
            args.chrome_path,
            args.timeout_seconds,
        )

        initial_state = wait_for_state(client, run_id, args.timeout_seconds)
        if initial_state.get("phase") != "waiting_for_agents":
            raise RuntimeError(
                "duel should wait for both agents and opening intents before combat starts: "
                + json.dumps(initial_state, indent=2)
            )
        log_ok("duel waits for participant readiness and opening intents before combat")

        client.set_participant_ready("player_1", controller_token=p1_token)
        single_ready_state = wait_for_state(client, run_id, min(args.timeout_seconds, 10))
        if single_ready_state.get("phase") != "waiting_for_agents":
            raise RuntimeError(
                "duel started before both participants were ready: "
                + json.dumps(single_ready_state, indent=2)
            )
        log_ok("single participant ready signal does not start combat")

        client.set_participant_intent(
            "player_1",
            "search",
            style="balanced",
            target_id="player_2",
            preferred_distance=100,
            aggression=0.5,
            duration_ms=6000,
            controller_token=p1_token,
            strafe_direction="alternate",
            movement_bias="evasive",
            fire_policy="only_when_aligned",
            distance_policy="maintain",
            replan_if=["target_far", "lost_los", "stuck"],
            sequence_number=1,
            decision_cadence_ms=750,
        )
        single_intent_state = wait_for_state(client, run_id, min(args.timeout_seconds, 10))
        if single_intent_state.get("phase") != "waiting_for_agents":
            raise RuntimeError(
                "duel started before player_2 readiness was signaled: "
                + json.dumps(single_intent_state, indent=2)
            )
        log_ok("combat intent alone does not bypass ready barrier")

        client.set_participant_intent(
            "player_1",
            "search",
            style="balanced",
            target_id="player_2",
            preferred_distance=100,
            aggression=0.5,
            duration_ms=3000,
            controller_token=p1_token,
            strafe_direction="alternate",
            movement_bias="evasive",
            fire_policy="only_when_aligned",
            distance_policy="maintain",
            replan_if=["target_far", "lost_los", "stuck"],
            sequence_number=3,
            decision_cadence_ms=750,
        )
        log_ok("set player_1 intent")
        client.set_participant_ready("player_2", controller_token=p2_token)
        both_ready_one_intent_state = wait_for_state(client, run_id, min(args.timeout_seconds, 10))
        if both_ready_one_intent_state.get("phase") != "waiting_for_agents":
            raise RuntimeError(
                "duel started before both opening intents were armed: "
                + json.dumps(both_ready_one_intent_state, indent=2)
            )
        log_ok("both ready signals still wait for both opening intents")
        client.set_participant_intent(
            "player_2",
            "search",
            style="balanced",
            target_id="player_1",
            preferred_distance=100,
            aggression=0.5,
            duration_ms=3000,
            controller_token=p2_token,
            strafe_direction="right",
            movement_bias="circle",
            fire_policy="burst_when_aligned",
            distance_policy="kite",
            replan_if=["low_health", "target_far"],
            sequence_number=4,
            decision_cadence_ms=750,
        )
        log_ok("set player_2 intent")

        active_state = wait_for(
            lambda: active_autopilot_check(client, run_id, "search", "search"),
            "state export shows active autopilot fields for both players",
            args.timeout_seconds,
        )
        if (
            active_state.get("player_1", {}).get("strafe_direction") != "alternate"
            or active_state.get("player_1", {}).get("movement_bias") != "evasive"
            or active_state.get("player_1", {}).get("fire_policy") != "only_when_aligned"
            or active_state.get("player_1", {}).get("distance_policy") != "maintain"
            or active_state.get("player_1", {}).get("replan_if") != ["target_far", "lost_los", "stuck"]
            or active_state.get("player_1", {}).get("sequence_number") != 3
            or active_state.get("player_1", {}).get("decision_cadence_ms") != 750
            or not active_state.get("player_1", {}).get("issued_at_ms")
            or not active_state.get("player_1", {}).get("expires_at_ms")
            or active_state.get("player_2", {}).get("strafe_direction") != "right"
            or active_state.get("player_2", {}).get("movement_bias") != "circle"
            or active_state.get("player_2", {}).get("fire_policy") != "burst_when_aligned"
            or active_state.get("player_2", {}).get("distance_policy") != "kite"
            or active_state.get("player_2", {}).get("replan_if") != ["low_health", "target_far"]
            or active_state.get("player_2", {}).get("sequence_number") != 4
            or active_state.get("player_2", {}).get("decision_cadence_ms") != 750
            or not active_state.get("player_2", {}).get("issued_at_ms")
            or not active_state.get("player_2", {}).get("expires_at_ms")
        ):
            raise RuntimeError(
                "state export did not include expected extended tactical fields: "
                + json.dumps(
                    {
                        "player_1": active_state.get("player_1", {}),
                        "player_2": active_state.get("player_2", {}),
                    },
                    indent=2,
                )
            )
        log_ok("state export includes extended tactical intent metadata")
        if (
            not active_state.get("player_1", {}).get("replan_recommended")
            or "target_far" not in active_state.get("player_1", {}).get("replan_reasons", [])
        ):
            raise RuntimeError(
                "state export did not include expected target_far replan recommendation: "
                + json.dumps(active_state.get("player_1", {}), indent=2)
            )
        log_ok("state export includes replan recommendation metadata")

        wait_for(
            lambda: motion_check(client, run_id, active_state),
            "positions or angles change after intents become active",
            min(args.timeout_seconds, 20),
        )

        expired_state = wait_for(
            lambda: fallback_check(client, run_id),
            "expired intents stop applying",
            min(args.timeout_seconds, 20),
        )
        log_ok("expired intents export inactive status")

        client.set_participant_intent(
            "player_1",
            "search",
            style="balanced",
            target_id="player_2",
            duration_ms=6000,
            controller_token=p1_token,
        )
        client.set_participant_intent(
            "player_2",
            "search",
            style="balanced",
            target_id="player_1",
            duration_ms=6000,
            controller_token=p2_token,
        )
        wait_for(
            lambda: active_autopilot_check(client, run_id, "search", "search"),
            "second intent pair becomes active",
            min(args.timeout_seconds, 20),
        )
        client.stop_participant_intent("player_1", controller_token=p1_token)
        client.stop_participant_intent("player_2", controller_token=p2_token)
        fallback_state = wait_for(
            lambda: fallback_check(client, run_id),
            "clear/stop intents returns to low-level command mode",
            min(args.timeout_seconds, 20),
        )

        try:
            client.set_participant_intent("player_2", "hold", controller_token=p1_token)
        except DoomArenaError as exc:
            log_ok(f"wrong controller token rejected: {exc}")
        else:
            raise RuntimeError("wrong controller token was accepted")

        client.set_participant_input("player_1", forward=1, turn=1, duration_ms=750, controller_token=p1_token)
        client.set_participant_input("player_2", turn=-1, attack=True, duration_ms=750, controller_token=p2_token)
        before_low_level_tick = int(fallback_state.get("tick", 0) or 0)
        low_level_state = wait_for(
            lambda: low_level_check(client, run_id, before_low_level_tick),
            "existing low-level set_participant_input works after clearing intents",
            min(args.timeout_seconds, 20),
        )

        events = wait_for_events(client, run_id, min(args.timeout_seconds, 30))
        summary = {
            "run_id": run_id,
            "initial_tick": initial_state.get("tick"),
            "active_tick": active_state.get("tick"),
            "fallback_tick": fallback_state.get("tick"),
            "low_level_tick": low_level_state.get("tick"),
            "player_1_active": {
                key: active_state.get("player_1", {}).get(key)
                for key in (
                    "controller_mode",
                    "intent",
                    "intent_status",
                    "intent_style",
                    "autopilot_action",
                    "autopilot_reason",
                    "aim_error",
                    "strafe_direction",
                    "movement_bias",
                    "fire_policy",
                    "distance_policy",
                    "replan_if",
                    "sequence_number",
                    "decision_cadence_ms",
                    "issued_at_ms",
                    "expires_at_ms",
                    "replan_recommended",
                    "replan_reasons",
                )
            },
            "player_2_active": {
                key: active_state.get("player_2", {}).get(key)
                for key in (
                    "controller_mode",
                    "intent",
                    "intent_status",
                    "intent_style",
                    "autopilot_action",
                    "autopilot_reason",
                    "aim_error",
                    "strafe_direction",
                    "movement_bias",
                    "fire_policy",
                    "distance_policy",
                    "replan_if",
                    "sequence_number",
                    "decision_cadence_ms",
                    "issued_at_ms",
                    "expires_at_ms",
                    "replan_recommended",
                    "replan_reasons",
                )
            },
            "events_sample": events[-8:],
        }
        print(json.dumps({"ok": True, "summary": summary}, indent=2), flush=True)
        print("duel autopilot smoke test passed", flush=True)
        return 0
    finally:
        if previous_tokens is None:
            CONTROLLER_TOKENS_PATH.unlink(missing_ok=True)
        else:
            CONTROLLER_TOKENS_PATH.write_bytes(previous_tokens)
        if browser_process is not None and not args.keep_browser and browser_process.poll() is None:
            browser_process.terminate()
            try:
                browser_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                browser_process.kill()
                browser_process.wait(timeout=5)
        if browser_temp_dir is not None and not args.keep_browser:
            browser_temp_dir.cleanup()
        if server_process is not None and server_process.poll() is None:
            server_process.terminate()
            try:
                server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server_process.kill()
                server_process.wait(timeout=5)
        if server_log is not None:
            server_log.close()


if __name__ == "__main__":
    raise SystemExit(main())
