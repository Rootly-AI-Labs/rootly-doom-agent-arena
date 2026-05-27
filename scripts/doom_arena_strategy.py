"""Hierarchical strategy helpers for Doom Arena duel control."""

from __future__ import annotations

import math
import time
from collections import deque
from copy import deepcopy
from typing import Any


CONTROL_MODE_FULL = "full"
CONTROL_MODE_HIERARCHICAL = "hierarchical"
CONTROL_MODES = {CONTROL_MODE_FULL, CONTROL_MODE_HIERARCHICAL}

STRATEGY_INTENSITIES = {"low", "medium", "high"}
STRATEGY_OBJECTIVES = {
    "find_enemy",
    "hold_advantage",
    "force_fight",
    "break_contact",
    "clear_side",
    "control_center",
    "finish_enemy",
}
STRATEGY_TARGET_ZONES = {
    "left_side",
    "right_side",
    "top_lane",
    "bottom_lane",
    "center",
    "last_seen",
    "enemy_side",
}
STRATEGY_REASONING_MAX_CHARS = 120
COMMIT_MS_MIN = 3000
COMMIT_MS_MAX = 8000
COMMIT_MS_DEFAULT = 8000
PLAN_ROUTE_MAX_WAYPOINTS = 16
PLAN_REASONING_MAX_CHARS = 160
PLAN_OBJECTIVE_MAX_CHARS = 64
PLAN_ENGAGEMENT_POLICIES = {
    "engage_if_visible",
    "avoid_until_target",
    "hold_fire",
    "force_fight",
}
PLAN_METADATA_FIELDS = (
    "plan_objective",
    "plan_route",
    "plan_engagement_policy",
    "plan_reasoning",
    "plan_route_cells",
)

STATIC_PICKUPS: tuple[dict[str, Any], ...] = (
    {
        "id": "health_top",
        "type": "health",
        "name": "medikit",
        "x": 0,
        "y": 672,
        "zone": "top_lane",
        "purpose": "restore_health",
    },
    {
        "id": "health_bottom",
        "type": "health",
        "name": "medikit",
        "x": 0,
        "y": -672,
        "zone": "bottom_lane",
        "purpose": "restore_health",
    },
    {
        "id": "weapon_center",
        "type": "weapon",
        "name": "shotgun",
        "x": 0,
        "y": 0,
        "zone": "center",
        "purpose": "upgrade_weapon",
    },
)

MAP_BOUNDS = {"x_min": -1024, "x_max": 1024, "y_min": -768, "y_max": 768}
MAP_CELL_SIZE = 64
MAP_ROWS = 24
MAP_COLS = 32
MAP_ASCII_PATH = "scripts/map_blueprints/duel_e1m8_ascii.txt"

STRATEGY_ACTIONS: dict[str, list[str]] = {
    "explore": ["scan_last_seen", "patrol_left", "patrol_right", "rotate_route", "probe_center"],
    "engage": ["push", "strafe_fight", "suppress", "close_gap", "finish_low_health"],
    "evade": ["kite", "break_los", "retreat_reset", "dodge_strafe", "hold_fire_reposition"],
    "position": ["flank_left", "flank_right", "camp_los", "hold_angle", "take_left_lane", "take_right_lane"],
    "recover": ["unstuck", "anti_spin", "switch_lane", "reset_to_center", "reverse_route"],
}

ALL_STRATEGY_ACTIONS = sorted({action for actions in STRATEGY_ACTIONS.values() for action in actions})

STRATEGY_METADATA_FIELDS = (
    "strategy_source",
    "strategy_category",
    "strategy_action",
    "strategy_intensity",
    "strategy_commit_ms",
    "strategy_objective",
    "strategy_target_zone",
    "strategy_reasoning",
)

