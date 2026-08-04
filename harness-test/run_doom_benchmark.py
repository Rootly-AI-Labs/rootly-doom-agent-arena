#!/usr/bin/env python3
"""Run a fully automated 10-match Doom Arena benchmark with two Codex agents."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from typing import Any
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import webbrowser


REPO_ROOT = Path(__file__).resolve().parents[1]
HARNESS_DIR = Path(__file__).resolve().parent
MCP_SERVER = REPO_ROOT / "scripts" / "doom_arena_mcp.py"
START_DOCKER = REPO_ROOT / "scripts" / "start-docker.sh"
START_DOCKER_PS1 = REPO_ROOT / "scripts" / "start-docker.ps1"

IS_WINDOWS = sys.platform == "win32"

BASE_URL = "http://127.0.0.1:8001"
PLAYER_1_MODEL = "gpt-5.5"
PLAYER_2_MODEL = "gpt-5.4"
MATCHES = 10
SCENARIO_ID = "duel_e1m8_blind_spawn"
AGENT_CLI = "codex"
# Empty means "pick the default for the selected CLI": stdio for Claude Code
# (--strict-mcp-config isolates it from the user's own MCP config, and stdio is
# the only transport that can carry the identity env vars), http for Codex.
MCP_TRANSPORT = ""
BYPASS_PERMISSIONS = True
ENABLE_WEAPON_PICKUPS = True
KEEP_BACKEND = False
OPEN_BROWSER = True
ROUND_TIMEOUT_SECONDS = 180
READY_TIMEOUT_SECONDS = 180
POLL_SECONDS = 2.0
MAX_AGENT_RESTARTS = 20


def child_process_kwargs() -> dict[str, Any]:
    """Isolate each agent in its own process group so it can be killed as a tree.

    `start_new_session` is POSIX-only and raises ValueError on Windows, so the
    Windows path uses CREATE_NEW_PROCESS_GROUP instead.
    """
    if IS_WINDOWS:
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def kill_process_tree(process: "subprocess.Popen[str]") -> None:
    if IS_WINDOWS:
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(process.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return
    os.killpg(process.pid, signal.SIGTERM)


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
    if IS_WINDOWS:
        start_command = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(START_DOCKER_PS1),
            "-NoOpenBrowser",
            "-TimeoutSeconds",
            "90",
        ]
    else:
        start_command = [
            "bash",
            str(START_DOCKER),
            "start",
            "--no-open-browser",
            "--timeout-seconds",
            "90",
        ]
    subprocess.run(start_command, cwd=REPO_ROOT, check=True)
    if not backend_is_healthy():
        raise RuntimeError(f"Doom Arena did not become healthy at {BASE_URL}")


def create_session() -> dict[str, Any]:
    payload = {
        "arena_mode": "duel",
        "control_mode": "hierarchical",
        "scenario_id": SCENARIO_ID,
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
        "enable_weapon_pickups": ENABLE_WEAPON_PICKUPS,
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


def agent_executable() -> str:
    """Resolve the CLI that drives the agents.

    On Windows the npm shims are `codex.CMD` / `claude.CMD`; CreateProcess
    cannot find the extensionless name, so always use the resolved path.
    """
    name = "claude" if AGENT_CLI == "claude" else "codex"
    resolved = shutil.which(name)
    if not resolved:
        raise RuntimeError(
            f"The {name} CLI was not found on PATH. Install it and confirm "
            f"`{name} --version` works before running the benchmark."
        )
    return resolved


def resolved_mcp_transport() -> str:
    if MCP_TRANSPORT:
        return MCP_TRANSPORT
    return "stdio" if AGENT_CLI == "claude" else "http"


def codex_executable() -> str:
    """Resolve the Codex CLI.

    On Windows the npm shim is `codex.CMD`; CreateProcess cannot find the
    extensionless `codex`, so always use the fully resolved path.
    """
    resolved = shutil.which("codex")
    if not resolved:
        raise RuntimeError(
            "The Codex CLI was not found on PATH. Install it and confirm "
            "`codex --version` works before running the benchmark."
        )
    return resolved


def mcp_python_executable() -> str:
    """Interpreter Codex should use to run the Doom Arena MCP server.

    `python3` does not exist on a standard Windows install, so fall back to
    the interpreter running this harness.
    """
    return shutil.which("python3") or sys.executable


def claude_mcp_config(model: str) -> str:
    """Inline MCP server definition passed to `claude --mcp-config`.

    Paired with --strict-mcp-config so the user's own doom-arena entry in
    ~/.claude.json is ignored; the benchmark always talks to this run's server.
    """
    if resolved_mcp_transport() == "http":
        server: dict[str, Any] = {"type": "http", "url": f"{BASE_URL}/mcp"}
    else:
        server = {
            "type": "stdio",
            "command": mcp_python_executable(),
            "args": [str(MCP_SERVER)],
            "env": {
                "DOOM_ARENA_BASE_URL": BASE_URL,
                "DOOM_ARENA_CODING_ASSISTANT": "Claude Code",
                "DOOM_ARENA_MODEL_IDENTITY": model,
            },
        }
    return json.dumps({"mcpServers": {"doom-arena": server}}, separators=(",", ":"))


def claude_command(model: str, prompt: str, session_id: str, resume: bool) -> list[str]:
    command = [
        agent_executable(),
        "--print",
        "--model",
        model,
        "--output-format",
        "stream-json",
        "--verbose",
        "--mcp-config",
        claude_mcp_config(model),
        "--strict-mcp-config",
        "--add-dir",
        str(REPO_ROOT),
    ]
    if BYPASS_PERMISSIONS:
        command.append("--dangerously-skip-permissions")
    if resume:
        command.extend(["--resume", session_id])
    else:
        # Pre-assigning the session id means a restart can resume without
        # scraping the id back out of the event log.
        command.extend(["--session-id", session_id])
    # The prompt is deliberately NOT appended as an argv element. On Windows the
    # npm shim runs through cmd.exe, which truncates an argument at its first
    # newline, so a multi-line prompt would arrive as just its heading. It is
    # written to stdin by launch_agent instead.
    return command


def mcp_transport_config(model: str) -> list[str]:
    """Build the `--config` overrides that point Codex at the Doom Arena MCP.

    HTTP is the default because a `[mcp_servers.doom-arena]` entry in the
    user's ~/.codex/config.toml commonly already sets `url`. Codex rejects a
    server that carries both `url` and `command` ("url is not supported for
    stdio"), so injecting stdio args on top of such an entry fails to load.
    """
    if resolved_mcp_transport() == "http":
        return [
            "--config",
            f'mcp_servers.doom-arena.url="{BASE_URL}/mcp"',
            "--config",
            "mcp_servers.doom-arena.startup_timeout_sec=10.0",
            "--config",
            "mcp_servers.doom-arena.tool_timeout_sec=60.0",
        ]

    mcp_args = json.dumps([str(MCP_SERVER)], separators=(",", ":"))
    mcp_env = (
        '{DOOM_ARENA_BASE_URL="'
        + BASE_URL
        + '",DOOM_ARENA_CODING_ASSISTANT="Codex CLI",DOOM_ARENA_MODEL_IDENTITY="'
        + model
        + '"}'
    )
    mcp_python = json.dumps(mcp_python_executable())
    return [
        "--config",
        f"mcp_servers.doom-arena.command={mcp_python}",
        "--config",
        f"mcp_servers.doom-arena.args={mcp_args}",
        "--config",
        f"mcp_servers.doom-arena.env={mcp_env}",
    ]


def codex_command(model: str, prompt: str, thread_id: str = "") -> list[str]:
    command = [
        codex_executable(),
        "--model",
        model,
        "--sandbox",
        "read-only",
        "--ask-for-approval",
        "never",
        "--cd",
        str(REPO_ROOT),
        *mcp_transport_config(model),
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
    if AGENT_CLI == "claude":
        # Claude Code accepts a caller-supplied session id, so the id is known
        # before launch instead of being recovered from the event stream.
        session_id = thread_id or str(uuid.uuid4())
        command = claude_command(model, prompt, session_id, resume=bool(thread_id))
    else:
        session_id = thread_id
        command = codex_command(model, prompt, thread_id)

    suffix = "" if restart_count == 0 else f".restart_{restart_count:02d}"
    log_path = HARNESS_DIR / f"{participant_id}_{model}{suffix}.jsonl"
    log_file = log_path.open("w", encoding="utf-8")
    prompt_via_stdin = AGENT_CLI == "claude"
    process = subprocess.Popen(
        command,
        cwd=REPO_ROOT,
        text=True,
        stdin=subprocess.PIPE if prompt_via_stdin else subprocess.DEVNULL,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        **child_process_kwargs(),
    )
    if prompt_via_stdin and process.stdin is not None:
        # stdout is a file, not a pipe, so writing the whole prompt cannot
        # deadlock against an unread output buffer.
        try:
            process.stdin.write(prompt)
            process.stdin.close()
        except OSError as error:
            raise RuntimeError(
                f"Could not send the prompt to {participant_id}: {error}"
            ) from error
    action = "Launched" if restart_count == 0 else f"Resumed (turn {restart_count + 1})"
    print(f"{action} {participant_id} with {model} via {AGENT_CLI} (PID {process.pid})")
    return AgentProcess(
        participant_id,
        model,
        process,
        log_path,
        log_file,
        restart_count,
        session_id,
    )


def read_thread_id(agent: AgentProcess) -> str:
    if agent.thread_id:
        return agent.thread_id
    if AGENT_CLI == "claude":
        raise RuntimeError(
            f"No Claude session id recorded for {agent.participant_id}; "
            f"cannot resume its context. Log: {agent.log_path}"
        )
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
    if not OPEN_BROWSER:
        print(f"Browser auto-open disabled. Open the game tab manually: {url}")
        return url
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
        "scenario_id": SCENARIO_ID,
        "rounds": MATCHES,
        "clear_duel_session": True,
    }
    response = request_json("POST", "/api/arena/reset", payload)
    if response.get("ok") is not True:
        raise RuntimeError("Arena reset did not report success")
    print("Arena reset after the completed benchmark.")


def stop_backend() -> None:
    if KEEP_BACKEND:
        print("Leaving the arena backend running (--keep-backend).")
        return
    if IS_WINDOWS:
        subprocess.run(
            ["docker", "compose", "-f", "docker/docker-compose.yml", "down"],
            cwd=REPO_ROOT,
            check=True,
        )
    else:
        subprocess.run(
            ["bash", str(START_DOCKER), "stop"],
            cwd=REPO_ROOT,
            check=True,
        )
    print("Docker backend stopped; localhost port 8001 is now free.")


def stop_agent(agent: AgentProcess) -> None:
    if agent.process.poll() is None:
        try:
            kill_process_tree(agent.process)
            agent.process.wait(timeout=8)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            if agent.process.poll() is None:
                try:
                    if IS_WINDOWS:
                        agent.process.kill()
                    else:
                        os.killpg(agent.process.pid, signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    pass
                agent.process.wait()
    agent.log_file.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Create the session and prompts, but do not launch agents or the game.",
    )
    parser.add_argument(
        "--matches",
        type=int,
        default=MATCHES,
        help=f"Number of matches in the session (default: {MATCHES}).",
    )
    parser.add_argument(
        "--player-1-model",
        default=PLAYER_1_MODEL,
        help=f"Model driving player_1 (default: {PLAYER_1_MODEL}).",
    )
    parser.add_argument(
        "--player-2-model",
        default=PLAYER_2_MODEL,
        help=f"Model driving player_2 (default: {PLAYER_2_MODEL}).",
    )
    parser.add_argument(
        "--scenario-id",
        default=SCENARIO_ID,
        help=f"Map / spawn variant (default: {SCENARIO_ID}).",
    )
    parser.add_argument(
        "--weapon-pickups",
        choices=("true", "false"),
        default="true",
        help="Whether weapons spawn on the map (default: true).",
    )
    parser.add_argument(
        "--round-timeout-seconds",
        type=int,
        default=ROUND_TIMEOUT_SECONDS,
        help=f"Per-round timeout (default: {ROUND_TIMEOUT_SECONDS}).",
    )
    parser.add_argument(
        "--agent-cli",
        choices=("codex", "claude"),
        default=AGENT_CLI,
        help=f"CLI that drives both agents (default: {AGENT_CLI}).",
    )
    parser.add_argument(
        "--bypass-permissions",
        action=argparse.BooleanOptionalAction,
        default=BYPASS_PERMISSIONS,
        help=(
            "Claude Code only: pass --dangerously-skip-permissions so the agent "
            "never blocks on a permission prompt (default: enabled)."
        ),
    )
    parser.add_argument(
        "--mcp-transport",
        choices=("http", "stdio"),
        default=MCP_TRANSPORT,
        help=(
            "How the agent reaches the Doom Arena MCP server. Defaults to stdio "
            f"for claude and http for codex. 'http' targets {BASE_URL}/mcp. For "
            "codex, 'stdio' requires that ~/.codex/config.toml does not set a url "
            "for mcp_servers.doom-arena."
        ),
    )
    parser.add_argument(
        "--keep-backend",
        action="store_true",
        help="Do not stop the arena backend after the benchmark completes.",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not auto-open the game tab; open the printed URL yourself.",
    )
    args = parser.parse_args()
    if args.matches < 1:
        parser.error("--matches must be at least 1")
    return args


def apply_args(args: argparse.Namespace) -> None:
    global MATCHES, PLAYER_1_MODEL, PLAYER_2_MODEL, SCENARIO_ID, MCP_TRANSPORT
    global ENABLE_WEAPON_PICKUPS, ROUND_TIMEOUT_SECONDS, KEEP_BACKEND, OPEN_BROWSER
    global AGENT_CLI, BYPASS_PERMISSIONS
    MATCHES = args.matches
    MCP_TRANSPORT = args.mcp_transport
    AGENT_CLI = args.agent_cli
    BYPASS_PERMISSIONS = args.bypass_permissions
    PLAYER_1_MODEL = args.player_1_model
    PLAYER_2_MODEL = args.player_2_model
    SCENARIO_ID = args.scenario_id
    ENABLE_WEAPON_PICKUPS = args.weapon_pickups == "true"
    ROUND_TIMEOUT_SECONDS = args.round_timeout_seconds
    KEEP_BACKEND = args.keep_backend
    OPEN_BROWSER = not args.no_browser


def main() -> int:
    args = parse_args()
    apply_args(args)
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
