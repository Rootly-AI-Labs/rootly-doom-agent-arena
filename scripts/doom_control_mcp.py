#!/usr/bin/env python3
"""MCP wrapper for Agentic Doom local dev-server endpoints.

This server intentionally talks only to the local Doom dev server. It never
reads Rootly credentials and it only emits the existing TSV command format.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any


VALID_COMMANDS = {"normal", "hold", "chase_player", "fight_each_other"}
VALID_SEVERITIES = {"SEV0", "SEV1", "SEV2", "SEV3", "SEV4", "SEV5"}
COMMAND_HEADER = "target_type\ttarget\tcommand\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MCP server for Agentic Doom.")
    parser.add_argument(
        "--server-url",
        default=os.environ.get("DOOM_CONTROL_SERVER", "http://127.0.0.1:8000"),
        help="Root URL of scripts/rootly_dev_server.py.",
    )
    return parser.parse_args()


class DoomControlError(RuntimeError):
    pass


class DoomControlClient:
    def __init__(self, server_url: str):
        self.server_url = server_url.rstrip("/")

    def get_game_state(self) -> str:
        return self._request("GET", "/api/agentic/state")

    def set_monster_command(self, incident_index: int, command: str) -> str:
        command = normalize_command(command)
        if incident_index < 0:
            raise DoomControlError("incident_index must be >= 0")

        rows = self._read_command_rows()
        rows = upsert_command(rows, "incident_index", str(incident_index), command)
        return self._write_command_rows(rows)

    def set_severity_command(self, severity: str, command: str) -> str:
        severity = severity.upper()
        command = normalize_command(command)

        if severity not in VALID_SEVERITIES:
            raise DoomControlError("severity must be one of SEV0, SEV1, SEV2, SEV3, SEV4, SEV5")

        rows = self._read_command_rows()
        rows = upsert_command(rows, "severity", severity, command)
        return self._write_command_rows(rows)

    def clear_all_monster_commands(self) -> str:
        return self._post_commands(COMMAND_HEADER)

    def _read_command_rows(self) -> list[tuple[str, str, str]]:
        try:
            body = self._request("GET", "/api/agentic/commands")
        except DoomControlError:
            return []

        rows: list[tuple[str, str, str]] = []
        for line_number, line in enumerate(body.splitlines(), 1):
            if not line.strip():
                continue
            if line_number == 1 and line == COMMAND_HEADER.rstrip("\n"):
                continue

            parts = line.split("\t")
            if len(parts) != 3:
                continue

            target_type, target, command = parts
            if target_type not in {"severity", "incident_index"}:
                continue
            if command not in VALID_COMMANDS:
                continue

            rows.append((target_type, target, command))

        return rows

    def _write_command_rows(self, rows: list[tuple[str, str, str]]) -> str:
        body = COMMAND_HEADER + "".join(
            f"{target_type}\t{target}\t{command}\n"
            for target_type, target, command in rows
        )
        return self._post_commands(body)

    def _post_commands(self, body: str) -> str:
        return self._request(
            "POST",
            "/api/agentic/commands",
            body.encode("utf-8"),
            "text/tab-separated-values; charset=utf-8",
        )

    def _request(
        self,
        method: str,
        path: str,
        data: bytes | None = None,
        content_type: str | None = None,
    ) -> str:
        headers = {}
        if content_type is not None:
            headers["Content-Type"] = content_type

        request = urllib.request.Request(
            self.server_url + path,
            data=data,
            headers=headers,
            method=method,
        )

        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise DoomControlError(f"{method} {path} failed with HTTP {exc.code}: {body}") from exc
        except OSError as exc:
            raise DoomControlError(
                f"Could not reach Doom dev server at {self.server_url}. "
                "Run: py scripts\\rootly_dev_server.py --port 8000"
            ) from exc


def normalize_command(command: str) -> str:
    command = command.strip().lower()
    if command not in VALID_COMMANDS:
        raise DoomControlError("command must be one of normal, hold, chase_player, fight_each_other")
    return command


def upsert_command(
    rows: list[tuple[str, str, str]],
    target_type: str,
    target: str,
    command: str,
) -> list[tuple[str, str, str]]:
    filtered = [
        row for row in rows
        if not (row[0] == target_type and row[1] == target)
    ]

    if command != "normal":
        filtered.append((target_type, target, command))

    return filtered


def tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": "get_game_state",
            "description": "Return the latest Agentic Doom game state TSV from the local dev server.",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
        {
            "name": "set_monster_command",
            "description": "Set a command for one Rootly incident monster by incident_index.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "incident_index": {"type": "integer", "minimum": 0},
                    "command": {"type": "string", "enum": sorted(VALID_COMMANDS)},
                },
                "required": ["incident_index", "command"],
                "additionalProperties": False,
            },
        },
        {
            "name": "set_severity_command",
            "description": "Set a command for all Rootly incident monsters with a severity.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "severity": {"type": "string", "enum": sorted(VALID_SEVERITIES)},
                    "command": {"type": "string", "enum": sorted(VALID_COMMANDS)},
                },
                "required": ["severity", "command"],
                "additionalProperties": False,
            },
        },
        {
            "name": "clear_all_monster_commands",
            "description": "Clear all external monster commands so Doom uses normal AI.",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    ]


def call_tool(client: DoomControlClient, name: str, arguments: dict[str, Any]) -> str:
    if name == "get_game_state":
        return client.get_game_state()

    if name == "set_monster_command":
        return client.set_monster_command(
            int(arguments["incident_index"]),
            str(arguments["command"]),
        )

    if name == "set_severity_command":
        return client.set_severity_command(
            str(arguments["severity"]),
            str(arguments["command"]),
        )

    if name == "clear_all_monster_commands":
        return client.clear_all_monster_commands()

    raise DoomControlError(f"Unknown tool: {name}")


def send_response(message_id: Any, result: Any) -> None:
    write_message({"jsonrpc": "2.0", "id": message_id, "result": result})


def send_error(message_id: Any, code: int, message: str) -> None:
    write_message(
        {
            "jsonrpc": "2.0",
            "id": message_id,
            "error": {
                "code": code,
                "message": message,
            },
        }
    )


def write_message(message: dict[str, Any]) -> None:
    body = json.dumps(message, separators=(",", ":")).encode("utf-8")
    sys.stdout.buffer.write(b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n")
    sys.stdout.buffer.write(body)
    sys.stdout.buffer.flush()


def read_message() -> dict[str, Any] | None:
    headers: dict[str, str] = {}

    while True:
        line = sys.stdin.buffer.readline()
        if line == b"":
            return None

        line = line.decode("ascii", errors="replace").strip()
        if line == "":
            break

        name, separator, value = line.partition(":")
        if separator:
            headers[name.lower()] = value.strip()

    length_text = headers.get("content-length")
    if length_text is None:
        raise json.JSONDecodeError("Missing Content-Length header", "", 0)

    body = sys.stdin.buffer.read(int(length_text))
    return json.loads(body.decode("utf-8"))


def handle_message(client: DoomControlClient, message: dict[str, Any]) -> bool:
    method = message.get("method")
    message_id = message.get("id")

    if method == "initialize":
        send_response(
            message_id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {},
                },
                "serverInfo": {
                    "name": "agentic-doom-control",
                    "version": "0.1.0",
                },
            },
        )
        return True

    if method == "notifications/initialized":
        return True

    if method == "tools/list":
        send_response(message_id, {"tools": tool_definitions()})
        return True

    if method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}

        try:
            text = call_tool(client, str(name), arguments)
            send_response(
                message_id,
                {
                    "content": [
                        {
                            "type": "text",
                            "text": text,
                        }
                    ],
                    "isError": False,
                },
            )
        except (KeyError, TypeError, ValueError, DoomControlError) as exc:
            send_response(
                message_id,
                {
                    "content": [
                        {
                            "type": "text",
                            "text": str(exc),
                        }
                    ],
                    "isError": True,
                },
            )
        return True

    if method == "shutdown":
        send_response(message_id, None)
        return False

    if message_id is not None:
        send_error(message_id, -32601, f"Method not found: {method}")

    return True


def main() -> int:
    args = parse_args()
    client = DoomControlClient(args.server_url)

    while True:
        try:
            message = read_message()
            if message is None:
                break
            keep_running = handle_message(client, message)
        except json.JSONDecodeError as exc:
            send_error(None, -32700, f"Parse error: {exc}")
            keep_running = True

        if not keep_running:
            break

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