BASE_DEFAULTS: dict[str, Any] = {
    "preferred_distance": 650,
    "duration_ms": COMMIT_MS_DEFAULT,
    "decision_cadence_ms": 750,
    "aim_tolerance": 12,
    "fire_burst_ms": 250,
    "min_fire_alignment": 8,
    "min_distance": 350,
    "max_distance": 900,
    "retreat_if_closer_than": 300,
    "push_if_farther_than": 1000,
    "replan_if": ["lost_los", "stuck", "low_health"],
    "strafe_direction": "auto",
    "movement_bias": "direct",
    "fire_policy": "only_when_aligned",
    "distance_policy": "maintain",
    "los_lost_action": "sweep",
    "stuck_recovery_strategy": "strafe_out",
    "movement_primitive": "",
    "turn_policy": "auto",
    "navigation_target": "opponent",
    "fire_mode": "fire_when_aligned",
}

# The current C autopilot accepts only:
# none, opponent, last_seen_enemy, center, left_lane, right_lane, keep_distance.
# Strategy names use left/right lane wording because those are the engine's
# supported lateral navigation targets.
PRESETS: dict[tuple[str, str], dict[str, Any]] = {
    ("explore", "scan_last_seen"): {
        "intent": "search",
        "style": "balanced",
        "fire_policy": "hold_fire",
        "fire_mode": "hold_fire",
        "navigation_target": "last_seen_enemy",
        "turn_policy": "face_last_seen",
        "los_lost_action": "advance_last_seen",
    },
    ("explore", "patrol_left"): {
        "intent": "search",
        "style": "balanced",
        "movement_bias": "cautious",
        "navigation_target": "left_lane",
        "turn_policy": "auto",
        "fire_policy": "only_when_aligned",
    },
    ("explore", "patrol_right"): {
        "intent": "search",
        "style": "balanced",
        "movement_bias": "cautious",
        "navigation_target": "right_lane",
        "turn_policy": "auto",
        "fire_policy": "only_when_aligned",
    },
    ("explore", "rotate_route"): {
        "intent": "search",
        "style": "balanced",
        "movement_bias": "cautious",
        "navigation_target": "center",
        "turn_policy": "auto",
    },
    ("explore", "probe_center"): {
        "intent": "search",
        "style": "balanced",
        "movement_bias": "cautious",
        "navigation_target": "center",
        "turn_policy": "auto",
    },
    ("engage", "push"): {
        "intent": "engage_opponent",
        "style": "aggressive",
        "distance_policy": "close",
        "movement_bias": "direct",
        "fire_policy": "only_when_aligned",
        "fire_mode": "fire_when_aligned",
        "navigation_target": "opponent",
        "turn_policy": "turn_to_enemy",
        "los_lost_action": "advance_last_seen",
        "preferred_distance": 500,
        "min_distance": 250,
        "max_distance": 800,
        "retreat_if_closer_than": 220,
        "push_if_farther_than": 700,
    },
    ("engage", "strafe_fight"): {
        "intent": "strafe_attack",
        "style": "aggressive",
        "distance_policy": "maintain",
        "movement_bias": "circle",
        "strafe_direction": "alternate",
        "fire_policy": "suppressive",
        "fire_mode": "suppressive",
        "navigation_target": "opponent",
        "turn_policy": "turn_to_enemy",
        "preferred_distance": 650,
        "min_distance": 350,
        "max_distance": 950,
    },
    ("engage", "suppress"): {
        "intent": "strafe_attack",
        "style": "aggressive",
        "movement_bias": "circle",
        "fire_policy": "suppressive",
        "fire_mode": "suppressive",
        "navigation_target": "opponent",
        "turn_policy": "turn_to_enemy",
    },
    ("engage", "close_gap"): {
        "intent": "engage_opponent",
        "style": "balanced",
        "distance_policy": "close",
        "movement_bias": "direct",
        "navigation_target": "opponent",
        "turn_policy": "turn_to_enemy",
    },
    ("engage", "finish_low_health"): {
        "intent": "engage_opponent",
        "style": "aggressive",
        "distance_policy": "close",
        "movement_bias": "direct",
        "fire_policy": "suppressive",
        "fire_mode": "suppressive",
        "navigation_target": "opponent",
        "turn_policy": "turn_to_enemy",
    },
    ("evade", "kite"): {
        "intent": "strafe_attack",
        "style": "evasive",
        "distance_policy": "kite",
        "movement_bias": "evasive",
        "strafe_direction": "switch_if_hit",
        "fire_policy": "burst_when_aligned",
        "fire_mode": "burst",
        "navigation_target": "keep_distance",
        "turn_policy": "turn_to_enemy",
        "los_lost_action": "hold_angle",
        "stuck_recovery_strategy": "back_up",
        "preferred_distance": 900,
        "min_distance": 600,
        "max_distance": 1300,
        "retreat_if_closer_than": 650,
        "push_if_farther_than": 1500,
    },
    ("evade", "break_los"): {
        "intent": "search",
        "style": "evasive",
        "distance_policy": "kite",
        "movement_bias": "evasive",
        "fire_policy": "hold_fire",
        "fire_mode": "hold_fire",
        "navigation_target": "center",
        "turn_policy": "auto",
    },
    ("evade", "retreat_reset"): {
        "intent": "search",
        "style": "cautious",
        "distance_policy": "kite",
        "movement_bias": "cautious",
        "navigation_target": "keep_distance",
        "turn_policy": "auto",
        "los_lost_action": "hold_angle",
        "stuck_recovery_strategy": "back_up",
    },
    ("evade", "dodge_strafe"): {
        "intent": "strafe_attack",
        "style": "evasive",
        "movement_bias": "evasive",
        "strafe_direction": "switch_if_hit",
        "fire_policy": "burst_when_aligned",
        "fire_mode": "burst",
        "navigation_target": "opponent",
        "turn_policy": "turn_to_enemy",
    },
    ("evade", "hold_fire_reposition"): {
        "intent": "search",
        "style": "cautious",
        "movement_bias": "cautious",
        "fire_policy": "hold_fire",
        "fire_mode": "hold_fire",
        "navigation_target": "center",
        "turn_policy": "auto",
    },
    ("position", "flank_left"): {
        "intent": "engage_opponent",
        "style": "balanced",
        "movement_bias": "circle",
        "navigation_target": "left_lane",
        "turn_policy": "auto",
        "los_lost_action": "advance_last_seen",
    },
    ("position", "flank_right"): {
        "intent": "engage_opponent",
        "style": "balanced",
        "movement_bias": "circle",
        "navigation_target": "right_lane",
        "turn_policy": "auto",
        "los_lost_action": "advance_last_seen",
    },
    ("position", "camp_los"): {
        "intent": "hold",
        "style": "balanced",
        "movement_bias": "cautious",
        "fire_policy": "only_when_aligned",
        "fire_mode": "fire_when_aligned",
        "navigation_target": "none",
        "turn_policy": "face_last_seen",
        "los_lost_action": "hold_angle",
        "stuck_recovery_strategy": "default",
    },
    ("position", "hold_angle"): {
        "intent": "hold",
        "style": "cautious",
        "movement_bias": "cautious",
        "navigation_target": "none",
        "turn_policy": "hold_angle",
        "los_lost_action": "hold_angle",
        "stuck_recovery_strategy": "default",
    },
    ("position", "take_left_lane"): {
        "intent": "search",
        "style": "balanced",
        "movement_bias": "direct",
        "navigation_target": "left_lane",
        "turn_policy": "auto",
    },
    ("position", "take_right_lane"): {
        "intent": "search",
        "style": "balanced",
        "movement_bias": "direct",
        "navigation_target": "right_lane",
        "turn_policy": "auto",
    },
    ("recover", "unstuck"): {
        "intent": "search",
        "style": "cautious",
        "movement_bias": "evasive",
        "navigation_target": "center",
        "turn_policy": "auto",
        "stuck_recovery_strategy": "strafe_out",
    },
    ("recover", "anti_spin"): {
        "intent": "search",
        "style": "balanced",
        "movement_bias": "direct",
        "navigation_target": "center",
        "turn_policy": "auto",
        "los_lost_action": "advance_last_seen",
        "stuck_recovery_strategy": "strafe_out",
    },
    ("recover", "switch_lane"): {
        "intent": "search",
        "style": "balanced",
        "movement_bias": "direct",
        "navigation_target": "center",
        "turn_policy": "auto",
    },
    ("recover", "reset_to_center"): {
        "intent": "search",
        "style": "cautious",
        "movement_bias": "cautious",
        "navigation_target": "center",
        "turn_policy": "auto",
    },
    ("recover", "reverse_route"): {
        "intent": "search",
        "style": "balanced",
        "movement_bias": "direct",
        "navigation_target": "center",
        "turn_policy": "auto",
    },
}

