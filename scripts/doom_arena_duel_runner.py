#!/usr/bin/env python3
"""Run a Doom Arena duel through the participant command path."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
RESULTS_ROOT = REPO_ROOT / "benchmarks" / "results"
DEFAULT_SERVER_URL = "http://127.0.0.1:8001"
PARTICIPANT_COMMAND_HEADER = (
    "run_id\tscenario_id\tcommand_id\tissued_at_ms\texpires_at_ms\t"
    "participant_id\tforward\tstrafe\tturn\tattack\tuse\tduration_ms\n"
)


def now_ms() -> int:
    return int(time.time() * 1000)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def clamp_int(value: Any, low: int, high: int, default: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(low, min(high, parsed))


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a Codex-vs-Claude Doom Arena duel.")
    parser.add_argument("--server-url", default=DEFAULT_SERVER_URL)
    parser.add_argument("--player-1-model", default="codex")
    parser.add_argument("--player-2-model", default="claude")
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--decision-interval-ms", type=int, default=750)
    parser.add_argument("--agent-timeout-ms", type=int, default=10000)
    parser.add_argument("--max-steps", type=int, default=0)
    parser.add_argument("--state-wait-timeout-seconds", type=int, default=45)
    parser.add_argument("--open-browser", action="store_true")
    parser.add_argument("--no-open-browser", action="store_true")
    parser.add_argument("--allow-placeholder-agents", action="store_true")
    parser.add_argument("--player-1-agent-cmd", default="")
    parser.add_argument("--player-2-agent-cmd", default="")
    parser.add_argument("--print-observation-sample", action="store_true")
    return parser.parse_args()


class ArenaClient:
    def __init__(self, server_url: str):
        self.server_url = server_url.rstrip("/")
        self.run_id = "run_unknown"
        self.scenario_id = "scenario_unknown"
        self.tool_calls = 0
        self.latencies_ms: list[float] = []

    def reset_duel(self, config: dict[str, Any]) -> dict[str, Any]:
        payload = self.request_json("POST", "/api/arena/reset", config)
        self.run_id = str(payload.get("run_id", self.run_id))
        self.scenario_id = str(payload.get("scenario_id", self.scenario_id))
        return payload

    def get_state_rows(self) -> list[dict[str, str]]:
        return parse_tsv(self.request_text("GET", "/api/arena/state"))

    def get_events(self) -> list[dict[str, str]]:
        try:
            return parse_tsv(self.request_text("GET", "/api/arena/events"))
        except RuntimeError:
            return []

    def write_participant_actions(self, actions: list[dict[str, Any]]) -> None:
        issued = now_ms()
        body = PARTICIPANT_COMMAND_HEADER
        for index, action in enumerate(actions):
            duration = int(action["duration_ms"])
            row = [
                self.run_id,
                self.scenario_id,
                f"duel_runner_{action['participant_id']}_{issued}_{index}",
                str(issued),
                str(issued + duration),
                action["participant_id"],
                str(action["forward"]),
                str(action["strafe"]),
                str(action["turn"]),
                "true" if action["attack"] else "false",
                "true" if action["use"] else "false",
                str(duration),
            ]
            body += "\t".join(row) + "\n"

        self.request_text(
            "POST",
            "/api/arena/participant-commands",
            body.encode("utf-8"),
            "text/tab-separated-values; charset=utf-8",
        )

    def request_json(self, method: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return json.loads(
            self.request_text(
                method,
                path,
                json.dumps(payload).encode("utf-8"),
                "application/json; charset=utf-8",
            )
        )

    def request_text(
        self,
        method: str,
        path: str,
        data: bytes | None = None,
        content_type: str | None = None,
    ) -> str:
        headers = {}
        if content_type:
            headers["Content-Type"] = content_type
        request = urllib.request.Request(
            self.server_url + path,
            data=data,
            headers=headers,
            method=method,
        )

        start = time.perf_counter()
        self.tool_calls += 1
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {path} failed with HTTP {exc.code}: {body}") from exc
        except OSError as exc:
            raise RuntimeError(f"Could not reach Doom Arena server at {self.server_url}") from exc
        finally:
            self.latencies_ms.append((time.perf_counter() - start) * 1000.0)

    def average_latency_ms(self) -> float:
        if not self.latencies_ms:
            return 0.0
        return sum(self.latencies_ms) / len(self.latencies_ms)


class ResultWriter:
    def __init__(self, run_dir: Path):
        self.run_dir = run_dir
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.events_file = (self.run_dir / "events.jsonl").open("w", encoding="utf-8")

    def write_config(self, config: dict[str, Any]) -> None:
        (self.run_dir / "config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    def write_event(self, event: dict[str, Any]) -> None:
        self.events_file.write(json.dumps(event, separators=(",", ":")) + "\n")
        self.events_file.flush()

    def write_summary(self, summary: dict[str, Any]) -> None:
        (self.run_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    def close(self) -> None:
        self.events_file.close()


class MissingAgentIntegration(RuntimeError):
    pass


class DuelAgent:
    def __init__(
        self,
        model_name: str,
        participant_id: str,
        allow_placeholder: bool,
        command: str = "",
    ):
        self.model_name = model_name
        self.participant_id = participant_id
        self.allow_placeholder = allow_placeholder
        self.command = command

    def next_action(self, observation: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class ExternalHookAgent(DuelAgent):
    def next_action(self, observation: dict[str, Any]) -> dict[str, Any]:
        if self.command:
            return run_subprocess_agent(self.command, observation)
        if not self.allow_placeholder:
            raise MissingAgentIntegration(
                f"{self.model_name} external agent hook is not configured. "
                f"Pass --{self.participant_id.replace('_', '-')}-agent-cmd, or rerun with "
                "--allow-placeholder-agents for local smoke testing."
            )
        return placeholder_action(self.participant_id, observation)


class PlaceholderAgent(DuelAgent):
    def next_action(self, observation: dict[str, Any]) -> dict[str, Any]:
        if not self.allow_placeholder:
            raise MissingAgentIntegration("Placeholder agents require --allow-placeholder-agents.")
        return placeholder_action(self.participant_id, observation)


def run_subprocess_agent(command: str, observation: dict[str, Any]) -> dict[str, Any]:
    args = shlex.split(command, posix=not sys.platform.startswith("win"))
    if not args:
        raise MissingAgentIntegration("Agent command is empty.")

    completed = subprocess.run(
        args,
        input=json.dumps(observation, separators=(",", ":")),
        text=True,
        capture_output=True,
        timeout=max(0.1, float(observation.get("agent_timeout_ms", 10000)) / 1000.0),
        cwd=REPO_ROOT,
        check=False,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        raise RuntimeError(f"agent command exited {completed.returncode}: {stderr}")

    stdout = completed.stdout.strip()
    if not stdout:
        raise RuntimeError("agent command produced empty stdout")
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"agent command produced invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("agent command must return one JSON object")
    return parsed


def create_agent(
    model_name: str,
    participant_id: str,
    allow_placeholder: bool,
    command: str = "",
) -> DuelAgent:
    normalized = model_name.strip().lower()
    if normalized in {"codex", "claude"}:
        return ExternalHookAgent(normalized, participant_id, allow_placeholder, command)
    if normalized in {"baseline", "manual"}:
        if command:
            return ExternalHookAgent(normalized, participant_id, allow_placeholder, command)
        return PlaceholderAgent(normalized, participant_id, allow_placeholder)
    return ExternalHookAgent(normalized, participant_id, allow_placeholder, command)


def placeholder_action(participant_id: str, observation: dict[str, Any]) -> dict[str, Any]:
    self_state = observation["state"].get(participant_id, {})
    relative_angle = int(self_state.get("opponent_relative_angle", 0) or 0)
    line_of_sight = bool(self_state.get("opponent_visible", False))
    distance = int(self_state.get("opponent_distance", 9999) or 9999)
    turn = 0
    if relative_angle > 8:
        turn = 1
    elif relative_angle < -8:
        turn = -1
    return {
        "participant_id": participant_id,
        "forward": 1 if distance > 420 or not line_of_sight else 0,
        "strafe": 0,
        "turn": turn,
        "attack": line_of_sight and abs(relative_angle) <= 10,
        "use": False,
        "duration_ms": observation.get("decision_interval_ms", 750),
    }


def parse_tsv(text: str) -> list[dict[str, str]]:
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return []
    header = lines[0].split("\t")
    return [dict(zip(header, line.split("\t"))) for line in lines[1:]]


def as_int(row: dict[str, str], key: str, default: int = 0) -> int:
    try:
        return int(row.get(key, "") or default)
    except ValueError:
        return default


def as_float(row: dict[str, str], key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key, "") or default)
    except ValueError:
        return default


def split_duel_rows(rows: list[dict[str, str]]) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    match = next((row for row in rows if row.get("kind") == "match"), {})
    player_1 = next((row for row in rows if row.get("kind") == "participant" and row.get("entity_id") == "player_1"), {})
    player_2 = next((row for row in rows if row.get("kind") == "participant" and row.get("entity_id") == "player_2"), {})
    return match, player_1, player_2


def participant_state(row: dict[str, str]) -> dict[str, Any]:
    return {
        "model": row.get("model", ""),
        "health": as_int(row, "health"),
        "ammo": as_int(row, "ammo_bullets"),
        "x": as_int(row, "x"),
        "y": as_int(row, "y"),
        "angle": as_int(row, "angle"),
        "alive": row.get("alive", "0") == "1",
        "last_action": row.get("last_action", ""),
        "command_status": row.get("command_status", ""),
        "damage_dealt": as_int(row, "damage_dealt"),
        "shots_fired": as_int(row, "shots_fired"),
        "shots_hit": as_int(row, "shots_hit"),
        "invalid_actions": as_int(row, "invalid_actions"),
        "opponent_distance": as_int(row, "distance_to_player"),
        "opponent_relative_angle": as_int(row, "relative_angle_to_player"),
        "opponent_visible": row.get("line_of_sight", "0") == "1",
    }


def build_shared_state(rows: list[dict[str, str]]) -> dict[str, Any]:
    match, player_1, player_2 = split_duel_rows(rows)
    return {
        "mode": "duel",
        "run_id": match.get("run_id") or player_1.get("run_id") or player_2.get("run_id", ""),
        "scenario_id": match.get("scenario_id") or player_1.get("scenario_id") or player_2.get("scenario_id", ""),
        "tick": as_int(match or player_1 or player_2, "tick"),
        "elapsed_time_seconds": as_float(match or player_1 or player_2, "elapsed_time_seconds"),
        "timeout_seconds": as_int(match or player_1 or player_2, "timeout_seconds", 120),
        "phase": match.get("phase") or player_1.get("phase") or "combat",
        "winner": match.get("winner") or player_1.get("winner") or None,
        "terminal_reason": match.get("terminal_reason") or player_1.get("terminal_reason") or None,
        "player_1": participant_state(player_1),
        "player_2": participant_state(player_2),
        "distance_between_players": as_int(player_1, "distance_to_player"),
        "line_of_sight": player_1.get("line_of_sight", "0") == "1",
        "relative_angle_player_1_to_player_2": as_int(player_1, "relative_angle_to_player"),
        "relative_angle_player_2_to_player_1": as_int(player_2, "relative_angle_to_player"),
    }


def build_observation(
    participant_id: str,
    opponent_id: str,
    model: str,
    shared_state: dict[str, Any],
    decision_interval_ms: int,
    agent_timeout_ms: int,
) -> dict[str, Any]:
    return {
        "participant_id": participant_id,
        "opponent_id": opponent_id,
        "model": model,
        "state_mode": "shared_full",
        "state": shared_state,
        "decision_interval_ms": decision_interval_ms,
        "agent_timeout_ms": agent_timeout_ms,
        "allowed_actions": {
            "forward": [-1, 0, 1],
            "strafe": [-1, 0, 1],
            "turn": [-1, 0, 1],
            "attack": [True, False],
            "use": [True, False],
            "duration_ms": [100, 2000],
        },
        "instruction": "Return only one JSON action object. Do not include prose.",
    }


def noop_action(participant_id: str, duration_ms: int) -> dict[str, Any]:
    return {
        "participant_id": participant_id,
        "forward": 0,
        "strafe": 0,
        "turn": 0,
        "attack": False,
        "use": False,
        "duration_ms": duration_ms,
    }


def validate_action(
    raw_action: Any,
    participant_id: str,
    default_duration_ms: int,
) -> tuple[dict[str, Any], str, str]:
    if not isinstance(raw_action, dict):
        return noop_action(participant_id, default_duration_ms), "noop_fallback", "missing_or_non_object"
    if raw_action.get("participant_id") != participant_id:
        return noop_action(participant_id, default_duration_ms), "noop_fallback", "wrong_participant_id"

    action = {
        "participant_id": participant_id,
        "forward": clamp_int(raw_action.get("forward", 0), -1, 1),
        "strafe": clamp_int(raw_action.get("strafe", 0), -1, 1),
        "turn": clamp_int(raw_action.get("turn", 0), -1, 1),
        "attack": parse_bool(raw_action.get("attack", False)),
        "use": parse_bool(raw_action.get("use", False)),
        "duration_ms": clamp_int(raw_action.get("duration_ms", default_duration_ms), 100, 2000, default_duration_ms),
    }
    return action, "valid", ""


def call_agent(
    agent: DuelAgent,
    observation: dict[str, Any],
    timeout_ms: int,
    default_duration_ms: int,
) -> tuple[dict[str, Any], str, str]:
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(agent.next_action, observation)
        try:
            raw_action = future.result(timeout=timeout_ms / 1000.0)
        except TimeoutError:
            return noop_action(agent.participant_id, default_duration_ms), "timeout", "agent_timeout"
        except Exception as exc:
            return noop_action(agent.participant_id, default_duration_ms), "error", str(exc)
    return validate_action(raw_action, agent.participant_id, default_duration_ms)


def wait_for_duel_state(client: ArenaClient, run_id: str, timeout_seconds: int) -> list[dict[str, str]]:
    deadline = time.time() + timeout_seconds
    last_error = ""
    metadata_status = "not checked"
    state_status = "not checked"
    while time.time() < deadline:
        try:
            metadata_status = "reachable"
            client.request_text("GET", "/api/arena/run-metadata")
        except RuntimeError as exc:
            metadata_status = str(exc)

        try:
            rows = client.get_state_rows()
            state_status = f"reachable with {len(rows)} rows"
            match, player_1, player_2 = split_duel_rows(rows)
            state_run_id = match.get("run_id") or player_1.get("run_id") or player_2.get("run_id")
            if player_1 and player_2 and state_run_id == run_id:
                return rows
        except RuntimeError as exc:
            last_error = str(exc)
            state_status = str(exc)
        time.sleep(0.25)
    detail = f" Last state error: {last_error}" if last_error else ""
    raise RuntimeError(
        "Timed out waiting for duel state.\n"
        f"  server_url: {client.server_url}\n"
        f"  expected run_id: {run_id}\n"
        f"  /api/arena/run-metadata: {metadata_status}\n"
        f"  /api/arena/state: {state_status}\n"
        "Open the browser at the server URL, or at /?duel=1 after this runner has reset the duel, "
        "and keep the WASM game running so arena_game_state.local.tsv is exported."
        f"{detail}"
    )


def event_record(
    step: int,
    shared_state: dict[str, Any],
    player_1_action: dict[str, Any],
    player_2_action: dict[str, Any],
    player_1_status: str,
    player_2_status: str,
    duel_events: list[dict[str, str]],
    player_1_error: str = "",
    player_2_error: str = "",
) -> dict[str, Any]:
    record = {
        "timestamp": utc_now(),
        "step": step,
        "state_tick": shared_state.get("tick"),
        "player_1_action": player_1_action,
        "player_2_action": player_2_action,
        "player_1_action_status": player_1_status,
        "player_2_action_status": player_2_status,
        "phase": shared_state.get("phase"),
        "winner": shared_state.get("winner"),
        "terminal_reason": shared_state.get("terminal_reason"),
        "health": {
            "player_1": shared_state["player_1"].get("health"),
            "player_2": shared_state["player_2"].get("health"),
        },
        "ammo": {
            "player_1": shared_state["player_1"].get("ammo"),
            "player_2": shared_state["player_2"].get("ammo"),
        },
        "duel_events": duel_events,
    }
    if player_1_error:
        record["player_1_error"] = player_1_error
    if player_2_error:
        record["player_2_error"] = player_2_error
    return record


def build_summary(
    client: ArenaClient,
    config: dict[str, Any],
    shared_state: dict[str, Any],
) -> dict[str, Any]:
    return {
        "run_id": client.run_id,
        "mode": "duel",
        "player_1_model": config["player_1_model"],
        "player_2_model": config["player_2_model"],
        "winner": shared_state.get("winner") or "running",
        "terminal_reason": shared_state.get("terminal_reason") or "",
        "elapsed_time_seconds": shared_state.get("elapsed_time_seconds", 0),
        "timeout_seconds": config["timeout_seconds"],
        "rounds": config["rounds"],
        "player_1_health_end": shared_state["player_1"].get("health", 0),
        "player_2_health_end": shared_state["player_2"].get("health", 0),
        "player_1_damage_dealt": shared_state["player_1"].get("damage_dealt", 0),
        "player_2_damage_dealt": shared_state["player_2"].get("damage_dealt", 0),
        "player_1_shots_fired": shared_state["player_1"].get("shots_fired", 0),
        "player_2_shots_fired": shared_state["player_2"].get("shots_fired", 0),
        "player_1_shots_hit": shared_state["player_1"].get("shots_hit", 0),
        "player_2_shots_hit": shared_state["player_2"].get("shots_hit", 0),
        "player_1_invalid_actions": shared_state["player_1"].get("invalid_actions", 0),
        "player_2_invalid_actions": shared_state["player_2"].get("invalid_actions", 0),
        "tool_calls": client.tool_calls,
        "average_latency_ms": round(client.average_latency_ms(), 3),
    }


def sample_shared_state() -> dict[str, Any]:
    return {
        "mode": "duel",
        "run_id": "run_sample",
        "scenario_id": "duel_e1m8",
        "tick": 220,
        "elapsed_time_seconds": 42.1,
        "timeout_seconds": 120,
        "phase": "combat",
        "winner": None,
        "terminal_reason": None,
        "player_1": {
            "model": "codex",
            "health": 84,
            "ammo": 31,
            "x": 412,
            "y": 2456,
            "angle": 90,
            "alive": True,
            "last_action": "strafe_left+attack",
            "command_status": "valid",
            "damage_dealt": 16,
            "shots_fired": 4,
            "shots_hit": 1,
            "invalid_actions": 0,
            "opponent_distance": 453,
            "opponent_relative_angle": -12,
            "opponent_visible": True,
        },
        "player_2": {
            "model": "claude",
            "health": 72,
            "ammo": 28,
            "x": 412,
            "y": 2909,
            "angle": 270,
            "alive": True,
            "last_action": "turn_right+attack",
            "command_status": "valid",
            "damage_dealt": 28,
            "shots_fired": 5,
            "shots_hit": 2,
            "invalid_actions": 0,
            "opponent_distance": 453,
            "opponent_relative_angle": 8,
            "opponent_visible": True,
        },
        "distance_between_players": 453,
        "line_of_sight": True,
        "relative_angle_player_1_to_player_2": -12,
        "relative_angle_player_2_to_player_1": 8,
    }


def print_observation_sample() -> None:
    sample = build_observation(
        "player_1",
        "player_2",
        "codex",
        sample_shared_state(),
        750,
        10000,
    )
    expected_action = {
        "participant_id": "player_1",
        "forward": -1,
        "strafe": 0,
        "turn": 1,
        "attack": True,
        "use": False,
        "duration_ms": 750,
    }
    print(json.dumps({"observation": sample, "expected_action_schema": expected_action}, indent=2))


def maybe_open_browser(server_url: str, enabled: bool) -> None:
    if not enabled:
        return
    url = server_url.rstrip("/") + "/?duel=1"
    if sys.platform.startswith("win"):
        subprocess.Popen(["cmd", "/c", "start", "", url], shell=False)
    else:
        subprocess.Popen(["python3", "-m", "webbrowser", url])


def main() -> int:
    args = parse_args()
    if args.print_observation_sample:
        print_observation_sample()
        return 0
    if args.rounds != 1:
        raise RuntimeError("Duel MVP currently supports --rounds 1 only.")
    if args.open_browser and args.no_open_browser:
        raise RuntimeError("Use either --open-browser or --no-open-browser, not both.")
    missing_codex_hook = args.player_1_model.strip().lower() == "codex" and not args.player_1_agent_cmd
    missing_claude_hook = args.player_2_model.strip().lower() == "claude" and not args.player_2_agent_cmd
    if not args.allow_placeholder_agents and (missing_codex_hook or missing_claude_hook):
        raise MissingAgentIntegration(
            "Codex/Claude external agent routing is not wired in this repo yet. "
            "Pass --player-1-agent-cmd and --player-2-agent-cmd, or use "
            "--allow-placeholder-agents for local smoke testing."
        )

    client = ArenaClient(args.server_url)
    reset_config = {
        "arena_mode": "duel",
        "player_1_model": args.player_1_model.lower(),
        "player_2_model": args.player_2_model.lower(),
        "round": 1,
        "seed": args.seed,
        "timeout_seconds": args.timeout_seconds,
    }
    reset = client.reset_duel(reset_config)
    if args.open_browser:
        maybe_open_browser(args.server_url, True)

    run_dir = RESULTS_ROOT / client.run_id
    writer = ResultWriter(run_dir)
    config = {
        "runner": "doom_arena_duel_runner",
        "server_url": args.server_url,
        "arena_mode": "duel",
        "player_1_model": reset_config["player_1_model"],
        "player_2_model": reset_config["player_2_model"],
        "rounds": args.rounds,
        "seed": args.seed,
        "timeout_seconds": args.timeout_seconds,
        "decision_interval_ms": args.decision_interval_ms,
        "agent_timeout_ms": args.agent_timeout_ms,
        "on_agent_failure": "noop",
        "state_mode": "shared_full",
        "max_steps": args.max_steps,
        "allow_placeholder_agents": bool(args.allow_placeholder_agents),
        "player_1_agent_cmd": args.player_1_agent_cmd,
        "player_2_agent_cmd": args.player_2_agent_cmd,
    }
    writer.write_config(config)

    agent_1 = create_agent(
        config["player_1_model"],
        "player_1",
        args.allow_placeholder_agents,
        args.player_1_agent_cmd,
    )
    agent_2 = create_agent(
        config["player_2_model"],
        "player_2",
        args.allow_placeholder_agents,
        args.player_2_agent_cmd,
    )

    writer.write_event({"timestamp": utc_now(), "step": 0, "event": "reset", "reset": reset})
    rows = wait_for_duel_state(client, client.run_id, args.state_wait_timeout_seconds)
    step = 0

    try:
        while True:
            shared_state = build_shared_state(rows)
            if shared_state.get("phase") == "finished":
                break
            if args.max_steps and step >= args.max_steps:
                break
            if shared_state.get("elapsed_time_seconds", 0) >= args.timeout_seconds + 2:
                break

            obs_1 = build_observation(
                "player_1",
                "player_2",
                config["player_1_model"],
                shared_state,
                args.decision_interval_ms,
                args.agent_timeout_ms,
            )
            obs_2 = build_observation(
                "player_2",
                "player_1",
                config["player_2_model"],
                shared_state,
                args.decision_interval_ms,
                args.agent_timeout_ms,
            )
            action_1, status_1, error_1 = call_agent(agent_1, obs_1, args.agent_timeout_ms, args.decision_interval_ms)
            action_2, status_2, error_2 = call_agent(agent_2, obs_2, args.agent_timeout_ms, args.decision_interval_ms)
            client.write_participant_actions([action_1, action_2])

            events = client.get_events()
            writer.write_event(
                event_record(
                    step + 1,
                    shared_state,
                    action_1,
                    action_2,
                    status_1,
                    status_2,
                    events[-5:],
                    error_1,
                    error_2,
                )
            )

            step += 1
            time.sleep(args.decision_interval_ms / 1000.0)
            rows = client.get_state_rows()

        final_state = build_shared_state(client.get_state_rows())
        if args.max_steps and step >= args.max_steps and final_state.get("phase") != "finished":
            final_state["terminal_reason"] = "max_steps"
        summary = build_summary(client, config, final_state)
        writer.write_summary(summary)
    finally:
        writer.close()

    print(json.dumps(summary, indent=2))
    print(f"results_dir={run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
