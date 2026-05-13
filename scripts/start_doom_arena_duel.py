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
    parser = argparse.ArgumentParser(description="Start Doom Arena server and browser.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--no-open-browser", action="store_true")
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
        print(f"Open browser: {server_url}/", flush=True)
        print("MCP endpoint for Codex and Claude:", flush=True)
        print(f"  {server_url}/mcp", flush=True)
        print("", flush=True)

        if not args.no_open_browser:
            webbrowser.open(server_url.rstrip("/") + "/", new=1, autoraise=True)

        print("Server running. Use the browser to start duels and copy prompts. Press Ctrl+C to stop.", flush=True)
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down.", flush=True)
        return 130
    finally:
        if server_process is not None:
            server_process.terminate()
            try:
                server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server_process.kill()
                server_process.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
