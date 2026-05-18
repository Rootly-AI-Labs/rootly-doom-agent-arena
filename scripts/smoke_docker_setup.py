#!/usr/bin/env python3
"""Smoke-test the Docker-backed Doom Arena runtime and host-side stdio MCP."""

from __future__ import annotations

import argparse
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test Docker Doom Arena setup.")
    parser.add_argument("--port", type=int, default=int(os.environ.get("DOOM_ARENA_PORT", "8001")))
    parser.add_argument("--timeout-seconds", type=int, default=90)
    parser.add_argument("--dev", action="store_true", help="Include docker-compose.dev.yml.")
    parser.add_argument("--no-build", action="store_true", help="Skip --build when starting Docker Compose.")
    return parser.parse_args()


def compose_files(dev: bool) -> list[str]:
    files = ["-f", "docker-compose.yml"]
    if dev:
        files += ["-f", "docker-compose.dev.yml"]
    return files


def run(cmd: list[str], *, env: dict[str, str] | None = None, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        env=env,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )


def require_docker() -> None:
    if shutil.which("docker") is None:
        raise RuntimeError("Docker CLI was not found.")
    try:
        run(["docker", "info"], capture=True)
    except subprocess.CalledProcessError as exc:
        output = exc.stdout or ""
        if "Server:" in output:
            output = output.split("Server:", 1)[1].strip()
        else:
            lines = [line for line in output.splitlines() if line.strip()]
            output = lines[-1] if lines else ""
        detail = f" Details: {output}" if output else ""
        raise RuntimeError("Docker daemon is not reachable. Start Docker and try again." + detail) from exc


def request(method: str, url: str, payload: object | None = None, timeout: float = 5.0) -> tuple[int, bytes]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def wait_for_health(base_url: str, timeout_seconds: int) -> None:
    deadline = time.time() + timeout_seconds
    url = base_url.rstrip("/") + "/api/arena/health"
    last_error = ""
    while time.time() < deadline:
        try:
            status, body = request("GET", url, timeout=2)
            if 200 <= status < 500:
                payload = json.loads(body.decode("utf-8"))
                if payload.get("ok") is True:
                    print(f"ok Docker server health: HTTP {status}")
                    return
                last_error = f"health payload was not ok: {payload}"
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for Docker server at {url}. Last error: {last_error}")


def read_mcp_message(stdout: Any) -> dict[str, Any]:
    headers: dict[str, str] = {}
    while True:
        line = stdout.readline()
        if line == b"":
            raise RuntimeError("MCP stdio process closed stdout")
        text = line.decode("ascii", errors="replace").strip()
        if text == "":
            break
        name, separator, value = text.partition(":")
        if separator:
            headers[name.lower()] = value.strip()
    length = int(headers.get("content-length", "0"))
    if length <= 0:
        raise RuntimeError("MCP stdio response did not include Content-Length")
    body = stdout.read(length)
    return json.loads(body.decode("utf-8"))


def read_mcp_message_with_timeout(process: subprocess.Popen[bytes], timeout_seconds: int) -> dict[str, Any]:
    messages: queue.Queue[dict[str, Any] | BaseException] = queue.Queue()

    def worker() -> None:
        try:
            messages.put(read_mcp_message(process.stdout))
        except BaseException as exc:  # noqa: BLE001 - return thread errors to the caller.
            messages.put(exc)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    try:
        result = messages.get(timeout=timeout_seconds)
    except queue.Empty as exc:
        process.kill()
        raise RuntimeError("Timed out waiting for MCP stdio response") from exc
    if isinstance(result, BaseException):
        raise result
    return result


