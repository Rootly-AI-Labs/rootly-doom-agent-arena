#!/usr/bin/env python3
"""Local Doom Agent Arena server.

Serves the Doom WASM files from src/ and stores local arena TSV control files.
All endpoints are local-only by default.
"""

from __future__ import annotations

import argparse
import copy
import html
import json
import random
import shutil
import sys
import threading
import time
import uuid
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from doom_arena_duel_prompts import (
    RESULTS_ROOT,
    build_controller_tokens,
    instructions as render_participant_instructions,
    write_controller_tokens,
)
from doom_arena_mcp import DoomArenaClient, DoomArenaError, call_tool, tool_definitions
from doom_arena_strategy import (
    CONTROL_MODE_HIERARCHICAL,
    PLAN_METADATA_FIELDS,
    PLAN_ROUTE_MAX_WAYPOINTS,
    STRATEGY_METADATA_FIELDS,
    normalize_control_mode,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
MAP_BLUEPRINTS_DIR = REPO_ROOT / "scripts" / "map_blueprints"

ARENA_STATE_TSV = SRC_DIR / "arena_game_state.local.tsv"
ARENA_EVENTS_TSV = SRC_DIR / "arena_duel_events.local.tsv"
ARENA_PLAYER_COMMAND_TSV = SRC_DIR / "arena_player_command.local.tsv"
ARENA_PARTICIPANT_COMMAND_TSV = SRC_DIR / "arena_participant_commands.local.tsv"
ARENA_PARTICIPANT_INTENT_TSV = SRC_DIR / "arena_participant_intents.local.tsv"
ARENA_PARTICIPANT_READY_TSV = SRC_DIR / "arena_participant_ready.local.tsv"
ARENA_ENEMY_COMMAND_TSV = SRC_DIR / "arena_enemy_commands.local.tsv"
ARENA_RUN_METADATA_TSV = SRC_DIR / "arena_run_metadata.local.tsv"
MCP_PRESENCE_STALE_AFTER_MS = 25000

DEFAULT_SCENARIO_ID = "e1m8_arena"
DEFAULT_ARENA_MODE = "enemies"
DUEL_DEFAULTS = {
    "arena_mode": "duel",
    "player_1_model": "",
    "player_2_model": "",
    "round": 1,
    "seed": 42,
    "timeout_seconds": 120,
}

# Scenarios available to the duel arena. Each scenario maps to a configured
# spawn variant inside the C engine (see src/doom/p_mobj.c and
# src/doom/arena_duel.c). After editing the C side, rebuild WASM via
# docs/build.md before adding entries here.
DUEL_SCENARIOS = [
    {
        "scenario_id": "duel_e1m8",
        "label": "Custom room open sight spawn",
        "requires_wasm_rebuild": False,
    },
    {
        "scenario_id": "duel_e1m8_blind_spawn",
        "label": "Custom room blind spawn",
        "requires_wasm_rebuild": False,
    },
    {
        "scenario_id": "duel_e1m8_corner_spawn",
        "label": "Custom room corner spawn",
        "requires_wasm_rebuild": False,
    },
]
DUEL_SCENARIO_IDS = {entry["scenario_id"] for entry in DUEL_SCENARIOS}
DUEL_ACTIVE_SCENARIO_IDS = {
    entry["scenario_id"]
    for entry in DUEL_SCENARIOS
    if not entry["requires_wasm_rebuild"]
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
PARTICIPANT_INTENT_PREVIOUS_HEADER = (
    "run_id\tscenario_id\tintent_id\tissued_at_ms\texpires_at_ms\t"
    "participant_id\tintent\tstyle\ttarget_id\tpreferred_distance\taggression\tduration_ms\t"
    "strafe_direction\tmovement_bias\tfire_policy\tdistance_policy\treplan_if\tsequence_number\tdecision_cadence_ms\n"
)
PARTICIPANT_INTENT_EXTENDED_PREVIOUS_HEADER = (
    "run_id\tscenario_id\tintent_id\tissued_at_ms\texpires_at_ms\t"
    "participant_id\tintent\tstyle\ttarget_id\tpreferred_distance\taggression\tduration_ms\t"
    "strafe_direction\tmovement_bias\tfire_policy\tdistance_policy\treplan_if\tsequence_number\tdecision_cadence_ms\t"
    "aim_tolerance\tfire_burst_ms\tmin_fire_alignment\tmin_distance\tmax_distance\t"
    "retreat_if_closer_than\tpush_if_farther_than\tlos_lost_action\tstuck_recovery_strategy\tmovement_primitive\n"
)
PARTICIPANT_INTENT_HEADER = (
    "run_id\tscenario_id\tintent_id\tissued_at_ms\texpires_at_ms\t"
    "participant_id\tintent\tstyle\ttarget_id\tpreferred_distance\taggression\tduration_ms\t"
    "strafe_direction\tmovement_bias\tfire_policy\tdistance_policy\treplan_if\tsequence_number\tdecision_cadence_ms\t"
    "aim_tolerance\tfire_burst_ms\tmin_fire_alignment\tmin_distance\tmax_distance\t"
    "retreat_if_closer_than\tpush_if_farther_than\tlos_lost_action\tstuck_recovery_strategy\tmovement_primitive\t"
    "turn_policy\tnavigation_target\tfire_mode\tintent_raw\t"
    "strategy_source\tstrategy_category\tstrategy_action\tstrategy_intensity\tstrategy_commit_ms\tstrategy_objective\tstrategy_target_zone\tstrategy_reasoning\t"
    "plan_objective\tplan_route\tplan_engagement_policy\tplan_reasoning\tplan_route_cells\n"
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
ALLOWED_STRAFE_DIRECTIONS = {"left", "right", "alternate", "auto", "hold_direction", "switch_if_hit"}
ALLOWED_MOVEMENT_BIASES = {"direct", "circle", "evasive", "cautious"}
ALLOWED_FIRE_POLICIES = {"hold_fire", "only_when_aligned", "burst_when_aligned", "suppressive"}
ALLOWED_DISTANCE_POLICIES = {"close", "maintain", "kite"}
ALLOWED_REPLAN_TRIGGERS = {"lost_los", "stuck", "low_health", "target_far", "target_close"}
ALLOWED_LOS_LOST_ACTIONS = {"turn_left", "turn_right", "advance_last_seen", "hold_angle", "sweep"}
ALLOWED_STUCK_RECOVERY_STRATEGIES = {"back_up", "turn_left", "turn_right", "strafe_out", "default"}
ALLOWED_MOVEMENT_PRIMITIVES = {
    "advance",
    "retreat",
    "strafe_left",
    "strafe_right",
    "circle_left",
    "circle_right",
    "hold_position",
}
ALLOWED_TURN_POLICIES = {"auto", "turn_to_enemy", "sweep_left", "sweep_right", "hold_angle", "face_last_seen"}
ALLOWED_NAVIGATION_TARGETS = {"none", "opponent", "last_seen_enemy", "center", "left_lane", "right_lane", "keep_distance"}
ALLOWED_FIRE_MODES = {"auto", "hold_fire", "fire_when_aligned", "single_shot", "burst", "suppressive"}
ALLOWED_PLAN_ENGAGEMENT_POLICIES = {"", "engage_if_visible", "avoid_until_target", "hold_fire", "force_fight"}
PARTICIPANT_INTENT_EXTRA_FIELDS = (
    "aim_tolerance",
    "fire_burst_ms",
    "min_fire_alignment",
    "min_distance",
    "max_distance",
    "retreat_if_closer_than",
    "push_if_farther_than",
    "los_lost_action",
    "stuck_recovery_strategy",
    "movement_primitive",
    "turn_policy",
    "navigation_target",
    "fire_mode",
)
PARTICIPANT_INTENT_STRATEGY_FIELDS = STRATEGY_METADATA_FIELDS
PARTICIPANT_INTENT_PLAN_FIELDS = PLAN_METADATA_FIELDS


def normalize_plan_route_field(value: Any) -> str:
    text = str(value or "").replace("\t", " ").strip()
    if not text:
        return ""
    points = []
    for part in text.split(";"):
        item = part.strip()
        if not item:
            continue
        pieces = [piece.strip() for piece in item.split(",")]
        if len(pieces) != 2:
            raise ValueError("plan_route must use x,y;x,y format")
        x = int(pieces[0])
        y = int(pieces[1])
        if x < -1024 or x > 1024 or y < -768 or y > 768:
            raise ValueError("plan_route waypoint is outside map bounds")
        points.append(f"{x},{y}")
    if len(points) > PLAN_ROUTE_MAX_WAYPOINTS:
        raise ValueError(f"plan_route can include at most {PLAN_ROUTE_MAX_WAYPOINTS} waypoints")
    return ";".join(points)


def normalize_plan_engagement_policy(value: Any) -> str:
    text = str(value or "").replace("\t", " ").strip().lower()
    if text not in ALLOWED_PLAN_ENGAGEMENT_POLICIES:
        raise ValueError(
            "plan_engagement_policy must be one of "
            + ", ".join(sorted(policy for policy in ALLOWED_PLAN_ENGAGEMENT_POLICIES if policy))
        )
    return text


def route_cells_text_for_stats(route: Any) -> str:
    try:
        if isinstance(route, str):
            return ";".join(part.strip().upper() for part in route.replace(",", ";").split(";") if part.strip())[:80]
        if isinstance(route, list):
            cells = []
            for item in route:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    cells.append(f"{str(item[0]).strip().upper()}{int(item[1]):02d}")
                else:
                    cells.append(str(item).strip().upper())
            return ";".join(cell for cell in cells if cell)[:80]
    except (TypeError, ValueError):
        pass
    return str(route or "").replace("\t", " ").strip()[:80]


def mcp_plan_argument_fields(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if tool_name != "set_participant_plan":
        return {}
    return {
        "plan_objective": str(arguments.get("objective", "")).replace("\t", " ").strip()[:64],
        "plan_route_cells": route_cells_text_for_stats(arguments.get("route", "")),
        "plan_engagement_policy": str(arguments.get("engagement_policy", "")).replace("\t", " ").strip()[:32],
        "plan_reasoning": " ".join(str(arguments.get("reasoning", "")).replace("\t", " ").split())[:160],
    }


def now_ms() -> int:
    return int(time.time() * 1000)


def new_run_id() -> str:
    return "run_" + uuid.uuid4().hex[:12]


def new_duel_session_id() -> str:
    return "session_" + uuid.uuid4().hex[:12]


def clamp_int(value: Any, low: int, high: int) -> int:
    return max(low, min(high, int(value)))


def normalize_optional_enum(
    value: Any,
    default: str,
    allowed: set[str],
    field_name: str,
    *,
    allow_blank: bool = False,
) -> str:
    normalized = str(value if value is not None else default).strip().lower()
    if normalized == "":
        if allow_blank:
            return ""
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


def normalize_optional_int(
    value: Any,
    field_name: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> str:
    if value is None or value == "":
        return ""
    parsed = int(value)
    if minimum is not None and parsed < minimum:
        raise ValueError(f"{field_name} must be >= {minimum}")
    if maximum is not None and parsed > maximum:
        raise ValueError(f"{field_name} must be <= {maximum}")
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
        self.stats_lock = threading.Lock()
        self.mcp_call_counter = 0
        self.mcp_calls: list[dict[str, Any]] = []
        self.active_mcp_calls: dict[str, dict[str, Any]] = {}
        self.mcp_presence: dict[str, dict[str, Any]] = {}
        self.mcp_presence_counter = 0
        self.participant_ready_agents: dict[str, str] = {}
        self.intent_records: list[dict[str, Any]] = []
        self.latest_intent_by_participant: dict[str, dict[str, Any]] = {}
        self.summary_written_runs: set[str] = set()
        self.run_results_dirs: dict[str, Path] = {self.run_id: RESULTS_ROOT / self.run_id}
        self.current_run_results_dir: Path = self.run_results_dirs[self.run_id]
        self.duel_session_id = ""
        self.duel_total_rounds = 1
        self.duel_current_round = 0
        self.duel_controller_tokens: dict[str, Any] = {}
        self.duel_player_1_prompt = ""
        self.duel_player_2_prompt = ""
        self.hide_enemy_position = False
        self.rationale_count = 0
        self.token_usage: dict[str, dict[str, int]] = {}
        self.duel_randomize_spawns = False
        self.duel_scenario_pool: list[str] = []
        self.duel_scenario_history: list[str] = []
        self.enable_cross_round_recap = False
        self.recap_window = 2
        self.enable_map_blueprint = False
        self.enable_weapon_pickups = True
        self.mirror_pair = False
        self.control_mode = CONTROL_MODE_HIERARCHICAL


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

        if path == "/api/arena/mcp-presence":
            self.write_mcp_presence()
            return

        if path == "/api/arena/mcp-call-telemetry":
            self.write_mcp_call_telemetry()
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
            try:
                self.create_duel_session()
            except Exception as exc:
                self.log_error("duel session creation failed: %s: %s", exc.__class__.__name__, exc)
                self.write_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {
                        "ok": False,
                        "error": f"failed to create duel session: {exc.__class__.__name__}: {exc}",
                    },
                )
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
            self.read_arena_state_with_config()
            return

        if path == "/api/arena/health":
            self.read_health()
            return

        if path == "/api/arena/player-command":
            self.read_file(ARENA_PLAYER_COMMAND_TSV, "arena_player_command.local.tsv")
            return

        if path == "/api/arena/participant-commands":
            self.read_file(ARENA_PARTICIPANT_COMMAND_TSV, "arena_participant_commands.local.tsv")
            return

        if path == "/api/arena/participant-intents":
            body = self.participant_intent_rows_to_tsv(self.current_run_participant_intent_rows())
            self.write_tsv(body)
            return

        if path == "/api/arena/participant-ready":
            self.read_file(ARENA_PARTICIPANT_READY_TSV, "arena_participant_ready.local.tsv")
            return

        if path == "/api/arena/mcp-presence":
            self.read_mcp_presence()
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

        if path == "/api/arena/run-stats":
            self.read_run_artifact("stats.json")
            return

        if path == "/api/arena/run-summary":
            self.read_run_artifact("summary.json")
            return

        if path == "/api/arena/run-results":
            self.read_run_results_page()
            return

        if path == "/api/arena/duel-session-results":
            self.read_duel_session_results()
            return

        if path == "/api/arena/previous-rounds-recap":
            self.read_previous_rounds_recap()
            return

        if path == "/api/arena/map-blueprint":
            self.read_map_blueprint()
            return

        if path == "/api/arena/run-instructions":
            self.read_run_instructions()
            return

        if path == "/api/arena/mcp-config":
            self.read_mcp_config()
            return

        super().do_GET()

    def read_body(self) -> bytes:
        length_header = self.headers.get("Content-Length")
        length = int(length_header or "0")
        return self.rfile.read(length)

    def read_health(self) -> None:
        self.write_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "run_id": self.server.run_id,
                "scenario_id": self.server.scenario_id,
                "arena_mode": self.server.arena_mode,
                "started_at_ms": self.server.started_at_ms,
            },
        )

    def write_mcp_presence(self) -> None:
        payload = self.read_json_body()
        record = self.record_mcp_presence(payload)
        self.write_json(HTTPStatus.OK, {"ok": True, "client": record})

    def record_mcp_presence(self, payload: dict[str, Any]) -> dict[str, Any]:
        client_name = str(payload.get("client_name", "")).strip()
        client_version = str(payload.get("client_version", "")).strip()
        client_id = str(payload.get("client_id", "")).strip()
        now = now_ms()

        if not client_name:
            client_name = "unknown MCP client"
        if not client_id:
            client_id = client_name.lower()

        record = {
            "client_id": client_id,
            "client_name": client_name,
            "client_version": client_version,
            "source_addr": str(payload.get("source_addr", "")),
            "connected_at_ms": int(payload.get("connected_at_ms", now)),
            "last_seen_at_ms": now,
            "status": "connected",
        }

        with self.server.stats_lock:
            existing = self.server.mcp_presence.get(client_id)
            if existing:
                record["connected_at_ms"] = int(existing.get("connected_at_ms", record["connected_at_ms"]))
            self.server.mcp_presence[client_id] = record

        return record

    def current_http_mcp_client_id(self) -> str:
        session_id = self.headers.get("Mcp-Session-Id") or self.headers.get("mcp-session-id")
        if session_id:
            return f"http:{session_id}"
        return f"http:{self.client_address[0]}"

    def new_http_mcp_client_id(self) -> str:
        session_id = self.headers.get("Mcp-Session-Id") or self.headers.get("mcp-session-id")
        if session_id:
            return f"http:{session_id}"
        with self.server.stats_lock:
            self.server.mcp_presence_counter += 1
            counter = self.server.mcp_presence_counter
        return f"http:{self.client_address[0]}:{counter:04d}"

    def current_http_mcp_presence(self) -> dict[str, Any]:
        client_id = self.current_http_mcp_client_id()
        with self.server.stats_lock:
            exact = self.server.mcp_presence.get(client_id)
            if exact:
                return copy.deepcopy(exact)
            same_source = [
                client for client in self.server.mcp_presence.values()
                if client.get("source_addr") == self.client_address[0]
            ]
            if not same_source:
                return {}
            same_source.sort(key=lambda client: int(client.get("last_seen_at_ms", 0)), reverse=True)
            return copy.deepcopy(same_source[0])

    def touch_http_mcp_presence(self) -> None:
        client_id = self.current_http_mcp_client_id()
        now = now_ms()
        with self.server.stats_lock:
            exact = self.server.mcp_presence.get(client_id)
            if exact:
                exact["last_seen_at_ms"] = now
                return
            same_source = [
                client for client in self.server.mcp_presence.values()
                if client.get("source_addr") == self.client_address[0]
            ]
            if not same_source:
                return
            same_source.sort(key=lambda client: int(client.get("last_seen_at_ms", 0)), reverse=True)
            same_source[0]["last_seen_at_ms"] = now

    def remove_http_mcp_presence(self) -> None:
        client_id = self.current_http_mcp_client_id()
        with self.server.stats_lock:
            if client_id in self.server.mcp_presence:
                self.server.mcp_presence.pop(client_id, None)
                return
            same_source = [
                client_id
                for client_id, client in self.server.mcp_presence.items()
                if client.get("source_addr") == self.client_address[0]
            ]
            if same_source:
                same_source.sort(
                    key=lambda selected_id: int(
                        self.server.mcp_presence.get(selected_id, {}).get("last_seen_at_ms", 0)
                    ),
                    reverse=True,
                )
                self.server.mcp_presence.pop(same_source[0], None)

    def read_mcp_presence(self) -> None:
        cutoff_ms = now_ms() - MCP_PRESENCE_STALE_AFTER_MS
        with self.server.stats_lock:
            self.server.mcp_presence = {
                client_id: client
                for client_id, client in self.server.mcp_presence.items()
                if int(client.get("last_seen_at_ms", 0)) >= cutoff_ms
            }
            clients = sorted(
                (copy.deepcopy(client) for client in self.server.mcp_presence.values()),
                key=lambda client: (
                    str(client.get("client_name", "")).lower(),
                    int(client.get("connected_at_ms", 0)),
                ),
            )
            ready_agents = copy.deepcopy(self.server.participant_ready_agents)

        self.write_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "clients": clients,
                "ready_agents": ready_agents,
            },
        )

    def run_dir(self, run_id: str | None = None) -> Path:
        selected_run_id = run_id or self.server.run_id
        mapped = self.server.run_results_dirs.get(selected_run_id)
        if mapped is not None:
            return mapped
        if run_id is None and self.server.current_run_results_dir:
            return self.server.current_run_results_dir
        return RESULTS_ROOT / selected_run_id

    def set_run_results_dir(self, run_id: str, target_dir: Path) -> None:
        target_dir.mkdir(parents=True, exist_ok=True)
        legacy_dir = RESULTS_ROOT / run_id
        if legacy_dir.exists() and legacy_dir != target_dir:
            for child in legacy_dir.iterdir():
                destination = target_dir / child.name
                if destination.exists():
                    if destination.is_dir():
                        shutil.rmtree(destination)
                    else:
                        destination.unlink()
                shutil.move(str(child), str(destination))
            try:
                legacy_dir.rmdir()
            except OSError:
                pass
        self.server.run_results_dirs[run_id] = target_dir
        if run_id == self.server.run_id:
            self.server.current_run_results_dir = target_dir

    def reset_mcp_stats(self) -> None:
        with self.server.stats_lock:
            self.server.mcp_call_counter = 0
            self.server.mcp_calls = []
            self.server.active_mcp_calls = {}
            self.server.participant_ready_agents = {}
            self.server.intent_records = []
            self.server.latest_intent_by_participant = {}
            self.server.rationale_count = 0
            self.server.token_usage = {}
            self.write_mcp_stats_locked()

    def start_mcp_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        message_id: Any,
    ) -> dict[str, Any]:
        started_at = now_ms()
        participant_id = str(arguments.get("participant_id", ""))
        try:
            request_chars = len(json.dumps(arguments, default=str))
        except (TypeError, ValueError):
            request_chars = 0
        with self.server.stats_lock:
            self.server.mcp_call_counter += 1
            call_id = f"mcp_call_{self.server.mcp_call_counter:06d}"
            record = {
                "call_id": call_id,
                "request_index": self.server.mcp_call_counter,
                "run_id": self.server.run_id,
                "scenario_id": self.server.scenario_id,
                "jsonrpc_id": message_id,
                "tool_name": tool_name,
                "participant_id": participant_id,
                "started_at_ms": started_at,
                "completed_at_ms": None,
                "latency_ms": None,
                "status": "in_flight",
                "is_error": False,
                "overlapped_by_later_call": False,
                "overlapped_by_call_id": "",
                "overlapped_at_ms": None,
                "request_chars": request_chars,
                "response_chars": 0,
            }
            record.update(mcp_plan_argument_fields(tool_name, arguments))
            if participant_id:
                self.record_token_chars_locked(participant_id, request_chars, 0)
            for active in self.server.active_mcp_calls.values():
                same_participant = (
                    participant_id
                    and active.get("participant_id") == participant_id
                    and active.get("run_id") == self.server.run_id
                )
                if same_participant:
                    active["overlapped_by_later_call"] = True
                    active["overlapped_by_call_id"] = call_id
                    active["overlapped_at_ms"] = started_at
            self.server.active_mcp_calls[call_id] = record
            return record

    def complete_mcp_tool_call(self, record: dict[str, Any], is_error: bool, text: str) -> None:
        completed_at = now_ms()
        response_chars = len(text) if isinstance(text, str) else 0
        with self.server.stats_lock:
            record["completed_at_ms"] = completed_at
            record["latency_ms"] = completed_at - int(record["started_at_ms"])
            record["status"] = "error" if is_error else "completed"
            record["is_error"] = bool(is_error)
            record["response_chars"] = response_chars
            if is_error:
                record["error"] = text[:500]
            else:
                self.attach_mcp_result_summary_locked(record, text)
            participant_id = str(record.get("participant_id", ""))
            if participant_id:
                self.record_token_chars_locked(participant_id, 0, response_chars)
            self.server.active_mcp_calls.pop(str(record["call_id"]), None)
            self.server.mcp_calls.append(record)
            if not is_error and record.get("tool_name") in {"set_participant_intent", "set_participant_strategy", "set_participant_plan"}:
                self.record_intent_lifecycle_locked(record, text)
            self.write_mcp_stats_locked()

    def record_token_chars_locked(self, participant_id: str, request_chars: int, response_chars: int) -> None:
        bucket = self.server.token_usage.setdefault(
            participant_id,
            {
                "request_chars": 0,
                "response_chars": 0,
                "request_tokens_estimated": 0,
                "response_tokens_estimated": 0,
                "total_tokens_estimated": 0,
                "tool_calls": 0,
            },
        )
        bucket["request_chars"] += int(request_chars)
        bucket["response_chars"] += int(response_chars)
        bucket["request_tokens_estimated"] = bucket["request_chars"] // 4
        bucket["response_tokens_estimated"] = bucket["response_chars"] // 4
        bucket["total_tokens_estimated"] = (
            bucket["request_tokens_estimated"] + bucket["response_tokens_estimated"]
        )
        if request_chars > 0:
            bucket["tool_calls"] += 1

    def attach_mcp_result_summary_locked(self, record: dict[str, Any], text: str) -> None:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return
        if not isinstance(payload, dict):
            return
        self.attach_mcp_result_payload_summary_locked(record, payload)

    def attach_mcp_result_payload_summary_locked(self, record: dict[str, Any], payload: dict[str, Any]) -> None:
        for key in ("accepted", "ready", "cleared", "started", "phase", "run_id", "intent_id", "issued_at_ms", "expires_at_ms"):
            if key in payload:
                record[key] = payload[key]
        normalized = payload.get("normalized_intent")
        if isinstance(normalized, dict):
            for key in (
                "intent",
                "intent_raw",
                "style",
                "target_id",
                "duration_ms",
                "sequence_number",
                "decision_cadence_ms",
                "strafe_direction",
                "movement_bias",
                "fire_policy",
                "distance_policy",
                *PARTICIPANT_INTENT_EXTRA_FIELDS,
                *PARTICIPANT_INTENT_STRATEGY_FIELDS,
                *PARTICIPANT_INTENT_PLAN_FIELDS,
            ):
                if key in normalized:
                    record[key] = normalized[key]

    def normalize_remote_mcp_call(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.server.mcp_call_counter += 1
        request_index = self.server.mcp_call_counter
        started_at = int(payload.get("started_at_ms") or now_ms())
        completed_at = int(payload.get("completed_at_ms") or started_at)
        is_error = bool(payload.get("is_error", False))
        participant_id = str(payload.get("participant_id", ""))
        if participant_id and participant_id not in PARTICIPANTS:
            participant_id = ""

        record = {
            "call_id": str(payload.get("call_id") or f"external_mcp_call_{request_index:06d}"),
            "request_index": request_index,
            "run_id": str(payload.get("run_id") or self.server.run_id),
            "scenario_id": str(payload.get("scenario_id") or self.server.scenario_id),
            "jsonrpc_id": payload.get("jsonrpc_id"),
            "tool_name": str(payload.get("tool_name") or "unknown"),
            "participant_id": participant_id,
            "started_at_ms": started_at,
            "completed_at_ms": completed_at,
            "latency_ms": max(0, completed_at - started_at),
            "status": "error" if is_error else "completed",
            "is_error": is_error,
            "overlapped_by_later_call": bool(payload.get("overlapped_by_later_call", False)),
            "overlapped_by_call_id": str(payload.get("overlapped_by_call_id", "")),
            "overlapped_at_ms": payload.get("overlapped_at_ms"),
            "source": "external_mcp_telemetry",
            **({"error": str(payload.get("error", ""))[:500]} if is_error else {}),
        }
        for key in PARTICIPANT_INTENT_PLAN_FIELDS:
            if key in payload:
                record[key] = payload[key]
        return record

    def record_intent_lifecycle_locked(self, call_record: dict[str, Any], text: str) -> None:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return
        if not isinstance(payload, dict) or not payload.get("accepted"):
            return
        normalized = payload.get("normalized_intent")
        if not isinstance(normalized, dict):
            return
        self.record_intent_payload_locked(payload, normalized, "mcp_tool", call_record)

    def record_participant_intent_row_locked(self, row: dict[str, str]) -> None:
        normalized = {
            "participant_id": row.get("participant_id", ""),
            "intent": row.get("intent", ""),
            "intent_raw": row.get("intent_raw", row.get("intent", "")),
            "style": row.get("style", ""),
            "target_id": row.get("target_id", ""),
            "preferred_distance": row.get("preferred_distance"),
            "aggression": row.get("aggression"),
            "duration_ms": row.get("duration_ms"),
            "strafe_direction": row.get("strafe_direction", ""),
            "movement_bias": row.get("movement_bias", ""),
            "fire_policy": row.get("fire_policy", ""),
            "distance_policy": row.get("distance_policy", ""),
            "replan_if": [
                item.strip()
                for item in str(row.get("replan_if", "")).split(",")
                if item.strip()
            ],
            "sequence_number": row.get("sequence_number") or None,
            "decision_cadence_ms": row.get("decision_cadence_ms") or None,
        }
        for key in PARTICIPANT_INTENT_EXTRA_FIELDS:
            normalized[key] = row.get(key, "")
        for key in PARTICIPANT_INTENT_STRATEGY_FIELDS:
            normalized[key] = row.get(key, "")
        for key in PARTICIPANT_INTENT_PLAN_FIELDS:
            normalized[key] = row.get(key, "")
        payload = {
            "accepted": True,
            "participant_id": row.get("participant_id", ""),
            "intent_id": row.get("intent_id", ""),
            "run_id": row.get("run_id", self.server.run_id),
            "scenario_id": row.get("scenario_id", self.server.scenario_id),
            "issued_at_ms": row.get("issued_at_ms", ""),
            "expires_at_ms": row.get("expires_at_ms", ""),
            "normalized_intent": normalized,
        }
        self.record_intent_payload_locked(payload, normalized, "participant_intents_api", None)

    def extract_rationale_record(
        self,
        raw: dict[str, Any] | None,
        normalized_row: dict[str, str],
    ) -> dict[str, Any] | None:
        if not isinstance(raw, dict):
            return None
        rationale_raw = raw.get("rationale")
        if rationale_raw is None:
            return None
        text = str(rationale_raw).strip()
        if not text:
            return None
        if len(text) > 1024:
            text = text[:1024]
        return {
            "ts_ms": now_ms(),
            "run_id": normalized_row.get("run_id", self.server.run_id),
            "scenario_id": normalized_row.get("scenario_id", self.server.scenario_id),
            "intent_id": normalized_row.get("intent_id", ""),
            "participant_id": normalized_row.get("participant_id", ""),
            "intent": normalized_row.get("intent", ""),
            "style": normalized_row.get("style", ""),
            "sequence_number": normalized_row.get("sequence_number") or None,
            "rationale": text,
        }

    def append_rationale_records(self, records: list[dict[str, Any]]) -> None:
        if not records:
            return
        try:
            run_dir = self.run_dir()
            run_dir.mkdir(parents=True, exist_ok=True)
            target = run_dir / "rationales.jsonl"
            with target.open("a", encoding="utf-8") as handle:
                for record in records:
                    handle.write(json.dumps(record, sort_keys=True) + "\n")
        except OSError:
            pass
        with self.server.stats_lock:
            self.server.rationale_count = getattr(self.server, "rationale_count", 0) + len(records)

    def build_previous_rounds_recap(
        self,
        participant_id: str,
        current_round: int,
        duel_session_id: str,
        window: int = 2,
    ) -> list[dict[str, Any]]:
        if not duel_session_id or current_round <= 1:
            return []
        session_dir = RESULTS_ROOT / duel_session_id
        if not session_dir.exists():
            return []
        recap_rounds: list[dict[str, Any]] = []
        for round_dir in sorted(session_dir.glob("round_*")):
            if not round_dir.is_dir():
                continue
            try:
                round_num = int(round_dir.name.split("_")[1])
            except (IndexError, ValueError):
                continue
            if round_num >= current_round:
                continue
            recap_rounds.append((round_num, round_dir))
        recap_rounds.sort(key=lambda t: t[0], reverse=True)
        if window > 0:
            recap_rounds = recap_rounds[:window]
        recap_rounds.sort(key=lambda t: t[0])
        result: list[dict[str, Any]] = []
        for round_num, round_dir in recap_rounds:
            summary_path = round_dir / "summary.json"
            stats_path = round_dir / "stats.json"
            entry: dict[str, Any] = {
                "round": round_num,
                "winner": None,
                "terminal_reason": None,
                "elapsed_time_seconds": None,
                "your_final_health": None,
                "opponent_final_health": None,
                "your_damage_dealt": None,
                "opponent_damage_dealt": None,
                "your_hit_rate": None,
                "opponent_prevailing_intent": None,
                "spawn_variant": None,
            }
            if summary_path.exists():
                try:
                    s = json.loads(summary_path.read_text(encoding="utf-8"))
                    entry["winner"] = s.get("winner")
                    entry["terminal_reason"] = s.get("terminal_reason")
                    entry["elapsed_time_seconds"] = s.get("elapsed_time_seconds")
                    entry["spawn_variant"] = s.get("scenario_id")
                    if participant_id == "player_1":
                        entry["your_final_health"] = s.get("player_1_health_end")
                        entry["opponent_final_health"] = s.get("player_2_health_end")
                        entry["your_damage_dealt"] = s.get("player_1_damage_dealt")
                        shots_f = s.get("player_1_shots_fired") or 0
                        shots_h = s.get("player_1_shots_hit") or 0
                    else:
                        entry["your_final_health"] = s.get("player_2_health_end")
                        entry["opponent_final_health"] = s.get("player_1_health_end")
                        entry["your_damage_dealt"] = s.get("player_2_damage_dealt")
                        shots_f = s.get("player_2_shots_fired") or 0
                        shots_h = s.get("player_2_shots_hit") or 0
                    entry["your_hit_rate"] = (
                        round(shots_h / shots_f, 3) if shots_f > 0 else 0.0
                    )
                except (OSError, KeyError, ValueError, json.JSONDecodeError):
                    pass
            if stats_path.exists():
                try:
                    st = json.loads(stats_path.read_text(encoding="utf-8"))
                    opponent_id = "player_2" if participant_id == "player_1" else "player_1"
                    by_p = st.get("by_participant", {})
                    opp = by_p.get(opponent_id, {})
                    # Best-guess prevailing intent from opponent's lifecycles
                    lifecycles = st.get("intent_lifecycles", [])
                    opp_intents = [
                        str(lc.get("intent_raw") or lc.get("intent") or "")
                        for lc in lifecycles
                        if lc.get("participant_id") == opponent_id
                        and lc.get("intent_raw") or lc.get("intent")
                    ]
                    if opp_intents:
                        from collections import Counter as _C
                        entry["opponent_prevailing_intent"] = _C(opp_intents).most_common(1)[0][0]
                except (OSError, KeyError, ValueError, json.JSONDecodeError):
                    pass
            result.append(entry)
        return result

    def match_is_finished(self) -> bool:
        try:
            score = score_from_state(read_arena_state())
        except (OSError, ValueError):
            return False
        return score.get("mode") == "duel" and score.get("phase") == "finished"

    def has_current_run_intents(self, rows: list[dict[str, str]]) -> bool:
        return any(
            row.get("run_id", self.server.run_id) == self.server.run_id
            and row.get("participant_id", "") in PARTICIPANTS
            and row.get("intent", "") not in {"", "none"}
            for row in rows
        )

    def record_intent_payload_locked(
        self,
        payload: dict[str, Any],
        normalized: dict[str, Any],
        source: str,
        call_record: dict[str, Any] | None,
    ) -> None:
        participant_id = str(payload.get("participant_id") or normalized.get("participant_id") or "")
        if participant_id not in PARTICIPANTS:
            return

        intent_id = str(payload.get("intent_id", ""))
        run_id = str(payload.get("run_id", self.server.run_id))
        existing = next(
            (
                intent
                for intent in self.server.intent_records
                if intent.get("run_id") == run_id
                and intent.get("participant_id") == participant_id
                and intent.get("intent_id") == intent_id
            ),
            None,
        )
        if existing is not None:
            if call_record is not None:
                existing["call_id"] = call_record["call_id"]
                existing["request_index"] = call_record.get("request_index")
                existing["mcp_call_latency_ms"] = call_record.get("latency_ms")
                existing["source"] = "mcp_tool"
                call_record["intent_id"] = existing["intent_id"]
                call_record["sequence_number"] = existing["sequence_number"]
            return

        fallback_started_at = call_record.get("started_at_ms") if call_record is not None else None
        issued_at = int(payload.get("issued_at_ms") or fallback_started_at or now_ms())
        duration_ms = int(normalized.get("duration_ms") or payload.get("duration_ms") or 0)
        expires_at = int(payload.get("expires_at_ms") or (issued_at + max(duration_ms, 0)))
        intent_record = {
            "call_id": call_record["call_id"] if call_record is not None else "",
            "request_index": call_record.get("request_index") if call_record is not None else None,
            "source": source,
            "run_id": str(payload.get("run_id", self.server.run_id)),
            "scenario_id": str(payload.get("scenario_id", self.server.scenario_id)),
            "participant_id": participant_id,
            "intent_id": intent_id,
            "intent": str(normalized.get("intent", "")),
            "style": str(normalized.get("style", "")),
            "target_id": str(normalized.get("target_id", "")),
            "preferred_distance": normalized.get("preferred_distance"),
            "aggression": normalized.get("aggression"),
            "strafe_direction": str(normalized.get("strafe_direction", "")),
            "movement_bias": str(normalized.get("movement_bias", "")),
            "fire_policy": str(normalized.get("fire_policy", "")),
            "distance_policy": str(normalized.get("distance_policy", "")),
            "replan_if": normalized.get("replan_if", []),
            "sequence_number": normalized.get("sequence_number"),
            "decision_cadence_ms": normalized.get("decision_cadence_ms"),
            "duration_ms": duration_ms,
            "issued_at_ms": issued_at,
            "expires_at_ms": expires_at,
            "mcp_call_latency_ms": call_record.get("latency_ms") if call_record is not None else None,
            "superseded_before_expiry": False,
            "superseded_at_ms": None,
            "superseded_by_intent_id": "",
            "superseded_by_sequence_number": None,
            "effective_until_ms": expires_at,
            "effective_duration_ms": max(0, expires_at - issued_at),
            "unused_duration_ms": 0,
            "previous_intent_id": "",
            "gap_after_previous_expiry_ms": None,
        }
        for key in PARTICIPANT_INTENT_EXTRA_FIELDS:
            intent_record[key] = normalized.get(key)
        for key in PARTICIPANT_INTENT_STRATEGY_FIELDS:
            intent_record[key] = normalized.get(key, "")
        for key in PARTICIPANT_INTENT_PLAN_FIELDS:
            intent_record[key] = normalized.get(key, "")

        previous = self.server.latest_intent_by_participant.get(participant_id)
        if previous:
            intent_record["previous_intent_id"] = previous.get("intent_id", "")
            previous_expires_at = int(previous.get("expires_at_ms") or 0)
            previous_issued_at = int(previous.get("issued_at_ms") or 0)
            previous["next_intent_id"] = intent_record["intent_id"]
            previous["next_sequence_number"] = intent_record["sequence_number"]
            previous["next_issued_at_ms"] = issued_at
            if issued_at < previous_expires_at:
                previous["superseded_before_expiry"] = True
                previous["superseded_at_ms"] = issued_at
                previous["superseded_by_intent_id"] = intent_record["intent_id"]
                previous["superseded_by_sequence_number"] = intent_record["sequence_number"]
                previous["effective_until_ms"] = issued_at
                previous["effective_duration_ms"] = max(0, issued_at - previous_issued_at)
                previous["unused_duration_ms"] = max(0, previous_expires_at - issued_at)
            else:
                previous["expired_before_next_intent"] = True
                previous["gap_after_expiry_before_next_ms"] = issued_at - previous_expires_at
                previous["sticky_after_expiry"] = True
                previous["sticky_extension_before_next_ms"] = issued_at - previous_expires_at
                intent_record["gap_after_previous_expiry_ms"] = issued_at - previous_expires_at

        self.server.intent_records.append(intent_record)
        self.server.latest_intent_by_participant[participant_id] = intent_record
        if call_record is not None:
            call_record["intent_id"] = intent_record["intent_id"]
            call_record["sequence_number"] = intent_record["sequence_number"]

    def build_mcp_stats_payload_locked(self) -> dict[str, Any]:
        generated_at = now_ms()
        calls = [copy.deepcopy(call) for call in self.server.mcp_calls]
        active_calls = [copy.deepcopy(call) for call in self.server.active_mcp_calls.values()]
        intents = [copy.deepcopy(intent) for intent in self.server.intent_records]
        latencies = [
            float(call["latency_ms"])
            for call in calls
            if call.get("latency_ms") is not None
        ]
        by_tool: dict[str, dict[str, Any]] = {}
        by_participant: dict[str, dict[str, Any]] = {}

        for call in calls:
            tool_name = str(call.get("tool_name", "unknown"))
            participant_id = str(call.get("participant_id", ""))
            tool_bucket = by_tool.setdefault(
                tool_name,
                {"count": 0, "completed": 0, "errors": 0, "average_latency_ms": 0.0, "max_latency_ms": 0.0},
            )
            tool_bucket["count"] += 1
            if call.get("is_error"):
                tool_bucket["errors"] += 1
            else:
                tool_bucket["completed"] += 1
            latency = float(call.get("latency_ms") or 0)
            tool_bucket.setdefault("_latencies", []).append(latency)

            if participant_id:
                participant_bucket = by_participant.setdefault(
                    participant_id,
                    {"count": 0, "completed": 0, "errors": 0, "average_latency_ms": 0.0, "max_latency_ms": 0.0},
                )
                participant_bucket["count"] += 1
                if call.get("is_error"):
                    participant_bucket["errors"] += 1
                else:
                    participant_bucket["completed"] += 1
                participant_bucket.setdefault("_latencies", []).append(latency)

        for buckets in (by_tool, by_participant):
            for bucket in buckets.values():
                bucket_latencies = bucket.pop("_latencies", [])
                if bucket_latencies:
                    bucket["average_latency_ms"] = round(sum(bucket_latencies) / len(bucket_latencies), 3)
                    bucket["max_latency_ms"] = round(max(bucket_latencies), 3)

        for intent in intents:
            expires_at = int(intent.get("expires_at_ms") or 0)
            if (
                expires_at > 0
                and generated_at > expires_at
                and not intent.get("superseded_before_expiry")
                and not intent.get("next_issued_at_ms")
            ):
                intent["sticky_after_expiry"] = True
                intent["sticky_extension_until_stats_ms"] = generated_at - expires_at

        superseded = [intent for intent in intents if intent.get("superseded_before_expiry")]
        expired_before_next = [intent for intent in intents if intent.get("expired_before_next_intent")]
        unused_durations = [
            int(intent.get("unused_duration_ms") or 0)
            for intent in superseded
        ]
        gaps = [
            int(intent.get("gap_after_expiry_before_next_ms") or 0)
            for intent in expired_before_next
        ]
        sticky_extensions = [
            int(intent.get("sticky_extension_before_next_ms") or intent.get("sticky_extension_until_stats_ms") or 0)
            for intent in intents
            if intent.get("sticky_after_expiry")
        ]
        inferred_decision_turns: list[dict[str, Any]] = []
        last_observation_by_participant: dict[str, dict[str, Any]] = {}
        for call in sorted(calls, key=lambda item: int(item.get("request_index") or 0)):
            participant_id = str(call.get("participant_id", ""))
            tool_name = str(call.get("tool_name", ""))
            if not participant_id:
                continue
            if tool_name == "get_participant_observation" and call.get("completed_at_ms") is not None:
                last_observation_by_participant[participant_id] = call
            elif tool_name in {"set_participant_intent", "set_participant_strategy", "set_participant_plan"} and call.get("started_at_ms") is not None:
                previous_observation = last_observation_by_participant.get(participant_id)
                if previous_observation is None:
                    continue
                decision_latency = int(call["started_at_ms"]) - int(previous_observation["completed_at_ms"])
                if decision_latency < 0:
                    continue
                inferred_decision_turns.append(
                    {
                        "participant_id": participant_id,
                        "observation_call_id": previous_observation.get("call_id"),
                        "intent_call_id": call.get("call_id"),
                        "observation_completed_at_ms": previous_observation.get("completed_at_ms"),
                        "intent_started_at_ms": call.get("started_at_ms"),
                        "inferred_decision_latency_ms": decision_latency,
                        "intent": call.get("intent"),
                        "sequence_number": call.get("sequence_number"),
                    }
                )
        inferred_decision_latencies = [
            int(turn["inferred_decision_latency_ms"])
            for turn in inferred_decision_turns
        ]

        # Phase 0 telemetry: intent diversity (Shannon entropy over intent_raw),
        # stuck-recovery invocations, distance-policy switches per participant.
        import math as _math
        intent_diversity_by_participant: dict[str, float] = {}
        stuck_recovery_by_participant: dict[str, int] = {}
        distance_policy_switches_by_participant: dict[str, int] = {}
        strategy_category_distribution: dict[str, int] = {}
        strategy_action_distribution: dict[str, int] = {}
        strategy_objective_distribution: dict[str, int] = {}
        strategy_target_zone_distribution: dict[str, int] = {}
        for pid in ("player_1", "player_2"):
            pid_intents = [i for i in intents if i.get("participant_id") == pid]
            raw_labels = [
                str(i.get("intent_raw") or i.get("intent") or "")
                for i in pid_intents
            ]
            if raw_labels:
                from collections import Counter as _Counter
                counts = _Counter(raw_labels)
                total = len(raw_labels)
                entropy = -sum(
                    (c / total) * _math.log2(c / total)
                    for c in counts.values()
                    if c > 0
                )
                intent_diversity_by_participant[pid] = round(entropy, 4)
            else:
                intent_diversity_by_participant[pid] = 0.0

            stuck_recovery_by_participant[pid] = sum(
                1 for i in pid_intents
                if i.get("stuck_recovery_strategy", "default") not in ("default", "", None)
            )
            dp_list = [
                str(i.get("distance_policy") or "")
                for i in pid_intents
                if i.get("distance_policy")
            ]
            switches = sum(1 for a, b in zip(dp_list, dp_list[1:]) if a != b)
            distance_policy_switches_by_participant[pid] = switches

            for intent in pid_intents:
                category = str(intent.get("strategy_category") or "")
                action = str(intent.get("strategy_action") or "")
                objective = str(intent.get("strategy_objective") or "")
                target_zone = str(intent.get("strategy_target_zone") or "")
                if category:
                    strategy_category_distribution[category] = strategy_category_distribution.get(category, 0) + 1
                if action:
                    strategy_action_distribution[action] = strategy_action_distribution.get(action, 0) + 1

                    if objective:
                        strategy_objective_distribution[objective] = strategy_objective_distribution.get(objective, 0) + 1
                    if target_zone:
                        strategy_target_zone_distribution[target_zone] = strategy_target_zone_distribution.get(target_zone, 0) + 1
        return {
            "run_id": self.server.run_id,
            "scenario_id": self.server.scenario_id,
            "match_seed": self.server.seed,
            "started_at_ms": self.server.started_at_ms,
            "generated_at_ms": generated_at,
            "note": "latency_ms is local MCP proxy/tool-call latency measured by the arena server, not LLM think time. inferred_chat_decision_latency_ms approximates time from observation completion to the next intent request.",
            "summary": {
                "total_mcp_calls": len(calls),
                "completed_mcp_calls": sum(1 for call in calls if not call.get("is_error")),
                "errored_mcp_calls": sum(1 for call in calls if call.get("is_error")),
                "in_flight_mcp_calls": len(active_calls),
                "overlapped_in_flight_mcp_calls": sum(1 for call in calls if call.get("overlapped_by_later_call")),
                "average_mcp_latency_ms": round(sum(latencies) / len(latencies), 3) if latencies else 0.0,
                "max_mcp_latency_ms": round(max(latencies), 3) if latencies else 0.0,
                "intents_sent": len(intents),
                "intents_superseded_before_expiry": len(superseded),
                "intents_expired_before_next": len(expired_before_next),
                "average_unused_intent_duration_ms": round(sum(unused_durations) / len(unused_durations), 3) if unused_durations else 0.0,
                "max_unused_intent_duration_ms": max(unused_durations) if unused_durations else 0,
                "average_gap_after_intent_expiry_ms": round(sum(gaps) / len(gaps), 3) if gaps else 0.0,
                "max_gap_after_intent_expiry_ms": max(gaps) if gaps else 0,
                "intents_continued_stale_after_expiry": len(sticky_extensions),
                "average_stale_intent_extension_ms": round(sum(sticky_extensions) / len(sticky_extensions), 3) if sticky_extensions else 0.0,
                "max_stale_intent_extension_ms": max(sticky_extensions) if sticky_extensions else 0,
                "average_inferred_chat_decision_latency_ms": round(sum(inferred_decision_latencies) / len(inferred_decision_latencies), 3) if inferred_decision_latencies else 0.0,
                "max_inferred_chat_decision_latency_ms": max(inferred_decision_latencies) if inferred_decision_latencies else 0,
                "rationales_logged": getattr(self.server, "rationale_count", 0),
                "intent_diversity_by_participant": intent_diversity_by_participant,
                "stuck_recovery_invocations_by_participant": stuck_recovery_by_participant,
                "distance_policy_switches_by_participant": distance_policy_switches_by_participant,
                "strategy_category_distribution": strategy_category_distribution,
                "strategy_action_distribution": strategy_action_distribution,
                "strategy_objective_distribution": strategy_objective_distribution,
                "strategy_target_zone_distribution": strategy_target_zone_distribution,
            },
            "by_tool": by_tool,
            "by_participant": by_participant,
            "calls": calls,
            "active_calls": active_calls,
            "inferred_decision_turns": inferred_decision_turns,
            "intent_lifecycles": intents,
            "token_usage_by_participant": copy.deepcopy(getattr(self.server, "token_usage", {})),
            "token_usage_note": (
                "Estimated from MCP tool call request/response sizes (~4 chars per token). "
                "Does not include the agent's system prompt, tool schemas, or full conversation "
                "history that the LLM receives each turn; treat as a lower-bound proxy."
            ),
        }

    def write_mcp_stats_locked(self) -> None:
        run_dir = self.run_dir()
        run_dir.mkdir(parents=True, exist_ok=True)
        payload = self.build_mcp_stats_payload_locked()
        (run_dir / "stats.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def write_run_events_artifact(self, events_text: str) -> None:
        rows = [
            row for row in parse_tsv_rows(events_text)
            if row.get("run_id", self.server.run_id) in {"", self.server.run_id}
        ]
        if not rows:
            return

        run_dir = self.run_dir()
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "events.jsonl").write_text(
            "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows),
            encoding="utf-8",
        )

    def maybe_write_finished_run_artifacts(self, state_text: str) -> None:
        rows = parse_tsv_rows(state_text)
        score = score_from_state(rows)
        if score.get("mode") != "duel" or score.get("phase") != "finished":
            return
        run_id = self.server.run_id
        if run_id in self.server.summary_written_runs:
            return
        run_dir = self.run_dir(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        summary = {
            "run_id": run_id,
            "mode": "duel",
            "player_1_model": self.server.player_1_model,
            "player_2_model": self.server.player_2_model,
            "round": self.server.round,
            "seed": self.server.seed,
            "winner": score.get("winner", ""),
            "terminal_reason": score.get("terminal_reason", ""),
            "elapsed_time_seconds": score.get("elapsed_time_seconds", 0),
            "timeout_seconds": score.get("timeout_seconds", self.server.timeout_seconds),
            "player_1_health_end": score.get("player_1_health", 0),
            "player_2_health_end": score.get("player_2_health", 0),
            "player_1_damage_dealt": score.get("player_1_damage_dealt", 0),
            "player_2_damage_dealt": score.get("player_2_damage_dealt", 0),
            "player_1_shots_fired": score.get("player_1_shots_fired", 0),
            "player_2_shots_fired": score.get("player_2_shots_fired", 0),
            "player_1_shots_hit": score.get("player_1_shots_hit", 0),
            "player_2_shots_hit": score.get("player_2_shots_hit", 0),
            "stats": "stats.json",
        }
        (run_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        if ARENA_EVENTS_TSV.exists():
            self.write_run_events_artifact(ARENA_EVENTS_TSV.read_text(encoding="utf-8", errors="replace"))
        self.server.summary_written_runs.add(run_id)
        with self.server.stats_lock:
            self.write_mcp_stats_locked()

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
            client_info = params.get("clientInfo") if isinstance(params, dict) else {}
            if not isinstance(client_info, dict):
                client_info = {}
            self.record_mcp_presence(
                {
                    "client_id": self.new_http_mcp_client_id(),
                    "client_name": str(client_info.get("name", "") or "HTTP MCP client"),
                    "client_version": str(client_info.get("version", "") or ""),
                    "source_addr": self.client_address[0],
                    "connected_at_ms": now_ms(),
                }
            )
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
                        "set_participant_plan, set_participant_strategy, or set_participant_intent, stop_participant_intent, "
                        "get_match_result, and get_duel_events to control assigned Doom Arena duel participants."
                    ),
                },
            }

        if method == "notifications/initialized":
            self.touch_http_mcp_presence()
            return None

        if method == "tools/list":
            self.touch_http_mcp_presence()
            return {"jsonrpc": "2.0", "id": message_id, "result": {"tools": tool_definitions()}}

        if method == "resources/list":
            self.touch_http_mcp_presence()
            return {"jsonrpc": "2.0", "id": message_id, "result": {"resources": []}}

        if method == "prompts/list":
            self.touch_http_mcp_presence()
            return {"jsonrpc": "2.0", "id": message_id, "result": {"prompts": []}}

        if method == "shutdown":
            self.remove_http_mcp_presence()
            return {"jsonrpc": "2.0", "id": message_id, "result": None}

        if method == "tools/call":
            tool_name = str(params.get("name"))
            arguments = params.get("arguments") or {}
            self.touch_http_mcp_presence()
            call_record = self.start_mcp_tool_call(tool_name, arguments if isinstance(arguments, dict) else {}, message_id)
            try:
                client = DoomArenaClient(f"http://{self.server.args.host}:{self.server.args.port}")
                presence = self.current_http_mcp_presence()
                client.client_name = str(presence.get("client_name", "") or "HTTP MCP client")
                client.client_version = str(presence.get("client_version", "") or "")
                text = call_tool(client, tool_name, arguments if isinstance(arguments, dict) else {})
                result = {"content": [{"type": "text", "text": text}], "isError": False}
            except (KeyError, TypeError, ValueError, DoomArenaError) as exc:
                text = str(exc)
                result = {"content": [{"type": "text", "text": text}], "isError": True}
            self.complete_mcp_tool_call(call_record, bool(result["isError"]), text)
            return {"jsonrpc": "2.0", "id": message_id, "result": result}

        return {
            "jsonrpc": "2.0",
            "id": message_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }

    def write_file(self, path: Path, label: str) -> None:
        body = self.read_body()
        path.write_bytes(body)
        if path == ARENA_STATE_TSV:
            self.maybe_write_finished_run_artifacts(body.decode("utf-8", errors="replace"))
        elif path == ARENA_EVENTS_TSV:
            self.write_run_events_artifact(body.decode("utf-8", errors="replace"))
        self.write_json(HTTPStatus.OK, {"ok": True, "path": label, "bytes": len(body)})

    def read_file(self, path: Path, label: str) -> None:
        if not path.exists():
            empty_tsv_headers = {
                ARENA_PLAYER_COMMAND_TSV: PLAYER_COMMAND_HEADER,
                ARENA_PARTICIPANT_COMMAND_TSV: PARTICIPANT_COMMAND_HEADER,
                ARENA_PARTICIPANT_READY_TSV: PARTICIPANT_READY_HEADER,
                ARENA_ENEMY_COMMAND_TSV: ENEMY_COMMAND_HEADER,
            }
            if path in empty_tsv_headers:
                self.write_tsv(empty_tsv_headers[path])
                return
            self.write_json(
                HTTPStatus.NOT_FOUND,
                {"ok": False, "error": f"{label} has not been written yet."},
            )
            return

        body = path.read_bytes()
        self.write_tsv_bytes(body)

    def read_arena_state_with_config(self) -> None:
        if not ARENA_STATE_TSV.exists():
            self.write_json(
                HTTPStatus.NOT_FOUND,
                {"ok": False, "error": "arena_game_state.local.tsv has not been written yet."},
            )
            return

        text = ARENA_STATE_TSV.read_text(encoding="utf-8", errors="replace")
        text = inject_arena_config_row(text, self.server.hide_enemy_position)
        self.write_tsv_bytes(text.encode("utf-8"))

    def write_tsv(self, body: str) -> None:
        self.write_tsv_bytes(body.encode("utf-8"))

    def write_tsv_bytes(self, body: bytes) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/tab-separated-values; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_run_artifact(self, filename: str) -> None:
        path = self.run_dir() / filename
        if not path.exists():
            self.write_json(
                HTTPStatus.NOT_FOUND,
                {
                    "ok": False,
                    "error": f"{filename} has not been written yet for {self.server.run_id}.",
                    "run_id": self.server.run_id,
                },
            )
            return

        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_previous_rounds_recap(self) -> None:
        query = urlparse(self.path).query
        params = parse_qs(query)
        participant_id = params.get("participant_id", [None])[0] or ""
        duel_session_id = params.get("duel_session_id", [None])[0] or self.server.duel_session_id
        try:
            current_round = int(params.get("current_round", [1])[0])
            window = int(params.get("window", [0])[0])
        except (TypeError, ValueError):
            current_round = 1
            window = 0
        if participant_id not in PARTICIPANTS:
            participant_id = "player_1"
        rounds = self.build_previous_rounds_recap(
            participant_id, current_round, duel_session_id, window
        )
        self.write_json(
            HTTPStatus.OK,
            {"ok": True, "rounds": rounds, "participant_id": participant_id},
        )

    def read_map_blueprint(self) -> None:
        query = urlparse(self.path).query
        params = parse_qs(query)
        scenario_id = params.get("scenario_id", [None])[0] or self.server.scenario_id or "duel_e1m8"
        path = MAP_BLUEPRINTS_DIR / f"{scenario_id}.json"
        if not path.exists():
            self.write_json(
                HTTPStatus.NOT_FOUND,
                {"ok": False, "error": f"No blueprint found for scenario_id={scenario_id}"},
            )
            return
        self.write_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "scenario_id": scenario_id,
                "blueprint": json.loads(path.read_text(encoding="utf-8")),
            },
        )

    def read_duel_session_results(self) -> None:
        query = urlparse(self.path).query
        params = parse_qs(query)
        duel_session_id = params.get("duel_session_id", [None])[0]
        if not duel_session_id:
            duel_session_id = self.server.duel_session_id

        if not duel_session_id:
            self.write_json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": "No active duel session."},
            )
            return

        session_dir = RESULTS_ROOT / duel_session_id
        rounds = []
        if session_dir.exists():
            for round_dir in sorted(session_dir.glob("round_*")):
                if round_dir.is_dir():
                    summary_file = round_dir / "summary.json"
                    if summary_file.exists():
                        try:
                            summary_data = json.loads(summary_file.read_text(encoding="utf-8"))
                            rounds.append(summary_data)
                        except Exception:
                            pass

        self.write_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "duel_session_id": duel_session_id,
                "total_rounds": self.server.duel_total_rounds,
                "player_1_model": self.server.player_1_model,
                "player_2_model": self.server.player_2_model,
                "rounds": rounds,
            },
        )

    def read_run_results_page(self) -> None:
        run_dir = self.run_dir()
        session_dir = Path()
        if self.server.duel_session_id:
            session_dir = RESULTS_ROOT / self.server.duel_session_id
        elif run_dir.parent.name.startswith("session_"):
            session_dir = run_dir.parent
        artifact_names = [
            "summary.json",
            "stats.json",
            "config.json",
            "controller_tokens.json",
            "events.jsonl",
            "player_1_mcp_instructions.md",
            "player_2_mcp_instructions.md",
        ]
        endpoint_by_name = {
            "summary.json": "/api/arena/run-summary",
            "stats.json": "/api/arena/run-stats",
        }
        rows = []

        for artifact_name in artifact_names:
            artifact_path = run_dir / artifact_name
            if artifact_path.exists():
                href = endpoint_by_name.get(artifact_name)
                if href:
                    rows.append(f'<li><a href="{href}">{html.escape(artifact_name)}</a></li>')
                else:
                    rows.append(f"<li>{html.escape(artifact_name)}</li>")

        if not rows:
            rows.append("<li>No result artifacts have been written yet.</li>")

        round_rows: list[str] = []
        if session_dir and session_dir.exists() and session_dir != run_dir:
            for candidate in sorted(session_dir.glob("round_*")):
                if candidate.is_dir():
                    round_rows.append(f"<li>{html.escape(candidate.name)}</li>")
        if not round_rows:
            round_rows.append("<li>No additional rounds found yet.</li>")

        session_folder_html = (
            f"""<p>Session folder:</p>
  <code>{html.escape(str(session_dir))}</code>"""
            if session_dir and session_dir.exists()
            else ""
        )

        body = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Doom Arena Results {html.escape(self.server.run_id)}</title>
  <style>
    body {{
      background: #10130d;
      color: #f7f5d8;
      font: 14px/1.45 Consolas, "Courier New", monospace;
      padding: 24px;
    }}
    h1 {{ color: #b8e986; font-size: 20px; }}
    a {{ color: #ffce6b; }}
    code {{
      display: block;
      padding: 10px;
      background: #050505;
      border: 1px solid rgba(255, 255, 255, 0.14);
      white-space: pre-wrap;
      word-break: break-all;
    }}
  </style>
</head>
<body>
  <h1>Doom Arena Match Results</h1>
  <p>Run ID: {html.escape(self.server.run_id)}</p>
  {session_folder_html}
  <p>Round folder:</p>
  <code>{html.escape(str(run_dir))}</code>
  <h2>Round Artifacts</h2>
  <ul>
    {''.join(rows)}
  </ul>
  <h2>Session Rounds</h2>
  <ul>
    {''.join(round_rows)}
  </ul>
</body>
</html>
""".encode("utf-8")

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def duel_prompt_text(self, participant_id: str) -> str:
        if participant_id == "player_1" and self.server.duel_player_1_prompt:
            return self.server.duel_player_1_prompt
        if participant_id == "player_2" and self.server.duel_player_2_prompt:
            return self.server.duel_player_2_prompt

        prompt_path = self.run_dir() / f"{participant_id}_mcp_instructions.md"
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8", errors="replace")
        return ""

    def read_run_instructions(self) -> None:
        query = parse_qs(urlparse(self.path).query)
        participant_id = str(query.get("participant_id", [""])[0])
        if participant_id not in PARTICIPANTS:
            self.write_json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": "participant_id must be player_1 or player_2."},
            )
            return

        prompt = self.duel_prompt_text(participant_id)
        if not prompt:
            self.write_json(
                HTTPStatus.NOT_FOUND,
                {
                    "ok": False,
                    "error": f"{participant_id} MCP instructions have not been written yet.",
                    "run_id": self.server.run_id,
                },
            )
            return

        self.write_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "run_id": self.server.run_id,
                "participant_id": participant_id,
                "prompt": prompt,
            },
        )

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
        intent_rows_for_stats: list[dict[str, str]] = []
        rationale_records: list[dict[str, Any]] = []

        try:
            if "application/json" in content_type:
                payload = json.loads(body.decode("utf-8"))
                if isinstance(payload, list):
                    intent_rows_for_stats = [
                        self.normalize_participant_intent(row)
                        for row in payload
                    ]
                    for raw, row in zip(payload, intent_rows_for_stats):
                        record = self.extract_rationale_record(raw, row)
                        if record is not None:
                            rationale_records.append(record)
                    body = self.participant_intent_rows_to_tsv(intent_rows_for_stats).encode("utf-8")
                elif isinstance(payload, dict):
                    intent_row = self.normalize_participant_intent(payload)
                    intent_rows_for_stats = [intent_row]
                    record = self.extract_rationale_record(payload, intent_row)
                    if record is not None:
                        rationale_records.append(record)
                    body = self.update_participant_intent_row(intent_row).encode("utf-8")
                else:
                    raise ValueError("JSON payload must be an object or list")
            else:
                text = body.decode("utf-8", errors="replace")
                intent_rows_for_stats = self.parse_participant_intent_rows(text)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self.write_json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": f"Invalid participant intent: {exc}"},
            )
            return

        if self.match_is_finished() and self.has_current_run_intents(intent_rows_for_stats):
            self.write_json(
                HTTPStatus.CONFLICT,
                {
                    "ok": False,
                    "error": "Match is already finished; post-finish participant intents are rejected.",
                    "run_id": self.server.run_id,
                },
            )
            return

        ARENA_PARTICIPANT_INTENT_TSV.write_bytes(body)
        if rationale_records:
            self.append_rationale_records(rationale_records)
        if intent_rows_for_stats:
            with self.server.stats_lock:
                for row in intent_rows_for_stats:
                    self.record_participant_intent_row_locked(row)
                self.write_mcp_stats_locked()
        self.write_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "path": "arena_participant_intents.local.tsv",
                "bytes": len(body),
                "rationales_logged": len(rationale_records),
            },
        )

    def write_mcp_call_telemetry(self) -> None:
        try:
            payload = self.read_json_body()
            if not payload:
                raise ValueError("telemetry payload must be a JSON object")
            with self.server.stats_lock:
                record = self.normalize_remote_mcp_call(payload)
                self.server.mcp_calls.append(record)
                result_text = ""
                result_payload = payload.get("result")
                if isinstance(result_payload, dict):
                    self.attach_mcp_result_payload_summary_locked(record, result_payload)
                    result_text = json.dumps(result_payload)
                elif isinstance(payload.get("result_text"), str):
                    result_text = str(payload.get("result_text", ""))
                    self.attach_mcp_result_summary_locked(record, result_text)
                if not record.get("is_error") and record.get("tool_name") in {"set_participant_intent", "set_participant_strategy", "set_participant_plan"} and result_text:
                    self.record_intent_lifecycle_locked(record, result_text)
                self.write_mcp_stats_locked()
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            self.write_json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": f"Invalid MCP telemetry: {exc}"},
            )
            return

        self.write_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "call_id": record.get("call_id", ""),
                "recorded": True,
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
                    self.update_participant_ready_agent(payload)
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

    def update_participant_ready_agent(self, payload: dict[str, Any]) -> None:
        participant_id = str(payload.get("participant_id", ""))
        agent_label = str(payload.get("agent_label", "")).strip()

        if participant_id not in PARTICIPANTS or not agent_label:
            return

        with self.server.stats_lock:
            self.server.participant_ready_agents[participant_id] = agent_label

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
        return self.update_participant_intent_row(intent_row)

    def participant_intent_row_preferred(
        self,
        current: dict[str, str] | None,
        candidate: dict[str, str] | None,
    ) -> bool:
        if candidate is None:
            return False
        if current is None:
            return True

        current_sequence = int(current.get("sequence_number", "") or 0)
        candidate_sequence = int(candidate.get("sequence_number", "") or 0)
        if candidate_sequence != current_sequence:
            return candidate_sequence > current_sequence

        current_issued = int(current.get("issued_at_ms", "0") or 0)
        candidate_issued = int(candidate.get("issued_at_ms", "0") or 0)
        if candidate_issued != current_issued:
            return candidate_issued > current_issued

        return candidate.get("intent_id", "") != current.get("intent_id", "")

    def current_run_participant_intent_rows(self) -> list[dict[str, str]]:
        rows_by_participant: dict[str, dict[str, str]] = {}
        current_ms = now_ms()

        for row in self.read_participant_intent_rows():
            participant_id = row.get("participant_id", "")
            if participant_id not in PARTICIPANTS:
                continue
            if row.get("run_id", "") != self.server.run_id:
                continue
            if row.get("scenario_id", "") != self.server.scenario_id:
                continue
            if int(row.get("expires_at_ms", "0") or 0) <= current_ms:
                continue
            if self.participant_intent_row_preferred(rows_by_participant.get(participant_id), row):
                rows_by_participant[participant_id] = row

        with self.server.stats_lock:
            latest_by_participant = copy.deepcopy(self.server.latest_intent_by_participant)

        for participant_id, intent in latest_by_participant.items():
            if participant_id not in PARTICIPANTS:
                continue
            if str(intent.get("run_id", "")) != self.server.run_id:
                continue
            if str(intent.get("scenario_id", "")) != self.server.scenario_id:
                continue
            if int(intent.get("expires_at_ms") or 0) <= current_ms:
                continue

            row = self.normalize_participant_intent(intent)
            if self.participant_intent_row_preferred(rows_by_participant.get(participant_id), row):
                rows_by_participant[participant_id] = row

        return [
            rows_by_participant[participant_id]
            for participant_id in sorted(rows_by_participant)
        ]

    def update_participant_intent_row(self, intent_row: dict[str, str]) -> str:
        rows = self.current_run_participant_intent_rows()
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

        intent_raw = str(payload.get("intent_raw") or payload.get("intent", "")).strip().lower()
        if payload.get("strategy_source") == "hierarchical" and payload.get("strategy_category") and payload.get("strategy_action"):
            intent_raw = f"{payload.get('strategy_category')}/{payload.get('strategy_action')}".strip().lower()
        intent_for_validation = str(payload.get("intent", "")).strip().lower()
        allowed = ALLOWED_PARTICIPANT_INTENTS
        if intent_for_validation not in allowed:
            raise ValueError(
                "intent must be one of "
                + ", ".join(sorted(allowed))
            )

        intent = intent_for_validation

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
        aim_tolerance = normalize_optional_int(
            payload.get("aim_tolerance"),
            "aim_tolerance",
            minimum=0,
            maximum=180,
        )
        fire_burst_ms = normalize_optional_int(
            payload.get("fire_burst_ms"),
            "fire_burst_ms",
            minimum=0,
            maximum=60000,
        )
        min_fire_alignment = normalize_optional_int(
            payload.get("min_fire_alignment"),
            "min_fire_alignment",
            minimum=0,
            maximum=180,
        )
        min_distance = normalize_optional_int(
            payload.get("min_distance"),
            "min_distance",
            minimum=0,
        )
        max_distance = normalize_optional_int(
            payload.get("max_distance"),
            "max_distance",
            minimum=0,
        )
        retreat_if_closer_than = normalize_optional_int(
            payload.get("retreat_if_closer_than"),
            "retreat_if_closer_than",
            minimum=0,
        )
        push_if_farther_than = normalize_optional_int(
            payload.get("push_if_farther_than"),
            "push_if_farther_than",
            minimum=0,
        )
        if min_distance and max_distance and int(min_distance) > int(max_distance):
            raise ValueError("min_distance must be <= max_distance")
        los_lost_action = normalize_optional_enum(
            payload.get("los_lost_action"),
            "sweep",
            ALLOWED_LOS_LOST_ACTIONS,
            "los_lost_action",
        )
        stuck_recovery_strategy = normalize_optional_enum(
            payload.get("stuck_recovery_strategy"),
            "default",
            ALLOWED_STUCK_RECOVERY_STRATEGIES,
            "stuck_recovery_strategy",
        )
        movement_primitive = normalize_optional_enum(
            payload.get("movement_primitive"),
            "",
            ALLOWED_MOVEMENT_PRIMITIVES,
            "movement_primitive",
            allow_blank=True,
        )
        turn_policy = normalize_optional_enum(
            payload.get("turn_policy"),
            "auto",
            ALLOWED_TURN_POLICIES,
            "turn_policy",
        )
        navigation_target = normalize_optional_enum(
            payload.get("navigation_target"),
            "opponent",
            ALLOWED_NAVIGATION_TARGETS,
            "navigation_target",
        )
        fire_mode = normalize_optional_enum(
            payload.get("fire_mode"),
            "auto",
            ALLOWED_FIRE_MODES,
            "fire_mode",
        )
        plan_route = normalize_plan_route_field(payload.get("plan_route", ""))
        plan_engagement_policy = normalize_plan_engagement_policy(payload.get("plan_engagement_policy", ""))

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
            "aim_tolerance": aim_tolerance,
            "fire_burst_ms": fire_burst_ms,
            "min_fire_alignment": min_fire_alignment,
            "min_distance": min_distance,
            "max_distance": max_distance,
            "retreat_if_closer_than": retreat_if_closer_than,
            "push_if_farther_than": push_if_farther_than,
            "los_lost_action": los_lost_action,
            "stuck_recovery_strategy": stuck_recovery_strategy,
            "movement_primitive": movement_primitive,
            "turn_policy": turn_policy,
            "navigation_target": navigation_target,
            "fire_mode": fire_mode,
            "intent_raw": intent_raw,
            "strategy_source": str(payload.get("strategy_source", "")),
            "strategy_category": str(payload.get("strategy_category", "")),
            "strategy_action": str(payload.get("strategy_action", "")),
            "strategy_intensity": str(payload.get("strategy_intensity", "")),
            "strategy_commit_ms": str(payload.get("strategy_commit_ms", "")),
            "strategy_objective": str(payload.get("strategy_objective", "")),
            "strategy_target_zone": str(payload.get("strategy_target_zone", "")),
            "strategy_reasoning": " ".join(str(payload.get("strategy_reasoning", "")).replace("\t", " ").split())[:120],
            "plan_objective": " ".join(str(payload.get("plan_objective", "")).replace("\t", " ").split())[:64],
            "plan_route": plan_route,
            "plan_engagement_policy": plan_engagement_policy,
            "plan_reasoning": " ".join(str(payload.get("plan_reasoning", "")).replace("\t", " ").split())[:160],
            "plan_route_cells": " ".join(str(payload.get("plan_route_cells", "")).replace("\t", " ").split())[:80],
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
        plan_previous_header = expected_header[:expected_header.index("plan_objective")]
        strategy_previous_header = expected_header[:expected_header.index("strategy_source")]
        strategy_metadata_previous_header = expected_header[:expected_header.index("strategy_objective")]
        extended_previous_header = PARTICIPANT_INTENT_EXTENDED_PREVIOUS_HEADER.strip().split("\t")
        previous_header = PARTICIPANT_INTENT_PREVIOUS_HEADER.strip().split("\t")
        legacy_header = PARTICIPANT_INTENT_LEGACY_HEADER.strip().split("\t")
        header = lines[0].split("\t")
        if header == legacy_header:
            parse_header = legacy_header
        elif header == previous_header:
            parse_header = previous_header
        elif header == extended_previous_header:
            parse_header = extended_previous_header
        elif header == expected_header:
            parse_header = expected_header
        elif header == plan_previous_header:
            parse_header = plan_previous_header
        elif header == strategy_previous_header:
            parse_header = strategy_previous_header
        elif header == strategy_metadata_previous_header:
            parse_header = strategy_metadata_previous_header
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
                        "aim_tolerance": "",
                        "fire_burst_ms": "",
                        "min_fire_alignment": "",
                        "min_distance": "",
                        "max_distance": "",
                        "retreat_if_closer_than": "",
                        "push_if_farther_than": "",
                        "los_lost_action": "sweep",
                        "stuck_recovery_strategy": "default",
                        "movement_primitive": "",
                        "turn_policy": "auto",
                        "navigation_target": "opponent",
                        "fire_mode": "auto",
                        "intent_raw": row.get("intent", ""),
                    }
                )
            if parse_header in (legacy_header, previous_header, extended_previous_header, plan_previous_header, strategy_previous_header, strategy_metadata_previous_header):
                for key in PARTICIPANT_INTENT_EXTRA_FIELDS:
                    if key not in row:
                        row[key] = ""
                if not row.get("los_lost_action"):
                    row["los_lost_action"] = "sweep"
                if not row.get("stuck_recovery_strategy"):
                    row["stuck_recovery_strategy"] = "default"
                if not row.get("turn_policy"):
                    row["turn_policy"] = "auto"
                if not row.get("navigation_target"):
                    row["navigation_target"] = "opponent"
                if not row.get("fire_mode"):
                    row["fire_mode"] = "auto"
                if not row.get("intent_raw"):
                    row["intent_raw"] = row.get("intent", "")
            for key in PARTICIPANT_INTENT_STRATEGY_FIELDS:
                if key not in row:
                    row[key] = ""
            for key in PARTICIPANT_INTENT_PLAN_FIELDS:
                if key not in row:
                    row[key] = ""
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
        for field_name in (
            "min_distance",
            "max_distance",
            "retreat_if_closer_than",
            "push_if_farther_than",
        ):
            if row.get(field_name, ""):
                normalize_optional_int(row[field_name], field_name, minimum=0)
        for field_name in ("aim_tolerance", "min_fire_alignment"):
            if row.get(field_name, ""):
                normalize_optional_int(row[field_name], field_name, minimum=0, maximum=180)
        if row.get("fire_burst_ms", ""):
            normalize_optional_int(row["fire_burst_ms"], "fire_burst_ms", minimum=0, maximum=60000)
        if (
            row.get("min_distance", "")
            and row.get("max_distance", "")
            and int(row["min_distance"]) > int(row["max_distance"])
        ):
            raise ValueError("min_distance must be <= max_distance")
        if row.get("los_lost_action", "sweep") not in ALLOWED_LOS_LOST_ACTIONS:
            raise ValueError("invalid los_lost_action")
        if row.get("stuck_recovery_strategy", "default") not in ALLOWED_STUCK_RECOVERY_STRATEGIES:
            raise ValueError("invalid stuck_recovery_strategy")
        if row.get("movement_primitive", "") and row["movement_primitive"] not in ALLOWED_MOVEMENT_PRIMITIVES:
            raise ValueError("invalid movement_primitive")
        if row.get("turn_policy", "auto") not in ALLOWED_TURN_POLICIES:
            raise ValueError("invalid turn_policy")
        if row.get("navigation_target", "opponent") not in ALLOWED_NAVIGATION_TARGETS:
            raise ValueError("invalid navigation_target")
        if row.get("fire_mode", "auto") not in ALLOWED_FIRE_MODES:
            raise ValueError("invalid fire_mode")
        if row.get("plan_route", ""):
            normalize_plan_route_field(row["plan_route"])
        normalize_plan_engagement_policy(row.get("plan_engagement_policy", ""))

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
        self.server.summary_written_runs.discard(self.server.run_id)
        default_run_dir = RESULTS_ROOT / self.server.run_id
        self.server.run_results_dirs[self.server.run_id] = default_run_dir
        self.server.current_run_results_dir = default_run_dir

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
        self.reset_mcp_stats()
        if bool(payload.get("clear_duel_session", False)):
            self.server.duel_session_id = ""
            self.server.duel_total_rounds = 1
            self.server.duel_current_round = 0
            self.server.duel_controller_tokens = {}
            self.server.duel_player_1_prompt = ""
            self.server.duel_player_2_prompt = ""

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

    def resolve_duel_scenario_pool(self, payload: dict[str, Any]) -> list[str]:
        explicit_pool = payload.get("scenario_pool")
        randomize_spawns = bool(payload.get("randomize_spawns", False))
        rotate_all_maps = bool(payload.get("rotate_all_maps", False))
        scenario_id = str(payload.get("scenario_id", "duel_e1m8"))

        if isinstance(explicit_pool, list):
            sanitized = [
                str(entry)
                for entry in explicit_pool
                if str(entry) in DUEL_SCENARIO_IDS
            ]
            if sanitized:
                return sanitized

        if rotate_all_maps:
            return [
                entry["scenario_id"]
                for entry in DUEL_SCENARIOS
                if not entry["requires_wasm_rebuild"]
            ]

        if randomize_spawns:
            return ["duel_e1m8", "duel_e1m8_blind_spawn"]

        if scenario_id in DUEL_SCENARIO_IDS:
            return [scenario_id]

        return ["duel_e1m8"]

    def pick_round_scenario_id(self, round_number: int, payload: dict[str, Any]) -> str:
        pool = list(self.server.duel_scenario_pool)
        if not pool:
            return str(payload.get("scenario_id", "duel_e1m8"))
        if len(pool) == 1:
            return pool[0]
        if self.server.duel_randomize_spawns:
            return random.choice(pool)
        return pool[(round_number - 1) % len(pool)]

    def create_duel_session(self) -> None:
        payload = self.read_json_body()
        decision_cadence_ms = int(payload.get("decision_cadence_ms", 750))
        intent_duration_ms = int(payload.get("intent_duration_ms", 25000))
        enforce_tokens = bool(payload.get("enforce_controller_tokens", True))
        continue_session = bool(payload.get("continue_session", False))
        restart_session = bool(payload.get("restart_session", False))
        try:
            requested_total_rounds = clamp_int(
                payload.get("rounds", payload.get("round", DUEL_DEFAULTS["round"])),
                1,
                50,
            )
        except (TypeError, ValueError):
            requested_total_rounds = int(DUEL_DEFAULTS["round"])

        new_session = not (
            (restart_session and self.server.duel_session_id)
            or (continue_session and self.server.duel_session_id)
        )
        if new_session:
            self.server.duel_randomize_spawns = bool(payload.get("randomize_spawns", False))
            self.server.duel_scenario_pool = self.resolve_duel_scenario_pool(payload)
            self.server.duel_scenario_history = []

        if restart_session and self.server.duel_session_id:
            duel_session_id = self.server.duel_session_id
            total_rounds = self.server.duel_total_rounds or requested_total_rounds
            round_number = self.server.duel_current_round or 1
        elif continue_session and self.server.duel_session_id:
            if not self.match_is_finished():
                self.write_json(
                    HTTPStatus.CONFLICT,
                    {
                        "ok": False,
                        "error": "Current round is still active; wait for phase=finished before starting next round.",
                        "duel_session_id": self.server.duel_session_id,
                        "current_round": self.server.duel_current_round,
                        "total_rounds": self.server.duel_total_rounds,
                    },
                )
                return
            if self.server.duel_current_round >= self.server.duel_total_rounds:
                self.write_json(
                    HTTPStatus.CONFLICT,
                    {
                        "ok": False,
                        "error": "No remaining rounds in this duel session.",
                        "duel_session_id": self.server.duel_session_id,
                        "current_round": self.server.duel_current_round,
                        "total_rounds": self.server.duel_total_rounds,
                    },
                )
                return
            duel_session_id = self.server.duel_session_id
            total_rounds = self.server.duel_total_rounds
            round_number = self.server.duel_current_round + 1
        else:
            duel_session_id = new_duel_session_id()
            total_rounds = requested_total_rounds
            round_number = 1
            self.server.duel_controller_tokens = {}
            self.server.duel_player_1_prompt = ""
            self.server.duel_player_2_prompt = ""

        player_1_model = str(payload.get("player_1_model", self.server.player_1_model or DUEL_DEFAULTS["player_1_model"]))
        player_2_model = str(payload.get("player_2_model", self.server.player_2_model or DUEL_DEFAULTS["player_2_model"]))
        try:
            seed_value = int(payload.get("seed", self.server.seed or DUEL_DEFAULTS["seed"]))
        except (TypeError, ValueError):
            seed_value = int(self.server.seed or DUEL_DEFAULTS["seed"])
        try:
            timeout_seconds_value = int(
                payload.get("timeout_seconds", self.server.timeout_seconds or DUEL_DEFAULTS["timeout_seconds"])
            )
        except (TypeError, ValueError):
            timeout_seconds_value = int(self.server.timeout_seconds or DUEL_DEFAULTS["timeout_seconds"])

        round_scenario_id = self.pick_round_scenario_id(round_number, payload)
        reset_payload = self.reset_arena_state(
            {
                **payload,
                "arena_mode": "duel",
                "scenario_id": round_scenario_id,
                "player_1_model": player_1_model,
                "player_2_model": player_2_model,
                "round": round_number,
                "seed": seed_value,
                "timeout_seconds": timeout_seconds_value,
            }
        )
        self.server.duel_scenario_history.append(round_scenario_id)
        run_id = str(reset_payload["run_id"])
        session_dir = RESULTS_ROOT / duel_session_id
        run_dir = session_dir / f"round_{round_number:02d}_{run_id}"
        run_dir.mkdir(parents=True, exist_ok=True)
        self.set_run_results_dir(run_id, run_dir)

        if self.server.duel_controller_tokens:
            controller_tokens = copy.deepcopy(self.server.duel_controller_tokens)
            controller_tokens["run_id"] = run_id
            controller_tokens["enforce_controller_tokens"] = bool(
                controller_tokens.get("enforce_controller_tokens", enforce_tokens)
            )
            if isinstance(controller_tokens.get("player_1"), dict):
                controller_tokens["player_1"]["model"] = str(reset_payload["player_1_model"])
            if isinstance(controller_tokens.get("player_2"), dict):
                controller_tokens["player_2"]["model"] = str(reset_payload["player_2_model"])
        else:
            controller_tokens = build_controller_tokens(
                run_id,
                str(reset_payload["player_1_model"]),
                str(reset_payload["player_2_model"]),
                enforce_tokens,
            )
        effective_enforce_tokens = bool(controller_tokens.get("enforce_controller_tokens", enforce_tokens))
        self.server.duel_controller_tokens = copy.deepcopy(controller_tokens)
        write_controller_tokens(run_dir, controller_tokens)
        (session_dir / "controller_tokens.json").write_text(
            json.dumps(controller_tokens, indent=2) + "\n",
            encoding="utf-8",
        )

        player_1_instructions = render_participant_instructions(
            "player_1",
            str(reset_payload["player_1_model"]),
            "player_2",
            controller_tokens["player_1"]["controller_token"],
            effective_enforce_tokens,
            decision_cadence_ms,
            intent_duration_ms,
            round_number,
            total_rounds,
            enable_cross_round_recap=self.server.enable_cross_round_recap,
            enable_map_blueprint=self.server.enable_map_blueprint,
            scenario_id=self.server.scenario_id,
            control_mode=self.server.control_mode,
        )
        player_2_instructions = render_participant_instructions(
            "player_2",
            str(reset_payload["player_2_model"]),
            "player_1",
            controller_tokens["player_2"]["controller_token"],
            effective_enforce_tokens,
            decision_cadence_ms,
            intent_duration_ms,
            round_number,
            total_rounds,
            enable_cross_round_recap=self.server.enable_cross_round_recap,
            enable_map_blueprint=self.server.enable_map_blueprint,
            scenario_id=self.server.scenario_id,
            control_mode=self.server.control_mode,
        )
        player_1_path = run_dir / "player_1_mcp_instructions.md"
        player_2_path = run_dir / "player_2_mcp_instructions.md"
        player_1_path.write_text(player_1_instructions, encoding="utf-8")
        player_2_path.write_text(player_2_instructions, encoding="utf-8")
        self.server.duel_player_1_prompt = player_1_instructions
        self.server.duel_player_2_prompt = player_2_instructions
        self.server.duel_session_id = duel_session_id
        self.server.duel_total_rounds = total_rounds
        self.server.duel_current_round = round_number
        (run_dir / "config.json").write_text(
            json.dumps(
                {
                    "runner": "doom_arena_server_duel_session",
                    "duel_session_id": duel_session_id,
                    "total_rounds": total_rounds,
                    "current_round": round_number,
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
                    "control_mode": self.server.control_mode,
                    "hide_enemy_position": self.server.hide_enemy_position,
                    "randomize_spawns": self.server.duel_randomize_spawns,
                    "scenario_pool": list(self.server.duel_scenario_pool),
                    "enforce_controller_tokens": effective_enforce_tokens,
                    "stats": "stats.json",
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
                "results_dir": str(session_dir),
                "round_results_dir": str(run_dir),
                "duel_session_id": duel_session_id,
                "total_rounds": total_rounds,
                "current_round": round_number,
                "has_next_round": round_number < total_rounds,
                "controller_tokens": str(run_dir / "controller_tokens.json"),
                "stats": str(run_dir / "stats.json"),
                "player_1_instructions": str(player_1_path),
                "player_2_instructions": str(player_2_path),
                "player_1_prompt": player_1_instructions,
                "player_2_prompt": player_2_instructions,
                "decision_cadence_ms": decision_cadence_ms,
                "intent_duration_ms": intent_duration_ms,
                "hide_enemy_position": self.server.hide_enemy_position,
                "randomize_spawns": self.server.duel_randomize_spawns,
                "rotate_all_maps": bool(payload.get("rotate_all_maps", False)),
                "scenario_pool": list(self.server.duel_scenario_pool),
                "scenario_history": list(self.server.duel_scenario_history),
                "control_mode": self.server.control_mode,
                "enable_cross_round_recap": self.server.enable_cross_round_recap,
                "recap_window": self.server.recap_window,
                "enable_map_blueprint": self.server.enable_map_blueprint,
                "enable_weapon_pickups": self.server.enable_weapon_pickups,
                "mirror_pair": self.server.mirror_pair,
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

        self.server.hide_enemy_position = bool(payload.get("hide_enemy_position", False))
        self.server.enable_cross_round_recap = bool(payload.get("enable_cross_round_recap", False))
        self.server.recap_window = 0
        self.server.enable_map_blueprint = bool(payload.get("enable_map_blueprint", False))
        self.server.enable_weapon_pickups = bool(payload.get("enable_weapon_pickups", True))
        self.server.mirror_pair = bool(payload.get("mirror_pair", False))
        self.server.control_mode = normalize_control_mode(payload.get("control_mode", CONTROL_MODE_HIERARCHICAL))

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
        round_results_dir = self.run_dir()
        if self.server.duel_session_id:
            results_dir = RESULTS_ROOT / self.server.duel_session_id
        else:
            results_dir = round_results_dir
        player_1_prompt = self.duel_prompt_text("player_1")
        player_2_prompt = self.duel_prompt_text("player_2")
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
            "duel_session_id": self.server.duel_session_id,
            "total_rounds": self.server.duel_total_rounds,
            "current_round": self.server.duel_current_round,
            "has_next_round": self.server.duel_current_round < self.server.duel_total_rounds,
            "results_dir": str(results_dir),
            "round_results_dir": str(round_results_dir),
            "player_1_prompt": player_1_prompt,
            "player_2_prompt": player_2_prompt,
            "hide_enemy_position": self.server.hide_enemy_position,
            "randomize_spawns": self.server.duel_randomize_spawns,
            "rotate_all_maps": len(self.server.duel_scenario_pool) > 1 and not self.server.duel_randomize_spawns,
            "scenario_pool": list(self.server.duel_scenario_pool),
            "scenario_history": list(self.server.duel_scenario_history),
            "control_mode": self.server.control_mode,
            "enable_cross_round_recap": self.server.enable_cross_round_recap,
            "recap_window": self.server.recap_window,
            "enable_map_blueprint": self.server.enable_map_blueprint,
            "enable_weapon_pickups": self.server.enable_weapon_pickups,
            "mirror_pair": self.server.mirror_pair,
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

    return parse_tsv_rows(ARENA_STATE_TSV.read_text(encoding="utf-8", errors="replace"))


CONFIG_COLUMN_HIDE_ENEMY = "hide_enemy_position"


def inject_arena_config_row(text: str, hide_enemy_position: bool) -> str:
    """Append a duel-config column + synthetic config row to the state TSV.

    Doom WASM writes the file with a fixed header; we extend it with a single
    config column so the existing zip-based parser picks up the value on an
    `arena_config` row that the observation builder can find by kind.
    """
    lines = text.splitlines()
    if not lines:
        return text
    header_cols = lines[0].split("\t")
    if CONFIG_COLUMN_HIDE_ENEMY not in header_cols:
        header_cols.append(CONFIG_COLUMN_HIDE_ENEMY)
        lines[0] = "\t".join(header_cols)
    try:
        kind_idx = header_cols.index("kind")
    except ValueError:
        return text
    config_idx = header_cols.index(CONFIG_COLUMN_HIDE_ENEMY)
    row = [""] * len(header_cols)
    row[kind_idx] = "arena_config"
    row[config_idx] = "1" if hide_enemy_position else "0"
    lines.append("\t".join(row))
    return "\n".join(lines) + "\n"


def parse_tsv_rows(text: str) -> list[dict[str, str]]:
    rows = text.splitlines()
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
    public_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    server_url = f"http://{public_host}:{port}"
    return {
        "ok": True,
        "transport": "stdio",
        "server_url": server_url,
        "base_url_env": f"DOOM_ARENA_BASE_URL={server_url}",
        "mcp_url": f"{server_url}/mcp",
        "claude_stdio": (
            "DOOM_ARENA_BASE_URL="
            f"{server_url} claude mcp add doom-arena -- python scripts/doom_arena_mcp.py"
        ),
        "codex_stdio_config": (
            'command = "python"\n'
            'args = ["scripts/doom_arena_mcp.py"]\n'
            f'env = {{ DOOM_ARENA_BASE_URL = "{server_url}" }}'
        ),
        "note": (
            "Docker runs the arena backend; desktop MCP clients should launch the host-side "
            "stdio script and point DOOM_ARENA_BASE_URL at this server URL."
        ),
    }


def print_mcp_help(host: str, port: int) -> None:
    config = mcp_config_payload(host, port)
    print("MCP backend URL for host-side stdio clients:")
    print(f"  {config['base_url_env']}")
    print("MCP config helper endpoint:")
    print(f"  {config['server_url']}/api/arena/mcp-config")
    print("Launch MCP with scripts/doom_arena_mcp.py from the host.")


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