_HISTORY: dict[tuple[str, str], dict[str, Any]] = {}


def now_ms() -> int:
    return int(time.time() * 1000)


def normalize_control_mode(value: Any) -> str:
    text = str(value or CONTROL_MODE_HIERARCHICAL).strip().lower()
    return text if text in CONTROL_MODES else CONTROL_MODE_HIERARCHICAL


def clamp_int(value: Any, minimum: int, maximum: int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def classify_zone(x: Any, y: Any, map_id: str = "duel_e1m8") -> str:
    try:
        xf = float(x)
        yf = float(y)
    except (TypeError, ValueError):
        return "unknown"
    if map_id.startswith("duel_e1m8") and abs(xf) < 160 and abs(yf) < 450:
        return "center_near"
    if xf < 0:
        return "left_side"
    return "right_side"


def relative_angle_bucket(angle: Any) -> str:
    try:
        value = float(angle)
    except (TypeError, ValueError):
        return "unknown"
    if abs(value) <= 15:
        return "ahead"
    if -45 <= value < -15:
        return "slight_left"
    if 15 < value <= 45:
        return "slight_right"
    if value < -45:
        return "hard_left"
    return "hard_right"


def accuracy_bucket(shots_fired: Any, shots_hit: Any) -> str:
    fired = int(shots_fired or 0)
    hit = int(shots_hit or 0)
    if fired <= 0:
        return "none"
    accuracy = hit / fired
    if accuracy < 0.25:
        return "low"
    if accuracy < 0.55:
        return "medium"
    return "high"


def pressure_bucket(self_health: Any, opponent_health: Any, opponent_known: bool) -> str:
    health = int(self_health or 0)
    if health <= 25:
        return "critical"
    if not opponent_known:
        return "unknown"
    advantage = health - int(opponent_health or 0)
    if advantage < -30:
        return "losing"
    if advantage > 30:
        return "winning"
    return "stable"


def elapsed_since(timestamp_ms: Any, current_ms: int) -> int | None:
    try:
        value = int(timestamp_ms)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return max(0, current_ms - value)


def damage_trend(last_dealt_ms: Any, last_taken_ms: Any, current_ms: int) -> str:
    dealt_recent = (elapsed_since(last_dealt_ms, current_ms) or 999999) <= 4000
    taken_recent = (elapsed_since(last_taken_ms, current_ms) or 999999) <= 4000
    if dealt_recent and taken_recent:
        return "trading"
    if dealt_recent:
        return "winning_trade"
    if taken_recent:
        return "losing_trade"
    return "quiet"


def pickup_distance(pickup: dict[str, Any], x: Any, y: Any) -> int | None:
    try:
        return int(round(math.dist((float(x), float(y)), (float(pickup["x"]), float(pickup["y"])))))
    except (TypeError, ValueError, KeyError):
        return None


def xy_to_grid_cell(x: Any, y: Any) -> str:
    try:
        xf = float(x)
        yf = float(y)
    except (TypeError, ValueError):
        return ""
    col = int((xf - MAP_BOUNDS["x_min"]) // MAP_CELL_SIZE) + 1
    row = int((MAP_BOUNDS["y_max"] - yf) // MAP_CELL_SIZE) + 1
    col = max(1, min(MAP_COLS, col))
    row = max(1, min(MAP_ROWS, row))
    return f"{chr(ord('A') + row - 1)}{col:02d}"


def blocked_grid_cells() -> list[str]:
    try:
        from pathlib import Path

        path = Path(__file__).resolve().parents[1] / MAP_ASCII_PATH
        rows = [line.rstrip("\n") for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except OSError:
        return []
    cells = []
    for row_index, row_text in enumerate(rows):
        for col_index, char in enumerate(row_text):
            if char == "#":
                cells.append(f"{chr(ord('A') + row_index)}{col_index + 1:02d}")
    return cells


def strategy_pickups_for_observation(x: Any, y: Any) -> list[dict[str, Any]]:
    pickups = []
    for pickup in STATIC_PICKUPS:
        item = dict(pickup)
        item["distance"] = pickup_distance(pickup, x, y)
        item["cell"] = xy_to_grid_cell(pickup.get("x"), pickup.get("y"))
        pickups.append(item)
    return pickups


def angle_delta(current: float, previous: float) -> float:
    return abs((current - previous + 180) % 360 - 180)


def detect_spin(history: deque[dict[str, Any]]) -> bool:
    if len(history) < 3:
        return False
    latest = history[-1]
    cutoff = int(latest["time_ms"]) - 3000
    window = [item for item in history if int(item["time_ms"]) >= cutoff]
    if len(window) < 3 or bool(latest.get("opponent_visible")):
        return False
    angle_change = sum(
        angle_delta(float(window[i]["angle"]), float(window[i - 1]["angle"]))
        for i in range(1, len(window))
    )
    position_delta = math.dist(
        (float(window[0]["x"]), float(window[0]["y"])),
        (float(window[-1]["x"]), float(window[-1]["y"])),
    )
    damage_delta = int(window[-1].get("damage_dealt") or 0) - int(window[0].get("damage_dealt") or 0)
    return angle_change > 270 and position_delta < 80 and damage_delta <= 0


def history_bucket(run_id: str, participant_id: str) -> dict[str, Any]:
    return _HISTORY.setdefault(
        (run_id, participant_id),
        {
            "snapshots": deque(maxlen=12),
            "last_observation": None,
            "last_strategy": None,
            "repeated_action_count": 0,
            "last_seen_ms": None,
            "last_seen_zone": "unknown",
            "last_seen_x": None,
            "last_seen_y": None,
            "last_seen_angle": None,
        },
    )


def last_action_result(previous: dict[str, Any] | None, current: dict[str, Any], spin: bool, stuck: bool) -> str:
    if previous is None:
        return "unknown"
    if int(current.get("damage_dealt") or 0) > int(previous.get("damage_dealt") or 0):
        return "dealt_damage"
    if int(current.get("health") or 0) < int(previous.get("health") or 0):
        return "took_damage"
    if previous.get("distance_bucket") == "far" and current.get("distance_bucket") in {"ideal", "close"}:
        return "closed_distance"
    if previous.get("los_status") == "lost_los" and current.get("los_status") == "visible":
        return "gained_los"
    if previous.get("los_status") == "visible" and current.get("los_status") == "lost_los":
        return "lost_los"
    if stuck:
        return "stuck"
    if spin:
        return "spun"
    return "no_progress"


def recommend_actions(tactical: dict[str, Any]) -> dict[str, list[str]]:
    visible = tactical.get("los") == "visible"
    distance = tactical.get("distance_bucket")
    pressure = tactical.get("pressure")
    if tactical.get("spin_detected"):
        return {"categories": ["recover", "explore", "position"], "actions": ["anti_spin", "switch_lane", "patrol_left", "patrol_right"]}
    if tactical.get("stuck_detected"):
        return {"categories": ["recover", "evade"], "actions": ["unstuck", "retreat_reset", "switch_lane"]}
    if visible and distance == "far":
        return {"categories": ["engage", "position"], "actions": ["push", "close_gap", "flank_left", "flank_right"]}
    if visible and distance in {"ideal", "unknown"}:
        return {"categories": ["engage", "position"], "actions": ["strafe_fight", "suppress", "camp_los"]}
    if visible and distance == "close" and pressure in {"losing", "critical"}:
        return {"categories": ["evade", "recover"], "actions": ["kite", "retreat_reset", "dodge_strafe"]}
    if tactical.get("opponent_recently_seen"):
        return {"categories": ["explore", "position"], "actions": ["scan_last_seen", "flank_left", "flank_right"]}
    return {"categories": ["explore", "position"], "actions": ["patrol_left", "patrol_right", "rotate_route"]}


def make_strategy_observation(full_observation: dict[str, Any], control_mode: str = CONTROL_MODE_HIERARCHICAL) -> dict[str, Any]:
    current_ms = now_ms()
    participant_id = str(full_observation.get("participant_id", ""))
    opponent_id = str(full_observation.get("opponent_id", ""))
    state = full_observation.get("state", {}) if isinstance(full_observation.get("state"), dict) else {}
    run_id = str(state.get("run_id", ""))
    scenario_id = str(state.get("scenario_id", "duel_e1m8"))
    self_raw = dict(full_observation.get("self", {}) or {})
    opponent_raw = dict(full_observation.get("opponent", {}) or {})
    tactical_raw = dict(full_observation.get("tactical_context", {}) or {})
    match_raw = dict(full_observation.get("match", {}) or {})
    self_state = state.get(participant_id, {}) if isinstance(state.get(participant_id), dict) else {}
    bucket = history_bucket(run_id, participant_id)

    current_zone = classify_zone(self_raw.get("x"), self_raw.get("y"), scenario_id)
    opponent_visible = bool(opponent_raw.get("visible"))
    if opponent_visible:
        bucket["last_seen_ms"] = current_ms
        opponent_x = opponent_raw.get("x", self_state.get("opponent_x"))
        opponent_y = opponent_raw.get("y", self_state.get("opponent_y"))
        bucket["last_seen_zone"] = classify_zone(opponent_x, opponent_y, scenario_id)

    snapshot = {
        "time_ms": current_ms,
        "x": self_raw.get("x", 0),
        "y": self_raw.get("y", 0),
        "angle": self_raw.get("angle", 0),
        "health": self_raw.get("health", 0),
        "damage_dealt": self_raw.get("damage_dealt", 0),
        "distance_bucket": self_raw.get("distance_bucket") or tactical_raw.get("distance_bucket"),
        "los_status": self_raw.get("los_status") or tactical_raw.get("los_status"),
        "opponent_visible": opponent_visible,
    }
    bucket["snapshots"].append(snapshot)
    spin = detect_spin(bucket["snapshots"])
    stuck = bool(self_state.get("stuck_recovery")) or "stuck" in (tactical_raw.get("replan_reasons") or [])
    result = last_action_result(bucket.get("last_observation"), snapshot, spin, stuck)
    bucket["last_observation"] = dict(snapshot)
    last_seen_ms = bucket.get("last_seen_ms")
    last_seen_age = current_ms - int(last_seen_ms) if last_seen_ms else None
    pressure = pressure_bucket(self_raw.get("health"), opponent_raw.get("health"), "health" in opponent_raw)
    distance_bucket = self_raw.get("distance_bucket") or tactical_raw.get("distance_bucket") or "unknown"
    los = self_raw.get("los_status") or tactical_raw.get("los_status") or ("visible" if opponent_visible else "lost_los")

    return {
        "control_mode": normalize_control_mode(control_mode),
        "participant_id": participant_id,
        "opponent_id": opponent_id,
        "match": {
            "phase": match_raw.get("phase"),
            "time_left_seconds": max(0.0, float(match_raw.get("timeout_seconds") or 0) - float(match_raw.get("elapsed_time_seconds") or 0)),
            "round": full_observation.get("current_round", state.get("current_round", 1)),
            "total_rounds": full_observation.get("total_rounds", state.get("total_rounds", 1)),
            "has_next_round": bool(full_observation.get("has_next_round", state.get("has_next_round", False))),
            "winner": match_raw.get("winner") or None,
        },
        "self": {
            "health": self_raw.get("health"),
            "ammo": self_raw.get("ammo_bullets"),
            "alive": bool(self_raw.get("alive")),
            "x": self_raw.get("x"),
            "y": self_raw.get("y"),
            "angle": self_raw.get("angle"),
            "zone": current_zone,
            "cell": xy_to_grid_cell(self_raw.get("x"), self_raw.get("y")),
        },
        "opponent": {
            "alive": bool(opponent_raw.get("alive")),
            "visible": opponent_visible,
            "health": opponent_raw.get("health") if opponent_visible and "health" in opponent_raw else None,
            "distance_bucket": distance_bucket,
            "relative_angle_bucket": relative_angle_bucket(opponent_raw.get("relative_angle") if opponent_visible else None),
            "last_seen": {
                "age_ms": last_seen_age,
                "zone": bucket.get("last_seen_zone", "unknown"),
            },
        },
        "tactical": {
            "pressure": pressure,
            "los": los,
            "damage_trend": damage_trend(self_raw.get("last_damage_dealt_ms"), self_raw.get("last_damage_taken_ms"), current_ms),
            "last_action_result": result,
            "stuck_detected": stuck,
            "spin_detected": spin,
            "repeated_action_count": int(bucket.get("repeated_action_count") or 0),
        },
        "map": {
            "current_zone": current_zone,
            "bounds": dict(MAP_BOUNDS),
            "grid": {"rows": "A-X", "cols": "01-32", "cell_size": MAP_CELL_SIZE},
            "blocked_cells": blocked_grid_cells(),
            "route_format": "list of up to 16 grid cells, e.g. ['M05', 'G05', 'G12', 'M17']; every straight segment must avoid blocked_cells",
            "pickups": strategy_pickups_for_observation(self_raw.get("x"), self_raw.get("y")),
        },
    }

def validate_strategy_context(objective: Any = "", target_zone: Any = "", reasoning: Any = "") -> tuple[str, str, str]:
    objective_text = str(objective or "").strip().lower()
    target_zone_text = str(target_zone or "").strip().lower()
    reasoning_text = " ".join(str(reasoning or "").replace("\t", " ").split())

    if objective_text and objective_text not in STRATEGY_OBJECTIVES:
        raise ValueError(f"unsupported strategy objective: {objective_text}")
    if target_zone_text and target_zone_text not in STRATEGY_TARGET_ZONES:
        raise ValueError(f"unsupported strategy target_zone: {target_zone_text}")
    if len(reasoning_text) > STRATEGY_REASONING_MAX_CHARS:
        reasoning_text = reasoning_text[:STRATEGY_REASONING_MAX_CHARS].rstrip()
    return objective_text, target_zone_text, reasoning_text


def validate_strategy(category: Any, action: Any, intensity: Any, commit_ms: Any) -> tuple[str, str, str, int]:
    category_text = str(category or "").strip().lower()
    action_text = str(action or "").strip().lower()
    intensity_text = str(intensity or "medium").strip().lower()
    if category_text not in STRATEGY_ACTIONS:
        raise ValueError("category must be one of " + ", ".join(sorted(STRATEGY_ACTIONS)))
    if action_text not in STRATEGY_ACTIONS[category_text]:
        raise ValueError("action must be one of " + ", ".join(STRATEGY_ACTIONS[category_text]) + f" for category={category_text}")
    if intensity_text not in STRATEGY_INTENSITIES:
        raise ValueError("intensity must be one of low, medium, high")
    return category_text, action_text, intensity_text, clamp_int(commit_ms, COMMIT_MS_MIN, COMMIT_MS_MAX, COMMIT_MS_DEFAULT)


def rewrite_for_anti_spin(category: str, action: str, context: dict[str, Any] | None) -> tuple[str, str]:
    tactical = (context or {}).get("tactical", {}) if isinstance(context, dict) else {}
    if tactical.get("spin_detected") and (category, action) in {
        ("position", "hold_angle"),
        ("position", "camp_los"),
        ("explore", "scan_last_seen"),
    }:
        return "recover", "anti_spin"
    if tactical.get("repeated_action_count", 0) >= 3 and tactical.get("last_action_result") == "no_progress":
        if action.endswith("_left"):
            return category, action.replace("_left", "_right")
        if action.endswith("_right"):
            return category, action.replace("_right", "_left")
        if action == "take_left_lane":
            return category, "take_right_lane"
        if action == "take_right_lane":
            return category, "take_left_lane"
    return category, action


def apply_intensity(expanded: dict[str, Any], category: str, intensity: str) -> None:
    if intensity == "low":
        expanded["aggression"] = 0.35
        if expanded.get("style") == "aggressive":
            expanded["style"] = "balanced"
        if expanded.get("fire_policy") == "suppressive":
            expanded["fire_policy"] = "burst_when_aligned"
            expanded["fire_mode"] = "burst"
        expanded["retreat_if_closer_than"] = max(int(expanded.get("retreat_if_closer_than") or 0), 350)
    elif intensity == "high":
        expanded["aggression"] = 0.85
        if category in {"engage", "position"}:
            expanded["style"] = "aggressive"
        if category == "engage":
            expanded["fire_policy"] = "suppressive"
            expanded["fire_mode"] = "suppressive"
            expanded["push_if_farther_than"] = min(int(expanded.get("push_if_farther_than") or 1000), 800)
    else:
        expanded["aggression"] = 0.60


def expand_strategy(
    *,
    participant_id: str,
    category: Any,
    action: Any,
    intensity: Any = "medium",
    commit_ms: Any = COMMIT_MS_DEFAULT,
    sequence_number: Any = None,
    target_zone: Any = "",
    objective: Any = "",
    reasoning: Any = "",
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    category_text, action_text, intensity_text, commit_value = validate_strategy(category, action, intensity, commit_ms)
    objective_text, target_zone_text, reasoning_text = validate_strategy_context(objective, target_zone, reasoning)
    category_text, action_text = rewrite_for_anti_spin(category_text, action_text, context)
    preset = PRESETS[(category_text, action_text)]
    expanded = {**BASE_DEFAULTS, **preset}
    expanded["duration_ms"] = commit_value
    expanded["strategy_commit_ms"] = commit_value
    expanded["participant_id"] = participant_id
    expanded["target_id"] = "player_2" if participant_id == "player_1" else "player_1"
    expanded["sequence_number"] = sequence_number
    expanded["intent_raw"] = f"{category_text}/{action_text}"
    expanded["strategy_source"] = "hierarchical"
    expanded["strategy_category"] = category_text
    expanded["strategy_action"] = action_text
    expanded["strategy_intensity"] = intensity_text
    expanded["strategy_objective"] = objective_text
    expanded["strategy_target_zone"] = target_zone_text
    expanded["strategy_reasoning"] = reasoning_text
    if target_zone_text:
        expanded["target_zone"] = target_zone_text
    apply_intensity(expanded, category_text, intensity_text)
    if (context or {}).get("tactical", {}).get("stuck_detected"):
        expanded["stuck_recovery_strategy"] = "strafe_out"
    return expanded


def record_strategy(run_id: str, participant_id: str, category: str, action: str) -> int:
    bucket = history_bucket(run_id, participant_id)
    previous = bucket.get("last_strategy") or {}
    if previous.get("category") == category and previous.get("action") == action:
        bucket["repeated_action_count"] = int(bucket.get("repeated_action_count") or 0) + 1
    else:
        bucket["repeated_action_count"] = 1
    bucket["last_strategy"] = {"category": category, "action": action, "time_ms": now_ms()}
    return int(bucket["repeated_action_count"])









