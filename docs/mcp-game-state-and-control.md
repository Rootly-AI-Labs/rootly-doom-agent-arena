# MCP game state and character control

This document explains what Doom Arena MCP agents receive, what they send back, and where the boundary sits between LLM reasoning and Doom-side movement.

## Current default loop

The default duel loop is coordinate-route control:

```text
get_participant_observation -> choose objective/route/engagement_policy/reasoning -> set_participant_plan -> observe again
```

The model does not press movement keys every frame. It chooses a short route in Doom map coordinates. Doom validates hard route legality, writes accepted plans into the existing participant intent TSV path, and the Doom executor follows the submitted waypoints literally while handling frame-level movement, turning, collision, aiming, and firing.

## Recommended MCP tools for duel agents

Use this small tool subset during normal benchmark play:

```text
set_participant_ready
get_participant_observation
set_participant_plan
wait_for_match_start
get_match_result
stop_participant_intent
get_duel_events optional
```

Compatibility tools still exist:

```text
set_participant_strategy  legacy hierarchical category/action path
set_participant_intent    full detailed policy path
```

Do not use low-level input tools for normal benchmark runs.

## `set_participant_plan`

`set_participant_plan` is the current default action tool.

Schema:

```json
{
  "participant_id": "player_1",
  "controller_token": "...",
  "objective": "your_goal",
  "route": ["A01", "A02"],
  "engagement_policy": "engage_if_visible",
  "reasoning": "short reason",
  "plan_summary": "goal, risk, fallback in one short line",
  "sequence_number": 1
}
```

Fields:

| Field | Meaning |
| --- | --- |
| `participant_id` | `player_1` or `player_2`. |
| `controller_token` | Per-player token from the generated prompt. |
| `objective` | Short free-form goal chosen by the model. |
| `route` | Up to 16 grid cells such as `M05`, `G05`, `G12`, `M17`. |
| `engagement_policy` | How to behave while following the route. |
| `reasoning` | One short sentence for logs/evaluation. |
| `plan_summary` | Optional compact public reasoning summary for analysis. |
| `sequence_number` | Increment every decision. Higher values override older policies. |

Allowed `engagement_policy` values:

```text
engage_if_visible
avoid_until_target
hold_fire
force_fight
```

`avoid_until_target` prioritizes movement. Doom suppresses attack while the route is still in progress, then normal firing can resume after the route target is reached.

Route constraints:

```text
rows A-W
columns 01-33
maximum 16 cells
every consecutive segment must be horizontal or vertical
diagonal segments are rejected
cells cannot be # wall cells
straight route segments cannot cross # wall cells
```

The server validates the segment from the player's current cell to the first submitted waypoint, then every segment between submitted waypoints. Every consecutive segment must share the same row or the same column. If any segment is diagonal, enters a wall cell, or crosses a blocked cell, the plan is rejected. The server does not insert connector cells, repair diagonals, trim already-passed cells, or choose alternate lanes for the model.

Near-wall routes are accepted if they are otherwise legal. If the Doom actor clips a wall corner or fails to progress during execution, that is reported back through route execution feedback instead of silently changing the route.

The server stores the accepted plan as:

```text
plan_objective
plan_route
plan_engagement_policy
plan_reasoning
plan_route_cells
```

Those fields are appended to the participant intent TSV so Doom still consumes one unified command stream.

## What `get_participant_observation` returns

In the default hierarchical mode, `get_participant_observation` returns compact route-planning state:

```text
control_mode
participant_id
opponent_id
match
self
opponent
tactical
map
last_plan
last_plan_result
previous_rounds when enabled
```

Important `match` fields:

```text
phase
time_left_seconds
round
total_rounds
has_next_round
winner
```

Important `self` fields:

```text
health
ammo
alive
x
y
cell
angle
zone
```

Important `opponent` fields:

```text
alive
visible
health if visible
x if visible
y if visible
cell if visible
distance_bucket
relative_angle_bucket
last_seen.age_ms
last_seen.zone
last_seen.cell
```

Important `tactical` fields:

```text
pressure
los
damage_trend
last_action_result
stuck_detected
spin_detected
repeated_action_count
```

Important `map` fields:

```text
current_zone
grid bounds
cell size
row/column labels
blocked cell count
weapon_pickups_enabled
pickups
```

Observations can include `last_plan` and `last_plan_result` after an accepted route command.

`last_plan` is the last public MCP command submitted by the model:

```json
{
  "accepted": true,
  "sequence_number": 4,
  "objective": "take lower shotgun",
  "route_cells": ["W08", "W17", "R17"],
  "engagement_policy": "avoid_until_target",
  "reasoning": "upgrade weapon before forcing contact",
  "plan_summary": "target lower shotgun, avoid center wall, fight if seen",
  "issued_at_ms": 123456,
  "expires_at_ms": 131456
}
```

