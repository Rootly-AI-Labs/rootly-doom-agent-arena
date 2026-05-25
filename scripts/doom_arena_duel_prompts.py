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


def load_map_blueprint(scenario_id: str) -> str:
    config = load_variants_config()
    scenario_text = str(scenario_id or "").strip()
    if scenario_text not in config.get("variants", {}):
        return ""
    return format_map_blueprint_prompt(scenario_text)


def _cross_round_recap_section(enabled: bool, total_rounds: int) -> str:
    if not enabled or total_rounds <= 1:
        return ""
    return """
Cross-round learning:
- Your observation includes a `previous_rounds` array with a recap of prior rounds.
- Each entry has: `round`, `winner`, `terminal_reason`, `elapsed_time_seconds`,
  `your_final_health`, `your_damage_dealt`, `your_hit_rate`,
  `opponent_prevailing_intent`, `spawn_variant`.
- On round 1 `previous_rounds` is empty â€” this is expected.
- Use recaps to adapt: if you lost last round, change your opening intent or spacing.
  If opponent's `prevailing_intent` was `search`, expect passive play and push early.
- Do not spend more than one decision reacting to recap data; keep the observe-intent loop fast.

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
    rows = [list(row) for row in raw_ascii.splitlines() if row]
    if not rows:
        return ""
    for row_index, row in enumerate(rows):
        for col_index, char in enumerate(row):
            if char in {"1", "2"}:
                rows[row_index][col_index] = "."
    bounds = blueprint.get("bounds", {})
    cell_size = int(blueprint.get("cell_size", 64) or 64)
    x_min = int(bounds.get("x_min", -(len(rows[0]) * cell_size) // 2))
    y_max = int(bounds.get("y_max", (len(rows) * cell_size) // 2))
    spawns = blueprint.get("spawns", {})
    for marker, player_key in (("1", "player_1"), ("2", "player_2")):
        spawn = spawns.get(player_key, {}) if isinstance(spawns, dict) else {}
        try:
            x = float(spawn.get("x"))
            y = float(spawn.get("y"))
        except (TypeError, ValueError):
            continue
        col = int((x - x_min) // cell_size)
        row = int((y_max - y) // cell_size)
        row, col = _nearest_spawn_marker_cell(rows, row, col)
        rows[row][col] = marker
    return "\n".join("".join(row) for row in rows)


def _static_map_context_section(scenario_id: str) -> str:
    try:
        blueprint = load_geometry_blueprint(scenario_id)
    except Exception:
        return ""
    bounds = blueprint.get("bounds", {})
    spawns = blueprint.get("spawns", {})
    player_1 = spawns.get("player_1", {})
    player_2 = spawns.get("player_2", {})
    ascii_map = _variant_ascii_map(blueprint)
    if not ascii_map:
        return ""
    wall_count = ascii_map.count("#")
    return f"""
