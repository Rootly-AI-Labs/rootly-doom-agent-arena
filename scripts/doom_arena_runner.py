#!/usr/bin/env python3
"""Autonomous Doom Agent Arena MVP benchmark runner."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
RESULTS_ROOT = REPO_ROOT / "benchmarks" / "results"
DEFAULT_SERVER_URL = "http://127.0.0.1:8000"
DEFAULT_TIMEOUT_SECONDS = 300
DEFAULT_DECISION_INTERVAL_MS = 1000
DEFAULT_STATE_POLL_INTERVAL_MS = 250
DEFAULT_PLAYER_COMMAND_DURATION_MS = 750
DEFAULT_ENEMY_COMMAND_DURATION_MS = 1500


def now_ms() -> int:
    return int(time.time() * 1000)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a Doom Agent Arena benchmark.")
    parser.add_argument("--server-url", default=DEFAULT_SERVER_URL)
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--decision-interval-ms", type=int, default=DEFAULT_DECISION_INTERVAL_MS)
    parser.add_argument("--state-poll-interval-ms", type=int, default=DEFAULT_STATE_POLL_INTERVAL_MS)
    parser.add_argument("--player-command-duration-ms", type=int, default=DEFAULT_PLAYER_COMMAND_DURATION_MS)
    parser.add_argument("--enemy-command-duration-ms", type=int, default=DEFAULT_ENEMY_COMMAND_DURATION_MS)
    parser.add_argument("--max-steps", type=int, default=0)
    parser.add_argument("--state-wait-timeout-seconds", type=int, default=45)
    parser.add_argument("--no-open-browser", action="store_true")
    return parser.parse_args()


class ArenaHttp:
    def __init__(self, server_url: str):
        self.server_url = server_url.rstrip("/")
        self.run_id = "run_unknown"
        self.scenario_id = "scenario_unknown"
        self.api_calls_count = 0
        self.latencies_ms: list[float] = []

    def reset(self) -> dict[str, Any]:
        payload = self.request_json("POST", "/api/arena/reset", {})
        self.run_id = str(payload.get("run_id", self.run_id))
        self.scenario_id = str(payload.get("scenario_id", self.scenario_id))
        return payload

    def get_state(self) -> list[dict[str, str]]:
        return parse_state(self.request_text("GET", "/api/arena/state"))

    def get_score(self) -> dict[str, Any]:
        return self.request_json("GET", "/api/arena/score")

    def set_player_input(self, action: dict[str, Any]) -> dict[str, Any]:
        issued = now_ms()
        duration = int(action.get("duration_ms", DEFAULT_PLAYER_COMMAND_DURATION_MS))
        payload = {
            "run_id": self.run_id,
            "scenario_id": self.scenario_id,
            "command_id": f"runner_player_cmd_{issued}",
            "issued_at_ms": issued,
            "expires_at_ms": issued + duration,
            "forward": int(action.get("forward", 0)),
            "strafe": int(action.get("strafe", 0)),
            "turn": int(action.get("turn", 0)),
            "attack": bool(action.get("attack", False)),
            "use": bool(action.get("use", False)),
            "duration_ms": duration,
        }
        return self.request_json("POST", "/api/arena/player-command", payload)

    def set_enemy_team_command(self, command: str, duration_ms: int) -> str:
        issued = now_ms()
        body = (
            "run_id\tscenario_id\tcommand_id\tissued_at_ms\texpires_at_ms\t"
            "target_type\ttarget\tcommand\targ1\targ2\n"
            f"{self.run_id}\t{self.scenario_id}\trunner_enemy_cmd_{issued}\t"
            f"{issued}\t{issued + duration_ms}\tteam\tenemy\t{command}\t\t\n"
        )
        return self.request_text(
            "POST",
            "/api/arena/enemy-commands",
            body.encode("utf-8"),
            "text/tab-separated-values; charset=utf-8",
        )

    def request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        content_type = "application/json; charset=utf-8" if data is not None else None
        return json.loads(self.request_text(method, path, data, content_type))

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
        self.api_calls_count += 1
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                body = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {path} failed with HTTP {exc.code}: {body}") from exc
        finally:
            self.latencies_ms.append((time.perf_counter() - start) * 1000.0)

        return body

    def average_latency_ms(self) -> float:
        if not self.latencies_ms:
            return 0.0
        return sum(self.latencies_ms) / len(self.latencies_ms)


class ResultWriter:
    def __init__(self, run_dir: Path):
        self.run_dir = run_dir
        self.events_path = run_dir / "events.jsonl"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.events_file = self.events_path.open("w", encoding="utf-8")

    def write_event(self, event: dict[str, Any]) -> None:
        self.events_file.write(json.dumps(event, separators=(",", ":")) + "\n")
        self.events_file.flush()

    def write_config(self, config: dict[str, Any]) -> None:
        (self.run_dir / "config.json").write_text(
            json.dumps(config, indent=2) + "\n",
            encoding="utf-8",
        )

    def write_summary(self, summary: dict[str, Any]) -> None:
        (self.run_dir / "summary.json").write_text(
            json.dumps(summary, indent=2) + "\n",
            encoding="utf-8",
        )

    def close(self) -> None:
        self.events_file.close()


def parse_state(text: str) -> list[dict[str, str]]:
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return []
    header = lines[0].split("\t")
    rows = []
    for line in lines[1:]:
        values = line.split("\t")
        rows.append(dict(zip(header, values)))
    return rows


def as_int(row: dict[str, str], key: str, default: int = 0) -> int:
    try:
        return int(row.get(key, "") or default)
    except ValueError:
        return default


def split_rows(rows: list[dict[str, str]]) -> tuple[dict[str, str], list[dict[str, str]]]:
    player = next((row for row in rows if row.get("kind") == "player"), {})
    enemies = [row for row in rows if row.get("kind") == "enemy"]
    return player, enemies


def live_enemies(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        row for row in rows
        if row.get("kind") == "enemy" and row.get("alive", "0") == "1"
    ]


def summarize_player(player: dict[str, str]) -> dict[str, Any]:
    return {
        "x": as_int(player, "x"),
        "y": as_int(player, "y"),
        "angle": as_int(player, "angle"),
        "health": as_int(player, "health"),
        "alive": player.get("alive", "0") == "1",
        "ready_weapon": as_int(player, "ready_weapon", -1),
        "ammo_bullets": as_int(player, "ammo_bullets"),
        "ammo_shells": as_int(player, "ammo_shells"),
        "ammo_cells": as_int(player, "ammo_cells"),
        "ammo_rockets": as_int(player, "ammo_rockets"),
        "position_delta": as_int(player, "position_delta"),
        "stuck_ticks": as_int(player, "stuck_ticks"),
    }


def choose_player_action(
    rows: list[dict[str, str]],
    duration_ms: int,
) -> dict[str, Any]:
    player, _ = split_rows(rows)
    enemies = live_enemies(rows)

    if not enemies:
        return {"name": "stop", "duration_ms": duration_ms}

    if as_int(player, "stuck_ticks") >= 6:
        return {"name": "unstick", "forward": 1, "turn": 1, "duration_ms": duration_ms}

    target = min(enemies, key=lambda row: as_int(row, "distance_to_player", 999999))
    relative_angle = as_int(target, "relative_angle_to_player")
    distance = as_int(target, "distance_to_player", 999999)
    line_of_sight = target.get("line_of_sight", "0") == "1"
    turn = 0

    if relative_angle > 8:
        turn = 1
    elif relative_angle < -8:
        turn = -1

    if line_of_sight and abs(relative_angle) <= 8:
        return {
            "name": "shoot",
            "attack": True,
            "target": target.get("entity_id", ""),
            "relative_angle": relative_angle,
            "distance": distance,
            "duration_ms": duration_ms,
        }

    if distance > 500 or not line_of_sight:
        return {
            "name": "move_toward_enemy",
            "forward": 1,
            "turn": turn,
            "target": target.get("entity_id", ""),
            "relative_angle": relative_angle,
            "distance": distance,
            "line_of_sight": line_of_sight,
            "duration_ms": duration_ms,
        }

    return {
        "name": "turn_toward_enemy",
        "turn": turn or 1,
        "target": target.get("entity_id", ""),
        "relative_angle": relative_angle,
        "distance": distance,
        "duration_ms": duration_ms,
    }


def terminal_status(
    rows: list[dict[str, str]],
    elapsed_seconds: float,
    timeout_seconds: int,
) -> tuple[str, str]:
    player, enemies = split_rows(rows)
    player_health = as_int(player, "health")
    player_alive = player.get("alive", "0") == "1" and player_health > 0
    alive_count = sum(1 for row in enemies if row.get("alive", "0") == "1")

    if player and not player_alive:
        return "enemy", "player_dead"
    if enemies and alive_count == 0 and player_health > 0:
        return "player", "all_enemies_dead"
    if elapsed_seconds >= timeout_seconds:
        return "enemy", "timeout"
    return "running", "running"


def wait_for_run_state(
    client: ArenaHttp,
    timeout_seconds: int,
    poll_interval_ms: int,
) -> list[dict[str, str]]:
    deadline = time.time() + timeout_seconds
    last_error = ""

    while time.time() < deadline:
        try:
            rows = client.get_state()
        except RuntimeError as exc:
            last_error = str(exc)
            rows = []

        player, enemies = split_rows(rows)
        if (
            player
            and enemies
            and player.get("run_id") == client.run_id
            and all(row.get("run_id") == client.run_id for row in enemies)
        ):
            client.scenario_id = player.get("scenario_id", client.scenario_id)
            return rows

        time.sleep(poll_interval_ms / 1000.0)

    detail = f" Last state error: {last_error}" if last_error else ""
    raise RuntimeError(f"Timed out waiting for arena state for run_id {client.run_id}.{detail}")


def event_from_state(
    client: ArenaHttp,
    rows: list[dict[str, str]],
    player_action: dict[str, Any] | None,
    enemy_commands: list[dict[str, Any]],
    status: str,
    terminal_reason: str,
) -> dict[str, Any]:
    player, enemies = split_rows(rows)
    alive_count = sum(1 for row in enemies if row.get("alive", "0") == "1")
    return {
        "timestamp_ms": now_ms(),
        "tick": as_int(player, "tick") if player else None,
        "run_id": client.run_id,
        "scenario_id": client.scenario_id,
        "player_state": summarize_player(player),
        "enemies_alive": alive_count,
        "enemies_total": len(enemies),
        "player_action": player_action,
        "enemy_commands": enemy_commands,
        "status": status,
        "terminal_reason": terminal_reason,
    }


def build_summary(
    client: ArenaHttp,
    rows: list[dict[str, str]],
    winner: str,
    terminal_reason: str,
    elapsed_seconds: float,
    player_actions_count: int,
    enemy_commands_count: int,
) -> dict[str, Any]:
    player, enemies = split_rows(rows)
    enemies_alive = sum(1 for row in enemies if row.get("alive", "0") == "1")
    enemies_total = len(enemies)
    return {
        "run_id": client.run_id,
        "scenario_id": client.scenario_id,
        "winner": winner,
        "terminal_reason": terminal_reason,
        "elapsed_time_seconds": round(elapsed_seconds, 3),
        "player_health_end": as_int(player, "health"),
        "enemies_total": enemies_total,
        "enemies_killed": max(0, enemies_total - enemies_alive),
        "enemies_alive": enemies_alive,
        "player_actions_count": player_actions_count,
        "enemy_commands_count": enemy_commands_count,
        "mcp_or_api_calls_count": client.api_calls_count,
        "average_loop_latency_ms": round(client.average_latency_ms(), 3),
    }


def main() -> int:
    args = parse_args()
    client = ArenaHttp(args.server_url)
    reset_payload = client.reset()
    if not args.no_open_browser:
        webbrowser.open(args.server_url.rstrip("/") + "/?arenaData=mock")

    run_dir = RESULTS_ROOT / client.run_id
    writer = ResultWriter(run_dir)
    config = {
        "server_url": args.server_url,
        "run_id": client.run_id,
        "scenario_id": client.scenario_id,
        "timeout_seconds": args.timeout_seconds,
        "decision_interval_ms": args.decision_interval_ms,
        "state_poll_interval_ms": args.state_poll_interval_ms,
        "player_command_duration_ms": args.player_command_duration_ms,
        "enemy_command_duration_ms": args.enemy_command_duration_ms,
        "max_steps": args.max_steps,
        "open_browser": not args.no_open_browser,
        "player_policy": "builtin_full_knowledge_nearest_enemy_v1",
        "enemy_policy": "team_chase_player_v1",
    }
    writer.write_config(config)
    writer.write_event(
        {
            "timestamp_ms": now_ms(),
            "run_id": client.run_id,
            "scenario_id": client.scenario_id,
            "event": "reset",
            "reset": reset_payload,
            "status": "waiting_for_browser_reload",
        }
    )

    start = time.time()
    rows = wait_for_run_state(
        client,
        args.state_wait_timeout_seconds,
        args.state_poll_interval_ms,
    )
    writer.write_event(
        event_from_state(
            client,
            rows,
            player_action=None,
            enemy_commands=[],
            status="started",
            terminal_reason="running",
        )
    )

    steps = 0
    player_actions_count = 0
    enemy_commands_count = 0
    winner = "running"
    terminal_reason = "running"

    try:
        while True:
            loop_start = time.perf_counter()
            elapsed = time.time() - start
            winner, terminal_reason = terminal_status(rows, elapsed, args.timeout_seconds)
            if winner != "running":
                break
            if args.max_steps > 0 and steps >= args.max_steps:
                terminal_reason = "max_steps"
                break

            player_action = choose_player_action(rows, args.player_command_duration_ms)
            enemies_alive = len(live_enemies(rows))
            enemy_commands: list[dict[str, Any]] = []

            client.set_player_input(player_action)
            player_actions_count += 1

            if enemies_alive > 0:
                client.set_enemy_team_command(
                    "chase_player",
                    duration_ms=args.enemy_command_duration_ms,
                )
                enemy_commands.append(
                    {
                        "target_type": "team",
                        "target": "enemy",
                        "command": "chase_player",
                        "duration_ms": args.enemy_command_duration_ms,
                    }
                )
                enemy_commands_count += 1

            writer.write_event(
                event_from_state(
                    client,
                    rows,
                    player_action=player_action,
                    enemy_commands=enemy_commands,
                    status="running",
                    terminal_reason="running",
                )
            )

            steps += 1
            elapsed_ms = (time.perf_counter() - loop_start) * 1000.0
            sleep_ms = max(0, args.decision_interval_ms - int(elapsed_ms))
            time.sleep(sleep_ms / 1000.0)
            rows = client.get_state()

        if terminal_reason == "max_steps":
            winner = "running"
        elif terminal_reason == "timeout":
            winner = "enemy"

        final_rows = client.get_state()
        elapsed = time.time() - start
        writer.write_event(
            event_from_state(
                client,
                final_rows,
                player_action=None,
                enemy_commands=[],
                status=winner,
                terminal_reason=terminal_reason,
            )
        )
        summary = build_summary(
            client,
            final_rows,
            winner,
            terminal_reason,
            elapsed,
            player_actions_count,
            enemy_commands_count,
        )
        writer.write_summary(summary)
    finally:
        writer.close()

    print(json.dumps(summary, indent=2))
    print(f"results_dir={run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
