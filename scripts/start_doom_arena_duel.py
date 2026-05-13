#!/usr/bin/env python3
"""One-command local launcher for Doom Arena Duel."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start Doom Arena server, browser, and MCP duel orchestrator.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--player-1-model", default="codex")
    parser.add_argument("--player-2-model", default="claude")
    parser.add_argument("--round", type=int, default=1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--decision-interval-ms", type=int, default=750)
    parser.add_argument("--decision-cadence-ms", type=int, default=750)
    parser.add_argument("--intent-duration-ms", type=int, default=2500)
    parser.add_argument("--max-in-flight-decisions", type=int, default=1)
    parser.add_argument("--fallback-intent", default="search")
    parser.add_argument("--fallback-style", default="balanced")
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument("--state-wait-timeout-seconds", type=int, default=45)
    parser.add_argument("--no-open-browser", action="store_true")
    parser.add_argument("--server-only", action="store_true", help="Start the arena server and browser, but do not run the orchestrator.")
    parser.add_argument(
        "--rolling-control",
        action="store_true",
        help="Opt in to local scripted rolling tactical intents. Default is external Codex/Claude MCP control only.",
    )
    parser.add_argument("--monitor-only", action="store_true", help="Deprecated alias for the default behavior.")
    parser.add_argument("--keep-server", action="store_true", help="Keep the arena server running after the orchestrator exits.")
    parser.add_argument("--no-controller-tokens", action="store_true")
    return parser.parse_args()


def request_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=1) as response:
            return 200 <= response.status < 500
    except (OSError, urllib.error.URLError):
        return False


def wait_for_server(server_url: str, timeout_seconds: int = 10) -> None:
    deadline = time.time() + timeout_seconds
    config_url = server_url.rstrip("/") + "/api/arena/mcp-config"
    while time.time() < deadline:
        if request_ok(config_url):
            return
        time.sleep(0.2)
    raise RuntimeError(f"Timed out waiting for Doom Arena server at {server_url}")


def run_command(args: list[str]) -> int:
    print("+ " + " ".join(args), flush=True)
    return subprocess.call(args, cwd=str(REPO_ROOT))


def main() -> int:
    args = parse_args()
    server_url = f"http://{args.host}:{args.port}"
    server_process: subprocess.Popen[str] | None = None

    server_cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "doom_arena_server.py"),
        "--host",
        args.host,
        "--port",
        str(args.port),
    ]

    try:
        print("Starting Doom Arena server...", flush=True)
        server_process = subprocess.Popen(server_cmd, cwd=str(REPO_ROOT))
        wait_for_server(server_url)

        print("", flush=True)
        print(f"Open browser: {server_url}/?duel=1", flush=True)
        print("MCP client command for Codex and Claude:", flush=True)
        print(f"  py scripts\\doom_arena_mcp.py --server-url {server_url}", flush=True)
        print("", flush=True)

        if not args.no_open_browser:
            webbrowser.open(server_url.rstrip("/") + "/?duel=1", new=1, autoraise=True)

        if args.server_only:
            print("Server-only mode. Press Ctrl+C to stop.", flush=True)
            while True:
                time.sleep(1)

        max_steps = args.max_steps
        if max_steps is None:
            max_steps = max(1, int((args.timeout_seconds * 1000) / max(1, args.decision_interval_ms)) + 30)

        orchestrator_cmd = [
            sys.executable,
            str(REPO_ROOT / "scripts" / "doom_arena_mcp_duel_orchestrator.py"),
            "--server-url",
            server_url,
            "--player-1-model",
            args.player_1_model,
            "--player-2-model",
            args.player_2_model,
            "--round",
            str(args.round),
            "--seed",
            str(args.seed),
            "--timeout-seconds",
            str(args.timeout_seconds),
            "--decision-interval-ms",
            str(args.decision_interval_ms),
            "--decision-cadence-ms",
            str(args.decision_cadence_ms),
            "--intent-duration-ms",
            str(args.intent_duration_ms),
            "--max-in-flight-decisions",
            str(args.max_in_flight_decisions),
            "--fallback-intent",
            args.fallback_intent,
            "--fallback-style",
            args.fallback_style,
            "--max-steps",
            str(max_steps),
            "--state-wait-timeout-seconds",
            str(args.state_wait_timeout_seconds),
        ]
        if args.rolling_control and not args.monitor_only:
            orchestrator_cmd.append("--rolling-control")
        if args.monitor_only:
            orchestrator_cmd.append("--monitor-only")
        if args.no_controller_tokens:
            orchestrator_cmd.append("--no-controller-tokens")

        exit_code = run_command(orchestrator_cmd)
        if args.keep_server:
            print("Keeping server running. Press Ctrl+C to stop.", flush=True)
            while True:
                time.sleep(1)
        return exit_code
    except KeyboardInterrupt:
        print("\nShutting down.", flush=True)
        return 130
    finally:
        if server_process is not None and not args.keep_server:
            server_process.terminate()
            try:
                server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server_process.kill()
                server_process.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
