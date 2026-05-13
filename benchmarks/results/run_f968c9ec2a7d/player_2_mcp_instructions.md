# Doom Arena MCP Instructions: player_2

You are one of two separate MCP agents in Doom Arena Duel.
You are `claude`.
You control only `player_2`.

Your controller_token is: `Zqa205iYLhiLFjPG9V158Mmqef-vvnuM`

Always include `controller_token` when calling `get_participant_observation`, `set_participant_intent`, and `stop_participant_intent`.

Core rule:
- You do not control frame-level movement.
- Choose one high-level intent every 2 seconds.
- Use MCP tool `set_participant_intent` for normal play.
- Do not use frame-level `forward`, `strafe`, `turn`, or `attack` controls.

Loop template:
1. Call MCP tool `get_participant_observation` with `participant_id="player_2"` and your controller token.
2. Read the shared state and choose one high-level intent.
3. Call MCP tool `set_participant_intent` once for this decision with `participant_id="player_2"`, your controller token, and one normalized intent.
4. Wait 2 seconds.
5. Repeat until `get_match_result` shows `phase="finished"`.

Allowed MCP tools:
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
{
  "participant_id": "player_2",
  "controller_token": "Zqa205iYLhiLFjPG9V158Mmqef-vvnuM",
  "intent": "strafe_attack",
  "style": "aggressive",
  "target_id": "player_1",
  "preferred_distance": 600,
  "aggression": 0.7,
  "duration_ms": 7000
}
```

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
- `health`
- `ammo`
- `opponent_distance` or distance if available
- `opponent_visible` or line of sight if available

Loop behavior:
- Observe state before every intent decision.
- Pick one high-level intent.
- Use `set_participant_intent`, not frame-level movement, for normal play.
- Wait 2 seconds between decisions.
- Reassess and refresh the intent before it expires if the same plan still makes sense.
- Use `duration_ms=7000` for normal combat intents so Doom-side autopilot keeps moving during model latency.
- Stop when `get_match_result` returns `phase="finished"`.
- During benchmark loops, avoid prose if tool-only behavior is expected.

Rules:
- Control only `player_2`.
- Do not control `player_1`.
- Never call `set_participant_intent` for `player_1`.
- Use `get_participant_observation` before each high-level intent decision.
- Use `set_participant_intent` once per decision during normal play.
- If phase is finished, stop sending intents and controls.
- Do not call or request tools that directly mutate health, position, ammo, or winner.
- Both players receive the same full shared state for this MVP.
- Keep choosing high-level intents until the match is finished.

Deprecated frame-level control guidance:
- Do not call low-level participant input tools or follow old instructions that tell you to continuously choose `forward`, `strafe`, `turn`, or `attack`.
- The Doom-side autopilot converts your high-level intent into normal gameplay controls.
