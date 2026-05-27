# MCP game state and character control

This document explains what Doom Arena MCP agents receive, what they send back, and where the boundary sits between LLM reasoning and Doom-side movement.

## Current default loop

The default duel loop is coordinate-route control:

```text
get_participant_observation -> choose objective/route/engagement_policy/reasoning -> set_participant_plan -> observe again
```

The model does not press movement keys every frame. It chooses a short route in Doom map coordinates. Doom validates the route, writes it into the existing participant intent TSV path, and the Doom autopilot follows the waypoints while handling frame-level movement, turning, collision, aiming, firing, and stuck recovery.

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
  "objective": "pick_up_shotgun",
  "route": ["M05", "G05", "G12", "M17"],
  "engagement_policy": "engage_if_visible",
  "reasoning": "take center weapon before forcing a fight",
  "sequence_number": 1
}
```

Fields:

| Field | Meaning |
| --- | --- |
| `participant_id` | `player_1` or `player_2`. |
| `controller_token` | Per-player token from the generated prompt. |
| `objective` | Short free-form goal, for example `pick_up_shotgun`, `heal`, `clear_top`, `flank`, `force_fight`. |
| `route` | Up to 16 grid cells such as `M05`, `G05`, `G12`, `M17`. |
| `engagement_policy` | How to behave while following the route. |
| `reasoning` | One short sentence for logs/evaluation. |
| `sequence_number` | Increment every decision. Higher values override older policies. |

Allowed `engagement_policy` values:

```text
engage_if_visible
avoid_until_target
hold_fire
force_fight
```

Route constraints:

```text
rows A-X
columns 01-32
maximum 16 cells
cells cannot be # wall cells
straight route segments cannot cross # wall cells
```

The server validates the segment from the player's current cell to the first submitted waypoint, then every segment between submitted waypoints. If any segment crosses a blocked cell, the plan is rejected and the model must add intermediate cells to route around the wall.

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
angle
zone
```

Important `opponent` fields:

```text
alive
visible
health if visible
distance_bucket
relative_angle_bucket
last_seen.age_ms
last_seen.zone
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
pickups
```

Example `map` block:

```json
{
  "current_zone": "left_side",
  "pickups": [
    {"id": "health_top", "type": "health", "name": "medikit", "x": 0, "y": 672, "zone": "top_lane", "purpose": "restore_health", "distance": 900},
    {"id": "health_bottom", "type": "health", "name": "medikit", "x": 0, "y": -672, "zone": "bottom_lane", "purpose": "restore_health", "distance": 900},
    {"id": "weapon_center", "type": "weapon", "name": "shotgun", "x": 0, "y": 0, "zone": "center", "purpose": "upgrade_weapon", "distance": 900}
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

The LLM chooses the route. Doom handles mechanics:

```text
waypoint following
turning toward route targets
collision-limited movement
aiming
line-of-sight checks
fire gating
engagement policy expansion
stuck detection
stuck recovery
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

Fog of war is enabled by default. In fog mode, the agent always sees its own position and state, but opponent exact coordinates are restricted unless the opponent is visible from that participant's perspective.

Visibility is directional. Player 1 seeing Player 2 does not automatically mean Player 2 sees Player 1. If a player is shot or damaged, the observation can reveal enough recent-contact context for recovery and response.

## Pickups

Current map pickups are exposed in observations through `map.pickups`:

```text
health_top: medikit at x=0 y=672
health_bottom: medikit at x=0 y=-672
weapon_center: shotgun at x=0 y=0
```

Agents can choose route waypoints that chase, deny, or avoid these pickups.

## Logs and latency

The UI command log shows the model-facing MCP call.

For `set_participant_plan`, the visible row includes:

```text
objective
route
route cells
engagement_policy
reasoning
sequence_number
decision latency
MCP latency
```

Decision latency estimates model thinking time:

```text
next set_participant_plan started_at_ms - previous get_participant_observation completed_at_ms
```

MCP latency measures local tool/server round-trip time after the request is sent.

Run stats persist `plan_objective`, `plan_route_cells`, `plan_engagement_policy`, and `plan_reasoning` on `set_participant_plan` calls so failed or stuck runs can be diagnosed from the submitted route.

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
8. when get_match_result returns phase=finished and has_next_round=false, call stop_participant_intent once and stop
```

For multi-round sessions:

```text
if phase=finished and has_next_round=true, poll get_match_result only
when run_id changes, call set_participant_ready again
reset sequence_number to 1
send a new opening set_participant_plan
```
