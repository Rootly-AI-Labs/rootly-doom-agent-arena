"""Shared prompt and token helpers for browser-created Doom Arena duels."""

from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Any

from doom_arena_map_blueprints import format_map_blueprint_prompt, load_geometry_blueprint, load_variants_config


REPO_ROOT = Path(__file__).resolve().parents[1]
RESULTS_ROOT = REPO_ROOT / "benchmarks" / "results"
CONTROLLER_TOKENS_PATH = REPO_ROOT / "src" / "arena_controller_tokens.local.json"
MAP_BLUEPRINTS_DIR = Path(__file__).resolve().parent / "map_blueprints"
MAP_BOUNDS = {"x_min": -1024, "x_max": 1024, "y_min": -768, "y_max": 768}
MAP_CELL_SIZE = 64
MAP_ROWS = 24
MAP_COLS = 32


def _xy_to_grid_cell(x: Any, y: Any) -> str:
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


def load_map_blueprint(scenario_id: str) -> str:
    config = load_variants_config()
    scenario_text = str(scenario_id or "").strip()
    if scenario_text not in config.get("variants", {}):
        return ""
    return format_map_blueprint_prompt(scenario_text)


def _cross_round_recap_section(enabled: bool, total_rounds: int) -> str:
    if total_rounds <= 1:
        return ""
    return """
Cross-round recap:
- If `previous_rounds` appears in observations, use it only to avoid repeating failed openings.
- Recaps are intentionally tiny: winner, whether you won, damage, first objectives, and resource pickup owner when available.

"""

def build_controller_tokens(run_id: str, player_1_model: str, player_2_model: str, enforce: bool) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "player_1": {
            "model": player_1_model,
            "controller_token": secrets.token_urlsafe(24),
        },
        "player_2": {
            "model": player_2_model,
            "controller_token": secrets.token_urlsafe(24),
        },
        "enforce_controller_tokens": enforce,
    }


def write_controller_tokens(run_dir: Path, tokens: dict[str, Any]) -> None:
    text = json.dumps(tokens, indent=2) + "\n"
    (run_dir / "controller_tokens.json").write_text(text, encoding="utf-8")
    CONTROLLER_TOKENS_PATH.write_text(text, encoding="utf-8")


def _map_blueprint_section(enabled: bool, scenario_id: str) -> str:
    if not enabled:
        return ""
    blueprint = load_map_blueprint(scenario_id)
    if not blueprint:
        return ""
    return f"""
Map blueprint:
Coordinates in your observations use the same frame as the blueprint below.
North is +Y, East is +X. Movement is collision-pathed by the autopilot - use
the blueprint for strategic reasoning, not for exact pathing.

{blueprint}

"""


def _nearest_spawn_marker_cell(rows: list[list[str]], row: int, col: int) -> tuple[int, int]:
    row_count = len(rows)
    col_count = len(rows[0]) if rows else 0
    if row_count <= 0 or col_count <= 0:
        return row, col
    row = max(0, min(row_count - 1, row))
    col = max(0, min(col_count - 1, col))
    if rows[row][col] != "#":
        return row, col
    limit = max(row_count, col_count)
    for radius in range(1, limit + 1):
        for candidate_row in range(row - radius, row + radius + 1):
            for candidate_col in range(col - radius, col + radius + 1):
                if abs(candidate_row - row) != radius and abs(candidate_col - col) != radius:
                    continue
                if not (0 <= candidate_row < row_count and 0 <= candidate_col < col_count):
                    continue
                if rows[candidate_row][candidate_col] != "#":
                    return candidate_row, candidate_col
    return row, col


def _variant_ascii_map(blueprint: dict[str, Any]) -> str:
    raw_ascii = str(blueprint.get("ascii_map", "")).strip()
    if not raw_ascii:
        return ""
    rows = []
    for raw_row in raw_ascii.splitlines():
        if not raw_row:
            continue
        # Static prompt maps show geometry only. Strip player/spawn markers so
        # the initial prompt does not reveal participant locations.
        rows.append("".join("#" if char == "#" else "." for char in raw_row))
    return "\n".join(rows)