`last_plan_result` is Doom-side execution feedback for that plan:

```json
{
  "status": "active",
  "current_waypoint_index": 2,
  "current_waypoint_count": 3,
  "current_waypoint_cell": "W17",
  "waypoints_reached": 1,
  "waypoints_remaining": 2,
  "distance_to_waypoint": 96,
  "distance_to_final_waypoint": 512
}
```

These fields are public command/result memory, not hidden chain-of-thought. They expose what was submitted and what happened during execution without telling the model which strategy to choose next.

`active_plan` remains as a compatibility alias for older clients. It includes the objective, route cells, current waypoint, current waypoint index/count, distance to the current waypoint, waypoints reached, waypoints remaining, status, and distance to the final waypoint.

Example `map` block:

```json
{
  "current_zone": "left_side",
  "bounds": {"x_min": -1056, "x_max": 1056, "y_min": -736, "y_max": 736},
  "cell_size": 64,
  "row_labels": "A-W",
  "col_labels": "01-33",
  "blocked_cell_count": 42,
  "weapon_pickups_enabled": true,
  "pickups": [
    {"id": "health_d06", "type": "health", "name": "medikit", "available": true, "cell": "D06", "x": -672, "y": 544, "distance": 900},
    {"id": "shotgun_i12", "type": "weapon", "name": "shotgun", "available": true, "cell": "I12", "x": -608, "y": 544, "distance": 900}
  ]
}
```

## Static map prompt vs repeated observations

The generated copy-paste prompt includes the static ASCII map once. Repeated observations do not resend the full map.

The static prompt includes:

```text
cell size
map bounds
coordinate frame
legend
ASCII map from scripts/map_blueprints/duel_e1m8_ascii.txt
blocked route cells
own selected spawn coordinate and angle
own selected spawn grid cell
pickup behavior note
```

The static prompt intentionally omits:

```text
opponent spawn coordinate
player markers in the ASCII map
unsupported upper/lower lane names
```

Legend:

```text
. walkable
# wall/collision/line-of-sight blocker
```

Each cell is currently `64 x 64` Doom units. Routes submitted by the LLM use grid cell labels, not raw coordinates. The server converts each cell to the center Doom coordinate internally.

Coordinate frame:

```text
+x east/right
-x west/left
+y north/up
-y south/down
```

## Data flow

Read path:

```text
Doom game state
  -> src/arena_game_state.local.tsv
  -> GET /api/arena/state
  -> MCP get_participant_observation
  -> LLM agent
```

Write path:

```text
LLM agent
  -> MCP set_participant_plan
  -> route validation in scripts/doom_arena_mcp.py
  -> POST /api/arena/participant-intents
  -> src/arena_participant_intents.local.tsv
  -> Doom ArenaParticipantIntent_TickOrRefresh
  -> Doom ArenaParticipantAutopilot_Decide
  -> Doom ticcmd frame controls
```

## Doom-side autopilot responsibilities

The LLM chooses the route. Doom handles mechanics only:

```text
waypoint following
turning toward route targets
collision-limited movement
aiming
line-of-sight checks
fire gating
engagement policy expansion
stuck/no-progress detection
stale-policy continuation
```

Doom converts the current accepted plan into normal Doom controls:

```text
forwardmove
sidemove
angleturn
attack button
use button
```

## Ready gate and opening plan

The match starts in:

```text
waiting_for_agents
```

Movement does not execute until both agents have:

```text
called set_participant_ready
submitted one opening set_participant_plan
```

Opening plans are armed and held until both sides are ready. Then the phase moves to `combat`.

## Sequence numbers and policy lease

Agents should increment `sequence_number` on every plan:

```text
1 opening plan
2 first combat plan
3 next combat plan
```

The server applies an internal `16000ms` route lease for `set_participant_plan`. This is not a sleep timer. It gives routes time to progress while still allowing agents to refresh plans from new observations and override immediately with a newer higher-sequence plan.

If the lease expires before a replacement arrives, Doom may mark the policy `stale` but keep executing it so the player does not freeze.

## Fog of war

Fog of war is enabled by default. In fog mode, the agent always sees its own position and state, but opponent exact coordinates are restricted unless the opponent is currently visible from that participant's perspective.

Visibility is directional and wall-gated. A participant sees the opponent only when Doom reports line of sight, the static ASCII map segment between them does not cross a `#` wall cell, and the opponent is inside the participant's view cone. If a participant is hit while looking away, the hit can briefly reveal the opponent only while geometric line of sight is still open. If the opponent moves behind a wall, live `x`, `y`, `cell`, health delta, pressure, and distance bucket disappear; only stale `last_seen` memory remains.

## Pickups

The generated prompt gives static pickup locations once. Pickup locations are derived from `H` and `S` markers in `scripts/map_blueprints/duel_e1m8_ascii.txt`, so moving those markers updates the WAD, minimap, generated prompt, and observation pickup cells.

