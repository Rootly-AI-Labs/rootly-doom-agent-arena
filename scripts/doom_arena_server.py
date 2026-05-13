#!/usr/bin/env python3
"""Local Doom Agent Arena server.

Serves the Doom WASM files from src/ and stores local arena TSV control files.
All endpoints are local-only by default.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from doom_arena_duel_prompts import (
    RESULTS_ROOT,
    build_controller_tokens,
    instructions as render_participant_instructions,
    write_controller_tokens,
)
from doom_arena_mcp import DoomArenaClient, DoomArenaError, call_tool, tool_definitions


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"

ARENA_STATE_TSV = SRC_DIR / "arena_game_state.local.tsv"
ARENA_EVENTS_TSV = SRC_DIR / "arena_duel_events.local.tsv"
ARENA_PLAYER_COMMAND_TSV = SRC_DIR / "arena_player_command.local.tsv"
ARENA_PARTICIPANT_COMMAND_TSV = SRC_DIR / "arena_participant_commands.local.tsv"
ARENA_PARTICIPANT_INTENT_TSV = SRC_DIR / "arena_participant_intents.local.tsv"
ARENA_PARTICIPANT_READY_TSV = SRC_DIR / "arena_participant_ready.local.tsv"
ARENA_ENEMY_COMMAND_TSV = SRC_DIR / "arena_enemy_commands.local.tsv"
ARENA_RUN_METADATA_TSV = SRC_DIR / "arena_run_metadata.local.tsv"

DEFAULT_SCENARIO_ID = "e1m8_arena"
DEFAULT_ARENA_MODE = "enemies"
DUEL_DEFAULTS = {
    "arena_mode": "duel",
    "player_1_model": "codex",
    "player_2_model": "claude",
    "round": 1,
    "seed": 42,
    "timeout_seconds": 120,
}
PLAYER_COMMAND_HEADER = (
    "run_id\tscenario_id\tcommand_id\tissued_at_ms\texpires_at_ms\t"
    "forward\tstrafe\tturn\tattack\tuse\tduration_ms\n"
)
PARTICIPANT_COMMAND_HEADER = (
    "run_id\tscenario_id\tcommand_id\tissued_at_ms\texpires_at_ms\t"
    "participant_id\tforward\tstrafe\tturn\tattack\tuse\tduration_ms\n"
)
PARTICIPANT_INTENT_LEGACY_HEADER = (
    "run_id\tscenario_id\tintent_id\tissued_at_ms\texpires_at_ms\t"
    "participant_id\tintent\tstyle\ttarget_id\tpreferred_distance\taggression\tduration_ms\n"
)
PARTICIPANT_INTENT_HEADER = (
    "run_id\tscenario_id\tintent_id\tissued_at_ms\texpires_at_ms\t"
    "participant_id\tintent\tstyle\ttarget_id\tpreferred_distance\taggression\tduration_ms\t"
    "strafe_direction\tmovement_bias\tfire_policy\tdistance_policy\treplan_if\tsequence_number\tdecision_cadence_ms\n"
)
PARTICIPANT_READY_HEADER = "run_id\tscenario_id\tparticipant_id\tready_at_ms\tstatus\n"
ENEMY_COMMAND_HEADER = (
    "run_id\tscenario_id\tcommand_id\tissued_at_ms\texpires_at_ms\t"
    "target_type\ttarget\tcommand\targ1\targ2\n"
)
RUN_METADATA_HEADER = (
    "run_id\tscenario_id\tarena_mode\tstarted_at_ms\tplayer_1_model\t"
    "player_2_model\tround\tseed\ttimeout_seconds\n"
)
PARTICIPANTS = {"player_1", "player_2"}
ALLOWED_PARTICIPANT_INTENTS = {"hold", "engage_opponent", "strafe_attack", "search"}
ALLOWED_PARTICIPANT_INTENT_STYLES = {"balanced", "aggressive", "evasive", "cautious"}
ALLOWED_STRAFE_DIRECTIONS = {"left", "right", "alternate", "auto"}
ALLOWED_MOVEMENT_BIASES = {"direct", "circle", "evasive", "cautious"}
ALLOWED_FIRE_POLICIES = {"hold_fire", "only_when_aligned", "burst_when_aligned", "suppressive"}
ALLOWED_DISTANCE_POLICIES = {"close", "maintain", "kite"}
ALLOWED_REPLAN_TRIGGERS = {"lost_los", "stuck", "low_health", "target_far", "target_close"}


def now_ms() -> int:
    return int(time.time() * 1000)


def new_run_id() -> str:
    return "run_" + uuid.uuid4().hex[:12]


def clamp_int(value: Any, low: int, high: int) -> int:
    return max(low, min(high, int(value)))


def normalize_optional_enum(value: Any, default: str, allowed: set[str], field_name: str) -> str:
    normalized = str(value if value is not None else default).strip().lower()
    if normalized == "":
        normalized = default
    if normalized not in allowed:
        raise ValueError(f"{field_name} must be one of " + ", ".join(sorted(allowed)))
    return normalized


def normalize_replan_if(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, str):
        triggers = [part.strip().lower() for part in value.split(",") if part.strip()]
    elif isinstance(value, list):
        triggers = [str(part).strip().lower() for part in value if str(part).strip()]
    else:
        raise ValueError("replan_if must be a list or comma-separated string")
    invalid = [trigger for trigger in triggers if trigger not in ALLOWED_REPLAN_TRIGGERS]
    if invalid:
        raise ValueError(
            "replan_if contains invalid trigger(s): "
            + ", ".join(invalid)
            + ". Allowed: "
            + ", ".join(sorted(ALLOWED_REPLAN_TRIGGERS))
        )
    return ",".join(triggers)


def normalize_optional_int(value: Any, field_name: str, *, minimum: int | None = None) -> str:
    if value is None or value == "":
        return ""
    parsed = int(value)
    if minimum is not None and parsed < minimum:
        raise ValueError(f"{field_name} must be >= {minimum}")
    return str(parsed)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve Doom Agent Arena locally.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--scenario-id", default=DEFAULT_SCENARIO_ID)
    parser.add_argument(
        "--quiet-mcp-help",
        action="store_true",
        help="Do not print the stdio MCP client launch command on startup.",
    )
    return parser.parse_args()


class DoomArenaServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[SimpleHTTPRequestHandler],
        args: argparse.Namespace,
    ):
        super().__init__(server_address, handler_class)
        self.args = args
        self.run_id = new_run_id()
        self.scenario_id = args.scenario_id
        self.arena_mode = DEFAULT_ARENA_MODE
        self.player_1_model = ""
        self.player_2_model = ""
        self.round = 1
        self.seed = 0
        self.timeout_seconds = 300
        self.started_at_ms = now_ms()
        self.reset_requested = False


class DoomArenaHandler(SimpleHTTPRequestHandler):
    server: DoomArenaServer

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, directory=str(SRC_DIR), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def serve_arena_index(self) -> None:
        try:
            content = (SRC_DIR / "index.html").read_bytes()
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND, "index.html not found")
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]

        if path == "/mcp":
            self.handle_mcp_http()
            return

        if path == "/api/arena/state":
            self.write_file(ARENA_STATE_TSV, "arena_game_state.local.tsv")
            return

        if path == "/api/arena/player-command":
            self.write_player_command()
            return

        if path == "/api/arena/participant-commands":
            self.write_participant_commands()
            return

        if path == "/api/arena/participant-intents":
            self.write_participant_intents()
            return

        if path == "/api/arena/participant-ready":
            self.write_participant_ready()
            return

        if path == "/api/arena/enemy-commands":
            self.write_file(ARENA_ENEMY_COMMAND_TSV, "arena_enemy_commands.local.tsv")
            return

        if path == "/api/arena/events":
            self.write_file(ARENA_EVENTS_TSV, "arena_duel_events.local.tsv")
            return

        if path == "/api/arena/reset":
            self.reset_arena()
            return

        if path == "/api/arena/duel-session":
            self.create_duel_session()
            return

        if path == "/api/arena/run-metadata":
            self.write_file(ARENA_RUN_METADATA_TSV, "arena_run_metadata.local.tsv")
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]

        if path in {"/", "/index.html", "/websockets-doom.html"}:
            self.serve_arena_index()
            return

        if path == "/api/arena/state":
            self.read_file(ARENA_STATE_TSV, "arena_game_state.local.tsv")
            return

        if path == "/api/arena/player-command":
            self.read_file(ARENA_PLAYER_COMMAND_TSV, "arena_player_command.local.tsv")
            return

        if path == "/api/arena/participant-commands":
            self.read_file(ARENA_PARTICIPANT_COMMAND_TSV, "arena_participant_commands.local.tsv")
            return

        if path == "/api/arena/participant-intents":
            self.read_file(ARENA_PARTICIPANT_INTENT_TSV, "arena_participant_intents.local.tsv")
            return

        if path == "/api/arena/participant-ready":
            self.read_file(ARENA_PARTICIPANT_READY_TSV, "arena_participant_ready.local.tsv")
            return

        if path == "/api/arena/enemy-commands":
            self.read_file(ARENA_ENEMY_COMMAND_TSV, "arena_enemy_commands.local.tsv")
            return

        if path == "/api/arena/events":
            self.read_file(ARENA_EVENTS_TSV, "arena_duel_events.local.tsv")
            return

        if path == "/api/arena/reset":
            self.read_reset()
            return

        if path == "/api/arena/run-metadata":
            self.read_file(ARENA_RUN_METADATA_TSV, "arena_run_metadata.local.tsv")
            return

        if path == "/api/arena/score":
            self.read_score()
            return

        if path == "/api/arena/mcp-config":
            self.read_mcp_config()
            return

        super().do_GET()

    def read_body(self) -> bytes:
        length_header = self.headers.get("Content-Length")
        length = int(length_header or "0")
        return self.rfile.read(length)

    def handle_mcp_http(self) -> None:
        try:
            payload = json.loads(self.read_body().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.write_json(
                HTTPStatus.BAD_REQUEST,
                {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}},
            )
            return

        if isinstance(payload, list):
            responses = [response for message in payload if (response := self.handle_mcp_message(message)) is not None]
            self.write_json(HTTPStatus.OK, responses)
            return

        if not isinstance(payload, dict):
            self.write_json(
                HTTPStatus.BAD_REQUEST,
                {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}},
            )
            return

        response = self.handle_mcp_message(payload)
        if response is None:
            self.write_json(HTTPStatus.ACCEPTED, {"ok": True})
            return
        self.write_json(HTTPStatus.OK, response)

    def handle_mcp_message(self, message: dict[str, Any]) -> dict[str, Any] | None:
        method = message.get("method")
        message_id = message.get("id")
        params = message.get("params") or {}

        if method == "initialize":
            protocol_version = str(params.get("protocolVersion") or "2025-11-25")
            return {
                "jsonrpc": "2.0",
                "id": message_id,
                "result": {
                    "protocolVersion": protocol_version,
                    "capabilities": {
                        "tools": {"listChanged": True},
                        "resources": {"listChanged": False},
                        "prompts": {"listChanged": False},
                        "logging": {},
                    },
                    "serverInfo": {
                        "name": "doom-agent-arena",
                        "title": "Doom Agent Arena",
                        "version": "0.1.0",
                        "description": "Local MCP tools for controlling Doom Arena duel participants.",
                    },
                    "instructions": (
                        "Use set_participant_ready, wait_for_match_start, get_participant_observation, "
                        "set_participant_intent, stop_participant_intent, get_match_result, and get_duel_events to control "
                        "assigned Doom Arena duel participants through high-level intents."
                    ),
                },
            }

        if method == "notifications/initialized":
            return None

        if method == "ping":
            return {"jsonrpc": "2.0", "id": message_id, "result": {}}

        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": message_id, "result": {"tools": tool_definitions()}}

        if method == "resources/list":
            return {"jsonrpc": "2.0", "id": message_id, "result": {"resources": []}}

        if method == "prompts/list":
            return {"jsonrpc": "2.0", "id": message_id, "result": {"prompts": []}}

        if method == "tools/call":
            try:
                client = DoomArenaClient(f"http://{self.server.args.host}:{self.server.args.port}")
                text = call_tool(client, str(params.get("name")), params.get("arguments") or {})
                result = {"content": [{"type": "text", "text": text}], "isError": False}
            except (KeyError, TypeError, ValueError, DoomArenaError) as exc:
                result = {"content": [{"type": "text", "text": str(exc)}], "isError": True}
            return {"jsonrpc": "2.0", "id": message_id, "result": result}

        return {
            "jsonrpc": "2.0",
            "id": message_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }

    def write_file(self, path: Path, label: str) -> None:
        body = self.read_body()
        path.write_bytes(body)
        self.write_json(HTTPStatus.OK, {"ok": True, "path": label, "bytes": len(body)})

    def read_file(self, path: Path, label: str) -> None:
        if not path.exists():
            self.write_json(
                HTTPStatus.NOT_FOUND,
                {"ok": False, "error": f"{label} has not been written yet."},
            )
            return

        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/tab-separated-values; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def write_player_command(self) -> None:
        body = self.read_body()
        content_type = self.headers.get("Content-Type", "")

        if "application/json" in content_type:
            try:
                payload = json.loads(body.decode("utf-8"))
                body = self.player_command_json_to_tsv(payload).encode("utf-8")
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                self.write_json(
                    HTTPStatus.BAD_REQUEST,
                    {"ok": False, "error": f"Invalid player command JSON: {exc}"},
                )
                return

        ARENA_PLAYER_COMMAND_TSV.write_bytes(body)
        self.write_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "path": "arena_player_command.local.tsv",
                "bytes": len(body),
            },
        )

    def write_participant_commands(self) -> None:
        body = self.read_body()
        content_type = self.headers.get("Content-Type", "")

        if "application/json" in content_type:
            try:
                payload = json.loads(body.decode("utf-8"))
                rows = payload if isinstance(payload, list) else [payload]
                body = self.participant_commands_json_to_tsv(rows).encode("utf-8")
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                self.write_json(
                    HTTPStatus.BAD_REQUEST,
                    {"ok": False, "error": f"Invalid participant command JSON: {exc}"},
                )
                return

        ARENA_PARTICIPANT_COMMAND_TSV.write_bytes(body)
        self.write_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "path": "arena_participant_commands.local.tsv",
                "bytes": len(body),
            },
        )

    def write_participant_intents(self) -> None:
        body = self.read_body()
        content_type = self.headers.get("Content-Type", "")

        try:
            if "application/json" in content_type:
                payload = json.loads(body.decode("utf-8"))
                if isinstance(payload, list):
                    body = self.participant_intents_json_to_tsv(payload).encode("utf-8")
                elif isinstance(payload, dict):
                    body = self.update_participant_intent_json(payload).encode("utf-8")
                else:
                    raise ValueError("JSON payload must be an object or list")
            else:
                self.validate_participant_intents_tsv(body.decode("utf-8", errors="replace"))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self.write_json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": f"Invalid participant intent: {exc}"},
            )
            return

        ARENA_PARTICIPANT_INTENT_TSV.write_bytes(body)
        self.write_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "path": "arena_participant_intents.local.tsv",
                "bytes": len(body),
            },
        )

    def write_participant_ready(self) -> None:
        body = self.read_body()
        content_type = self.headers.get("Content-Type", "")

        try:
            if "application/json" in content_type:
                payload = json.loads(body.decode("utf-8"))
                if isinstance(payload, list):
                    rows = [self.normalize_participant_ready(row) for row in payload]
                    body = self.participant_ready_rows_to_tsv(rows).encode("utf-8")
                elif isinstance(payload, dict):
                    body = self.update_participant_ready_json(payload).encode("utf-8")
                else:
                    raise ValueError("JSON payload must be an object or list")
            else:
                self.validate_participant_ready_tsv(body.decode("utf-8", errors="replace"))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self.write_json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": f"Invalid participant ready state: {exc}"},
            )
            return

        ARENA_PARTICIPANT_READY_TSV.write_bytes(body)
        self.write_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "path": "arena_participant_ready.local.tsv",
                "bytes": len(body),
            },
        )

    def player_command_json_to_tsv(self, payload: dict[str, Any]) -> str:
        issued = int(payload.get("issued_at_ms", now_ms()))
        duration = int(payload.get("duration_ms", 250))
        expires = int(payload.get("expires_at_ms", issued + duration))
        command_id = str(payload.get("command_id", f"player_cmd_{issued}"))

        row = [
            str(payload.get("run_id", self.server.run_id)),
            str(payload.get("scenario_id", self.server.scenario_id)),
            command_id,
            str(issued),
            str(expires),
            str(int(payload.get("forward", 0))),
            str(int(payload.get("strafe", 0))),
            str(int(payload.get("turn", 0))),
            "true" if bool(payload.get("attack", False)) else "false",
            "true" if bool(payload.get("use", False)) else "false",
            str(duration),
        ]
        return PLAYER_COMMAND_HEADER + "\t".join(row) + "\n"

    def participant_commands_json_to_tsv(self, rows: list[dict[str, Any]]) -> str:
        body = PARTICIPANT_COMMAND_HEADER
        for payload in rows:
            participant_id = str(payload.get("participant_id", ""))
            if participant_id not in {"player_1", "player_2"}:
                raise ValueError("participant_id must be player_1 or player_2")

            issued = int(payload.get("issued_at_ms", now_ms()))
            duration = int(payload.get("duration_ms", 750))
            expires = int(payload.get("expires_at_ms", issued + duration))
            command_id = str(payload.get("command_id", f"{participant_id}_cmd_{issued}"))
            row = [
                str(payload.get("run_id", self.server.run_id)),
                str(payload.get("scenario_id", self.server.scenario_id)),
                command_id,
                str(issued),
                str(expires),
                participant_id,
                str(clamp_int(payload.get("forward", 0), -1, 1)),
                str(clamp_int(payload.get("strafe", 0), -1, 1)),
                str(clamp_int(payload.get("turn", 0), -1, 1)),
                "true" if bool(payload.get("attack", False)) else "false",
                "true" if bool(payload.get("use", False)) else "false",
                str(duration),
            ]
            body += "\t".join(row) + "\n"
        return body

    def update_participant_intent_json(self, payload: dict[str, Any]) -> str:
        intent_row = self.normalize_participant_intent(payload)
        rows = self.read_participant_intent_rows()
        current_ms = now_ms()
        rows = [
            row for row in rows
            if row.get("participant_id") != intent_row["participant_id"]
            and int(row.get("expires_at_ms", "0")) > current_ms
        ]
        rows.append(intent_row)
        return self.participant_intent_rows_to_tsv(rows)

    def participant_intents_json_to_tsv(self, rows: list[dict[str, Any]]) -> str:
        return self.participant_intent_rows_to_tsv(
            [self.normalize_participant_intent(payload) for payload in rows]
        )

    def normalize_participant_intent(self, payload: dict[str, Any]) -> dict[str, str]:
        participant_id = str(payload.get("participant_id", ""))
        if participant_id not in PARTICIPANTS:
            raise ValueError("participant_id must be player_1 or player_2")

        intent = str(payload.get("intent", "")).strip().lower()
        if intent not in ALLOWED_PARTICIPANT_INTENTS:
            raise ValueError(
                "intent must be one of "
                + ", ".join(sorted(ALLOWED_PARTICIPANT_INTENTS))
            )

        style = str(payload.get("style", "balanced")).strip().lower()
        if style not in ALLOWED_PARTICIPANT_INTENT_STYLES:
            raise ValueError(
                "style must be one of "
                + ", ".join(sorted(ALLOWED_PARTICIPANT_INTENT_STYLES))
            )

        issued = int(payload.get("issued_at_ms", now_ms()))
        duration = int(payload.get("duration_ms", 7000))
        if duration <= 0:
            raise ValueError("duration_ms must be positive")
        expires = int(payload.get("expires_at_ms", issued + duration))
        current_ms = now_ms()
        if expires <= issued:
            raise ValueError("expires_at_ms must be after issued_at_ms")
        if expires <= current_ms:
            raise ValueError("expired intents are not accepted")

        preferred_distance = int(payload.get("preferred_distance", 600))
        if preferred_distance <= 0:
            raise ValueError("preferred_distance must be positive")

        aggression = float(payload.get("aggression", 0.5))
        if aggression < 0.0 or aggression > 1.0:
            raise ValueError("aggression must be between 0.0 and 1.0")

        intent_id = str(payload.get("intent_id", f"{participant_id}_intent_{issued}"))
        target_id = str(payload.get("target_id", "player_2" if participant_id == "player_1" else "player_1"))
        if target_id not in PARTICIPANTS:
            raise ValueError("target_id must be player_1 or player_2")
        if target_id == participant_id:
            raise ValueError("target_id must be the opposing participant")

        strafe_direction = normalize_optional_enum(
            payload.get("strafe_direction"),
            "auto",
            ALLOWED_STRAFE_DIRECTIONS,
            "strafe_direction",
        )
        movement_bias = normalize_optional_enum(
            payload.get("movement_bias"),
            "direct",
            ALLOWED_MOVEMENT_BIASES,
            "movement_bias",
        )
        fire_policy = normalize_optional_enum(
            payload.get("fire_policy"),
            "only_when_aligned",
            ALLOWED_FIRE_POLICIES,
            "fire_policy",
        )
        distance_policy = normalize_optional_enum(
            payload.get("distance_policy"),
            "maintain",
            ALLOWED_DISTANCE_POLICIES,
            "distance_policy",
        )
        replan_if = normalize_replan_if(payload.get("replan_if"))
        sequence_number = normalize_optional_int(
            payload.get("sequence_number"),
            "sequence_number",
            minimum=0,
        )
        decision_cadence_ms = normalize_optional_int(
            payload.get("decision_cadence_ms"),
            "decision_cadence_ms",
            minimum=1,
        )

        return {
            "run_id": str(payload.get("run_id", self.server.run_id)),
            "scenario_id": str(payload.get("scenario_id", self.server.scenario_id)),
            "intent_id": intent_id,
            "issued_at_ms": str(issued),
            "expires_at_ms": str(expires),
            "participant_id": participant_id,
            "intent": intent,
            "style": style,
            "target_id": target_id,
            "preferred_distance": str(preferred_distance),
            "aggression": f"{aggression:.3f}",
            "duration_ms": str(duration),
            "strafe_direction": strafe_direction,
            "movement_bias": movement_bias,
            "fire_policy": fire_policy,
            "distance_policy": distance_policy,
            "replan_if": replan_if,
            "sequence_number": sequence_number,
            "decision_cadence_ms": decision_cadence_ms,
        }

    def read_participant_intent_rows(self) -> list[dict[str, str]]:
        if not ARENA_PARTICIPANT_INTENT_TSV.exists():
            return []
        text = ARENA_PARTICIPANT_INTENT_TSV.read_text(encoding="utf-8", errors="replace")
        return self.parse_participant_intent_rows(text, reject_expired=False)

    def parse_participant_intent_rows(self, text: str, reject_expired: bool = True) -> list[dict[str, str]]:
        lines = text.splitlines()
        if not lines:
            return []
        expected_header = PARTICIPANT_INTENT_HEADER.strip().split("\t")
        legacy_header = PARTICIPANT_INTENT_LEGACY_HEADER.strip().split("\t")
        header = lines[0].split("\t")
        if header == legacy_header:
            parse_header = legacy_header
        elif header == expected_header:
            parse_header = expected_header
        else:
            raise ValueError("participant intent TSV header does not match expected schema")
        rows = []
        for line in lines[1:]:
            if not line.strip():
                continue
            values = line.split("\t")
            if len(values) != len(parse_header):
                raise ValueError("participant intent TSV row has wrong column count")
            row = dict(zip(parse_header, values))
            if parse_header == legacy_header:
                row.update(
                    {
                        "strafe_direction": "auto",
                        "movement_bias": "direct",
                        "fire_policy": "only_when_aligned",
                        "distance_policy": "maintain",
                        "replan_if": "",
                        "sequence_number": "",
                        "decision_cadence_ms": "",
                    }
                )
            self.validate_participant_intent_row(row, reject_expired=reject_expired)
            rows.append(row)
        return rows

    def validate_participant_intents_tsv(self, text: str) -> None:
        self.parse_participant_intent_rows(text)

    def validate_participant_intent_row(self, row: dict[str, str], reject_expired: bool = True) -> None:
        participant_id = row.get("participant_id", "")
        if participant_id not in PARTICIPANTS:
            raise ValueError("participant_id must be player_1 or player_2")
        if row.get("intent", "") not in ALLOWED_PARTICIPANT_INTENTS:
            raise ValueError("invalid intent")
        if row.get("style", "") not in ALLOWED_PARTICIPANT_INTENT_STYLES:
            raise ValueError("invalid style")
        target_id = row.get("target_id", "")
        if target_id not in PARTICIPANTS or target_id == participant_id:
            raise ValueError("target_id must be the opposing participant")
        issued = int(row.get("issued_at_ms", "0"))
        expires = int(row.get("expires_at_ms", "0"))
        if expires <= issued:
            raise ValueError("expires_at_ms must be after issued_at_ms")
        if reject_expired and expires <= now_ms():
            raise ValueError("expired intents are not accepted")
        if int(row.get("duration_ms", "0")) <= 0:
            raise ValueError("duration_ms must be positive")
        if int(row.get("preferred_distance", "0")) <= 0:
            raise ValueError("preferred_distance must be positive")
        aggression = float(row.get("aggression", "0"))
        if aggression < 0.0 or aggression > 1.0:
            raise ValueError("aggression must be between 0.0 and 1.0")
        if row.get("strafe_direction", "auto") not in ALLOWED_STRAFE_DIRECTIONS:
            raise ValueError("invalid strafe_direction")
        if row.get("movement_bias", "direct") not in ALLOWED_MOVEMENT_BIASES:
            raise ValueError("invalid movement_bias")
        if row.get("fire_policy", "only_when_aligned") not in ALLOWED_FIRE_POLICIES:
            raise ValueError("invalid fire_policy")
        if row.get("distance_policy", "maintain") not in ALLOWED_DISTANCE_POLICIES:
            raise ValueError("invalid distance_policy")
        replan_if = row.get("replan_if", "")
        if replan_if:
            normalize_replan_if(replan_if)
        sequence_number = row.get("sequence_number", "")
        if sequence_number:
            normalize_optional_int(sequence_number, "sequence_number", minimum=0)
        decision_cadence_ms = row.get("decision_cadence_ms", "")
        if decision_cadence_ms:
            normalize_optional_int(decision_cadence_ms, "decision_cadence_ms", minimum=1)

    def participant_intent_rows_to_tsv(self, rows: list[dict[str, str]]) -> str:
        keys = PARTICIPANT_INTENT_HEADER.strip().split("\t")
        body = PARTICIPANT_INTENT_HEADER
        for row in rows:
            self.validate_participant_intent_row(row)
            body += "\t".join(row.get(key, "") for key in keys) + "\n"
        return body

    def update_participant_ready_json(self, payload: dict[str, Any]) -> str:
        ready_row = self.normalize_participant_ready(payload)
        rows = [
            row for row in self.read_participant_ready_rows()
            if row.get("participant_id") != ready_row["participant_id"]
        ]
        rows.append(ready_row)
        return self.participant_ready_rows_to_tsv(rows)

    def normalize_participant_ready(self, payload: dict[str, Any]) -> dict[str, str]:
        participant_id = str(payload.get("participant_id", ""))
        if participant_id not in PARTICIPANTS:
            raise ValueError("participant_id must be player_1 or player_2")

        status = str(payload.get("status", "ready")).strip().lower()
        if status != "ready":
            raise ValueError("status must be ready")

        ready_at_ms = int(payload.get("ready_at_ms", now_ms()))
        if ready_at_ms <= 0:
            raise ValueError("ready_at_ms must be positive")

        return {
            "run_id": self.server.run_id,
            "scenario_id": self.server.scenario_id,
            "participant_id": participant_id,
            "ready_at_ms": str(ready_at_ms),
            "status": status,
        }

    def read_participant_ready_rows(self) -> list[dict[str, str]]:
        if not ARENA_PARTICIPANT_READY_TSV.exists():
            return []
        text = ARENA_PARTICIPANT_READY_TSV.read_text(encoding="utf-8", errors="replace")
        return self.parse_participant_ready_rows(text)

    def parse_participant_ready_rows(self, text: str) -> list[dict[str, str]]:
        lines = text.splitlines()
        if not lines:
            return []
        header = lines[0].split("\t")
        expected_header = PARTICIPANT_READY_HEADER.strip().split("\t")
        if header != expected_header:
            raise ValueError("participant ready TSV header does not match expected schema")
        rows = []
        for line in lines[1:]:
            if not line.strip():
                continue
            values = line.split("\t")
            if len(values) != len(expected_header):
                raise ValueError("participant ready TSV row has wrong column count")
            row = dict(zip(expected_header, values))
            self.validate_participant_ready_row(row)
            rows.append(row)
        return rows

    def validate_participant_ready_tsv(self, text: str) -> None:
        self.parse_participant_ready_rows(text)

    def validate_participant_ready_row(self, row: dict[str, str]) -> None:
        if row.get("run_id", "") != self.server.run_id:
            raise ValueError("run_id does not match active run")
        if row.get("scenario_id", "") != self.server.scenario_id:
            raise ValueError("scenario_id does not match active scenario")
        if row.get("participant_id", "") not in PARTICIPANTS:
            raise ValueError("participant_id must be player_1 or player_2")
        if int(row.get("ready_at_ms", "0")) <= 0:
            raise ValueError("ready_at_ms must be positive")
        if row.get("status", "") != "ready":
            raise ValueError("status must be ready")

    def participant_ready_rows_to_tsv(self, rows: list[dict[str, str]]) -> str:
        keys = PARTICIPANT_READY_HEADER.strip().split("\t")
        body = PARTICIPANT_READY_HEADER
        for row in rows:
            self.validate_participant_ready_row(row)
            body += "\t".join(row.get(key, "") for key in keys) + "\n"
        return body

    def reset_arena_state(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.apply_reset_config(payload)
        self.server.run_id = new_run_id()
        self.server.started_at_ms = now_ms()
        self.server.reset_requested = True

        for path in (
            ARENA_STATE_TSV,
            ARENA_EVENTS_TSV,
            ARENA_PLAYER_COMMAND_TSV,
            ARENA_PARTICIPANT_COMMAND_TSV,
            ARENA_PARTICIPANT_INTENT_TSV,
            ARENA_PARTICIPANT_READY_TSV,
            ARENA_ENEMY_COMMAND_TSV,
        ):
            try:
                path.unlink()
            except FileNotFoundError:
                pass

        ARENA_PLAYER_COMMAND_TSV.write_text(PLAYER_COMMAND_HEADER, encoding="utf-8")
        ARENA_PARTICIPANT_COMMAND_TSV.write_text(PARTICIPANT_COMMAND_HEADER, encoding="utf-8")
        ARENA_PARTICIPANT_INTENT_TSV.write_text(PARTICIPANT_INTENT_HEADER, encoding="utf-8")
        ARENA_PARTICIPANT_READY_TSV.write_text(PARTICIPANT_READY_HEADER, encoding="utf-8")
        ARENA_ENEMY_COMMAND_TSV.write_text(ENEMY_COMMAND_HEADER, encoding="utf-8")
        write_run_metadata(self.server)

        return {
            "ok": True,
            "run_id": self.server.run_id,
            "scenario_id": self.server.scenario_id,
            "arena_mode": self.server.arena_mode,
            "player_1_model": self.server.player_1_model,
            "player_2_model": self.server.player_2_model,
            "round": self.server.round,
            "seed": self.server.seed,
            "timeout_seconds": self.server.timeout_seconds,
            "reset_requested": True,
        }

    def reset_arena(self) -> None:
        self.write_json(HTTPStatus.OK, self.reset_arena_state(self.read_json_body()))

    def create_duel_session(self) -> None:
        payload = self.read_json_body()
        decision_cadence_ms = int(payload.get("decision_cadence_ms", 750))
        intent_duration_ms = int(payload.get("intent_duration_ms", 3000))
        enforce_tokens = bool(payload.get("enforce_controller_tokens", True))
        reset_payload = self.reset_arena_state(
            {
                **payload,
                "arena_mode": "duel",
                "player_1_model": payload.get("player_1_model", DUEL_DEFAULTS["player_1_model"]),
                "player_2_model": payload.get("player_2_model", DUEL_DEFAULTS["player_2_model"]),
                "round": payload.get("round", DUEL_DEFAULTS["round"]),
                "seed": payload.get("seed", DUEL_DEFAULTS["seed"]),
                "timeout_seconds": payload.get("timeout_seconds", DUEL_DEFAULTS["timeout_seconds"]),
            }
        )
        run_id = str(reset_payload["run_id"])
        run_dir = RESULTS_ROOT / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        controller_tokens = build_controller_tokens(
            run_id,
            str(reset_payload["player_1_model"]),
            str(reset_payload["player_2_model"]),
            enforce_tokens,
        )
        write_controller_tokens(run_dir, controller_tokens)

        player_1_instructions = render_participant_instructions(
            "player_1",
            str(reset_payload["player_1_model"]),
            "player_2",
            controller_tokens["player_1"]["controller_token"],
            enforce_tokens,
            decision_cadence_ms,
            intent_duration_ms,
        )
        player_2_instructions = render_participant_instructions(
            "player_2",
            str(reset_payload["player_2_model"]),
            "player_1",
            controller_tokens["player_2"]["controller_token"],
            enforce_tokens,
            decision_cadence_ms,
            intent_duration_ms,
        )
        player_1_path = run_dir / "player_1_mcp_instructions.md"
        player_2_path = run_dir / "player_2_mcp_instructions.md"
        player_1_path.write_text(player_1_instructions, encoding="utf-8")
        player_2_path.write_text(player_2_instructions, encoding="utf-8")
        (run_dir / "config.json").write_text(
            json.dumps(
                {
                    "runner": "doom_arena_server_duel_session",
                    "run_id": run_id,
                    "scenario_id": reset_payload.get("scenario_id", ""),
                    "arena_mode": "duel",
                    "player_1_model": reset_payload["player_1_model"],
                    "player_2_model": reset_payload["player_2_model"],
                    "round": reset_payload["round"],
                    "seed": reset_payload["seed"],
                    "timeout_seconds": reset_payload["timeout_seconds"],
                    "decision_cadence_ms": decision_cadence_ms,
                    "intent_duration_ms": intent_duration_ms,
                    "control_path": "external MCP clients call HTTP doom-arena tools",
                    "enforce_controller_tokens": enforce_tokens,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        self.write_json(
            HTTPStatus.OK,
            {
                **reset_payload,
                "results_dir": str(run_dir),
                "controller_tokens": str(run_dir / "controller_tokens.json"),
                "player_1_instructions": str(player_1_path),
                "player_2_instructions": str(player_2_path),
                "player_1_prompt": player_1_instructions,
                "player_2_prompt": player_2_instructions,
                "decision_cadence_ms": decision_cadence_ms,
                "intent_duration_ms": intent_duration_ms,
            },
        )

    def read_json_body(self) -> dict[str, Any]:
        body = self.read_body()
        if not body:
            return {}

        content_type = self.headers.get("Content-Type", "")
        if "application/json" not in content_type:
            return {}

        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}

        if isinstance(payload, dict):
            return payload
        return {}

    def apply_reset_config(self, payload: dict[str, Any]) -> None:
        arena_mode = str(payload.get("arena_mode", DEFAULT_ARENA_MODE)).lower()
        if arena_mode not in {"enemies", "duel"}:
            arena_mode = DEFAULT_ARENA_MODE

        self.server.arena_mode = arena_mode
        self.server.scenario_id = str(
            payload.get(
                "scenario_id",
                "duel_e1m8" if arena_mode == "duel" else self.server.args.scenario_id,
            )
        )

        if arena_mode == "duel":
            self.server.player_1_model = str(
                payload.get("player_1_model", DUEL_DEFAULTS["player_1_model"])
            ).lower()
            self.server.player_2_model = str(
                payload.get("player_2_model", DUEL_DEFAULTS["player_2_model"])
            ).lower()
            self.server.round = int(payload.get("round", DUEL_DEFAULTS["round"]))
            self.server.seed = int(payload.get("seed", DUEL_DEFAULTS["seed"]))
            self.server.timeout_seconds = int(
                payload.get("timeout_seconds", DUEL_DEFAULTS["timeout_seconds"])
            )
        else:
            self.server.player_1_model = ""
            self.server.player_2_model = ""
            self.server.round = 1
            self.server.seed = 0
            self.server.timeout_seconds = 300

    def read_reset(self) -> None:
        payload = {
            "ok": True,
            "run_id": self.server.run_id,
            "scenario_id": self.server.scenario_id,
            "arena_mode": self.server.arena_mode,
            "player_1_model": self.server.player_1_model,
            "player_2_model": self.server.player_2_model,
            "round": self.server.round,
            "seed": self.server.seed,
            "timeout_seconds": self.server.timeout_seconds,
            "reset_requested": self.server.reset_requested,
        }
        self.server.reset_requested = False
        self.write_json(HTTPStatus.OK, payload)

    def read_score(self) -> None:
        state = read_arena_state()
        self.write_json(HTTPStatus.OK, score_from_state(state))

    def write_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        message = format % args
        sys.stderr.write(
            "%s - - [%s] %s\n"
            % (self.address_string(), self.log_date_time_string(), message)
        )

    def read_mcp_config(self) -> None:
        self.write_json(HTTPStatus.OK, mcp_config_payload(self.server.args.host, self.server.args.port))


def read_arena_state() -> list[dict[str, str]]:
    if not ARENA_STATE_TSV.exists():
        return []

    rows = ARENA_STATE_TSV.read_text(encoding="utf-8", errors="replace").splitlines()
    if not rows:
        return []

    header = rows[0].split("\t")
    parsed = []
    for line in rows[1:]:
        if not line.strip():
            continue
        values = line.split("\t")
        parsed.append(dict(zip(header, values)))
    return parsed


def score_from_state(rows: list[dict[str, str]]) -> dict[str, Any]:
    match = next((row for row in rows if row.get("kind") == "match"), {})
    participants = [row for row in rows if row.get("kind") == "participant"]
    if match or participants:
        player_1 = next((row for row in participants if row.get("entity_id") == "player_1"), {})
        player_2 = next((row for row in participants if row.get("entity_id") == "player_2"), {})
        phase = match.get("phase") or player_1.get("phase") or "combat"
        winner = match.get("winner") or player_1.get("winner") or ""
        return {
            "ok": True,
            "mode": "duel",
            "phase": phase,
            "winner": winner or ("running" if phase != "finished" else "draw"),
            "terminal_reason": match.get("terminal_reason") or player_1.get("terminal_reason") or "",
            "elapsed_time_seconds": float(match.get("elapsed_time_seconds") or player_1.get("elapsed_time_seconds") or 0),
            "timeout_seconds": int(match.get("timeout_seconds") or player_1.get("timeout_seconds") or 120),
            "player_1_health": int(player_1.get("health", "0") or 0),
            "player_2_health": int(player_2.get("health", "0") or 0),
            "player_1_alive": player_1.get("alive", "0") == "1",
            "player_2_alive": player_2.get("alive", "0") == "1",
            "player_1_damage_dealt": int(player_1.get("damage_dealt", "0") or 0),
            "player_2_damage_dealt": int(player_2.get("damage_dealt", "0") or 0),
            "player_1_shots_fired": int(player_1.get("shots_fired", "0") or 0),
            "player_2_shots_fired": int(player_2.get("shots_fired", "0") or 0),
            "player_1_shots_hit": int(player_1.get("shots_hit", "0") or 0),
            "player_2_shots_hit": int(player_2.get("shots_hit", "0") or 0),
        }

    player = next((row for row in rows if row.get("kind") == "player"), {})
    enemies = [row for row in rows if row.get("kind") == "enemy"]
    player_alive = player.get("alive", "0") == "1"
    enemies_alive = sum(1 for row in enemies if row.get("alive", "0") == "1")
    enemies_total = len(enemies)

    winner = "running"
    if player and not player_alive:
        winner = "enemy"
    elif enemies_total > 0 and enemies_alive == 0 and player_alive:
        winner = "player"

    return {
        "ok": True,
        "winner": winner,
        "player_health": int(player.get("health", "0") or 0),
        "player_alive": player_alive,
        "enemies_total": enemies_total,
        "enemies_alive": enemies_alive,
        "enemies_killed": max(0, enemies_total - enemies_alive),
    }


def write_run_metadata(server: DoomArenaServer) -> None:
    row = [
        server.run_id,
        server.scenario_id,
        server.arena_mode,
        str(server.started_at_ms),
        server.player_1_model,
        server.player_2_model,
        str(server.round),
        str(server.seed),
        str(server.timeout_seconds),
    ]
    ARENA_RUN_METADATA_TSV.write_text(
        RUN_METADATA_HEADER + "\t".join(row) + "\n",
        encoding="utf-8",
    )


def mcp_config_payload(host: str, port: int) -> dict[str, Any]:
    server_url = f"http://{host}:{port}"
    return {
        "ok": True,
        "transport": "http",
        "server_url": server_url,
        "mcp_url": f"{server_url}/mcp",
        "claude": f"claude mcp add --transport http doom-arena {server_url}/mcp",
        "codex_config": f'url = "{server_url}/mcp"',
        "note": (
            "Doom Arena also supports stdio via scripts\\doom_arena_mcp.py, but HTTP MCP "
            "is preferred on native Windows to avoid stdio pipe issues."
        ),
    }


def print_mcp_help(host: str, port: int) -> None:
    config = mcp_config_payload(host, port)
    print("MCP endpoint for Codex/Claude:")
    print(f"  {config['mcp_url']}")
    print("MCP config endpoint:")
    print(f"  {config['server_url']}/api/arena/mcp-config")
    print("Note: HTTP MCP is preferred on native Windows; stdio remains available for debugging.")


def main() -> int:
    args = parse_args()
    server = DoomArenaServer((args.host, args.port), DoomArenaHandler, args)
    url = f"http://{args.host}:{args.port}/"

    print(f"Serving Doom Agent Arena from {SRC_DIR}")
    print(f"Open {url}")
    print(f"Run id: {server.run_id}")
    print(f"Scenario id: {server.scenario_id}")
    print(f"Arena mode: {server.arena_mode}")
    if not args.quiet_mcp_help:
        print_mcp_help(args.host, args.port)
    write_run_metadata(server)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.server_close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
