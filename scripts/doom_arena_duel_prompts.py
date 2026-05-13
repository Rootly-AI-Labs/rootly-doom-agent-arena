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
    intent_duration_ms: int = 3000,
) -> str:
    token_line = (
        f"Your controller_token is: `{controller_token}`\n\n"
        "Always include `controller_token` when calling `set_participant_ready`, "
        "`wait_for_match_start`, `get_participant_observation`, `set_participant_intent`, "
        "and `stop_participant_intent`.\n"
        if enforce_tokens
        else "Controller token enforcement is disabled for this local trusted smoke run.\n"
    )
    return f"""# Doom Arena MCP Instructions: {participant_id}

You are one of two separate MCP agents in Doom Arena Duel.
You are `{model}`.
You control only `{participant_id}`.

{token_line}
Core rule:
- You do not control frame-level movement.
- You are sending short-lived tactical policies.
- Doom continues executing the latest valid policy until a newer one arrives or it expires.
- After sending an intent, immediately observe again and choose the next intent.
- Do not run your own timer, sleep loop, or `Start-Sleep`; keep updating as fast as the chat environment allows.
- Use MCP tool `set_participant_intent` for normal play.
- Do not use frame-level `forward`, `strafe`, `turn`, or `attack` controls.

Loop template:
1. Call MCP tool `set_participant_ready` once with `participant_id="{participant_id}"` and your controller token.
2. Call MCP tool `wait_for_match_start` with `participant_id="{participant_id}"`, your controller token, and `timeout_ms=60000`.
3. Once the phase is `combat`, call `get_participant_observation` and choose one high-level intent.
4. Increment `sequence_number`.
5. Call MCP tool `set_participant_intent` once for this decision with `participant_id="{participant_id}"`, your controller token, the incremented `sequence_number`, and one normalized intent.
6. Immediately call `get_participant_observation` again and choose the next high-level intent.
7. Repeat observation and intent decisions until `get_match_result` shows `phase="finished"`.

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
  "replan_if": ["lost_los", "stuck", "low_health"]
}}
```

Fast tactical mode:
- Keep the observe -> intent -> observe loop moving as fast as the chat environment allows.
- Use `duration_ms={intent_duration_ms}` for normal combat intents so Doom keeps executing between chat decisions.
- Treat `decision_cadence_ms={decision_cadence_ms}` as metadata/debug only, not as an instruction to wait.
- Include `sequence_number` and increment it on every decision.
- Newer intents with higher `sequence_number` override older intents immediately.

Stable mode:
- Use `duration_ms` between 2500 and 7000.
- Use this when you need slower, more stable tactical planning.

Intent policy:

| Situation | Intent |
| --- | --- |
| Match `phase` is `finished` | Call `stop_participant_intent`, then stop the loop. |
| Opponent visible and aligned or close combat | `strafe_attack` with style `aggressive`. |
| Opponent visible and far away | `engage_opponent` with style `balanced`. |
| Opponent hidden or not visible | `search` with style `balanced`. |
| Very close or under pressure | `strafe_attack` with style `evasive`. |
| Winning on health near timeout | `hold` with style `cautious`, or `strafe_attack` with style `evasive`. |
| Unsure what to do | `engage_opponent` with style `balanced`. |

State fields to watch:
- `phase`
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
- `sequence_number`
- `decision_cadence_ms`
- `health`
- `ammo`
- `opponent_distance` or distance if available
- `opponent_visible` or line of sight if available

Loop behavior:
- Signal readiness once at the start with `set_participant_ready`.
- Use `wait_for_match_start` so you do not waste combat intents while the other participant connects.
- If `wait_for_match_start` times out and phase is still `waiting_for_agents`, call it again.
- Observe state before every intent decision.
- Pick one high-level intent.
- Use `set_participant_intent`, not frame-level movement, for normal play.
- After each `set_participant_intent`, immediately observe again and send the next updated intent.
- Do not call `Start-Sleep` or run your own delay.
- Reassess and refresh the intent before it expires if the same plan still makes sense.
- Use `duration_ms={intent_duration_ms}` for fast tactical combat intents unless the browser-provided settings differ.
- Keep incrementing `sequence_number`; do not reuse an older number.
- Stop when `get_match_result` returns `phase="finished"`.
- During benchmark loops, avoid prose if tool-only behavior is expected.

Rules:
- Control only `{participant_id}`.
- Do not control `{opponent_id}`.
- Never call `set_participant_ready` for `{opponent_id}`.
- Never call `set_participant_intent` for `{opponent_id}`.
- Do not send combat intents while phase is `waiting_for_agents`; wait for the match start barrier instead.
- Use `get_participant_observation` before each high-level intent decision.
- Use `set_participant_intent` once per decision during normal play.
- If phase is finished, stop sending intents and controls.
- Do not call or request tools that directly mutate health, position, ammo, or winner.
- Both players receive the same full shared state for this MVP.
- Keep choosing high-level intents until the match is finished.

Deprecated frame-level control guidance:
- Do not call low-level participant input tools or follow old instructions that tell you to continuously choose `forward`, `strafe`, `turn`, or `attack`.
- The Doom-side autopilot converts your high-level intent into normal gameplay controls.
"""