Each medikit restores `+100` health, capped at the duel max health of `150`.

Repeated observations keep pickup data structured: `id`, `type`, `name`, `available`, `cell`, `x`, `y`, and `distance`.
`available` is derived from live Doom pickup objects. When a pickup is no longer present, observations expose only `available=false`; they do not expose who took it or when.

`weapon_pickups_enabled=false` means the shotgun is disabled for the session. In that mode, the Doom runtime removes shotgun objects, the UI hides the shotgun marker, and `map.pickups` only includes non-weapon resources such as health packs.

## Logs and latency

The UI command log shows the model-facing MCP call.

For `set_participant_plan`, the visible row includes:

```text
objective
route
route cells
engagement_policy
reasoning
plan_summary
sequence_number
decision latency
MCP latency
```

Decision latency estimates model thinking time:

```text
next set_participant_plan started_at_ms - previous get_participant_observation completed_at_ms
```

MCP latency measures local tool/server round-trip time after the request is sent.

Run stats persist `plan_objective`, `plan_route_cells`, `plan_engagement_policy`, `plan_reasoning`, and optional `plan_summary` on `set_participant_plan` calls so failed or stuck runs can be diagnosed from the submitted route.

Invalid route plans return structured rejection payloads instead of only surfacing a generic tool failure. The response includes:

```text
accepted=false
error_type
error
plan
route_diagnostics.start_cell
route_diagnostics.from_cell
route_diagnostics.to_cell
route_diagnostics.blocked_cells_crossed
```

Each round also writes `decision_trace.jsonl`. It records model-facing observations and plan submissions, including accepted/rejected status, objective, route cells, engagement policy, reasoning, route diagnostics, latency, and active-plan execution state. This file is intended to separate model planning errors from MCP/server/Doom execution issues.

Total MCP commands count all tool calls, not only action calls:

```text
set_participant_ready
get_participant_observation
set_participant_plan
wait_for_match_start
get_match_result
stop_participant_intent
errors
```

## Compatibility modes

`set_participant_strategy` still exists for older hierarchical category/action experiments. It maps:

```text
category/action/intensity/objective/target_zone/reasoning
```

into the old full intent fields.

`set_participant_intent` still exists for full-mode/backward-compatible runs. It exposes detailed policy knobs such as:

```text
intent
style
movement_bias
fire_policy
distance_policy
navigation_target
turn_policy
spacing bounds
LOS behavior
stuck recovery
```

Those are no longer the default recommended interface for route-planning benchmark runs.

## Practical default agent loop

```text
1. set_participant_ready
2. get_participant_observation
3. set_participant_plan with sequence_number=1
4. wait_for_match_start
5. get_participant_observation
6. set_participant_plan with a new route and sequence_number=2
7. repeat observe -> plan with increasing sequence_number
8. do not stop just because has_next_round=false; that only means the current match is the final match
9. when get_match_result returns phase=finished and has_next_round=false, call stop_participant_intent once and stop
```

For multi-round sessions:

```text
if phase is waiting_for_agents, waiting_for_first_intents, or combat, keep playing even when has_next_round=false
if phase=finished and has_next_round=true, poll get_match_result only
when run_id changes, call set_participant_ready again
reset sequence_number to 1
send a new opening set_participant_plan
if phase=finished and has_next_round=false, stop
```

## Match logging outputs

Each match writes raw debug artifacts plus a compact derived summary under:

```text
benchmarks/results/session_.../round_XX_run_.../
```

Important artifacts:

- `summary.json`: final outcome, winner, terminal reason, elapsed time, final health, damage, and shots.
- `analysis_summary.json`: compact benchmark metrics intended for comparison.
- `stats.json`: full MCP call, latency, lifecycle, and command telemetry.
- `decision_trace.jsonl`: observation and plan trace.
- `events.jsonl`: raw runtime/game events such as path points, pickups, damage, and match finish.

`analysis_summary.json` keeps the high-signal fields:

- `outcome`: winner, terminal reason, elapsed time, timeout.
- `combat`: damage dealt/taken, shots fired/hit, accuracy, final health.
- `resources`: first shotgun pickup, first health pickup, pickup counts, and compact pickup events.
- `routing`: plan counts, invalid plan counts, route errors, route repairs, dropped passed cells, inserted connector cells, and path summaries.
- `latency`: decision and MCP average, p95, and max latency.
- `errors`: compact error counts.
- `lifecycle`: stale/sticky and superseded plan counts.
- `fairness`: scenario, spawn variant, player models, fog-of-war, weapon-spawn, and seed.
- `reasoning`: recent objective/route/engagement/reasoning/plan-summary samples.

Repeated compact observations intentionally omit the full `blocked_cells` list. The static ASCII map and blocked geometry are provided in the initial MCP prompt; repeated observations keep only compact map metadata and live state.