def write_mcp_message(process: subprocess.Popen[bytes], message: dict[str, Any]) -> None:
    body = json.dumps(message, separators=(",", ":")).encode("utf-8")
    process.stdin.write(b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n")
    process.stdin.write(body)
    process.stdin.flush()


def smoke_stdio_mcp(base_url: str) -> None:
    env = os.environ.copy()
    env["DOOM_ARENA_BASE_URL"] = base_url
    env["PYTHONUNBUFFERED"] = "1"
    process = subprocess.Popen(
        [sys.executable, str(REPO_ROOT / "scripts" / "doom_arena_mcp.py")],
        cwd=str(REPO_ROOT),
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        write_mcp_message(
            process,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "doom-arena-docker-smoke", "version": "0"},
                },
            },
        )
        initialized = read_mcp_message_with_timeout(process, 10)
        if "result" not in initialized:
            raise RuntimeError(f"MCP initialize failed: {initialized}")

        write_mcp_message(process, {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        write_mcp_message(
            process,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "reset_duel",
                    "arguments": {
                        "player_1_model": "codex",
                        "player_2_model": "claude",
                        "round": 1,
                        "seed": 20260518,
                        "timeout_seconds": 30,
                    },
                },
            },
        )
        response = read_mcp_message_with_timeout(process, 15)
        result = response.get("result", {})
        if result.get("isError"):
            raise RuntimeError(f"MCP reset_duel failed: {result}")
        text = result.get("content", [{}])[0].get("text", "")
        payload = json.loads(text)
        if not payload.get("run_id"):
            raise RuntimeError(f"MCP reset_duel response did not include run_id: {payload}")
        print("ok host-side stdio MCP reached Docker backend")
    finally:
        try:
            write_mcp_message(process, {"jsonrpc": "2.0", "id": 99, "method": "shutdown", "params": {}})
        except (BrokenPipeError, OSError):
            pass
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def smoke_results_persist(base_url: str) -> None:
    status, body = request(
        "POST",
        base_url.rstrip("/") + "/api/arena/duel-session",
        {
            "player_1_model": "codex",
            "player_2_model": "claude",
            "rounds": 1,
            "seed": 20260518,
            "timeout_seconds": 30,
            "enforce_controller_tokens": False,
        },
    )
    if status != 200:
        raise RuntimeError(f"POST /api/arena/duel-session returned HTTP {status}: {body[:500]!r}")
    payload = json.loads(body.decode("utf-8"))
    session_id = str(payload.get("duel_session_id", ""))
    run_id = str(payload.get("run_id", ""))
    if not session_id or not run_id:
        raise RuntimeError(f"duel-session response did not include session/run ids: {payload}")

    round_dir = REPO_ROOT / "benchmarks" / "results" / session_id / f"round_01_{run_id}"
    expected = [
        round_dir / "config.json",
        round_dir / "controller_tokens.json",
        round_dir / "player_1_mcp_instructions.md",
        round_dir / "player_2_mcp_instructions.md",
    ]
    missing = [str(path) for path in expected if not path.exists()]
    if missing:
        raise RuntimeError("Docker results did not persist to the host: " + ", ".join(missing))
    print(f"ok results persisted under {round_dir.relative_to(REPO_ROOT)}")


def main() -> int:
    args = parse_args()
    require_docker()

    env = os.environ.copy()
    env["DOOM_ARENA_PORT"] = str(args.port)
    compose = ["docker", "compose", *compose_files(args.dev), "up", "-d"]
    if not args.no_build:
        compose.append("--build")
    run(compose, env=env)

    base_url = f"http://127.0.0.1:{args.port}"
    wait_for_health(base_url, args.timeout_seconds)

    status, body = request("GET", base_url.rstrip("/") + "/")
    if status != 200 or b"Websockets Doom" not in body:
        raise RuntimeError(f"browser/index route failed: HTTP {status}")
    print("ok browser/index route loads")

    status, body = request("GET", base_url.rstrip("/") + "/api/arena/mcp-config")
    if status != 200:
        raise RuntimeError(f"arena API did not respond: HTTP {status}")
    config = json.loads(body.decode("utf-8"))
    if config.get("base_url_env") != f"DOOM_ARENA_BASE_URL={base_url}":
        raise RuntimeError(f"mcp config did not advertise expected base URL: {config}")
    print("ok arena API responds")

    smoke_stdio_mcp(base_url)
    smoke_results_persist(base_url)
    print("docker setup smoke test passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
    except subprocess.CalledProcessError as exc:
        output = exc.stdout or ""
        print(f"ERROR: command failed: {' '.join(exc.cmd)}", file=sys.stderr)
        if output:
            print(output, file=sys.stderr)
        raise SystemExit(exc.returncode)
