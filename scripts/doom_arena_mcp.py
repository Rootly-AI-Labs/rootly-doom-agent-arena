#!/usr/bin/env python3
"""MCP wrapper for Doom Agent Arena local endpoints."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


VALID_ENEMY_COMMANDS = {"normal", "hold", "chase_player", "guard_position"}
DEFAULT_SCENARIO_ID = "e1m8_arena"
ENEMY_COMMAND_HEADER = (
    "run_id\tscenario_id\tcommand_id\tissued_at_ms\texpires_at_ms\t"
    "target_type\ttarget\tcommand\targ1\targ2\n"
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
    "strafe_direction\tmovement_bias\tfire_policy\tdistance_policy\treplan_if\tsequence_number\tdecision_cadence_ms\t"
    "aim_tolerance\tfire_burst_ms\tmin_fire_alignment\tmin_distance\tmax_distance\t"
    "retreat_if_closer_than\tpush_if_farther_than\tlos_lost_action\tstuck_recovery_strategy\tmovement_primitive\t"
    "turn_policy\tnavigation_target\tfire_mode\tintent_raw\n"
)
PARTICIPANT_READY_HEADER = "run_id\tscenario_id\tparticipant_id\tready_at_ms\tstatus\n"
PARTICIPANT_READY_KEYS = ["run_id", "scenario_id", "participant_id", "ready_at_ms", "status"]
PARTICIPANTS = {"player_1", "player_2"}
VALID_PARTICIPANT_INTENTS = {"hold", "engage_opponent", "strafe_attack", "search"}
VALID_PARTICIPANT_INTENT_STYLES = {"balanced", "aggressive", "evasive", "cautious"}
VALID_STRAFE_DIRECTIONS = {"left", "right", "alternate", "auto", "hold_direction", "switch_if_hit"}
VALID_MOVEMENT_BIASES = {"direct", "circle", "evasive", "cautious"}
VALID_FIRE_POLICIES = {"hold_fire", "only_when_aligned", "burst_when_aligned", "suppressive"}
VALID_DISTANCE_POLICIES = {"close", "maintain", "kite"}
VALID_REPLAN_TRIGGERS = {"lost_los", "stuck", "low_health", "target_far", "target_close"}
VALID_LOS_LOST_ACTIONS = {"turn_left", "turn_right", "advance_last_seen", "hold_angle", "sweep"}
VALID_STUCK_RECOVERY_STRATEGIES = {"back_up", "turn_left", "turn_right", "strafe_out", "default"}
VALID_MOVEMENT_PRIMITIVES = {
    "advance",
    "retreat",
    "strafe_left",
    "strafe_right",
    "circle_left",
    "circle_right",
    "hold_position",
}
VALID_TURN_POLICIES = {"auto", "turn_to_enemy", "sweep_left", "sweep_right", "hold_angle", "face_last_seen"}
VALID_NAVIGATION_TARGETS = {"none", "opponent", "last_seen_enemy", "center", "left_lane", "right_lane", "keep_distance"}
VALID_FIRE_MODES = {"auto", "hold_fire", "fire_when_aligned", "single_shot", "burst", "suppressive"}
REPO_ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_TOKENS_PATH = REPO_ROOT / "src" / "arena_controller_tokens.local.json"
MCP_LOG_PATH = os.environ.get("DOOM_ARENA_MCP_LOG", str(REPO_ROOT / "src" / "arena_mcp_stdio.log"))
MCP_OUTPUT_FRAMING = "content-length"


def env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


EXPOSE_LOW_LEVEL_PARTICIPANT_MCP = env_flag("DOOM_ARENA_EXPOSE_LOW_LEVEL_MCP")
PARTICIPANT_TELEMETRY: dict[tuple[str, str], dict[str, int | None]] = {}
EXTERNAL_MCP_CALL_COUNTER = 0


def now_ms() -> int:
    return int(time.time() * 1000)


def log_mcp(message: str) -> None:
    if not MCP_LOG_PATH:
        return
    try:
        with open(MCP_LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {message}\n")
    except OSError:
        pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MCP server for Doom Agent Arena.")
    default_server_url = os.environ.get(
        "DOOM_ARENA_BASE_URL",
        os.environ.get("DOOM_ARENA_SERVER", "http://127.0.0.1:8001"),
    )
    parser.add_argument(
        "--server-url",
        default=default_server_url,
        help="Root URL of scripts/doom_arena_server.py.",
    )
    return parser.parse_args()


class DoomArenaError(RuntimeError):
    pass


class DoomArenaClient:
    # Don't re-POST presence on every single tool call; refreshing well inside
    # the server's 25s stale window keeps the client "connected" without spam.
    PRESENCE_MIN_PING_INTERVAL_MS = 5000

    def __init__(self, server_url: str):
        self.server_url = server_url.rstrip("/")
        self.run_id = "run_unknown"
        self.scenario_id = DEFAULT_SCENARIO_ID
        self.client_name = ""
        self.client_version = ""
        self.client_id = f"mcp_{os.getpid()}"
        self._last_presence_ping_ms = 0
        # Keep MCP startup independent from the browser/arena HTTP state. Some
        # MCP clients expect initialize to be answered immediately and will mark
        # the server failed if startup performs slow network work.

    def note_client_initialized(self, params: dict[str, Any]) -> None:
        client_info = params.get("clientInfo") if isinstance(params, dict) else {}
        if not isinstance(client_info, dict):
            client_info = {}

        # Capture identity for later labeling, but do NOT register presence here.
        # `initialize` fires whenever any assistant merely has this MCP server
        # configured; presence should reflect agents actively using the arena,
        # which we detect from real tool calls (see mark_active).
        self.client_name = str(client_info.get("name", "") or "unknown MCP client").strip()
        self.client_version = str(client_info.get("version", "") or "").strip()
        self.client_id = f"{self.client_name.lower() or 'mcp'}:{os.getpid()}"

    def mark_active(self) -> None:
        """Refresh presence in response to a real arena tool call (throttled)."""
        now = now_ms()
        if now - self._last_presence_ping_ms < self.PRESENCE_MIN_PING_INTERVAL_MS:
            return
        self._last_presence_ping_ms = now
        self._post_presence_ping()

    def _post_presence_ping(self) -> None:
        body = json.dumps(
            {
                "client_id": self.client_id,
                "client_name": self.client_name,
                "client_version": self.client_version,
                "connected_at_ms": now_ms(),
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            self.server_url + "/api/arena/mcp-presence",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        try:
            with urllib.request.urlopen(request, timeout=0.5) as response:
                response.read()
        except (OSError, urllib.error.URLError) as exc:
            log_mcp(f"mcp presence post failed: {exc}")

    def agent_label(self) -> str:
        if self.client_name and self.client_version:
            return f"{self.client_name} {self.client_version}"
        return self.client_name or "MCP agent"

    def get_arena_state(self, run_id: str | None = None) -> str:
        rows = parse_state(self._request("GET", "/api/arena/state"))
        state = make_shared_arena_state(rows)
        if run_id and state.get("run_id") not in {"", run_id}:
            raise DoomArenaError(f"latest state run_id {state.get('run_id')} does not match requested {run_id}")
        return json.dumps(state, indent=2)

    def get_player_observation(self) -> str:
        state = parse_state(self._request("GET", "/api/arena/state"))
        return json.dumps(make_player_observation(state), indent=2)

    def get_enemy_observation(self) -> str:
        state = parse_state(self._request("GET", "/api/arena/state"))
        return json.dumps(make_enemy_observation(state), indent=2)

    def get_match_result(self, run_id: str | None = None) -> str:
        rows = parse_state(self._request("GET", "/api/arena/state"))
        state = make_shared_arena_state(rows)
        duel_session = self._read_duel_session_status()
        if run_id and state.get("run_id") not in {"", run_id}:
            raise DoomArenaError(f"latest state run_id {state.get('run_id')} does not match requested {run_id}")
        return json.dumps(
            {
                "run_id": state.get("run_id", ""),
                "scenario_id": state.get("scenario_id", ""),
                "mode": state.get("mode", ""),
                "phase": state.get("phase", ""),
                "winner": state.get("winner", ""),
                "terminal_reason": state.get("terminal_reason", ""),
                "elapsed_time_seconds": state.get("elapsed_time_seconds", 0),
                "timeout_seconds": state.get("timeout_seconds", 120),
                "duel_session_id": duel_session.get("duel_session_id", ""),
                "current_round": duel_session.get("current_round", state.get("player_1", {}).get("round")),
                "total_rounds": duel_session.get("total_rounds", 1),
                "has_next_round": duel_session.get("has_next_round", False),
                "player_1": state.get("player_1", {}),
                "player_2": state.get("player_2", {}),
            },
            indent=2,
        )

    def get_duel_events(self, run_id: str | None = None, limit: int = 25) -> str:
        try:
            rows = parse_state(self._request("GET", "/api/arena/events"))
        except DoomArenaError:
            rows = []
        if run_id:
            rows = [row for row in rows if row.get("run_id", "") in {"", run_id}]
        limit = clamp_int(limit, 1, 5000, 25)
        return json.dumps({"events": rows[-limit:]}, indent=2)

    def get_participant_observation(self, participant_id: str, controller_token: str | None = None) -> str:
        participant_id = normalize_participant_id(participant_id)
        self._verify_controller_token(participant_id, controller_token)
        state = parse_state(self._request("GET", "/api/arena/state"))
        observation = make_participant_observation(state, participant_id)
        duel_session = self._read_duel_session_status()
        observation["duel_session_id"] = duel_session.get("duel_session_id", "")
        observation["current_round"] = duel_session.get("current_round", observation.get("state", {}).get(participant_id, {}).get("round"))
        observation["total_rounds"] = duel_session.get("total_rounds", 1)
        observation["has_next_round"] = duel_session.get("has_next_round", False)
        if isinstance(observation.get("state"), dict):
            observation["state"]["duel_session_id"] = observation["duel_session_id"]
            observation["state"]["current_round"] = observation["current_round"]
            observation["state"]["total_rounds"] = observation["total_rounds"]
            observation["state"]["has_next_round"] = observation["has_next_round"]
        # Phase 1: cross-round recap
        if duel_session.get("enable_cross_round_recap"):
            observation["previous_rounds"] = self._fetch_previous_rounds_recap(
                participant_id,
                int(duel_session.get("current_round", 1)),
                str(duel_session.get("duel_session_id", "")),
                int(duel_session.get("recap_window", 0)),
            )
        return json.dumps(observation, indent=2)

    def _fetch_previous_rounds_recap(
        self,
        participant_id: str,
        current_round: int,
        duel_session_id: str,
        window: int,
    ) -> list[dict]:
        try:
            url = (
                f"/api/arena/previous-rounds-recap"
                f"?participant_id={participant_id}"
                f"&duel_session_id={duel_session_id}"
                f"&current_round={current_round}"
                f"&window={window}"
            )
            text = self._request("GET", url)
            data = json.loads(text) if text else {}
            return data.get("rounds", [])
        except Exception:
            return []

    def set_participant_ready(self, participant_id: str, controller_token: str | None = None) -> str:
        participant_id = normalize_participant_id(participant_id)
        self._verify_controller_token(participant_id, controller_token)
        ready_at = now_ms()
        payload = {
            "run_id": self.run_id,
            "scenario_id": self.scenario_id,
            "participant_id": participant_id,
            "ready_at_ms": ready_at,
            "status": "ready",
            "agent_label": self.agent_label(),
        }
        response_text = self._request(
            "POST",
            "/api/arena/participant-ready",
            json.dumps(payload).encode("utf-8"),
            "application/json; charset=utf-8",
        )
        return json.dumps(
            {
                "accepted": True,
                "participant_id": participant_id,
                "agent_label": self.agent_label(),
                "ready": True,
                "ready_at_ms": ready_at,
                "server_response": parse_optional_json(response_text),
            },
            indent=2,
        )

    def wait_for_match_start(
        self,
        participant_id: str,
        controller_token: str | None = None,
        timeout_ms: int = 60000,
        poll_ms: int = 250,
    ) -> str:
        participant_id = normalize_participant_id(participant_id)
        self._verify_controller_token(participant_id, controller_token)
        timeout_ms = clamp_int(timeout_ms, 100, 300000, 60000)
        poll_ms = clamp_int(poll_ms, 50, 5000, 250)
        started_at = now_ms()
        latest_state: dict[str, Any] = {}
        ready_participants: set[str] = set()
        intent_participants: set[str] = set()
        while now_ms() - started_at <= timeout_ms:
            try:
                rows = parse_state(self._request("GET", "/api/arena/state"))
                latest_state = make_shared_arena_state(rows)
            except DoomArenaError as exc:
                latest_state = {"phase": "unavailable", "error": str(exc)}
            phase = str(latest_state.get("phase", ""))
            participant_state = latest_state.get(participant_id, {})
            state_run_id = str(latest_state.get("run_id", self.run_id or ""))
            state_scenario_id = str(latest_state.get("scenario_id", self.scenario_id or ""))
            ready_participants = {
                row.get("participant_id", "")
                for row in self._read_participant_ready_rows()
                if row.get("run_id", "") == state_run_id
                and row.get("scenario_id", "") == state_scenario_id
                and row.get("participant_id", "") in PARTICIPANTS
                and row.get("status", "") == "ready"
            }
            try:
                intent_rows = self._read_participant_intent_rows()
                current_ms = now_ms()
                intent_participants = {
                    row.get("participant_id", "")
                    for row in intent_rows
                    if row.get("run_id", "") == state_run_id
                    and row.get("scenario_id", "") == state_scenario_id
                    and row.get("participant_id", "") in PARTICIPANTS
                    and row.get("intent", "") not in {"", "none"}
                    and int(row.get("expires_at_ms", "0") or 0) > current_ms
                }
            except DoomArenaError:
                intent_participants = set()
            if (
                phase == "waiting_for_agents"
                and isinstance(participant_state, dict)
                and str(participant_state.get("intent", "none")) in {"", "none"}
                and str(participant_state.get("intent_status", "inactive")) == "inactive"
                and participant_id not in intent_participants
            ):
                return json.dumps(
                    {
                        "started": False,
                        "phase": phase,
                        "participant_id": participant_id,
                        "needs_opening_intent": True,
                        "instruction": (
                            "Call set_participant_intent once with an opening high-level intent "
                            "before waiting again. Doom will hold it until the other participant "
                            "also has an opening intent."
                        ),
                        "elapsed_wait_ms": now_ms() - started_at,
                        "run_id": latest_state.get("run_id", ""),
                    },
                    indent=2,
                )
            if phase and phase != "waiting_for_agents" and phase != "unavailable":
                return json.dumps(
                    {
                        "started": phase == "combat",
                        "phase": phase,
                        "participant_id": participant_id,
                        "elapsed_wait_ms": now_ms() - started_at,
                        "run_id": latest_state.get("run_id", ""),
                    },
                    indent=2,
                )
            time.sleep(poll_ms / 1000.0)

        return json.dumps(
            {
                "started": False,
                "phase": latest_state.get("phase", "waiting_for_agents"),
                "participant_id": participant_id,
                "elapsed_wait_ms": now_ms() - started_at,
                "timeout_ms": timeout_ms,
                "run_id": latest_state.get("run_id", ""),
                "ready_participants": sorted(ready_participants),
                "intent_participants": sorted(intent_participants),
                "missing_ready_participants": sorted(PARTICIPANTS - ready_participants),
                "missing_opening_intent_participants": sorted(PARTICIPANTS - intent_participants),
            },
            indent=2,
        )

    def set_participant_input(
        self,
        participant_id: str,
        forward: int = 0,
        strafe: int = 0,
        turn: int = 0,
        attack: bool = False,
        use: bool = False,
        duration_ms: int = 750,
        controller_token: str | None = None,
    ) -> str:
        participant_id = normalize_participant_id(participant_id)
        self._verify_controller_token(participant_id, controller_token)
        forward = clamp_int(forward, -1, 1)
        strafe = clamp_int(strafe, -1, 1)
        turn = clamp_int(turn, -1, 1)
        attack = bool(attack)
        use = bool(use)
        duration_ms = clamp_int(duration_ms, 100, 2000, 750)
        rows = [
            row for row in self._read_participant_command_rows()
            if row["participant_id"] != participant_id
        ]
        command = self._participant_command_row(
            participant_id,
            forward,
            strafe,
            turn,
            attack,
            use,
            duration_ms,
        )
        rows.append(command)
        self._write_participant_command_rows(rows)
        return json.dumps(
            {
                "accepted": True,
                "participant_id": participant_id,
                "command_id": command["command_id"],
                "run_id": command["run_id"],
                "scenario_id": command["scenario_id"],
                "normalized_command": {
                    "participant_id": participant_id,
                    "forward": forward,
                    "strafe": strafe,
                    "turn": turn,
                    "attack": attack,
                    "use": use,
                    "duration_ms": duration_ms,
                },
            },
            indent=2,
        )

    def stop_participant(self, participant_id: str, controller_token: str | None = None) -> str:
        return self.set_participant_input(participant_id, duration_ms=100, controller_token=controller_token)

    def set_participant_intent(
        self,
        participant_id: str,
        intent: str,
        style: str = "balanced",
        target_id: str | None = None,
        preferred_distance: int = 600,
        aggression: float = 0.5,
        duration_ms: int = 25000,
        controller_token: str | None = None,
        *,
        strafe_direction: str = "auto",
        movement_bias: str = "direct",
        fire_policy: str = "only_when_aligned",
        distance_policy: str = "maintain",
        replan_if: Any = None,
        sequence_number: Any = None,
        decision_cadence_ms: Any = None,
        aim_tolerance: Any = None,
        fire_burst_ms: Any = None,
        min_fire_alignment: Any = None,
        min_distance: Any = None,
        max_distance: Any = None,
        retreat_if_closer_than: Any = None,
        push_if_farther_than: Any = None,
        los_lost_action: str = "sweep",
        stuck_recovery_strategy: str = "default",
        movement_primitive: str = "",
        turn_policy: str = "auto",
        navigation_target: str = "opponent",
        fire_mode: str = "auto",
        rationale: str | None = None,
    ) -> str:
        participant_id = normalize_participant_id(participant_id)
        self._verify_controller_token(participant_id, controller_token)
        intent = normalize_participant_intent(intent)
        style = normalize_participant_intent_style(style)
        target_id = normalize_participant_target(participant_id, target_id)
        preferred_distance = clamp_int(preferred_distance, 1, 10000, 600)
        aggression = clamp_float(aggression, 0.0, 1.0, 0.5)
        duration_ms = clamp_int(duration_ms, 100, 60000, 25000)
        strafe_direction = normalize_tactical_enum(
            strafe_direction,
            "auto",
            VALID_STRAFE_DIRECTIONS,
            "strafe_direction",
        )
        movement_bias = normalize_tactical_enum(
            movement_bias,
            "direct",
            VALID_MOVEMENT_BIASES,
            "movement_bias",
        )
        fire_policy = normalize_tactical_enum(
            fire_policy,
            "only_when_aligned",
            VALID_FIRE_POLICIES,
            "fire_policy",
        )
        distance_policy = normalize_tactical_enum(
            distance_policy,
            "maintain",
            VALID_DISTANCE_POLICIES,
            "distance_policy",
        )
        replan_if_text = normalize_replan_if(replan_if)
        sequence_number_text = normalize_optional_nonnegative_int(sequence_number, "sequence_number")
        decision_cadence_ms_text = normalize_optional_positive_int(decision_cadence_ms, "decision_cadence_ms")
        aim_tolerance_text = normalize_optional_int_range(
            aim_tolerance,
            "aim_tolerance",
            minimum=0,
            maximum=180,
        )
        fire_burst_ms_text = normalize_optional_int_range(
            fire_burst_ms,
            "fire_burst_ms",
            minimum=0,
            maximum=60000,
        )
        min_fire_alignment_text = normalize_optional_int_range(
            min_fire_alignment,
            "min_fire_alignment",
            minimum=0,
            maximum=180,
        )
        min_distance_text = normalize_optional_int_range(min_distance, "min_distance", minimum=0)
        max_distance_text = normalize_optional_int_range(max_distance, "max_distance", minimum=0)
        retreat_if_closer_than_text = normalize_optional_int_range(
            retreat_if_closer_than,
            "retreat_if_closer_than",
            minimum=0,
        )
        push_if_farther_than_text = normalize_optional_int_range(
            push_if_farther_than,
            "push_if_farther_than",
            minimum=0,
        )
        if min_distance_text and max_distance_text and int(min_distance_text) > int(max_distance_text):
            raise DoomArenaError("min_distance must be <= max_distance")
        los_lost_action = normalize_tactical_enum(
            los_lost_action,
            "sweep",
            VALID_LOS_LOST_ACTIONS,
            "los_lost_action",
        )
        stuck_recovery_strategy = normalize_tactical_enum(
            stuck_recovery_strategy,
            "default",
            VALID_STUCK_RECOVERY_STRATEGIES,
            "stuck_recovery_strategy",
        )
        movement_primitive = normalize_tactical_enum(
            movement_primitive,
            "",
            VALID_MOVEMENT_PRIMITIVES,
            "movement_primitive",
            allow_blank=True,
        )
        turn_policy = normalize_tactical_enum(
            turn_policy,
            "auto",
            VALID_TURN_POLICIES,
            "turn_policy",
        )
        navigation_target = normalize_tactical_enum(
            navigation_target,
            "opponent",
            VALID_NAVIGATION_TARGETS,
            "navigation_target",
        )
        fire_mode = normalize_tactical_enum(
            fire_mode,
            "auto",
            VALID_FIRE_MODES,
            "fire_mode",
        )
        issued = now_ms()
        intent_id = f"{participant_id}_intent_{issued}"
        payload = {
            "run_id": self.run_id,
            "scenario_id": self.scenario_id,
            "intent_id": intent_id,
            "issued_at_ms": issued,
            "expires_at_ms": issued + duration_ms,
            "participant_id": participant_id,
            "intent": intent,
            "style": style,
            "target_id": target_id,
            "preferred_distance": preferred_distance,
            "aggression": aggression,
            "duration_ms": duration_ms,
            "strafe_direction": strafe_direction,
            "movement_bias": movement_bias,
            "fire_policy": fire_policy,
            "distance_policy": distance_policy,
            "replan_if": replan_if_text.split(",") if replan_if_text else [],
            "sequence_number": sequence_number_text,
            "decision_cadence_ms": decision_cadence_ms_text,
            "aim_tolerance": aim_tolerance_text,
            "fire_burst_ms": fire_burst_ms_text,
            "min_fire_alignment": min_fire_alignment_text,
            "min_distance": min_distance_text,
            "max_distance": max_distance_text,
            "retreat_if_closer_than": retreat_if_closer_than_text,
            "push_if_farther_than": push_if_farther_than_text,
            "los_lost_action": los_lost_action,
            "stuck_recovery_strategy": stuck_recovery_strategy,
            "movement_primitive": movement_primitive,
            "turn_policy": turn_policy,
            "navigation_target": navigation_target,
            "fire_mode": fire_mode,
        }
        rationale_text = str(rationale).strip() if rationale else ""
        if rationale_text:
            payload["rationale"] = rationale_text[:1024]
        response_text = self._request(
            "POST",
            "/api/arena/participant-intents",
            json.dumps(payload).encode("utf-8"),
            "application/json; charset=utf-8",
        )
        return json.dumps(
            {
                "accepted": True,
                "participant_id": participant_id,
                "intent_id": intent_id,
                "run_id": self.run_id,
                "scenario_id": self.scenario_id,
                "issued_at_ms": issued,
                "expires_at_ms": issued + duration_ms,
                "normalized_intent": {
                    "participant_id": participant_id,
                    "intent": intent,
                    "style": style,
                    "target_id": target_id,
                    "preferred_distance": preferred_distance,
                    "aggression": aggression,
                    "duration_ms": duration_ms,
                    "strafe_direction": strafe_direction,
                    "movement_bias": movement_bias,
                    "fire_policy": fire_policy,
                    "distance_policy": distance_policy,
                    "replan_if": replan_if_text.split(",") if replan_if_text else [],
                    "sequence_number": int(sequence_number_text) if sequence_number_text else None,
                    "decision_cadence_ms": int(decision_cadence_ms_text) if decision_cadence_ms_text else None,
                    "aim_tolerance": int(aim_tolerance_text) if aim_tolerance_text else None,
                    "fire_burst_ms": int(fire_burst_ms_text) if fire_burst_ms_text else None,
                    "min_fire_alignment": int(min_fire_alignment_text) if min_fire_alignment_text else None,
                    "min_distance": int(min_distance_text) if min_distance_text else None,
                    "max_distance": int(max_distance_text) if max_distance_text else None,
                    "retreat_if_closer_than": int(retreat_if_closer_than_text) if retreat_if_closer_than_text else None,
                    "push_if_farther_than": int(push_if_farther_than_text) if push_if_farther_than_text else None,
                    "los_lost_action": los_lost_action,
                    "stuck_recovery_strategy": stuck_recovery_strategy,
                    "movement_primitive": movement_primitive,
                    "turn_policy": turn_policy,
                    "navigation_target": navigation_target,
                    "fire_mode": fire_mode,
                },
                "server_response": parse_optional_json(response_text),
            },
            indent=2,
        )

    def stop_participant_intent(self, participant_id: str, controller_token: str | None = None) -> str:
        participant_id = normalize_participant_id(participant_id)
        self._verify_controller_token(participant_id, controller_token)
        current_ms = now_ms()
        rows = [
            row for row in self._read_participant_intent_rows()
            if row.get("participant_id") != participant_id
            and int(row.get("expires_at_ms", "0") or 0) > current_ms
        ]
        self._write_participant_intent_rows(rows)
        return json.dumps(
            {
                "accepted": True,
                "participant_id": participant_id,
                "cleared": True,
                "run_id": self.run_id,
                "scenario_id": self.scenario_id,
            },
            indent=2,
        )

    def set_player_input(
        self,
        forward: int = 0,
        strafe: int = 0,
        turn: int = 0,
        attack: bool = False,
        use: bool = False,
        duration_ms: int = 250,
    ) -> str:
        issued = now_ms()
        payload = {
            "run_id": self.run_id,
            "scenario_id": self.scenario_id,
            "command_id": f"player_cmd_{issued}",
            "issued_at_ms": issued,
            "expires_at_ms": issued + duration_ms,
            "forward": clamp_int(forward, -1, 1),
            "strafe": clamp_int(strafe, -1, 1),
            "turn": clamp_int(turn, -1, 1),
            "attack": bool(attack),
            "use": bool(use),
            "duration_ms": duration_ms,
        }
        return self._request(
            "POST",
            "/api/arena/player-command",
            json.dumps(payload).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def stop_player(self) -> str:
        return self.set_player_input(duration_ms=100)

    def set_enemy_command(
        self,
        enemy_id: str,
        command: str,
        duration_ms: int = 1000,
        arg1: str = "",
        arg2: str = "",
    ) -> str:
        command = normalize_enemy_command(command)
        rows = self._read_enemy_command_rows()
        rows = [
            row for row in rows
            if not (row["target_type"] == "enemy_id" and row["target"] == enemy_id)
        ]
        if command != "normal":
            rows.append(self._enemy_command_row("enemy_id", enemy_id, command, duration_ms, arg1, arg2))
        return self._write_enemy_command_rows(rows)

    def set_enemy_team_command(
        self,
        command: str,
        duration_ms: int = 1000,
        arg1: str = "",
        arg2: str = "",
    ) -> str:
        command = normalize_enemy_command(command)
        rows = [
            row for row in self._read_enemy_command_rows()
            if not (row["target_type"] == "team" and row["target"] == "enemy")
        ]
        if command != "normal":
            rows.append(self._enemy_command_row("team", "enemy", command, duration_ms, arg1, arg2))
        return self._write_enemy_command_rows(rows)

    def clear_enemy_commands(self) -> str:
        return self._post_enemy_commands(ENEMY_COMMAND_HEADER)

    def reset_arena(self) -> str:
        text = self._request("POST", "/api/arena/reset", b"{}", "application/json; charset=utf-8")
        self._sync_run_metadata_from_text(text)
        return text

    def reset_duel(
        self,
        player_1_model: str = "",
        player_2_model: str = "",
        round_number: int = 1,
        seed: int = 42,
        timeout_seconds: int = 120,
    ) -> str:
        payload = {
            "arena_mode": "duel",
            "player_1_model": str(player_1_model).lower(),
            "player_2_model": str(player_2_model).lower(),
            "round": int(round_number),
            "seed": int(seed),
            "timeout_seconds": int(timeout_seconds),
        }
        text = self._request(
            "POST",
            "/api/arena/reset",
            json.dumps(payload).encode("utf-8"),
            "application/json; charset=utf-8",
        )
        self._sync_run_metadata_from_text(text)
        return text

    def _controller_tokens(self) -> dict[str, Any]:
        try:
            with CONTROLLER_TOKENS_PATH.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except FileNotFoundError:
            return {"enforce_controller_tokens": False}
        except json.JSONDecodeError as exc:
            raise DoomArenaError(f"Invalid controller token file: {CONTROLLER_TOKENS_PATH}") from exc
        if not isinstance(payload, dict):
            raise DoomArenaError(f"Invalid controller token file: {CONTROLLER_TOKENS_PATH}")
        return payload

    def _verify_controller_token(self, participant_id: str, controller_token: str | None) -> None:
        self._sync_run_metadata()
        payload = self._controller_tokens()
        if not bool(payload.get("enforce_controller_tokens", False)):
            return
        token_run_id = str(payload.get("run_id", ""))
        if token_run_id and token_run_id != self.run_id:
            raise DoomArenaError(
                f"Controller token file is for run_id {token_run_id}, but MCP client is on {self.run_id}."
            )
        participant = payload.get(participant_id)
        if not isinstance(participant, dict):
            raise DoomArenaError(f"No controller token configured for {participant_id}.")
        expected = str(participant.get("controller_token", ""))
        if not controller_token:
            raise DoomArenaError(f"controller_token is required for {participant_id}.")
        if str(controller_token) != expected:
            raise DoomArenaError(f"Invalid controller_token for {participant_id}.")

    def look_at_enemy(self, enemy_id: str, duration_ms: int = 250) -> str:
        obs = make_player_observation(parse_state(self._request("GET", "/api/arena/state")))
        enemy = find_enemy(obs["enemies"], enemy_id)
        turn = 1 if enemy["relative_angle_to_player"] > 0 else -1
        if abs(enemy["relative_angle_to_player"]) <= 5:
            turn = 0
        return self.set_player_input(turn=turn, duration_ms=duration_ms)

    def attack_enemy(self, enemy_id: str, duration_ms: int = 250) -> str:
        obs = make_player_observation(parse_state(self._request("GET", "/api/arena/state")))
        enemy = find_enemy(obs["enemies"], enemy_id)
        if abs(enemy["relative_angle_to_player"]) > 5:
            turn = 1 if enemy["relative_angle_to_player"] > 0 else -1
            return self.set_player_input(turn=turn, duration_ms=duration_ms)
        return self.set_player_input(attack=True, duration_ms=duration_ms)

    def move_toward_enemy(self, enemy_id: str, duration_ms: int = 250) -> str:
        obs = make_player_observation(parse_state(self._request("GET", "/api/arena/state")))
        enemy = find_enemy(obs["enemies"], enemy_id)
        turn = 0
        if abs(enemy["relative_angle_to_player"]) > 10:
            turn = 1 if enemy["relative_angle_to_player"] > 0 else -1
        return self.set_player_input(forward=1, turn=turn, duration_ms=duration_ms)

    def _enemy_command_row(
        self,
        target_type: str,
        target: str,
        command: str,
        duration_ms: int,
        arg1: str = "",
        arg2: str = "",
    ) -> dict[str, str]:
        issued = now_ms()
        return {
            "run_id": self.run_id,
            "scenario_id": self.scenario_id,
            "command_id": f"enemy_cmd_{issued}",
            "issued_at_ms": str(issued),
            "expires_at_ms": str(issued + duration_ms),
            "target_type": target_type,
            "target": target,
            "command": command,
            "arg1": arg1,
            "arg2": arg2,
        }

    def _participant_command_row(
        self,
        participant_id: str,
        forward: int,
        strafe: int,
        turn: int,
        attack: bool,
        use: bool,
        duration_ms: int,
    ) -> dict[str, str]:
        issued = now_ms()
        return {
            "run_id": self.run_id,
            "scenario_id": self.scenario_id,
            "command_id": f"{participant_id}_cmd_{issued}",
            "issued_at_ms": str(issued),
            "expires_at_ms": str(issued + duration_ms),
            "participant_id": participant_id,
            "forward": str(clamp_int(forward, -1, 1)),
            "strafe": str(clamp_int(strafe, -1, 1)),
            "turn": str(clamp_int(turn, -1, 1)),
            "attack": "true" if bool(attack) else "false",
            "use": "true" if bool(use) else "false",
            "duration_ms": str(duration_ms),
        }

    def _read_participant_command_rows(self) -> list[dict[str, str]]:
        try:
            body = self._request("GET", "/api/arena/participant-commands")
        except DoomArenaError:
            return []
        return parse_participant_command_rows(body)

    def _write_participant_command_rows(self, rows: list[dict[str, str]]) -> str:
        body = PARTICIPANT_COMMAND_HEADER
        for row in rows:
            body += "\t".join(row.get(key, "") for key in PARTICIPANT_COMMAND_KEYS) + "\n"
        return self._request(
            "POST",
            "/api/arena/participant-commands",
            body.encode("utf-8"),
            "text/tab-separated-values; charset=utf-8",
        )

    def _read_participant_intent_rows(self) -> list[dict[str, str]]:
        try:
            body = self._request("GET", "/api/arena/participant-intents")
        except DoomArenaError:
            return []
        return parse_participant_intent_rows(body)

    def _write_participant_intent_rows(self, rows: list[dict[str, str]]) -> str:
        body = PARTICIPANT_INTENT_HEADER
        for row in rows:
            body += "\t".join(row.get(key, "") for key in PARTICIPANT_INTENT_KEYS) + "\n"
        return self._request(
            "POST",
            "/api/arena/participant-intents",
            body.encode("utf-8"),
            "text/tab-separated-values; charset=utf-8",
        )

    def _read_participant_ready_rows(self) -> list[dict[str, str]]:
        try:
            body = self._request("GET", "/api/arena/participant-ready")
        except DoomArenaError:
            return []
        return parse_participant_ready_rows(body)

    def _read_duel_session_status(self) -> dict[str, Any]:
        try:
            payload = json.loads(self._request("GET", "/api/arena/reset"))
        except (DoomArenaError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _read_enemy_command_rows(self) -> list[dict[str, str]]:
        try:
            body = self._request("GET", "/api/arena/enemy-commands")
        except DoomArenaError:
            return []
        return parse_enemy_command_rows(body)

    def _write_enemy_command_rows(self, rows: list[dict[str, str]]) -> str:
        body = ENEMY_COMMAND_HEADER
        for row in rows:
            body += "\t".join(row.get(key, "") for key in ENEMY_COMMAND_KEYS) + "\n"
        return self._post_enemy_commands(body)

    def _post_enemy_commands(self, body: str) -> str:
        return self._request(
            "POST",
            "/api/arena/enemy-commands",
            body.encode("utf-8"),
            "text/tab-separated-values; charset=utf-8",
        )

    def _sync_run_metadata(self) -> None:
        try:
            self._sync_run_metadata_from_tsv(self._request("GET", "/api/arena/run-metadata"))
        except DoomArenaError:
            pass

    def _sync_run_metadata_from_text(self, text: str) -> None:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return
        self.run_id = str(payload.get("run_id", self.run_id))
        self.scenario_id = str(payload.get("scenario_id", self.scenario_id))

    def _sync_run_metadata_from_tsv(self, text: str) -> None:
        rows = parse_state(text)
        if not rows:
            return
        row = rows[0]
        self.run_id = str(row.get("run_id", self.run_id))
        self.scenario_id = str(row.get("scenario_id", self.scenario_id))

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
            raise DoomArenaError(f"{method} {path} failed with HTTP {exc.code}: {body}") from exc
        except OSError as exc:
            raise DoomArenaError(
                f"Could not reach Doom Arena server at {self.server_url}. "
                "Run: py scripts\\doom_arena_server.py --port 8001"
            ) from exc

    def post_mcp_call_telemetry(self, payload: dict[str, Any]) -> None:
        try:
            self._request(
                "POST",
                "/api/arena/mcp-call-telemetry",
                json.dumps(payload).encode("utf-8"),
                "application/json; charset=utf-8",
            )
        except DoomArenaError as exc:
            log_mcp(f"failed to post MCP telemetry: {exc}")


ENEMY_COMMAND_KEYS = [
    "run_id",
    "scenario_id",
    "command_id",
    "issued_at_ms",
    "expires_at_ms",
    "target_type",
    "target",
    "command",
    "arg1",
    "arg2",
]

PARTICIPANT_COMMAND_KEYS = [
    "run_id",
    "scenario_id",
    "command_id",
    "issued_at_ms",
    "expires_at_ms",
    "participant_id",
    "forward",
    "strafe",
    "turn",
    "attack",
    "use",
    "duration_ms",
]

PARTICIPANT_INTENT_KEYS = [
    "run_id",
    "scenario_id",
    "intent_id",
    "issued_at_ms",
    "expires_at_ms",
    "participant_id",
    "intent",
    "style",
    "target_id",
    "preferred_distance",
    "aggression",
    "duration_ms",
    "strafe_direction",
    "movement_bias",
    "fire_policy",
    "distance_policy",
    "replan_if",
    "sequence_number",
    "decision_cadence_ms",
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
]
PARTICIPANT_INTENT_LEGACY_KEYS = PARTICIPANT_INTENT_KEYS[:12]


def clamp_int(value: Any, low: int, high: int, default: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(low, min(high, parsed))


def clamp_float(value: Any, low: float, high: float, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(low, min(high, parsed))


def normalize_enemy_command(command: str) -> str:
    command = command.strip().lower()
    if command not in VALID_ENEMY_COMMANDS:
        raise DoomArenaError("command must be one of normal, hold, chase_player, guard_position")
    return command


def normalize_participant_id(participant_id: str) -> str:
    participant_id = participant_id.strip().lower()
    if participant_id not in PARTICIPANTS:
        raise DoomArenaError("participant_id must be player_1 or player_2")
    return participant_id


def normalize_participant_intent(intent: str) -> str:
    intent = intent.strip().lower()
    if intent not in VALID_PARTICIPANT_INTENTS:
        raise DoomArenaError(
            "intent must be one of "
            + ", ".join(sorted(VALID_PARTICIPANT_INTENTS))
        )
    return intent


def normalize_participant_intent_style(style: str) -> str:
    style = style.strip().lower()
    if style not in VALID_PARTICIPANT_INTENT_STYLES:
        raise DoomArenaError(
            "style must be one of "
            + ", ".join(sorted(VALID_PARTICIPANT_INTENT_STYLES))
        )
    return style


def normalize_participant_target(participant_id: str, target_id: str | None) -> str:
    target = (target_id or ("player_2" if participant_id == "player_1" else "player_1")).strip().lower()
    if target not in PARTICIPANTS:
        raise DoomArenaError("target_id must be player_1 or player_2")
    if target == participant_id:
        raise DoomArenaError("target_id must be the opposing participant")
    return target


def normalize_tactical_enum(
    value: Any,
    default: str,
    allowed: set[str],
    field_name: str,
    *,
    allow_blank: bool = False,
) -> str:
    text = str(value if value is not None else default).strip().lower()
    if not text:
        if allow_blank:
            return ""
        text = default
    if text not in allowed:
        raise DoomArenaError(f"{field_name} must be one of " + ", ".join(sorted(allowed)))
    return text


def normalize_replan_if(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, str):
        triggers = [part.strip().lower() for part in value.split(",") if part.strip()]
    elif isinstance(value, list):
        triggers = [str(part).strip().lower() for part in value if str(part).strip()]
    else:
        raise DoomArenaError("replan_if must be a list or comma-separated string")
    invalid = [trigger for trigger in triggers if trigger not in VALID_REPLAN_TRIGGERS]
    if invalid:
        raise DoomArenaError(
            "replan_if contains invalid trigger(s): "
            + ", ".join(invalid)
            + ". Allowed: "
            + ", ".join(sorted(VALID_REPLAN_TRIGGERS))
        )
    return ",".join(triggers)


def normalize_optional_nonnegative_int(value: Any, field_name: str) -> str:
    if value is None or value == "":
        return ""
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise DoomArenaError(f"{field_name} must be an integer") from exc
    if parsed < 0:
        raise DoomArenaError(f"{field_name} must be >= 0")
    return str(parsed)


def normalize_optional_positive_int(value: Any, field_name: str) -> str:
    if value is None or value == "":
        return ""
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise DoomArenaError(f"{field_name} must be an integer") from exc
    if parsed <= 0:
        raise DoomArenaError(f"{field_name} must be positive")
    return str(parsed)


def normalize_optional_int_range(
    value: Any,
    field_name: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> str:
    if value is None or value == "":
        return ""
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise DoomArenaError(f"{field_name} must be an integer") from exc
    if minimum is not None and parsed < minimum:
        raise DoomArenaError(f"{field_name} must be >= {minimum}")
    if maximum is not None and parsed > maximum:
        raise DoomArenaError(f"{field_name} must be <= {maximum}")
    return str(parsed)


def optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_optional_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def parse_participant_command_rows(body: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line_number, line in enumerate(body.splitlines(), 1):
        if not line.strip():
            continue
        parts = line.split("\t")
        if line_number == 1 and parts[0] == "run_id":
            continue
        if len(parts) < len(PARTICIPANT_COMMAND_KEYS):
            continue
        row = dict(zip(PARTICIPANT_COMMAND_KEYS, parts[:len(PARTICIPANT_COMMAND_KEYS)]))
        if row["participant_id"] in PARTICIPANTS:
            rows.append(row)
    return rows


def parse_participant_intent_rows(body: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line_number, line in enumerate(body.splitlines(), 1):
        if not line.strip():
            continue
        parts = line.split("\t")
        if line_number == 1 and parts[0] == "run_id":
            continue
        if len(parts) < len(PARTICIPANT_INTENT_LEGACY_KEYS):
            continue
        row = dict(zip(PARTICIPANT_INTENT_KEYS, parts[:len(PARTICIPANT_INTENT_KEYS)]))
        row.setdefault("strafe_direction", "auto")
        row.setdefault("movement_bias", "direct")
        row.setdefault("fire_policy", "only_when_aligned")
        row.setdefault("distance_policy", "maintain")
        row.setdefault("replan_if", "")
        row.setdefault("sequence_number", "")
        row.setdefault("decision_cadence_ms", "")
        row.setdefault("aim_tolerance", "")
        row.setdefault("fire_burst_ms", "")
        row.setdefault("min_fire_alignment", "")
        row.setdefault("min_distance", "")
        row.setdefault("max_distance", "")
        row.setdefault("retreat_if_closer_than", "")
        row.setdefault("push_if_farther_than", "")
        row.setdefault("los_lost_action", "sweep")
        row.setdefault("stuck_recovery_strategy", "default")
        row.setdefault("movement_primitive", "")
        row.setdefault("turn_policy", "auto")
        row.setdefault("navigation_target", "opponent")
        row.setdefault("fire_mode", "auto")
        if (
            row["participant_id"] in PARTICIPANTS
            and row["target_id"] in PARTICIPANTS
            and row["target_id"] != row["participant_id"]
            and row["intent"] in VALID_PARTICIPANT_INTENTS
            and row["style"] in VALID_PARTICIPANT_INTENT_STYLES
            and row["strafe_direction"] in VALID_STRAFE_DIRECTIONS
            and row["movement_bias"] in VALID_MOVEMENT_BIASES
            and row["fire_policy"] in VALID_FIRE_POLICIES
            and row["distance_policy"] in VALID_DISTANCE_POLICIES
            and row["los_lost_action"] in VALID_LOS_LOST_ACTIONS
            and row["stuck_recovery_strategy"] in VALID_STUCK_RECOVERY_STRATEGIES
            and (row["movement_primitive"] == "" or row["movement_primitive"] in VALID_MOVEMENT_PRIMITIVES)
            and row["turn_policy"] in VALID_TURN_POLICIES
            and row["navigation_target"] in VALID_NAVIGATION_TARGETS
            and row["fire_mode"] in VALID_FIRE_MODES
        ):
            rows.append(row)
    return rows


def parse_participant_ready_rows(body: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line_number, line in enumerate(body.splitlines(), 1):
        if not line.strip():
            continue
        parts = line.split("\t")
        if line_number == 1 and parts == PARTICIPANT_READY_KEYS:
            continue
        if len(parts) != len(PARTICIPANT_READY_KEYS):
            continue
        row = dict(zip(PARTICIPANT_READY_KEYS, parts))
        if (
            row["participant_id"] in PARTICIPANTS
            and row["status"] == "ready"
            and row["ready_at_ms"].isdigit()
            and int(row["ready_at_ms"]) > 0
        ):
            rows.append(row)
    return rows


def parse_enemy_command_rows(body: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line_number, line in enumerate(body.splitlines(), 1):
        if not line.strip():
            continue
        parts = line.split("\t")
        if line_number == 1 and parts[0] == "run_id":
            continue
        if line_number == 1 and parts[0] == "target_type":
            continue
        if len(parts) >= 10:
            row = dict(zip(ENEMY_COMMAND_KEYS, parts[:10]))
        elif len(parts) >= 3:
            issued = str(now_ms())
            row = {
                "run_id": "run_unknown",
                "scenario_id": DEFAULT_SCENARIO_ID,
                "command_id": f"legacy_enemy_cmd_{line_number}",
                "issued_at_ms": issued,
                "expires_at_ms": str(int(issued) + 1000),
                "target_type": parts[0],
                "target": parts[1],
                "command": parts[2],
                "arg1": "",
                "arg2": "",
            }
        else:
            continue

        if row["target_type"] in {"team", "enemy_id"} and row["command"] in VALID_ENEMY_COMMANDS:
            rows.append(row)
    return rows


def parse_state(body: str) -> list[dict[str, str]]:
    lines = body.splitlines()
    if not lines:
        return []
    header = lines[0].split("\t")
    rows = []
    for line in lines[1:]:
        if line.strip():
            rows.append(dict(zip(header, line.split("\t"))))
    return rows


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


def first_value(rows: list[dict[str, str]], key: str, default: str = "") -> str:
    for row in rows:
        value = row.get(key, "")
        if value != "":
            return value
    return default


def distance_bucket(distance: int, preferred_distance: int) -> str:
    preferred = preferred_distance if preferred_distance > 0 else 600
    if distance <= 0:
        return "unknown"
    if distance < max(1, int(preferred * 0.7)):
        return "close"
    if distance > max(1, int(preferred * 1.5)):
        return "far"
    return "ideal"


def pressure_state(health: int, opponent_health: int) -> str:
    if health <= 0:
        return "dead"
    if health <= 25:
        return "critical"
    delta = health - opponent_health
    if delta >= 25:
        return "winning"
    if delta <= -25:
        return "losing"
    return "even"


def executed_fire_action(autopilot_action: str) -> str:
    return "attack" if "attack" in autopilot_action else "hold_fire"


def executed_movement_action(autopilot_action: str) -> str:
    if not autopilot_action or autopilot_action == "none":
        return "none"
    return autopilot_action.replace("+attack", "")


def executed_strafe_direction(strafe_direction: str, autopilot_action: str) -> str:
    if not any(part in autopilot_action for part in ("strafe", "circle", "kite", "evasive", "backoff", "unstick")):
        return "none"
    if strafe_direction in {"left", "right"}:
        return strafe_direction
    if strafe_direction == "alternate":
        return "alternating"
    return "auto"


def policy_compliance_reason(observation: dict[str, Any]) -> str:
    reasons = []
    if observation.get("fire_policy") == "hold_fire" and observation.get("executed_fire_action") == "hold_fire":
        reasons.append("fire_policy_obeyed")
    elif observation.get("fire_policy") == "suppressive" and observation.get("executed_fire_action") == "attack":
        reasons.append("suppressive_fire_allowed")
    elif observation.get("executed_fire_action") == "hold_fire":
        reasons.append("fire_gated_by_los_ammo_or_aim")

    movement = str(observation.get("executed_movement_action", ""))
    distance = observation.get("distance_policy", "")
    if distance == "kite" and ("kite" in movement or "backoff" in movement or "evasive" in movement):
        reasons.append("distance_policy_obeyed")
    elif distance == "close" and ("close" in movement or "forward" in movement):
        reasons.append("distance_policy_obeyed")
    elif distance == "maintain":
        reasons.append("distance_policy_obeyed")

    if observation.get("strafe_direction") in {"left", "right", "alternate"}:
        reasons.append("strafe_policy_requested")
    if observation.get("stuck_recovery"):
        reasons.append("stuck_recovery_safety_override")
    if observation.get("replan_recommended"):
        reasons.append("replan_recommended")

    return ",".join(reasons) if reasons else "default_execution"


def update_participant_timing(
    run_id: str,
    participant_id: str,
    health: int,
    damage_dealt: int,
) -> tuple[int | None, int | None]:
    key = (run_id, participant_id)
    current = PARTICIPANT_TELEMETRY.get(key)
    current_ms = now_ms()
    if current is None:
        current = {
            "health": health,
            "damage_dealt": damage_dealt,
            "last_damage_taken_ms": None,
            "last_damage_dealt_ms": None,
        }
        PARTICIPANT_TELEMETRY[key] = current
        return None, None

    if health < int(current.get("health") or 0):
        current["last_damage_taken_ms"] = current_ms
    if damage_dealt > int(current.get("damage_dealt") or 0):
        current["last_damage_dealt_ms"] = current_ms
    current["health"] = health
    current["damage_dealt"] = damage_dealt
    return current.get("last_damage_taken_ms"), current.get("last_damage_dealt_ms")


def enrich_participant_state(
    observation: dict[str, Any],
    opponent: dict[str, Any],
    run_id: str,
) -> dict[str, Any]:
    preferred_distance = int(observation.get("preferred_distance") or 0)
    distance = int(observation.get("opponent_distance") or 0)
    last_taken_ms, last_dealt_ms = update_participant_timing(
        run_id,
        str(observation.get("participant_id", "")),
        int(observation.get("health") or 0),
        int(observation.get("damage_dealt") or 0),
    )

    observation["health_delta"] = int(observation.get("health") or 0) - int(opponent.get("health") or 0)
    observation["distance_bucket"] = distance_bucket(distance, preferred_distance)
    observation["los_status"] = "visible" if observation.get("opponent_visible") else "lost_los"
    observation["pressure_state"] = pressure_state(
        int(observation.get("health") or 0),
        int(opponent.get("health") or 0),
    )
    observation["last_damage_taken_ms"] = last_taken_ms
    observation["last_damage_dealt_ms"] = last_dealt_ms
    observation["requested_fire_policy"] = observation.get("fire_policy", "")
    observation["executed_fire_action"] = executed_fire_action(str(observation.get("autopilot_action", "")))
    observation["requested_distance_policy"] = observation.get("distance_policy", "")
    observation["executed_movement_action"] = executed_movement_action(str(observation.get("autopilot_action", "")))
    observation["requested_strafe_direction"] = observation.get("strafe_direction", "")
    observation["executed_strafe_direction"] = executed_strafe_direction(
        str(observation.get("strafe_direction", "")),
        str(observation.get("autopilot_action", "")),
    )
    observation["requested_los_lost_action"] = observation.get("los_lost_action", "")
    observation["requested_stuck_recovery_strategy"] = observation.get("stuck_recovery_strategy", "")
    observation["requested_movement_primitive"] = observation.get("movement_primitive", "")
    observation["requested_turn_policy"] = observation.get("turn_policy", "")
    observation["requested_navigation_target"] = observation.get("navigation_target", "")
    observation["requested_fire_mode"] = observation.get("fire_mode", "")
    observation["policy_compliance_reason"] = policy_compliance_reason(observation)
    return observation


def participant_state(row: dict[str, str]) -> dict[str, Any]:
    observation = {
        "participant_id": row.get("entity_id", ""),
        "model": row.get("model", ""),
        "health": as_int(row, "health"),
        "ammo": as_int(row, "ammo_bullets"),
        "x": as_int(row, "x"),
        "y": as_int(row, "y"),
        "angle": as_int(row, "angle"),
        "alive": row.get("alive", "0") == "1",
        "last_action": row.get("last_action", ""),
        "command_status": row.get("command_status", ""),
        "intent": row.get("intent", ""),
        "intent_status": row.get("intent_status", ""),
        "intent_id": row.get("intent_id", ""),
        "intent_style": row.get("intent_style", ""),
        "autopilot_action": row.get("autopilot_action", ""),
        "autopilot_reason": row.get("autopilot_reason", ""),
        "aim_error": as_int(row, "aim_error"),
        "preferred_distance": as_int(row, "preferred_distance"),
        "stuck_recovery": row.get("stuck_recovery", "0") == "1",
        "controller_mode": row.get("controller_mode", ""),
        "strafe_direction": row.get("strafe_direction", ""),
        "movement_bias": row.get("movement_bias", ""),
        "fire_policy": row.get("fire_policy", ""),
        "distance_policy": row.get("distance_policy", ""),
        "aim_tolerance": as_int(row, "aim_tolerance") if row.get("aim_tolerance", "") else None,
        "fire_burst_ms": as_int(row, "fire_burst_ms") if row.get("fire_burst_ms", "") else None,
        "min_fire_alignment": as_int(row, "min_fire_alignment") if row.get("min_fire_alignment", "") else None,
        "min_distance": as_int(row, "min_distance") if row.get("min_distance", "") else None,
        "max_distance": as_int(row, "max_distance") if row.get("max_distance", "") else None,
        "retreat_if_closer_than": as_int(row, "retreat_if_closer_than") if row.get("retreat_if_closer_than", "") else None,
        "push_if_farther_than": as_int(row, "push_if_farther_than") if row.get("push_if_farther_than", "") else None,
        "los_lost_action": row.get("los_lost_action", ""),
        "stuck_recovery_strategy": row.get("stuck_recovery_strategy", ""),
        "movement_primitive": row.get("movement_primitive", ""),
        "turn_policy": row.get("turn_policy", ""),
        "navigation_target": row.get("navigation_target", ""),
        "fire_mode": row.get("fire_mode", ""),
        "executed_turn_policy": row.get("executed_turn_policy", ""),
        "executed_navigation_target": row.get("executed_navigation_target", ""),
        "executed_fire_mode": row.get("executed_fire_mode", ""),
        "replan_if": [part for part in row.get("replan_if", "").split(",") if part],
        "sequence_number": as_int(row, "sequence_number") if row.get("sequence_number", "") else None,
        "decision_cadence_ms": as_int(row, "decision_cadence_ms") if row.get("decision_cadence_ms", "") else None,
        "issued_at_ms": as_int(row, "issued_at_ms") if row.get("issued_at_ms", "") else None,
        "expires_at_ms": as_int(row, "expires_at_ms") if row.get("expires_at_ms", "") else None,
        "replan_recommended": row.get("replan_recommended", "0") == "1",
        "replan_reasons": [part for part in row.get("replan_reasons", "").split(",") if part],
        "damage_dealt": as_int(row, "damage_dealt"),
        "shots_fired": as_int(row, "shots_fired"),
        "shots_hit": as_int(row, "shots_hit"),
        "invalid_actions": as_int(row, "invalid_actions"),
        "opponent_distance": as_int(row, "distance_to_player"),
        "opponent_relative_angle": as_int(row, "relative_angle_to_player"),
        "opponent_visible": row.get("line_of_sight", "0") == "1",
    }
    return observation


def make_shared_arena_state(rows: list[dict[str, str]]) -> dict[str, Any]:
    match = next((row for row in rows if row.get("kind") == "match"), {})
    player_1_row = next(
        (row for row in rows if row.get("kind") == "participant" and row.get("entity_id") == "player_1"),
        {},
    )
    player_2_row = next(
        (row for row in rows if row.get("kind") == "participant" and row.get("entity_id") == "player_2"),
        {},
    )
    run_id = match.get("run_id") or first_value(rows, "run_id")
    scenario_id = match.get("scenario_id") or first_value(rows, "scenario_id")
    mode = match.get("mode") or match.get("arena_mode") or first_value(rows, "mode", "duel")
    player_1 = participant_state(player_1_row)
    player_2 = participant_state(player_2_row)
    if player_1_row or player_2_row:
        enrich_participant_state(player_1, player_2, run_id)
        enrich_participant_state(player_2, player_1, run_id)
    state = {
        "mode": mode,
        "run_id": run_id,
        "scenario_id": scenario_id,
        "tick": as_int(match, "tick", as_int(player_1_row, "tick")),
        "elapsed_time_seconds": as_float(match, "elapsed_time_seconds", as_float(player_1_row, "elapsed_time_seconds")),
        "timeout_seconds": as_int(match, "timeout_seconds", as_int(player_1_row, "timeout_seconds", 120)),
        "phase": match.get("phase", player_1_row.get("phase", "")),
        "winner": match.get("winner", player_1_row.get("winner", "")),
        "terminal_reason": match.get("terminal_reason", player_1_row.get("terminal_reason", "")),
        "player_1": player_1,
        "player_2": player_2,
        "distance_between_players": as_int(match, "distance_between_players", as_int(player_1_row, "distance_to_player")),
        "line_of_sight": (match.get("line_of_sight") or player_1_row.get("line_of_sight", "0")) == "1",
        "relative_angle_player_1_to_player_2": as_int(
            match,
            "relative_angle_player_1_to_player_2",
            as_int(player_1_row, "relative_angle_to_player"),
        ),
        "relative_angle_player_2_to_player_1": as_int(
            match,
            "relative_angle_player_2_to_player_1",
            as_int(player_2_row, "relative_angle_to_player"),
        ),
    }
    if not player_1_row and not player_2_row:
        state["rows"] = rows
    return state


def make_player_observation(rows: list[dict[str, str]]) -> dict[str, Any]:
    player = next((row for row in rows if row.get("kind") == "player"), {})
    enemies = []
    for row in rows:
        if row.get("kind") != "enemy":
            continue
        enemies.append(
            {
                "enemy_id": row.get("entity_id", ""),
                "type": row.get("type", ""),
                "health": as_int(row, "health"),
                "alive": row.get("alive", "0") == "1",
                "x": as_int(row, "x"),
                "y": as_int(row, "y"),
                "distance_to_player": as_int(row, "distance_to_player"),
                "relative_angle_to_player": as_int(row, "relative_angle_to_player"),
                "line_of_sight": row.get("line_of_sight", "0") == "1",
            }
        )

    return {
        "player": {
            "health": as_int(player, "health"),
            "alive": player.get("alive", "0") == "1",
            "x": as_int(player, "x"),
            "y": as_int(player, "y"),
            "angle": as_int(player, "angle"),
            "ready_weapon": player.get("ready_weapon", ""),
            "ammo_bullets": as_int(player, "ammo_bullets"),
            "ammo_shells": as_int(player, "ammo_shells"),
            "ammo_cells": as_int(player, "ammo_cells"),
            "ammo_rockets": as_int(player, "ammo_rockets"),
        },
        "enemies": enemies,
        "objective": "kill_all_enemies_and_survive",
    }


def make_enemy_observation(rows: list[dict[str, str]]) -> dict[str, Any]:
    player_obs = make_player_observation(rows)
    return {
        "player": player_obs["player"],
        "enemies": [
            {
                **enemy,
                "can_see_player": enemy["line_of_sight"],
                "current_command": next(
                    (row.get("current_command", "normal") for row in rows if row.get("entity_id") == enemy["enemy_id"]),
                    "normal",
                ),
            }
            for enemy in player_obs["enemies"]
        ],
        "objective": "kill_player",
    }


def make_participant_observation(rows: list[dict[str, str]], participant_id: str) -> dict[str, Any]:
    match = next((row for row in rows if row.get("kind") == "match"), {})
    config_row = next((row for row in rows if row.get("kind") == "arena_config"), {})
    hide_enemy_position = config_row.get("hide_enemy_position", "0") == "1"
    state = make_shared_arena_state(rows)
    participant = next(
        (row for row in rows if row.get("kind") == "participant" and row.get("entity_id") == participant_id),
        {},
    )
    opponent_id = "player_2" if participant_id == "player_1" else "player_1"
    opponent = next(
        (row for row in rows if row.get("kind") == "participant" and row.get("entity_id") == opponent_id),
        {},
    )
    self_state = state.get(participant_id, {})
    opponent_state = state.get(opponent_id, {})
    opponent_visible = participant.get("line_of_sight", "0") == "1"

    if hide_enemy_position:
        opponent_block: dict[str, Any] = {
            "participant_id": opponent_id,
            "alive": opponent.get("alive", "0") == "1",
            "visible": opponent_visible,
        }
        if opponent_visible:
            opponent_block.update(
                {
                    "distance": as_int(participant, "distance_to_player"),
                    "relative_angle": as_int(participant, "relative_angle_to_player"),
                    "distance_bucket": opponent_state.get("distance_bucket"),
                    "los_status": opponent_state.get("los_status"),
                }
            )
    else:
        opponent_block = {
            "participant_id": opponent_id,
            "health": as_int(opponent, "health"),
            "alive": opponent.get("alive", "0") == "1",
            "x": as_int(opponent, "x"),
            "y": as_int(opponent, "y"),
            "angle": as_int(opponent, "angle"),
            "ammo_bullets": as_int(opponent, "ammo_bullets"),
            "visible": opponent_visible,
            "distance": as_int(participant, "distance_to_player"),
            "relative_angle": as_int(participant, "relative_angle_to_player"),
            "pressure_state": opponent_state.get("pressure_state"),
            "distance_bucket": opponent_state.get("distance_bucket"),
            "los_status": opponent_state.get("los_status"),
            "requested_fire_policy": opponent_state.get("requested_fire_policy"),
            "executed_fire_action": opponent_state.get("executed_fire_action"),
            "requested_distance_policy": opponent_state.get("requested_distance_policy"),
            "executed_movement_action": opponent_state.get("executed_movement_action"),
            "requested_strafe_direction": opponent_state.get("requested_strafe_direction"),
            "executed_strafe_direction": opponent_state.get("executed_strafe_direction"),
            "requested_los_lost_action": opponent_state.get("requested_los_lost_action"),
            "requested_stuck_recovery_strategy": opponent_state.get("requested_stuck_recovery_strategy"),
            "requested_movement_primitive": opponent_state.get("requested_movement_primitive"),
            "requested_turn_policy": opponent_state.get("requested_turn_policy"),
            "requested_navigation_target": opponent_state.get("requested_navigation_target"),
            "requested_fire_mode": opponent_state.get("requested_fire_mode"),
            "executed_turn_policy": opponent_state.get("executed_turn_policy"),
            "executed_navigation_target": opponent_state.get("executed_navigation_target"),
            "executed_fire_mode": opponent_state.get("executed_fire_mode"),
        }

    return {
        "participant_id": participant_id,
        "opponent_id": opponent_id,
        "state_mode": "fog_of_war" if hide_enemy_position else "shared_full",
        "self": {
            "health": as_int(participant, "health"),
            "alive": participant.get("alive", "0") == "1",
            "x": as_int(participant, "x"),
            "y": as_int(participant, "y"),
            "angle": as_int(participant, "angle"),
            "ammo_bullets": as_int(participant, "ammo_bullets"),
            "command_status": participant.get("command_status", ""),
            "last_action": participant.get("last_action", ""),
            "damage_dealt": as_int(participant, "damage_dealt"),
            "shots_fired": as_int(participant, "shots_fired"),
            "shots_hit": as_int(participant, "shots_hit"),
            "invalid_actions": as_int(participant, "invalid_actions"),
            "health_delta": self_state.get("health_delta"),
            "distance_bucket": self_state.get("distance_bucket"),
            "los_status": self_state.get("los_status"),
            "pressure_state": self_state.get("pressure_state"),
            "last_damage_taken_ms": self_state.get("last_damage_taken_ms"),
            "last_damage_dealt_ms": self_state.get("last_damage_dealt_ms"),
            "requested_fire_policy": self_state.get("requested_fire_policy"),
            "executed_fire_action": self_state.get("executed_fire_action"),
            "requested_distance_policy": self_state.get("requested_distance_policy"),
            "executed_movement_action": self_state.get("executed_movement_action"),
            "requested_strafe_direction": self_state.get("requested_strafe_direction"),
            "executed_strafe_direction": self_state.get("executed_strafe_direction"),
            "requested_los_lost_action": self_state.get("requested_los_lost_action"),
            "requested_stuck_recovery_strategy": self_state.get("requested_stuck_recovery_strategy"),
            "requested_movement_primitive": self_state.get("requested_movement_primitive"),
            "requested_turn_policy": self_state.get("requested_turn_policy"),
            "requested_navigation_target": self_state.get("requested_navigation_target"),
            "requested_fire_mode": self_state.get("requested_fire_mode"),
            "executed_turn_policy": self_state.get("executed_turn_policy"),
            "executed_navigation_target": self_state.get("executed_navigation_target"),
            "executed_fire_mode": self_state.get("executed_fire_mode"),
            "policy_compliance_reason": self_state.get("policy_compliance_reason"),
        },
        "opponent": opponent_block,
        "tactical_context": {
            "health_delta": self_state.get("health_delta"),
            "distance_bucket": self_state.get("distance_bucket"),
            "los_status": self_state.get("los_status"),
            "pressure_state": self_state.get("pressure_state"),
            "last_damage_taken_ms": self_state.get("last_damage_taken_ms"),
            "last_damage_dealt_ms": self_state.get("last_damage_dealt_ms"),
            "replan_recommended": self_state.get("replan_recommended"),
            "replan_reasons": self_state.get("replan_reasons"),
            "requested_fire_policy": self_state.get("requested_fire_policy"),
            "executed_fire_action": self_state.get("executed_fire_action"),
            "requested_distance_policy": self_state.get("requested_distance_policy"),
            "executed_movement_action": self_state.get("executed_movement_action"),
            "requested_strafe_direction": self_state.get("requested_strafe_direction"),
            "executed_strafe_direction": self_state.get("executed_strafe_direction"),
            "requested_los_lost_action": self_state.get("requested_los_lost_action"),
            "requested_stuck_recovery_strategy": self_state.get("requested_stuck_recovery_strategy"),
            "requested_movement_primitive": self_state.get("requested_movement_primitive"),
            "requested_turn_policy": self_state.get("requested_turn_policy"),
            "requested_navigation_target": self_state.get("requested_navigation_target"),
            "requested_fire_mode": self_state.get("requested_fire_mode"),
            "executed_turn_policy": self_state.get("executed_turn_policy"),
            "executed_navigation_target": self_state.get("executed_navigation_target"),
            "executed_fire_mode": self_state.get("executed_fire_mode"),
            "policy_compliance_reason": self_state.get("policy_compliance_reason"),
        },
        "match": {
            "phase": match.get("phase", participant.get("phase", "")),
            "winner": match.get("winner", participant.get("winner", "")),
            "terminal_reason": match.get("terminal_reason", participant.get("terminal_reason", "")),
            "elapsed_time_seconds": match.get("elapsed_time_seconds", participant.get("elapsed_time_seconds", "")),
            "timeout_seconds": as_int(match or participant, "timeout_seconds", 120),
        },
        "allowed_intents": sorted(VALID_PARTICIPANT_INTENTS),
        "allowed_styles": sorted(VALID_PARTICIPANT_INTENT_STYLES),
        "allowed_tactical_controls": {
            "strafe_direction": sorted(VALID_STRAFE_DIRECTIONS),
            "movement_bias": sorted(VALID_MOVEMENT_BIASES),
            "fire_policy": sorted(VALID_FIRE_POLICIES),
            "distance_policy": sorted(VALID_DISTANCE_POLICIES),
            "los_lost_action": sorted(VALID_LOS_LOST_ACTIONS),
            "stuck_recovery_strategy": sorted(VALID_STUCK_RECOVERY_STRATEGIES),
            "movement_primitive": sorted(VALID_MOVEMENT_PRIMITIVES),
            "turn_policy": sorted(VALID_TURN_POLICIES),
            "navigation_target": sorted(VALID_NAVIGATION_TARGETS),
            "fire_mode": sorted(VALID_FIRE_MODES),
            "aim_tolerance": [0, 180],
            "fire_burst_ms": [0, 60000],
            "min_fire_alignment": [0, 180],
            "min_distance": [0, 10000],
            "max_distance": [0, 10000],
            "retreat_if_closer_than": [0, 10000],
            "push_if_farther_than": [0, 10000],
            "replan_if": sorted(VALID_REPLAN_TRIGGERS),
            "decision_cadence_ms_recommended": [500, 3000],
        },
        "intent_duration_ms": [100, 60000],
        "objective": "reduce_opponent_health_to_zero",
    }
    if EXPOSE_LOW_LEVEL_PARTICIPANT_MCP:
        observation["debug_allowed_controls"] = {
            "forward": [-1, 0, 1],
            "strafe": [-1, 0, 1],
            "turn": [-1, 0, 1],
            "attack": [False, True],
            "use": [False, True],
            "duration_ms": [100, 2000],
        }
    return observation


def find_enemy(enemies: list[dict[str, Any]], enemy_id: str) -> dict[str, Any]:
    for enemy in enemies:
        if enemy["enemy_id"] == enemy_id:
            return enemy
    raise DoomArenaError(f"Unknown enemy_id: {enemy_id}")


def tool_definitions() -> list[dict[str, Any]]:
    tools = [
        {
            "name": "reset_duel",
            "description": "Reset Doom Arena into duel mode and request browser/WASM reload.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "player_1_model": {"type": "string"},
                    "player_2_model": {"type": "string"},
                    "round": {"type": "integer", "minimum": 1},
                    "seed": {"type": "integer"},
                    "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 3600},
                },
                "additionalProperties": False,
            },
        },
        {"name": "get_arena_state", "description": "Return current shared Doom Arena state JSON.", "inputSchema": optional_run_id_schema()},
        {"name": "get_match_result", "description": "Return current match phase, winner, terminal reason, and score.", "inputSchema": optional_run_id_schema()},
        {
            "name": "get_duel_events",
            "description": "Return recent duel events.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "run_id": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 5000},
                },
                "additionalProperties": False,
            },
        },
        {"name": "get_player_observation", "description": "Return player-agent observation JSON.", "inputSchema": empty_schema()},
        {"name": "get_enemy_observation", "description": "Return enemy-commander observation JSON.", "inputSchema": empty_schema()},
        {
            "name": "get_participant_observation",
            "description": "Return symmetric duel observation JSON for one participant.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "participant_id": {"type": "string", "enum": sorted(PARTICIPANTS)},
                    "controller_token": {"type": "string"},
                },
                "required": ["participant_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "set_participant_ready",
            "description": "Signal that one MCP participant is connected and ready for the duel start barrier.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "participant_id": {"type": "string", "enum": sorted(PARTICIPANTS)},
                    "controller_token": {"type": "string"},
                },
                "required": ["participant_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "wait_for_match_start",
            "description": "Block briefly until both participants are ready, both opening intents are armed, and the duel phase leaves waiting_for_agents.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "participant_id": {"type": "string", "enum": sorted(PARTICIPANTS)},
                    "controller_token": {"type": "string"},
                    "timeout_ms": {"type": "integer", "minimum": 100, "maximum": 300000},
                    "poll_ms": {"type": "integer", "minimum": 50, "maximum": 5000},
                },
                "required": ["participant_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "set_participant_intent",
            "description": "Set high-level autopilot intent for player_1 or player_2.",
            "inputSchema": participant_intent_schema(),
        },
        {
            "name": "stop_participant_intent",
            "description": "Clear the active high-level autopilot intent for one participant.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "participant_id": {"type": "string", "enum": sorted(PARTICIPANTS)},
                    "controller_token": {"type": "string"},
                },
                "required": ["participant_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "set_player_input",
            "description": "Send embodied player input through Doom's normal input path.",
            "inputSchema": participant_input_schema(required_participant=False),
        },
        {"name": "stop_player", "description": "Stop player input.", "inputSchema": empty_schema()},
        {
            "name": "set_enemy_command",
            "description": "Set a high-level command for one arena enemy.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "enemy_id": {"type": "string"},
                    "command": {"type": "string", "enum": sorted(VALID_ENEMY_COMMANDS)},
                    "duration_ms": {"type": "integer", "minimum": 1, "maximum": 60000},
                },
                "required": ["enemy_id", "command"],
                "additionalProperties": False,
            },
        },
        {
            "name": "set_enemy_team_command",
            "description": "Set a high-level command for all arena enemies.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "enum": sorted(VALID_ENEMY_COMMANDS)},
                    "duration_ms": {"type": "integer", "minimum": 1, "maximum": 60000},
                },
                "required": ["command"],
                "additionalProperties": False,
            },
        },
        {"name": "clear_enemy_commands", "description": "Clear all enemy commands.", "inputSchema": empty_schema()},
        {"name": "reset_arena", "description": "Reset arena run state and request browser reload.", "inputSchema": empty_schema()},
        helper_schema("look_at_enemy"),
        helper_schema("attack_enemy"),
        helper_schema("move_toward_enemy"),
    ]
    if EXPOSE_LOW_LEVEL_PARTICIPANT_MCP:
        insert_at = next(
            index for index, tool in enumerate(tools) if tool["name"] == "set_participant_intent"
        )
        tools[insert_at:insert_at] = [
            {
                "name": "set_participant_input",
                "description": "Debug only: send symmetric low-level duel input for player_1 or player_2.",
                "inputSchema": participant_input_schema(required_participant=True),
            },
            {
                "name": "stop_participant",
                "description": "Debug only: stop one duel participant's low-level input.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "participant_id": {"type": "string", "enum": sorted(PARTICIPANTS)},
                        "controller_token": {"type": "string"},
                    },
                    "required": ["participant_id"],
                    "additionalProperties": False,
                },
            },
        ]
    return tools


def empty_schema() -> dict[str, Any]:
    return {"type": "object", "properties": {}, "additionalProperties": False}


def optional_run_id_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {"run_id": {"type": "string"}},
        "additionalProperties": False,
    }


def participant_input_schema(required_participant: bool) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "forward": {"type": "integer", "minimum": -1, "maximum": 1},
        "strafe": {"type": "integer", "minimum": -1, "maximum": 1},
        "turn": {"type": "integer", "minimum": -1, "maximum": 1},
        "attack": {"type": "boolean"},
        "use": {"type": "boolean"},
        "duration_ms": {"type": "integer", "minimum": 1, "maximum": 5000},
    }
    required = []
    if required_participant:
        properties["participant_id"] = {"type": "string", "enum": sorted(PARTICIPANTS)}
        properties["controller_token"] = {"type": "string"}
        required = ["participant_id"]
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def participant_intent_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "participant_id": {"type": "string", "enum": sorted(PARTICIPANTS)},
            "controller_token": {"type": "string"},
            "intent": {"type": "string", "enum": sorted(VALID_PARTICIPANT_INTENTS)},
            "style": {"type": "string", "enum": sorted(VALID_PARTICIPANT_INTENT_STYLES)},
            "target_id": {"type": "string", "enum": sorted(PARTICIPANTS)},
            "preferred_distance": {"type": "integer", "minimum": 1, "maximum": 10000},
            "aggression": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "duration_ms": {"type": "integer", "minimum": 100, "maximum": 60000},
            "strafe_direction": {"type": "string", "enum": sorted(VALID_STRAFE_DIRECTIONS)},
            "movement_bias": {"type": "string", "enum": sorted(VALID_MOVEMENT_BIASES)},
            "fire_policy": {"type": "string", "enum": sorted(VALID_FIRE_POLICIES)},
            "distance_policy": {"type": "string", "enum": sorted(VALID_DISTANCE_POLICIES)},
            "aim_tolerance": {"type": "integer", "minimum": 0, "maximum": 180},
            "fire_burst_ms": {"type": "integer", "minimum": 0, "maximum": 60000},
            "min_fire_alignment": {"type": "integer", "minimum": 0, "maximum": 180},
            "min_distance": {"type": "integer", "minimum": 0},
            "max_distance": {"type": "integer", "minimum": 0},
            "retreat_if_closer_than": {"type": "integer", "minimum": 0},
            "push_if_farther_than": {"type": "integer", "minimum": 0},
            "los_lost_action": {"type": "string", "enum": sorted(VALID_LOS_LOST_ACTIONS)},
            "stuck_recovery_strategy": {"type": "string", "enum": sorted(VALID_STUCK_RECOVERY_STRATEGIES)},
            "movement_primitive": {"type": "string", "enum": sorted(VALID_MOVEMENT_PRIMITIVES)},
            "turn_policy": {"type": "string", "enum": sorted(VALID_TURN_POLICIES)},
            "navigation_target": {"type": "string", "enum": sorted(VALID_NAVIGATION_TARGETS)},
            "fire_mode": {"type": "string", "enum": sorted(VALID_FIRE_MODES)},
            "replan_if": {
                "type": "array",
                "items": {"type": "string", "enum": sorted(VALID_REPLAN_TRIGGERS)},
            },
            "sequence_number": {"type": "integer", "minimum": 0},
            "decision_cadence_ms": {"type": "integer", "minimum": 1},
            "rationale": {
                "type": "string",
                "maxLength": 1024,
                "description": "Optional short reasoning string for this intent. Logged for post-match analysis; not enforced.",
            },
        },
        "required": ["participant_id", "intent"],
        "additionalProperties": False,
    }


def helper_schema(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "description": f"{name} by emitting normal player input.",
        "inputSchema": {
            "type": "object",
            "properties": {"enemy_id": {"type": "string"}},
            "required": ["enemy_id"],
            "additionalProperties": False,
        },
    }


def call_tool(client: DoomArenaClient, name: str, arguments: dict[str, Any]) -> str:
    if name == "get_arena_state":
        return client.get_arena_state(optional_string(arguments.get("run_id")))
    if name == "get_match_result":
        return client.get_match_result(optional_string(arguments.get("run_id")))
    if name == "get_duel_events":
        return client.get_duel_events(optional_string(arguments.get("run_id")), int(arguments.get("limit", 25)))
    if name == "reset_duel":
        return client.reset_duel(
            str(arguments.get("player_1_model", "")),
            str(arguments.get("player_2_model", "")),
            int(arguments.get("round", 1)),
            int(arguments.get("seed", 42)),
            int(arguments.get("timeout_seconds", 120)),
        )
    if name == "get_player_observation":
        return client.get_player_observation()
    if name == "get_enemy_observation":
        return client.get_enemy_observation()
    if name == "get_participant_observation":
        return client.get_participant_observation(
            str(arguments["participant_id"]),
            optional_string(arguments.get("controller_token")),
        )
    if name == "set_participant_ready":
        return client.set_participant_ready(
            str(arguments["participant_id"]),
            optional_string(arguments.get("controller_token")),
        )
    if name == "wait_for_match_start":
        return client.wait_for_match_start(
            str(arguments["participant_id"]),
            optional_string(arguments.get("controller_token")),
            int(arguments.get("timeout_ms", 60000)),
            int(arguments.get("poll_ms", 250)),
        )
    if name == "set_participant_input":
        if not EXPOSE_LOW_LEVEL_PARTICIPANT_MCP:
            raise DoomArenaError(
                "Low-level participant MCP tools are disabled. Use set_participant_intent, "
                "or relaunch with DOOM_ARENA_EXPOSE_LOW_LEVEL_MCP=1 for debug access."
            )
        return client.set_participant_input(
            str(arguments["participant_id"]),
            int(arguments.get("forward", 0)),
            int(arguments.get("strafe", 0)),
            int(arguments.get("turn", 0)),
            bool(arguments.get("attack", False)),
            bool(arguments.get("use", False)),
            int(arguments.get("duration_ms", 750)),
            optional_string(arguments.get("controller_token")),
        )
    if name == "stop_participant":
        if not EXPOSE_LOW_LEVEL_PARTICIPANT_MCP:
            raise DoomArenaError(
                "Low-level participant MCP tools are disabled. Use stop_participant_intent, "
                "or relaunch with DOOM_ARENA_EXPOSE_LOW_LEVEL_MCP=1 for debug access."
            )
        return client.stop_participant(
            str(arguments["participant_id"]),
            optional_string(arguments.get("controller_token")),
        )
    if name == "set_participant_intent":
        return client.set_participant_intent(
            str(arguments["participant_id"]),
            str(arguments["intent"]),
            str(arguments.get("style", "balanced")),
            optional_string(arguments.get("target_id")),
            int(arguments.get("preferred_distance", 600)),
            float(arguments.get("aggression", 0.5)),
            int(arguments.get("duration_ms", 25000)),
            optional_string(arguments.get("controller_token")),
            strafe_direction=str(arguments.get("strafe_direction", "auto")),
            movement_bias=str(arguments.get("movement_bias", "direct")),
            fire_policy=str(arguments.get("fire_policy", "only_when_aligned")),
            distance_policy=str(arguments.get("distance_policy", "maintain")),
            replan_if=arguments.get("replan_if"),
            sequence_number=arguments.get("sequence_number"),
            decision_cadence_ms=arguments.get("decision_cadence_ms"),
            aim_tolerance=arguments.get("aim_tolerance"),
            fire_burst_ms=arguments.get("fire_burst_ms"),
            min_fire_alignment=arguments.get("min_fire_alignment"),
            min_distance=arguments.get("min_distance"),
            max_distance=arguments.get("max_distance"),
            retreat_if_closer_than=arguments.get("retreat_if_closer_than"),
            push_if_farther_than=arguments.get("push_if_farther_than"),
            los_lost_action=str(arguments.get("los_lost_action", "sweep")),
            stuck_recovery_strategy=str(arguments.get("stuck_recovery_strategy", "default")),
            movement_primitive=str(arguments.get("movement_primitive", "")),
            turn_policy=str(arguments.get("turn_policy", "auto")),
            navigation_target=str(arguments.get("navigation_target", "opponent")),
            fire_mode=str(arguments.get("fire_mode", "auto")),
            rationale=optional_string(arguments.get("rationale")),
        )
    if name == "stop_participant_intent":
        return client.stop_participant_intent(
            str(arguments["participant_id"]),
            optional_string(arguments.get("controller_token")),
        )
    if name == "set_player_input":
        return client.set_player_input(
            int(arguments.get("forward", 0)),
            int(arguments.get("strafe", 0)),
            int(arguments.get("turn", 0)),
            bool(arguments.get("attack", False)),
            bool(arguments.get("use", False)),
            int(arguments.get("duration_ms", 250)),
        )
    if name == "stop_player":
        return client.stop_player()
    if name == "set_enemy_command":
        return client.set_enemy_command(
            str(arguments["enemy_id"]),
            str(arguments["command"]),
            int(arguments.get("duration_ms", 1000)),
        )
    if name == "set_enemy_team_command":
        return client.set_enemy_team_command(
            str(arguments["command"]),
            int(arguments.get("duration_ms", 1000)),
        )
    if name == "clear_enemy_commands":
        return client.clear_enemy_commands()
    if name == "reset_arena":
        return client.reset_arena()
    if name == "look_at_enemy":
        return client.look_at_enemy(str(arguments["enemy_id"]))
    if name == "attack_enemy":
        return client.attack_enemy(str(arguments["enemy_id"]))
    if name == "move_toward_enemy":
        return client.move_toward_enemy(str(arguments["enemy_id"]))
    raise DoomArenaError(f"Unknown tool: {name}")


def send_response(message_id: Any, result: Any) -> None:
    write_message({"jsonrpc": "2.0", "id": message_id, "result": result})
    log_mcp(f"sent response id={message_id!r}")


def send_error(message_id: Any, code: int, message: str) -> None:
    write_message({"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": message}})
    log_mcp(f"sent error id={message_id!r} code={code}")


def write_message(message: dict[str, Any]) -> None:
    body = json.dumps(message, separators=(",", ":")).encode("utf-8")
    if MCP_OUTPUT_FRAMING == "ndjson":
        sys.stdout.buffer.write(body + b"\n")
    else:
        sys.stdout.buffer.write(b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n")
        sys.stdout.buffer.write(b"\r\n")
        sys.stdout.buffer.write(body)
    sys.stdout.buffer.flush()
    log_mcp(f"wrote message bytes={len(body)} framing={MCP_OUTPUT_FRAMING}")


def read_message() -> dict[str, Any] | None:
    global MCP_OUTPUT_FRAMING
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if line == b"":
            return None
        line = line.decode("ascii", errors="replace").strip()
        # MCP stdio normally uses Content-Length framing. Some local launchers
        # and debugging clients use newline-delimited JSON-RPC; accepting that
        # form makes the server tolerant without changing the normal path.
        if not headers and line.startswith("{"):
            MCP_OUTPUT_FRAMING = "ndjson"
            return json.loads(line)
        if line == "":
            break
        name, separator, value = line.partition(":")
        if separator:
            headers[name.lower()] = value.strip()

    length_text = headers.get("content-length")
    if length_text is None:
        raise json.JSONDecodeError("Missing Content-Length header", "", 0)
    MCP_OUTPUT_FRAMING = "content-length"
    body = sys.stdin.buffer.read(int(length_text))
    return json.loads(body.decode("utf-8"))


def handle_message(client: DoomArenaClient, message: dict[str, Any]) -> bool:
    method = message.get("method")
    message_id = message.get("id")
    log_mcp(f"recv method={method!r} id={message_id!r}")

    if method == "initialize":
        params = message.get("params") or {}
        log_mcp(f"initialize params={json.dumps(params, separators=(',', ':'))[:1000]}")
        client.note_client_initialized(params)
        protocol_version = str(params.get("protocolVersion") or "2024-11-05")
        send_response(
            message_id,
            {
                "protocolVersion": protocol_version,
                "capabilities": {
                    "tools": {"listChanged": True},
                },
                "serverInfo": {
                    "name": "doom-agent-arena",
                    "version": "0.1.0",
                },
            },
        )
        return True
    if method == "notifications/initialized":
        return True
    if method == "ping":
        send_response(message_id, {})
        return True
    if method == "tools/list":
        send_response(message_id, {"tools": tool_definitions()})
        return True
    if method == "resources/list":
        send_response(message_id, {"resources": []})
        return True
    if method == "prompts/list":
        send_response(message_id, {"prompts": []})
        return True
    if method == "logging/setLevel":
        send_response(message_id, None)
        return True
    if method in {"notifications/cancelled", "notifications/progress"}:
        return True
    if method == "tools/call":
        global EXTERNAL_MCP_CALL_COUNTER
        params = message.get("params") or {}
        tool_name = str(params.get("name"))
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            arguments = {}
        EXTERNAL_MCP_CALL_COUNTER += 1
        client.mark_active()
        started_at = now_ms()
        call_id = f"stdio_mcp_{os.getpid()}_{EXTERNAL_MCP_CALL_COUNTER:06d}"
        try:
            text = call_tool(client, tool_name, arguments)
            completed_at = now_ms()
            result_payload = parse_optional_json(text)
            client.post_mcp_call_telemetry(
                {
                    "call_id": call_id,
                    "jsonrpc_id": message_id,
                    "tool_name": tool_name,
                    "participant_id": str(arguments.get("participant_id", "")),
                    "run_id": client.run_id,
                    "scenario_id": client.scenario_id,
                    "started_at_ms": started_at,
                    "completed_at_ms": completed_at,
                    "is_error": False,
                    "result": result_payload if isinstance(result_payload, dict) else {},
                }
            )
            send_response(message_id, {"content": [{"type": "text", "text": text}], "isError": False})
        except (KeyError, TypeError, ValueError, DoomArenaError) as exc:
            completed_at = now_ms()
            client.post_mcp_call_telemetry(
                {
                    "call_id": call_id,
                    "jsonrpc_id": message_id,
                    "tool_name": tool_name,
                    "participant_id": str(arguments.get("participant_id", "")),
                    "run_id": client.run_id,
                    "scenario_id": client.scenario_id,
                    "started_at_ms": started_at,
                    "completed_at_ms": completed_at,
                    "is_error": True,
                    "error": str(exc),
                }
            )
            send_response(message_id, {"content": [{"type": "text", "text": str(exc)}], "isError": True})
        return True
    if method == "shutdown":
        send_response(message_id, None)
        return False
    if message_id is not None:
        send_error(message_id, -32601, f"Method not found: {method}")
    return True


def main() -> int:
    args = parse_args()
    log_mcp(f"start server_url={args.server_url}")
    client = DoomArenaClient(args.server_url)
    log_mcp("client ready; waiting for MCP messages")
    while True:
        try:
            message = read_message()
            if message is None:
                log_mcp("stdin closed")
                break
            keep_running = handle_message(client, message)
        except json.JSONDecodeError as exc:
            log_mcp(f"parse error: {exc}")
            send_error(None, -32700, f"Parse error: {exc}")
            keep_running = True
        except Exception as exc:  # Keep stderr quiet unless explicit file logging is enabled.
            log_mcp(f"fatal error: {exc}\n{traceback.format_exc()}")
            raise
        if not keep_running:
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
