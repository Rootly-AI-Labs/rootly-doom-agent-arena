"""Shared prompt and token helpers for browser-created Doom Arena duels."""

from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
RESULTS_ROOT = REPO_ROOT / "benchmarks" / "results"
CONTROLLER_TOKENS_PATH = REPO_ROOT / "src" / "arena_controller_tokens.local.json"


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

Rules:
- Control only `{participant_id}`.
- Do not control `{opponent_id}`.
- Never call `set_participant_ready` for `{opponent_id}`.
- Never call `set_participant_intent` for `{opponent_id}`.
- Only send your own opening high-level intent while phase is `waiting_for_agents`; Doom will hold it until both opening intents are present.
- Use `get_participant_observation` before each high-level intent decision.
- Use `set_participant_intent` once per decision during normal play.
- If phase is finished and `has_next_round=false`, stop sending intents and controls.
- If phase is finished and `has_next_round=true`, wait for the next `run_id`, then restart the ready/opening flow.
- Do not call or request tools that directly mutate health, position, ammo, or winner.
- Both players receive the same full shared state for this MVP.
- Keep choosing high-level intents until the benchmark session is finished.

Deprecated frame-level control guidance:
- Do not call low-level participant input tools or follow old instructions that tell you to continuously choose `forward`, `strafe`, `turn`, or `attack`.
- The Doom-side autopilot converts your high-level intent into normal gameplay controls.
"""