def _blocked_cell_list(ascii_map: str) -> str:
    cells = []
    for row_index, row_text in enumerate(ascii_map.splitlines()):
        for col_index, char in enumerate(row_text):
            if char == "#":
                cells.append(f"{chr(ord('A') + row_index)}{col_index + 1:02d}")
    return ", ".join(cells)


def _static_pickup_context(enable_weapon_pickups: bool, blueprint: dict[str, Any]) -> str:
    pickups = []
    for pickup in blueprint.get("pickups", []):
        if pickup.get("type") == "weapon" and not enable_weapon_pickups:
            continue
        name = str(pickup.get("name") or pickup.get("type") or "pickup")
        note = "heals +100 up to 150" if pickup.get("type") == "health" else "5-pellet weapon pickup"
        pickups.append((pickup.get("id", ""), name, pickup.get("x"), pickup.get("y"), note))
    lines = []
    for pickup_id, name, x, y, note in pickups:
        lines.append(f"- {pickup_id}: {name}, cell={_xy_to_grid_cell(x, y)}, x={x}, y={y}, {note}.")
    return "\n".join(lines) if lines else "- none"


def _static_map_context_section(
    scenario_id: str,
    participant_id: str = "",
    enable_weapon_pickups: bool = True,
) -> str:
    try:
        blueprint = load_geometry_blueprint(scenario_id)
    except Exception:
        return ""
    bounds = blueprint.get("bounds", {})
    spawns = blueprint.get("spawns", {})
    own_spawn = spawns.get(participant_id, {}) if isinstance(spawns, dict) else {}
    own_spawn_line = ""
    if own_spawn:
        own_spawn_cell = _xy_to_grid_cell(own_spawn.get("x"), own_spawn.get("y"))
        own_spawn_line = (
            f"- Your selected spawn: x={own_spawn.get('x')} y={own_spawn.get('y')} "
            f"cell={own_spawn_cell} angle={own_spawn.get('angle_deg')}. Opponent spawn is intentionally omitted.\n"
        )
    ascii_map = _variant_ascii_map(blueprint)
    if not ascii_map:
        return ""
    blocked_cells = _blocked_cell_list(ascii_map)
    return f"""
Static map context:
- The static map is provided here once so repeated observations stay compact.
- Use this map from chat memory while observations provide live positions and visibility.
- Map: `{blueprint.get('map_id', 'duel_e1m8')}` / variant `{blueprint.get('scenario_id', scenario_id)}`.
- Cell size: each ASCII cell is `{blueprint.get('cell_size', 64)} x {blueprint.get('cell_size', 64)}` Doom units.
- Bounds: x={bounds.get('x_min')}..{bounds.get('x_max')}, y={bounds.get('y_min')}..{bounds.get('y_max')}.
- Coordinate frame: +x is east/right, -x is west/left, +y is north/up, -y is south/down.
- Grid frame: rows `A-X` are north/top to south/bottom; columns `01-32` are west/left to east/right.
{own_spawn_line}- Legend: `.` walkable, `#` wall/collision/sight blocker.
- Blocked route cells: {blocked_cells}.
- Opponent spawn and player markers are intentionally omitted from the static map prompt.
- Observations include compact `map.pickups` entries with resource id, availability, cell, and distance from you.
- The Doom autopilot handles frame-level movement.

Static resources:
{_static_pickup_context(enable_weapon_pickups, blueprint)}

ASCII map:
```text
{ascii_map}
```

"""