Static map context:
- The static map is provided here once so repeated observations stay compact.
- Use this map from chat memory while observations provide live positions and visibility.
- Map: `{blueprint.get('map_id', 'duel_e1m8')}` / variant `{blueprint.get('scenario_id', scenario_id)}`.
- Cell size: each ASCII cell is `{blueprint.get('cell_size', 64)} x {blueprint.get('cell_size', 64)}` Doom units.
- Bounds: x={bounds.get('x_min')}..{bounds.get('x_max')}, y={bounds.get('y_min')}..{bounds.get('y_max')}.
- Coordinate frame: +x is east/right, -x is west/left, +y is north/up, -y is south/down.
- Legend: `.` walkable, `#` wall/collision/sight blocker, `1` Player 1 selected spawn, `2` Player 2 selected spawn.
- Wall cells: `{wall_count}`. Every `#` is generated into Doom wall collision and line-of-sight blocking geometry.
- Selected spawns: player_1 x={player_1.get('x')} y={player_1.get('y')} angle={player_1.get('angle_deg')}; player_2 x={player_2.get('x')} y={player_2.get('y')} angle={player_2.get('angle_deg')}.
- The `1` and `2` markers below are overlaid from the selected spawn variant, so they can differ from the raw map `.txt` markers.
- Use the map for broad strategy and memory, not exact path planning. The Doom autopilot handles collision pathing.

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
            "`wait_for_match_start`, `get_participant_observation`, `set_participant_strategy`, "
            "`stop_participant_intent`, and `get_match_result`.\n"
            if enforce_tokens
            else "Controller token enforcement is disabled for this local trusted smoke run.\n"
        )
        return f"""# Doom Arena MCP Instructions: {participant_id}

You are one of two separate MCP agents in Doom Arena Duel.
You control only `{participant_id}`. Do not control `{opponent_id}`.

{strategy_token_line}
{session_line}
Core rules:
- Use hierarchical strategy control only.
- Use `set_participant_strategy` for normal play.
- Do not use `set_participant_intent` in hierarchical mode.
- Do not send detailed tactical parameters such as `movement_bias`, `fire_policy`, `distance_policy`, `navigation_target`, or `turn_policy`.
- Do not call low-level movement/input tools.
- Read compact observations using `match`, `self`, `opponent`, `tactical`, `map`, `allowed_actions`, and `recommended`.
- Choose category and action together in one tool call. Do not call one tool for category and another for action.

Loop:
1. Call `set_participant_ready` once with `participant_id="{participant_id}"` and your controller token.
2. Call `get_participant_observation`.
3. Send one opening `set_participant_strategy` with `sequence_number=1`.
4. Call `wait_for_match_start` with `participant_id="{participant_id}"`, your controller token, and `timeout_ms=60000`.
5. During combat, repeat: `get_participant_observation` -> choose exactly one `category`/`action`/`intensity` -> call `set_participant_strategy`.
6. Increment `sequence_number` after every strategy call.
7. After each `set_participant_strategy`, immediately observe again if the match is still active.
8. Do not choose timing fields. The server uses an 8000 ms policy lease by default; it is not a sleep timer and newer higher-sequence strategies override immediately.
9. Do not use `Start-Sleep`, timers, or manual waiting loops. Keep updates moving as fast as the chat environment allows.

Allowed MCP tools:
- `set_participant_ready`
- `get_participant_observation`
- `set_participant_strategy`
- `wait_for_match_start`
- `get_match_result`
- `stop_participant_intent`
- `get_duel_events` if useful

Strategy schema:

```json
{{
  "participant_id": "{participant_id}",
  "controller_token": "{controller_token if enforce_tokens else '<disabled>'}",
  "category": "engage",
  "action": "strafe_fight",
  "intensity": "medium",
  "sequence_number": 1
}}
```

The server applies an internal 8000 ms policy lease to every strategy call. Do not include timing fields in normal play.\n\nAllowed categories and actions:
- `explore`: `scan_last_seen`, `patrol_left`, `patrol_right`, `rotate_route`, `probe_center`
- `engage`: `push`, `strafe_fight`, `suppress`, `close_gap`, `finish_low_health`
- `evade`: `kite`, `break_los`, `retreat_reset`, `dodge_strafe`, `hold_fire_reposition`
- `position`: `flank_left`, `flank_right`, `camp_los`, `hold_angle`, `take_left_lane`, `take_right_lane`
- `recover`: `unstuck`, `anti_spin`, `switch_lane`, `reset_to_center`, `reverse_route`

Allowed intensity:
- `low`
- `medium`
- `high`

{_static_map_context_section(scenario_id)}Decision guide:
- Opponent visible and far: use `engage/push`, `engage/close_gap`, or `position/flank_left` / `position/flank_right`.
- Opponent visible at good range: use `engage/strafe_fight`, `engage/suppress`, or `position/camp_los`.
- Opponent visible and close while losing: use `evade/kite`, `evade/retreat_reset`, or `evade/dodge_strafe`.
- Opponent hidden but recently seen: use `explore/scan_last_seen`, `position/flank_left`, or `position/flank_right`.
- Opponent hidden and not recently seen: use `explore/patrol_left`, `explore/patrol_right`, or `explore/rotate_route`.
- `spin_detected=true`: use `recover/anti_spin` or `recover/switch_lane`.
- `stuck_detected=true`: use `recover/unstuck` or `evade/retreat_reset`.
- Winning: keep pressure with `engage/strafe_fight`, `engage/push`, or `position/camp_los`.
- Losing: use `evade/kite`, `evade/retreat_reset`, or a reposition/flank action.

Stop rules:
- If `get_match_result` returns `phase="finished"` and `has_next_round=false`, call `stop_participant_intent` once, then stop all tool calls.
- If `phase="finished"` and `has_next_round=true`, poll only `get_match_result` until `run_id` changes, then start the next match with `set_participant_ready` and reset `sequence_number=1`.

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
11. If `has_next_round=false`, stop after the final match result.

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
- Stop when `get_match_result` returns `phase="finished"` and `has_next_round=false`.
- If `phase="finished"` and `has_next_round=true`, keep polling until `run_id` changes, then start the next match.
- During benchmark loops, avoid prose if tool-only behavior is expected.

Stop rules â€” read carefully:
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









