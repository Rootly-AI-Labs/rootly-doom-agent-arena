#!/usr/bin/env python3
"""Run a fully automated 10-match Doom Arena benchmark with two Codex agents."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import webbrowser


REPO_ROOT = Path(__file__).resolve().parents[1]
HARNESS_DIR = Path(__file__).resolve().parent
MCP_SERVER = REPO_ROOT / "scripts" / "doom_arena_mcp.py"
START_DOCKER = REPO_ROOT / "scripts" / "start-docker.sh"

BASE_URL = "http://127.0.0.1:8001"
PLAYER_1_MODEL = "gpt-5.5"
PLAYER_2_MODEL = "gpt-5.4"
MATCHES = 10
ROUND_TIMEOUT_SECONDS = 180
READY_TIMEOUT_SECONDS = 180
POLL_SECONDS = 2.0
MAX_AGENT_RESTARTS = 20


@dataclass
class AgentProcess:
    participant_id: str
    model: str
    process: subprocess.Popen[str]
    log_path: Path
    log_file: Any
    restart_count: int = 0
    thread_id: str = ""


def request_json(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    timeout: float = 10,
) -> dict[str, Any]:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(BASE_URL + path, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            parsed = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} failed: HTTP {error.code}: {detail}") from error
    except (URLError, TimeoutError) as error:
        raise RuntimeError(f"{method} {path} failed: {error}") from error
    if not isinstance(parsed, dict):
        raise RuntimeError(f"{method} {path} returned a non-object JSON response")
    return parsed


def backend_is_healthy() -> bool:
    try:
        return request_json("GET", "/api/arena/health", timeout=2).get("ok") is True
    except RuntimeError:
        return False


def docker_is_ready() -> bool:
    result = subprocess.run(
        ["docker", "info"],
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def ensure_backend() -> None:
    if backend_is_healthy():
        print(f"Arena backend is healthy at {BASE_URL}")
        return

    if not docker_is_ready() and sys.platform == "darwin":
        print("Starting Docker Desktop ...")
        subprocess.run(["open", "-a", "Docker"], check=True)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline and not docker_is_ready():
            time.sleep(2)

    if not docker_is_ready():
        raise RuntimeError("Docker is not ready. Start Docker Desktop and run this script again.")

    print("Building and starting Doom Arena ...")
    subprocess.run(
        [
            "bash",
            str(START_DOCKER),
            "start",
            "--no-open-browser",
            "--timeout-seconds",
            "90",
        ],
        cwd=REPO_ROOT,
        check=True,
    )
    if not backend_is_healthy():
        raise RuntimeError(f"Doom Arena did not become healthy at {BASE_URL}")


def create_session() -> dict[str, Any]:
    payload = {
        "arena_mode": "duel",
        "control_mode": "hierarchical",
        "scenario_id": "duel_e1m8_blind_spawn",
        "player_1_model": PLAYER_1_MODEL,
        "player_2_model": PLAYER_2_MODEL,
        "rounds": MATCHES,
        "round": 1,
        "seed": 42,
        "timeout_seconds": ROUND_TIMEOUT_SECONDS,
        "decision_cadence_ms": 750,
        "intent_duration_ms": 25000,
        "hide_enemy_position": True,
        "randomize_spawns": False,
        "rotate_all_maps": False,
        "recap_window": 1,
        "enable_map_blueprint": False,
        "enable_weapon_pickups": True,
        "mirror_pair": False,
        "enforce_controller_tokens": True,
        "continue_session": False,
        "restart_session": False,
    }
    session = request_json("POST", "/api/arena/duel-session", payload)
    required = ("duel_session_id", "run_id", "player_1_prompt", "player_2_prompt")
    missing = [key for key in required if not session.get(key)]
    if missing:
        raise RuntimeError("Session response is missing: " + ", ".join(missing))
    if int(session.get("total_rounds", 0)) != MATCHES:
        raise RuntimeError(f"Arena did not create the requested {MATCHES}-match session")
    return session


def codex_command(model: str, prompt: str, thread_id: str = "") -> list[str]:
    mcp_args = json.dumps([str(MCP_SERVER)], separators=(",", ":"))
    mcp_env = (
        '{DOOM_ARENA_BASE_URL="'
        + BASE_URL
        + '",DOOM_ARENA_CODING_ASSISTANT="Codex CLI",DOOM_ARENA_MODEL_IDENTITY="'
        + model
        + '"}'
    )
    command = [
        "codex",
        "--model",
        model,
        "--sandbox",
        "read-only",
        "--ask-for-approval",
        "never",
        "--cd",
        str(REPO_ROOT),
        "--config",
        'mcp_servers.doom-arena.command="python3"',
        "--config",
        f"mcp_servers.doom-arena.args={mcp_args}",
        "--config",
        f"mcp_servers.doom-arena.env={mcp_env}",
        "--config",
        'mcp_servers.doom-arena.default_tools_approval_mode="approve"',
        "exec",
    ]
    if thread_id:
        command.extend(["resume", "--json", thread_id, prompt])
    else:
        command.extend(["--json", prompt])
    return command


def launch_agent(
    participant_id: str,
    model: str,
    prompt: str,
    restart_count: int = 0,
    thread_id: str = "",
) -> AgentProcess:
    prompt += (
        f"\n\nAutomation requirement: This is a {MATCHES}-match session. "
        "Begin immediately, call the Doom Arena MCP tools, and remain active across every match. "
        "When a match finishes and has_next_round is true, keep polling get_match_result until "
        "the browser advances the arena, then continue controlling the same participant. "
        "Do not produce your final response or disconnect until has_next_round is false."
    )
    suffix = "" if restart_count == 0 else f".restart_{restart_count:02d}"
    log_path = HARNESS_DIR / f"{participant_id}_{model}{suffix}.jsonl"
    log_file = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        codex_command(model, prompt, thread_id),
        cwd=REPO_ROOT,
        text=True,
        stdin=subprocess.DEVNULL,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    action = "Launched" if restart_count == 0 else f"Resumed (turn {restart_count + 1})"
    print(f"{action} {participant_id} with {model} (PID {process.pid})")
    return AgentProcess(
        participant_id,
        model,
        process,
        log_path,
        log_file,
        restart_count,
        thread_id,
    )


def read_thread_id(agent: AgentProcess) -> str:
    if agent.thread_id:
        return agent.thread_id
    agent.log_file.flush()
    try:
        with agent.log_path.open("r", encoding="utf-8") as log:
            for line in log:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "thread.started" and event.get("thread_id"):
                    return str(event["thread_id"])
    except OSError as error:
        raise RuntimeError(f"Could not read Codex thread log {agent.log_path}: {error}") from error
    raise RuntimeError(
        f"Codex did not report a thread_id for {agent.participant_id}; "
        f"cannot preserve its context. Log: {agent.log_path}"
    )


def relaunch_agent(agent: AgentProcess) -> AgentProcess:
    if agent.restart_count >= MAX_AGENT_RESTARTS:
        raise RuntimeError(
            f"{agent.participant_id} exceeded {MAX_AGENT_RESTARTS} supervised restarts"
        )
    thread_id = read_thread_id(agent)
    agent.log_file.close()
    instruction_path = "/api/arena/run-instructions?" + urlencode(
        {"participant_id": agent.participant_id}
    )
    instruction = request_json("GET", instruction_path, timeout=5)
    prompt = str(instruction.get("prompt") or "")
    if not prompt:
        raise RuntimeError(
            f"Arena returned no current prompt for {agent.participant_id}"
        )
    return launch_agent(
        agent.participant_id,
        agent.model,
        prompt,
        restart_count=agent.restart_count + 1,
        thread_id=thread_id,
    )


def agent_failure(agent: AgentProcess) -> RuntimeError:
    agent.log_file.flush()
    tail = ""
    try:
        tail = "\n".join(agent.log_path.read_text(encoding="utf-8").splitlines()[-20:])
    except OSError:
        pass
    return RuntimeError(
        f"{agent.participant_id} ({agent.model}) exited with code "
        f"{agent.process.returncode}. Log: {agent.log_path}\n{tail}"
    )


def wait_for_agents_ready(agents: list[AgentProcess]) -> dict[str, Any]:
    deadline = time.monotonic() + READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        for agent in agents:
            code = agent.process.poll()
            if code is not None:
                raise agent_failure(agent)

        presence = request_json("GET", "/api/arena/mcp-presence", timeout=5)
        clients = presence.get("clients") or []
        ready = presence.get("ready_agents") or {}
        both_ready = bool(ready.get("player_1")) and bool(ready.get("player_2"))
        print(
            f"Waiting for agents: MCP clients={len(clients)}, "
            f"P1 ready={bool(ready.get('player_1'))}, P2 ready={bool(ready.get('player_2'))}",
            end="\r",
            flush=True,
        )
        # Stdio MCP clients may disappear from the transient `clients` list
        # between calls. The server's ready-agent registry is authoritative and
        # can only be populated through successful authenticated MCP tool calls.
        if both_ready:
            print("\nBoth MCP agents are connected and ready.")
            return presence
        time.sleep(POLL_SECONDS)
    raise TimeoutError(f"Agents did not become MCP-ready within {READY_TIMEOUT_SECONDS} seconds")


def open_game() -> str:
    query = urlencode({"duel": "1", "autoStart": "1"})
    url = f"{BASE_URL}/?{query}"
    print(f"Starting the browser game: {url}")
    if not webbrowser.open(url, new=2):
        raise RuntimeError(f"Could not open a browser. Open this URL manually: {url}")
    return url


def monitor_session(session_id: str, agents: list[AgentProcess]) -> dict[str, Any]:
    deadline = time.monotonic() + MATCHES * (ROUND_TIMEOUT_SECONDS + 120)
    last_completed = -1
    path = "/api/arena/duel-session-results?" + urlencode({"duel_session_id": session_id})

    while time.monotonic() < deadline:
        results = request_json("GET", path, timeout=5)
        rounds = results.get("rounds") or []
        completed = len(rounds)
        if completed != last_completed:
            print(f"Completed matches: {completed}/{MATCHES}")
            last_completed = completed
        if completed >= MATCHES:
            return results

        for index, agent in enumerate(agents):
            code = agent.process.poll()
            if code is None:
                continue
            if code != 0:
                raise agent_failure(agent)
            print(
                f"{agent.participant_id} ({agent.model}) completed its Codex turn "
                f"before the benchmark ended; resuming the same Codex thread."
            )
            agents[index] = relaunch_agent(agent)
        time.sleep(POLL_SECONDS)

    raise TimeoutError(f"The {MATCHES}-match benchmark exceeded its overall timeout")


def reset_arena() -> None:
    payload = {
        "arena_mode": "duel",
        "scenario_id": "duel_e1m8_blind_spawn",
        "rounds": MATCHES,
        "clear_duel_session": True,
    }
    response = request_json("POST", "/api/arena/reset", payload)
    if response.get("ok") is not True:
        raise RuntimeError("Arena reset did not report success")
    print("Arena reset after the completed benchmark.")


def stop_backend() -> None:
    subprocess.run(
        ["bash", str(START_DOCKER), "stop"],
        cwd=REPO_ROOT,
        check=True,
    )
    print("Docker backend stopped; localhost port 8001 is now free.")


def stop_agent(agent: AgentProcess) -> None:
    if agent.process.poll() is None:
        try:
            os.killpg(agent.process.pid, signal.SIGTERM)
            agent.process.wait(timeout=8)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            if agent.process.poll() is None:
                try:
                    os.killpg(agent.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                agent.process.wait()
    agent.log_file.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Create the 10-match session and prompts, but do not launch agents or the game.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    agents: list[AgentProcess] = []
    completed = False
    ensure_backend()
    session = create_session()
    session_id = str(session["duel_session_id"])
    print(f"Created session {session_id} with {MATCHES} matches")
    print(f"Results directory: {session.get('results_dir', '')}")

    if args.prepare_only:
        print("Prepare-only mode: agents and browser were not launched.")
        return 0

    try:
        agents = [
            launch_agent("player_1", PLAYER_1_MODEL, str(session["player_1_prompt"])),
            launch_agent("player_2", PLAYER_2_MODEL, str(session["player_2_prompt"])),
        ]
        wait_for_agents_ready(agents)
        game_url = open_game()
        results = monitor_session(session_id, agents)
        summary = {
            "duel_session_id": session_id,
            "game_url": game_url,
            "player_1_model": PLAYER_1_MODEL,
            "player_2_model": PLAYER_2_MODEL,
            "requested_matches": MATCHES,
            "completed_matches": len(results.get("rounds") or []),
            "results": results,
        }
        summary_path = HARNESS_DIR / "doom_benchmark_summary.json"
        summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(f"Benchmark complete. Summary: {summary_path}")
        reset_arena()
        completed = True
        stop_backend()
        return 0
    except KeyboardInterrupt:
        print("\nBenchmark interrupted; preserving the arena state for inspection.", file=sys.stderr)
        return 130
    finally:
        for agent in agents:
            stop_agent(agent)
        if not completed:
            print("Arena was not reset because the benchmark did not complete.", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