def instructions(
    participant_id: str,
    model: str,
    opponent_id: str,
    controller_token: str,
    enforce_tokens: bool,
    decision_cadence_ms: int = 750,
    intent_duration_ms: int = 25000,
    current_round: int = 1,
    total_rounds: int = 1,
    enable_cross_round_recap: bool = False,
    enable_map_blueprint: bool = False,
    scenario_id: str = "duel_e1m8",
    control_mode: str = "full",
    enable_weapon_pickups: bool = True,
) -> str:
    token_line = (
        f"Your controller_token is: `{controller_token}`\n\n"
        "Always include `controller_token` when calling `set_participant_ready`, "
        "`wait_for_match_start`, `get_participant_observation`, `set_participant_intent`, "
        "and `stop_participant_intent`.\n"
        if enforce_tokens
        else "Controller token enforcement is disabled for this local trusted smoke run.\n"
    )
    session_line = (
        f"This benchmark session has `{total_rounds}` total matches. "
        f"You are starting match `{current_round}`.\n"
        if total_rounds > 1
        else "This benchmark session has a single match.\n"
    )
    if str(control_mode).strip().lower() == "hierarchical":
        strategy_token_line = (
            f"Your controller_token is: `{controller_token}`\n\n"
            "Always include `controller_token` when calling `set_participant_ready`, "
            "`wait_for_match_start`, `get_participant_observation`, `set_participant_plan`, "
            "`stop_participant_intent`, and `get_match_result`.\n"
            if enforce_tokens
            else "Controller token enforcement is disabled for this local trusted smoke run.\n"
        )
        stop_rules = (
            """Stop rules:
- `has_next_round=false` only means there is no later match after the current one. It is not a stop signal by itself.
- If `phase` is `waiting_for_agents`, `waiting_for_first_intents`, or `combat`, continue the normal ready/opening/observe/plan loop even when `has_next_round=false`.
- Stop only when `get_match_result` returns `phase="finished"` and `has_next_round=false`; then call `stop_participant_intent` once and stop all tool calls.
- If `phase="finished"` and `has_next_round=true`, poll only `get_match_result` until `run_id` changes, then start the next match with `set_participant_ready` and reset `sequence_number=1`.

"""
            if total_rounds > 1
            else """Stop rule:
- This single match is still active while `phase` is `waiting_for_agents`, `waiting_for_first_intents`, or `combat`; continue the normal ready/opening/observe/plan loop.
- Stop only when `get_match_result` returns `phase="finished"`; then call `stop_participant_intent` once and stop all tool calls.

"""
        )
        return f"""# Doom Arena MCP Instructions: {participant_id}

You are one of two separate MCP agents in Doom Arena Duel.
You control only `{participant_id}`. Do not control `{opponent_id}`.

{strategy_token_line}
{session_line}
Core rules:
- Normal action tool: `set_participant_plan` only.
- Do not use `set_participant_strategy`, `set_participant_intent`, detailed tactical parameters, or low-level movement/input tools in this mode.
- Read compact observations using `match`, `self`, `opponent`, `tactical`, and `map`.
- Choose objective, route, engagement_policy, and short reasoning together in one tool call.
- Keep `reasoning` short: one sentence about why this route was chosen.

Loop:
- Ready once, observe, send an opening `set_participant_plan` with `sequence_number=1`, then call `wait_for_match_start`.
- During combat, repeat: `get_participant_observation` -> `set_participant_plan` -> observe again.
- Increment `sequence_number` after every plan call.
- Do not choose timing fields or wait for the route lease; newer higher-sequence plans override immediately.
- Do not use `Start-Sleep`, timers, or manual waiting loops.
- On the final match, `has_next_round=false` can appear before the match is finished. Keep playing until `phase="finished"`.

Allowed MCP tools:
- `set_participant_ready`
- `get_participant_observation`
- `set_participant_plan`
- `wait_for_match_start`
- `get_match_result`
- `stop_participant_intent`
- `get_duel_events` if useful

Plan schema:

```json
{{
  "participant_id": "{participant_id}",
  "controller_token": "{controller_token if enforce_tokens else '<disabled>'}",
  "objective": "your_goal",
  "route": ["A01", "A02"],
  "engagement_policy": "engage_if_visible",
  "reasoning": "short reason",
  "sequence_number": 1
}}
```

`objective` and `reasoning` are lightweight planning/logging fields. The route is the only movement plan you submit.

Route rules:
- `route` is a list of up to 16 grid cells, e.g. `["M05", "G05", "G12", "M17"]`.
- Rows are `A-X` from north/top to south/bottom. Columns are `01-32` from west/left to east/right.
- Each cell is `64 x 64` Doom units. The server converts cells into Doom coordinates at the cell center.
- Do not put waypoints inside `#` wall cells.
- Do not choose any cell listed under `Blocked route cells`.
- Every straight route segment must avoid blocked cells, including the segment from your current `self.cell` to the first waypoint. Add intermediate cells to route around walls.
- Do not use broad strategy labels like "clear upper" or "flank left" as the route. Submit exact cells only.
- Do not replace a route just because it is still executing. Submit a new route when the route is blocked, stale, complete, stuck, enemy contact changes, or your plan intentionally changes.
- The Doom autopilot handles frame-level turning, collision, and waypoint following.

Allowed engagement_policy:
- `engage_if_visible`
- `avoid_until_target` (prioritize reaching the route target; Doom suppresses attack while the route is still in progress)
- `hold_fire`
- `force_fight`

{_static_map_context_section(scenario_id, participant_id, enable_weapon_pickups)}

{stop_rules}

{_cross_round_recap_section(enable_cross_round_recap, total_rounds)}
"""
    return f"""# Doom Arena MCP Instructions: {participant_id}

You are one of two separate MCP agents in Doom Arena Duel.
You are `{participant_id}`.
You control only `{participant_id}`.

{token_line}
{session_line}
Core rule:
- You do not control frame-level movement.
- You are sending short-lived tactical policies.
- Doom continues executing the latest LLM-authored policy until a newer one arrives or the intent is manually stopped. If a chat response is slow, Doom may mark the policy `stale` but still executes it instead of falling back to no policy.
- The match does not begin executing movement until both agents are ready and both agents have submitted their first high-level intent.
- After sending an intent, immediately observe again and choose the next intent; do not wait for the previous action to finish.
- If the previous intent is still active, send a higher `sequence_number` to override it with the updated tactical policy.
- Do not run your own timer, sleep loop, or `Start-Sleep`; keep updating as fast as the chat environment allows.
- During the active match, use MCP tool calls only between decisions; do not add prose or explanations unless the benchmark session is finished or the user asks.
- Use MCP tool `set_participant_intent` for normal play.
- Do not use frame-level `forward`, `strafe`, `turn`, or `attack` controls.
- Watch `run_id`, `current_round`, `total_rounds`, and `has_next_round` in observations and match results.

Loop template:
1. Call MCP tool `set_participant_ready` once with `participant_id="{participant_id}"` and your controller token.
2. Call MCP tool `get_participant_observation` while phase may still be `waiting_for_agents`.
3. Choose a synchronized opening intent, set `sequence_number=1`, use `duration_ms=60000`, and call `set_participant_intent`. This arms your first policy but Doom will not execute movement until both agents have submitted opening intents. Your opening intent can be `engage_opponent`, `strafe_attack`, `search`, or `hold`; pick the best action from the current observation.
4. Call MCP tool `wait_for_match_start` with `participant_id="{participant_id}"`, your controller token, and `timeout_ms=60000`.
5. Once the phase is `combat`, immediately call `get_participant_observation` and choose the next high-level intent.
6. Increment `sequence_number`.
7. Call MCP tool `set_participant_intent` once for this decision with `participant_id="{participant_id}"`, your controller token, the incremented `sequence_number`, and one normalized intent.
8. Immediately call `get_participant_observation` again and choose the next high-level intent, even if the previous intent is still executing.
9. Repeat observation and intent decisions until `get_match_result` shows `phase="finished"`.
10. If `has_next_round=true`, stay in the same chat turn, keep polling `get_match_result` until `run_id` changes, then treat that as the next match: call `set_participant_ready` again, reset `sequence_number=1`, and repeat the opening flow.
11. If `has_next_round=false` before `phase="finished"`, keep playing the current final match. Stop only after the final match result reports `phase="finished"`.

Allowed MCP tools:
- `set_participant_ready`
- `wait_for_match_start`
- `get_participant_observation`
- `set_participant_intent`
- `stop_participant_intent`
- `get_match_result`
- `get_duel_events` if useful

Available intents:
- `engage_opponent`
- `strafe_attack`
- `hold`
- `search`

Available styles:
- `balanced`
- `aggressive`
- `evasive`
- `cautious`

Intent schema example:

```json
{{
  "participant_id": "{participant_id}",
  "controller_token": "{controller_token if enforce_tokens else '<disabled>'}",
  "intent": "strafe_attack",
  "style": "aggressive",
  "target_id": "{opponent_id}",
  "preferred_distance": 600,
  "aggression": 0.7,
  "duration_ms": {intent_duration_ms},
  "sequence_number": 1,
  "decision_cadence_ms": {decision_cadence_ms},
  "strafe_direction": "auto",
  "movement_bias": "circle",
  "fire_policy": "only_when_aligned",
  "distance_policy": "maintain",
  "aim_tolerance": 10,
  "fire_burst_ms": 250,
  "min_fire_alignment": 8,
  "min_distance": 350,
  "max_distance": 900,
  "retreat_if_closer_than": 300,
  "push_if_farther_than": 1000,
  "los_lost_action": "sweep",
  "stuck_recovery_strategy": "strafe_out",
  "turn_policy": "turn_to_enemy",
  "navigation_target": "opponent",
  "fire_mode": "fire_when_aligned",
  "replan_if": ["lost_los", "stuck", "low_health"]
}}
```

Fast tactical mode:
- Keep the observe -> intent -> observe loop moving as fast as the chat environment allows.
- Use `duration_ms={intent_duration_ms}` for normal combat intents as a lease, not as a delay. Newer higher-sequence intents still override immediately.
- If your previous intent is shown as `stale`, immediately send a higher-sequence replacement; the stale policy is only there to prevent no-policy freezes while chat is slow.
- Treat `decision_cadence_ms={decision_cadence_ms}` as metadata/debug only, not as an instruction to wait.
- Include `sequence_number` and increment it on every decision.
- Newer intents with higher `sequence_number` override older intents immediately, even if the older intent has not expired.
- Do not wait for `autopilot_action` such as `engage_opponent`, `strafe_attack`, `search`, or `hold` to complete; observe and replace it with the best current policy.
- Actively choose `fire_policy`, `fire_mode`, `distance_policy`, `movement_bias`, `turn_policy`, `navigation_target`, and `strafe_direction`; also choose `los_lost_action`, `stuck_recovery_strategy`, and distance/fire bounds every time you send an intent.
- Do not send `movement_primitive` by default. Include it only as a short one-policy override when the current observation specifically calls for a primitive movement, and do not keep repeating `circle_left` or `circle_right` after line of sight is lost.
- Prefer explicit `strafe_direction` values (`left`, `right`, `alternate`, `hold_direction`, or `switch_if_hit`) during combat; use `auto` only when you are unsure.

Stable mode:
- Use `duration_ms` between 20000 and 25000.
- Use this when you need slower, more stable tactical planning.

Intent policy:

| Situation | Intent and tactical controls |
| --- | --- |
| Match `phase` is `waiting_for_agents`, `waiting_for_first_intents`, or `combat` and `has_next_round=false` | This is the active final match. Continue the normal ready/opening/observe/intent loop; do not stop yet. |
| Match `phase` is `finished` and `has_next_round=false` | Call `stop_participant_intent`, then stop the loop. |
| Match `phase` is `finished` and `has_next_round=true` | Keep polling `get_match_result` until `run_id` changes, then start the next match by calling `set_participant_ready` again and resetting `sequence_number` to `1`. |
| Opponent hidden / `los_status=lost_los` | `search`, style `balanced`, `fire_policy=hold_fire`, `movement_bias=direct`, `distance_policy=maintain`, `navigation_target=last_seen_enemy`, omit `movement_primitive`. |
| Opponent visible and far / `distance_bucket=far` | `engage_opponent`, style `balanced`, `distance_policy=close`, `movement_bias=direct`, `fire_policy=only_when_aligned`. |
| Opponent visible and close / `distance_bucket=close` | `strafe_attack`, style `aggressive` or `evasive`, `distance_policy=kite` if pressured, otherwise `maintain`, `movement_bias=evasive` or `circle`, `fire_policy=suppressive`. |
| Low health / `pressure_state=critical` or `losing` | Prefer `strafe_attack`, style `evasive`, `distance_policy=kite`, `movement_bias=evasive`, `fire_policy=burst_when_aligned` or `only_when_aligned`. |
| Winning with good health | Prefer `strafe_attack`, style `aggressive`, `distance_policy=maintain`, `movement_bias=circle`, `fire_policy=suppressive`. |
| `replan_recommended=true` | Change at least one of `distance_policy`, `movement_bias`, `fire_policy`, or `strafe_direction` unless the current policy already matches the reason. |
| Unsure what to do | `engage_opponent`, style `balanced`, `distance_policy=maintain`, `movement_bias=direct`, `fire_policy=only_when_aligned`. |

Tactical parameter rules:
- `fire_policy=hold_fire` only when searching or avoiding bad shots with no line of sight.
- `fire_policy=only_when_aligned` is the conservative default.
- `fire_policy=burst_when_aligned` is for low health or evasive play.
- `fire_policy=suppressive` is for visible close fights or when pushing an advantage.
- `distance_policy=close` when the opponent is far and visible.
- `distance_policy=maintain` when distance is ideal or you are winning a stable fight.
- `distance_policy=kite` when target is close, health is low, or pressure is high.
- `movement_bias=direct` when closing distance.
- `movement_bias=circle` when visible and near ideal range.
- `movement_bias=evasive` when close, losing, or taking damage.
- `movement_bias=cautious` when winning near timeout or avoiding overcommitment.
- `strafe_direction=alternate` is a good default for combat; switch to `left` or `right` if the prior direction is not working.
- `aim_tolerance` and `min_fire_alignment` control how tightly aim must line up before firing; lower values are stricter.
- `fire_burst_ms` controls burst length when using `fire_policy=burst_when_aligned`.
- `min_distance`, `max_distance`, `retreat_if_closer_than`, and `push_if_farther_than` control spacing around the opponent.
- `los_lost_action` controls what Doom does when line of sight is lost: `turn_left`, `turn_right`, `advance_last_seen`, `hold_angle`, or `sweep`.
- `stuck_recovery_strategy` controls how Doom escapes stuck states: `back_up`, `turn_left`, `turn_right`, `strafe_out`, or `default`.
- `movement_primitive` is optional and overrides the high-level movement pattern for one policy only: `advance`, `retreat`, `strafe_left`, `strafe_right`, `circle_left`, `circle_right`, or `hold_position`. Omit it unless you need that exact primitive right now.
- `turn_policy` controls non-frame-level turning: `auto`, `turn_to_enemy`, `sweep_left`, `sweep_right`, `hold_angle`, or `face_last_seen`.
- `navigation_target` controls broad movement target: `opponent`, `last_seen_enemy`, `center`, `left_lane`, `right_lane`, `keep_distance`, or `none`.
- `fire_mode` controls firing style: `auto`, `hold_fire`, `fire_when_aligned`, `single_shot`, `burst`, or `suppressive`.

State fields to watch:
- `phase`
- `run_id`
- `current_round`
- `total_rounds`
- `has_next_round`
- `winner`
- `controller_mode`
- `intent`
- `intent_status`
- `autopilot_action`
- `autopilot_reason`
- `aim_error`
- `stuck_recovery`
- `replan_recommended`
- `replan_reasons`
- `health_delta`
- `distance_bucket`
- `los_status`
- `pressure_state`
- `last_damage_taken_ms`
- `last_damage_dealt_ms`
- `requested_fire_policy`
- `executed_fire_action`
- `requested_distance_policy`
- `executed_movement_action`
- `requested_strafe_direction`
- `executed_strafe_direction`
- `requested_los_lost_action`
- `requested_stuck_recovery_strategy`
- `requested_movement_primitive`
- `requested_turn_policy`
- `requested_navigation_target`
- `requested_fire_mode`
- `executed_turn_policy`
- `executed_navigation_target`
- `executed_fire_mode`
- `policy_compliance_reason`
- `aim_tolerance`
- `fire_burst_ms`
- `min_fire_alignment`
- `min_distance`
- `max_distance`
- `retreat_if_closer_than`
- `push_if_farther_than`
- `los_lost_action`
- `stuck_recovery_strategy`
- `movement_primitive`
- `turn_policy`
- `navigation_target`
- `fire_mode`
- `sequence_number`
- `decision_cadence_ms`
- `health`
- `ammo`
- `opponent_distance` or distance if available
- `opponent_visible` or line of sight if available

Loop behavior:
- Signal readiness at the start of each match with `set_participant_ready`.
- Send one opening `set_participant_intent` before calling `wait_for_match_start`; choose the best current opening action from the observation. It is a synchronized start signal, not immediate movement.
- Use a long opening intent duration such as `duration_ms=60000` so it stays armed while the other participant connects.
- Use `wait_for_match_start` after the opening intent so both participants begin executing first actions together.
- If `wait_for_match_start` times out and phase is still `waiting_for_agents`, refresh your opening intent with the same plan and a higher `sequence_number`, then call `wait_for_match_start` again.
- Observe state before every intent decision.
- Pick one high-level intent.
- Use `set_participant_intent`, not frame-level movement, for normal play.
- After each `set_participant_intent`, immediately observe again and send the next updated intent if the match is still active.
- Treat every post-start intent as a replaceable tactical policy. If the last intent is still running, override it with the new higher-sequence intent.
- Do not call `Start-Sleep` or run your own delay.
- Reassess and refresh the intent before it expires if the same plan still makes sense.
- Keep incrementing `sequence_number` within the current match; reset it to `1` when a new `run_id` starts.
- Do not stop just because `has_next_round=false`; that can simply mean the current match is the final match.
- Stop only when `get_match_result` returns `phase="finished"` and `has_next_round=false`.
- If `phase="finished"` and `has_next_round=true`, keep polling until `run_id` changes, then start the next match.
- During benchmark loops, avoid prose if tool-only behavior is expected.

Stop rules - read carefully:
- When `get_match_result` returns any phase other than `finished`, keep playing the current match even if `has_next_round=false`.
- When `get_match_result` returns `phase="finished"` AND `has_next_round=false`:
  call `stop_participant_intent` once, then **stop all tool calls immediately**.
  Do not call `get_participant_observation`, `set_participant_intent`, or any other tool after this.
- When `get_match_result` returns `phase="finished"` AND `has_next_round=true`:
  call only `get_match_result` (no other tools) until `run_id` changes, then
  restart with `set_participant_ready` for the new round.

Rules:
- Control only `{participant_id}`.
- Do not control `{opponent_id}`.
- Never call `set_participant_ready` for `{opponent_id}`.
- Never call `set_participant_intent` for `{opponent_id}`.
- Only send your own opening high-level intent while phase is `waiting_for_agents`; Doom will hold it until both opening intents are present.
- Use `get_participant_observation` before each high-level intent decision.
- Use `set_participant_intent` once per decision during normal play.
- Do not call or request tools that directly mutate health, position, ammo, or winner.
- Both players receive the same full shared state for this MVP.
- Keep choosing high-level intents until the benchmark session is finished.

{_map_blueprint_section(enable_map_blueprint, scenario_id)}
{_cross_round_recap_section(enable_cross_round_recap, total_rounds)}
Deprecated frame-level control guidance:
- Do not call low-level participant input tools or follow old instructions that tell you to continuously choose `forward`, `strafe`, `turn`, or `attack`.
- The Doom-side autopilot converts your high-level intent into normal gameplay controls.
"""









