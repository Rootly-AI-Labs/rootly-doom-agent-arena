# MCP game state and character control

This document explains what each Doom Arena MCP agent receives from the game, what commands it sends back, and where the boundary sits between the model and the Doom-side autopilot.

## Short version

Each agent runs an observe-and-act loop:

```text
get_participant_observation -> choose category/action/intensity/objective/target_zone/reasoning -> set_participant_strategy -> observe again
```

The model does not directly press movement keys every frame. In the current hierarchical flow, it sends compact tactical strategies with `set_participant_strategy`: `category`, `action`, `intensity`, optional `objective`, optional `target_zone`, short `reasoning`, and `sequence_number`. The server expands those strategies into the existing Doom intent fields. In full control mode, agents can still use `set_participant_intent` directly with intent names such as `engage_opponent`, `strafe_attack`, `search`, or `hold`. Doom reads the latest valid expanded policy every tick and converts it into normal Doom controls:

```text
forwardmove
sidemove
angleturn
attack button
use button
```

The model decides tactics. Doom executes mechanics.

## Data flow

The runtime loop has four layers:

1. Doom writes live state to `src/arena_game_state.local.tsv`.
2. `scripts/doom_arena_server.py` serves that state through local HTTP endpoints.
3. `scripts/doom_arena_mcp.py` exposes MCP tools that agents call.
4. Doom reads accepted intent rows from `src/arena_participant_intents.local.tsv` and the autopilot converts them into per-tick movement and firing.

The important write path is:

```text
LLM agent
  -> MCP set_participant_strategy in hierarchical mode or set_participant_intent in full mode
  -> strategy expansion in scripts/doom_arena_strategy.py when using set_participant_strategy
  -> POST /api/arena/participant-intents
  -> src/arena_participant_intents.local.tsv
  -> Doom ArenaParticipantIntent_TickOrRefresh
  -> Doom ArenaParticipantAutopilot_Decide
  -> Doom ticcmd frame controls
```

The important read path is:

```text
Doom game state
  -> src/arena_game_state.local.tsv
  -> GET /api/arena/state
  -> MCP get_participant_observation
  -> LLM agent
```

## MCP endpoint, auth, and tool surface

When an MCP client shows this:

```text
doom-arena
Auth: Unsupported
URL: http://127.0.0.1:8001/mcp
Tools: attack_enemy, clear_enemy_commands, get_arena_state, ...
```

It means:

| Field | Meaning |
| --- | --- |
| `doom-arena` | The MCP server name advertised to the client. |
| `Auth: Unsupported` | The MCP protocol endpoint itself does not use OAuth or API-key auth. It is a local localhost endpoint. Duel control is protected separately by per-player `controller_token` values. |
| `URL: http://127.0.0.1:8001/mcp` | The local HTTP MCP JSON-RPC endpoint exposed by the Doom Arena server. |
| `Tools` | Every callable MCP tool the arena exposes. Some are for normal duel agents, some are setup/admin tools, and some are legacy/debug tools. |

Important: `Auth: Unsupported` does not mean any player can safely control any duel participant. The normal duel tools still verify `participant_id` plus `controller_token` when token enforcement is enabled for the run.

For benchmark play, use this small subset:

```text
set_participant_ready
get_participant_observation
set_participant_strategy
wait_for_match_start
get_match_result
stop_participant_intent
get_duel_events
set_participant_intent only for full-mode/backward-compatible runs
```

Do not use reset tools or low-level input tools during a benchmark round. They are useful for setup, debugging, or older single-player arena flows, but they bypass the intended high-level duel control loop.

## Full MCP tool reference

### Recommended duel tools

| Tool | Reads or writes | Purpose |
| --- | --- | --- |
| `set_participant_ready` | Writes ready state | Marks `player_1` or `player_2` as ready at the duel start barrier. Does not move the player. |
| `get_participant_observation` | Reads state | Returns participant-scoped duel state for `player_1` or `player_2`. This is the normal observation call for duel agents. |
| `set_participant_strategy` | Writes intent | Submits compact hierarchical strategy in `control_mode="hierarchical"`. The server expands it into a full intent row. |
| `set_participant_intent` | Writes intent | Submits the detailed high-level tactical policy Doom will execute through the autopilot. This is the full-mode/backward-compatible action call. |
| `wait_for_match_start` | Reads/polls state | Waits until both participants are ready, both have opening intents, and the phase leaves `waiting_for_agents`. |
| `get_match_result` | Reads state | Returns phase, winner, terminal reason, score fields, round metadata, and both player summaries. |
| `stop_participant_intent` | Writes intent file | Clears the active high-level policy for one participant. Use after the final match finishes. |
| `get_duel_events` | Reads event log | Returns recent duel events for debugging, analysis, or post-round reasoning. Optional during normal play. |

### Setup and admin tools

| Tool | Reads or writes | Purpose |
| --- | --- | --- |
| `reset_duel` | Writes run/session config | Resets Doom Arena into duel mode and requests browser/WASM reload. Takes model labels, round number, seed, and timeout. |
| `reset_arena` | Writes run config | Resets generic arena state and requests browser reload. Older/general reset path. |
| `get_arena_state` | Reads state | Returns the full shared arena state JSON. Useful for dashboards and debugging, but not participant-scoped. |

### Legacy single-player and enemy-control tools

These are not the recommended duel benchmark interface. They exist for older arena modes and debugging.

| Tool | Reads or writes | Purpose |
| --- | --- | --- |
| `get_player_observation` | Reads state | Returns the older player-agent observation JSON for the single controllable browser player. |
| `get_enemy_observation` | Reads state | Returns the older enemy-commander observation JSON. |
| `set_player_input` | Writes player command | Sends direct low-level input for the single browser player path: forward, strafe, turn, attack, use, duration. |
| `stop_player` | Writes player command | Stops the legacy single-player input by sending a short neutral command. |
| `set_enemy_command` | Writes enemy command | Sets a high-level command for one arena enemy by `enemy_id`. |
| `set_enemy_team_command` | Writes enemy command | Sets a high-level command for all arena enemies. |
| `clear_enemy_commands` | Writes enemy command file | Clears all active enemy commands. |
| `look_at_enemy` | Reads state, writes player input | Helper that turns the legacy player toward an enemy. Internally emits `set_player_input`. |
| `attack_enemy` | Reads state, writes player input | Helper that turns toward an enemy if needed, then attacks. Internally emits `set_player_input`. |
| `move_toward_enemy` | Reads state, writes player input | Helper that moves the legacy player forward while turning toward an enemy. Internally emits `set_player_input`. |

### Optional debug duel low-level tools

These are hidden unless low-level participant MCP tools are exposed locally with `DOOM_ARENA_EXPOSE_LOW_LEVEL_MCP=1`.

| Tool | Reads or writes | Purpose |
| --- | --- | --- |
| `set_participant_input` | Writes participant command | Debug-only direct low-level input for `player_1` or `player_2`: forward, strafe, turn, attack, use, duration. |
| `stop_participant` | Writes participant command | Debug-only neutral low-level participant command. This is not the same as `stop_participant_intent`. |

### Tool safety model

The tool surface has three control levels:

| Level | Tools | Benchmark use |
| --- | --- | --- |
| High-level duel policy | `set_participant_strategy`, `set_participant_intent`, `stop_participant_intent` | Use `set_participant_strategy` for normal hierarchical model-vs-model duel evaluation. Use `set_participant_intent` for full-mode/backward-compatible runs. |
| Duel lifecycle/read tools | `set_participant_ready`, `wait_for_match_start`, `get_participant_observation`, `get_match_result`, `get_duel_events` | Use for normal duel coordination and observation. |
| Admin/debug/legacy controls | `reset_duel`, `reset_arena`, `set_player_input`, `stop_player`, enemy tools, helper tools, optional low-level participant tools | Do not use inside a fair benchmark round unless intentionally debugging. |

The important distinction is that `set_participant_strategy` and `set_participant_intent` test whether the model can choose high-level tactics while Doom handles mechanics. Low-level input tools test something else: direct control, debug recovery, or legacy arena behavior.

Hierarchical mode adds one preferred tool above the full intent schema:

```text
set_participant_strategy
```

In hierarchical mode the model sends only the compact model-facing decision:

```json
{
  "participant_id": "player_1",
  "controller_token": "...",
  "category": "position",
  "action": "flank_left",
  "intensity": "medium",
  "objective": "clear_side",
  "target_zone": "right_side",
  "reasoning": "enemy hidden, checking unvisited side",
  "sequence_number": 7
}
```

`objective`, `target_zone`, and `reasoning` are lightweight planning and evaluation metadata. They help logs show what the model was trying to do, but they are not low-level Doom movement controls. The MCP wrapper expands the compact strategy into the existing `set_participant_intent` fields. Doom still consumes the same participant intent TSV and autopilot path.

## MCP tools used in duel mode

### `get_participant_observation`

Purpose: return the current game state from one participant's perspective.

Input:

```json
{
  "participant_id": "player_1",
  "controller_token": "..."
}
```

Important returned top-level fields:

```text
participant_id
opponent_id
state_mode
self
opponent
tactical_context
match
allowed_intents
allowed_styles
allowed_tactical_controls
intent_duration_ms
objective
duel_session_id
current_round
total_rounds
has_next_round
state
```

`state_mode` is either:

```text
shared_full
fog_of_war
```

In `shared_full`, the agent can see both players' positions, angles, health, ammo, and policy telemetry.

In `fog_of_war`, the opponent block is restricted. The opponent's exact position is hidden unless line of sight is true. The agent still receives whether the opponent is alive and whether the opponent is currently visible.

### `set_participant_ready`

Purpose: tell the duel start barrier that this agent is connected and ready.

Input:

```json
{
  "participant_id": "player_1",
  "controller_token": "..."
}
```

This does not move the character. It only records a ready row for the current run.

### `wait_for_match_start`

Purpose: wait until both players have called `set_participant_ready`, both players have submitted an opening intent, and the match leaves `waiting_for_agents`.

Input:

```json
{
  "participant_id": "player_1",
  "controller_token": "...",
  "timeout_ms": 60000,
  "poll_ms": 250
}
```

If the agent has not sent an opening policy yet, this tool can return `needs_opening_intent=true`. In hierarchical mode, the agent should send one `set_participant_strategy` first, then wait again. In full mode, it can send one `set_participant_intent` first.

### `set_participant_intent`

Purpose: set the high-level tactical policy for one player.

Minimum input:

```json
{
  "participant_id": "player_1",
  "controller_token": "...",
  "intent": "engage_opponent"
}
```

Typical full input:

```json
{
  "participant_id": "player_1",
  "controller_token": "...",
  "intent": "strafe_attack",
  "style": "aggressive",
  "target_id": "player_2",
  "preferred_distance": 600,
  "aggression": 0.7,
  "duration_ms": 25000,
  "sequence_number": 4,
  "decision_cadence_ms": 750,
  "strafe_direction": "alternate",
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
  "replan_if": ["lost_los", "stuck", "low_health"],
  "rationale": "Opponent is visible at good range, keep strafing and fire when aligned."
}
```

What the server does with this:

1. Validates the participant and controller token.
2. Normalizes enum values and numeric ranges.
3. Adds an `intent_id`, `issued_at_ms`, and `expires_at_ms`.
4. Writes the active policy to `arena_participant_intents.local.tsv`.
5. Returns the normalized intent that Doom will read.

Important behavior:

```text
sequence_number
```

Agents should increment this every decision. Higher sequence numbers override older intents immediately.

```text
duration_ms
```

This is a lease, not a sleep timer. Doom keeps executing the latest policy while the agent thinks. If the lease expires before a replacement arrives, Doom marks it `stale` but can keep executing it instead of freezing.

### `set_participant_strategy`

Purpose: submit one compact hierarchical tactical decision. This is the preferred action tool when `control_mode="hierarchical"`.

Input:

```json
{
  "participant_id": "player_1",
  "controller_token": "...",
  "category": "position",
  "action": "flank_left",
  "intensity": "medium",
  "objective": "clear_side",
  "target_zone": "right_side",
  "reasoning": "enemy hidden, checking unvisited side",
  "sequence_number": 4
}
```

Allowed categories and actions:

```text
explore: scan_last_seen, patrol_left, patrol_right, rotate_route, probe_center
engage: push, strafe_fight, suppress, close_gap, finish_low_health
evade: kite, break_los, retreat_reset, dodge_strafe, hold_fire_reposition
position: flank_left, flank_right, camp_los, hold_angle, take_left_lane, take_right_lane
recover: unstuck, anti_spin, switch_lane, reset_to_center, reverse_route
```

Allowed intensity:

```text
low
medium
high
```

Allowed objective:

```text
find_enemy
hold_advantage
force_fight
break_contact
clear_side
control_center
finish_enemy
```

Allowed target zone:

```text
left_side
right_side
top_lane
bottom_lane
center
last_seen
enemy_side
```

`reasoning` is optional, one line, and capped at 120 characters.

The server applies an internal `8000ms` policy lease to every `set_participant_strategy` call. Agents should not include timing fields in normal hierarchical play. Older clients may still send the legacy `commit_ms` field; the server keeps accepting and clamping it for backward compatibility.

Expansion location:

```text
scripts/doom_arena_strategy.py
```

The internal strategy lease is a policy lease, not a sleep timer. Agents should still observe and submit the next strategy as soon as they can; newer higher-sequence strategies override immediately.

The expansion result is sent through the existing participant-intent path and preserves strategy metadata:

```text
strategy_source=hierarchical
strategy_category
strategy_action
strategy_intensity
strategy_commit_ms
strategy_objective
strategy_target_zone
strategy_reasoning
intent_raw=category/action
```

Generated hierarchical prompts now include the static ASCII map once in the starting prompt. Repeated `get_participant_observation` calls intentionally do not include the full ASCII map; they include dynamic state plus a lightweight `map` block that points back to `initial_prompt_ascii`. The current live tactical map and Doom wall collision are generated from `scripts/map_blueprints/duel_e1m8_ascii.txt`; spawn variants are resolved from `scripts/map_blueprints/duel_e1m8_variants.json`. The live prompt does not expose unsupported map-route labels such as `upper_open` or `lower_open`. Hierarchical strategy names use the engine-supported lateral targets directly:

```text
left_lane
right_lane
center
last_seen_enemy
keep_distance
opponent
none
```

### `stop_participant_intent`

Purpose: clear the active intent for one participant.

Input:

```json
{
  "participant_id": "player_1",
  "controller_token": "..."
}
```

Use this when the final match is finished. It removes that participant's current intent row.

### `get_match_result`

Purpose: return the match phase, winner, terminal reason, and score summary.

Important fields:

```text
phase
winner
terminal_reason
run_id
current_round
total_rounds
has_next_round
player_1
player_2
```

For multi-round sessions, if `phase=finished` and `has_next_round=true`, agents should keep polling `get_match_result` until the `run_id` changes, then start the next round with `set_participant_ready` again.

### `get_duel_events`

Purpose: return recent duel events for debugging or post-round reasoning.

Input:

```json
{
  "run_id": "run_...",
  "limit": 25
}
```

This is optional during normal play.

## Static map prompt vs dynamic observations

Map information is split across the first prompt and repeated observations.

The generated starting prompt includes the static map because it does not change during a match:

```text
Static map context
cell size
map bounds
coordinate frame
legend
ASCII map from scripts/map_blueprints/duel_e1m8_ascii.txt with player/spawn markers stripped out
```

Legend:

```text
. = walkable space
# = wall, collision, and line-of-sight blocker
```

Each ASCII cell is currently `64 x 64` Doom units. The coordinate frame is `+x` east/right, `-x` west/left, `+y` north/up, and `-y` south/down. The static prompt map intentionally omits player markers and the opponent spawn. Each copied player prompt includes only that player's own selected spawn coordinate and angle from the selected spawn variant; live movement/visibility still belongs in observations.

`get_participant_observation` stays compact. It does not repeat the full ASCII map. It returns live state such as player coordinates, angle, health, ammo, visibility, distance buckets, last-seen opponent zone, tactical state, and a tiny map reference:

```json
{
  "map": {
    "current_zone": "left_side"
  }
}
```

This is intentional: the benchmark can test whether the model remembers and reasons over the static map from chat context without flooding every observation with repeated map text.
## What game state the agent receives

`get_participant_observation` returns different shapes depending on `control_mode`.

In `control_mode="full"`, it returns the detailed observation described below.

In `control_mode="hierarchical"`, it returns compact strategy-ready state:

```text
participant_id
opponent_id
match
self
opponent
tactical
map
allowed_actions
recommended
```

The compact observation intentionally removes detailed execution fields such as `movement_bias`, `fire_policy`, `distance_policy`, `turn_policy`, `navigation_target`, timing, and spacing bounds. The model chooses `category/action/intensity`, optional `objective`, optional `target_zone`, and short `reasoning`; the server fills in the detailed fields and applies the default lease.

### Match state

The `match` block tells the agent where the round is in its lifecycle:

```text
phase
winner
terminal_reason
elapsed_time_seconds
timeout_seconds
```

Common `phase` values:

```text
waiting_for_agents
combat
finished
```

### Self state

The `self` block describes the controlled player:

```text
health
alive
x
y
angle
ammo_bullets
command_status
last_action
damage_dealt
shots_fired
shots_hit
invalid_actions
health_delta
distance_bucket
los_status
pressure_state
last_damage_taken_ms
last_damage_dealt_ms
requested_* policy fields
executed_* autopilot fields
policy_compliance_reason
```

The important physical fields are:

```text
x, y
```

Map coordinates in Doom units.

```text
angle
```

Facing direction in degrees.

```text
health, ammo_bullets, alive
```

Survival and firing capacity.

The important tactical fields are:

```text
distance_bucket
los_status
pressure_state
health_delta
replan_recommended
replan_reasons
```

These are derived helper fields for decision-making.

### Opponent state

In `shared_full`, the opponent block includes:

```text
participant_id
health
alive
x
y
angle
ammo_bullets
visible
distance
relative_angle
pressure_state
distance_bucket
los_status
requested_* policy fields
executed_* autopilot fields
```

In `fog_of_war`, the opponent block is restricted:

```text
participant_id
alive
visible
```

If `visible=true`, it can also include:

```text
distance
relative_angle
distance_bucket
los_status
```

That means in fog-of-war mode the agent must reason from its own location, the compact map summary, recent sightings, and current visibility rather than always knowing exact opponent coordinates.

### Tactical context

The `tactical_context` block repeats the most important tactical values in one place:

```text
health_delta
distance_bucket
los_status
pressure_state
last_damage_taken_ms
last_damage_dealt_ms
replan_recommended
replan_reasons
requested_fire_policy
executed_fire_action
requested_distance_policy
executed_movement_action
requested_strafe_direction
executed_strafe_direction
requested_los_lost_action
requested_stuck_recovery_strategy
requested_movement_primitive
requested_turn_policy
requested_navigation_target
requested_fire_mode
executed_turn_policy
executed_navigation_target
executed_fire_mode
policy_compliance_reason
```

Use this to compare what the model asked for against what Doom actually executed.

### Derived tactical fields

`distance_bucket` groups distance relative to the preferred distance:

```text
close
ideal
far
unknown
```

`los_status` is:

```text
visible
lost_los
```

`pressure_state` compares health and fight status. It is used to tell whether the agent is winning, losing, stable, or in danger.

`executed_fire_action` is derived from the autopilot action:

```text
attack
hold_fire
```

`executed_movement_action` is derived from the autopilot action:

```text
advance
retreat
strafe
hold
search
stuck_recovery
```

The exact strings can vary by action label, but the purpose is to expose whether the policy produced the intended behavior.

## What commands the agent sends

Normal play uses high-level intent commands, not low-level frame commands.

The four regular intent names are:

```text
engage_opponent
strafe_attack
hold
search
```

The four styles are:

```text
balanced
aggressive
evasive
cautious
```

The tactical controls are:

```text
strafe_direction
movement_bias
fire_policy
distance_policy
replan_if
sequence_number
decision_cadence_ms
aim_tolerance
fire_burst_ms
min_fire_alignment
min_distance
max_distance
retreat_if_closer_than
push_if_farther_than
los_lost_action
stuck_recovery_strategy
movement_primitive
turn_policy
navigation_target
fire_mode
rationale
```

### Intent meaning

`engage_opponent`

Move toward or fight the opponent, depending on distance and policy. This is the normal "find and fight" intent.

`strafe_attack`

Prioritize lateral movement while aiming and firing. This is the normal close or mid-range combat intent.

`hold`

Hold position, turn according to `turn_policy`, and fire only when the fire gates allow it.

`search`

Reacquire the opponent when line of sight is lost. This uses `los_lost_action` and `navigation_target` heavily.

### Tactical control meaning

`strafe_direction`

Controls lateral direction:

```text
left
right
alternate
auto
hold_direction
switch_if_hit
```

`movement_bias`

Controls broad movement flavor:

```text
direct
circle
evasive
cautious
```

`fire_policy`

Controls broad firing intent:

```text
hold_fire
only_when_aligned
burst_when_aligned
suppressive
```

`distance_policy`

Controls range management:

```text
close
maintain
kite
```

`los_lost_action`

Controls what Doom does when the opponent is no longer visible:

```text
turn_left
turn_right
advance_last_seen
hold_angle
sweep
```

`stuck_recovery_strategy`

Controls how Doom escapes when movement stalls:

```text
back_up
turn_left
turn_right
strafe_out
default
```

`movement_primitive`

Optional one-policy override:

```text
advance
retreat
strafe_left
strafe_right
circle_left
circle_right
hold_position
```

Do not use this by default. It overrides the normal high-level movement pattern for one policy and can cause bad behavior if repeated blindly.

`turn_policy`

Controls non-frame-level turning:

```text
auto
turn_to_enemy
sweep_left
sweep_right
hold_angle
face_last_seen
```

`navigation_target`

Controls broad movement target:

```text
none
opponent
last_seen_enemy
center
left_lane
right_lane
keep_distance
```

`fire_mode`

Controls concrete firing style:

```text
auto
hold_fire
fire_when_aligned
single_shot
burst
suppressive
```

## What Doom-side autopilot controls

The Doom-side autopilot receives:

```text
participant id
current intent
self x/y/angle
opponent x/y/health
self health/ammo
distance
relative angle
line of sight
stuck ticks
current tick
phase finished flag
```

It returns:

```text
active
forward
strafe
turn
attack
use
aim_error
stuck_recovery
replan_recommended
replan_reasons
action
reason
```

Doom then applies that output to the actual `ticcmd_t`:

```text
cmd->forwardmove = command.forward * ARENA_PLAYER_FORWARD_SPEED
cmd->sidemove    = command.strafe  * ARENA_PLAYER_SIDE_SPEED
cmd->angleturn   = -command.turn   * ARENA_PLAYER_TURN_SPEED
BT_ATTACK        = command.attack
BT_USE           = command.use
```

So the model does not choose raw frame inputs. The model chooses policy fields, and Doom converts those fields into physical controls.

### Autopilot responsibilities

Doom handles:

```text
turning toward the opponent
aim error calculation
line-of-sight checks
fire gating
burst timing
single-shot timing
distance management
forward/back movement
strafing and circle movement
lost-line-of-sight reacquisition
stuck detection
stuck recovery
movement primitive override
navigation target adjustment
strict spacing rules
stale-intent continuation
```

### Model responsibilities

The model handles:

```text
when to search vs engage
when to push, kite, or hold
how aggressive to be
which fire policy to request
which spacing bounds to request
which direction or lane to bias toward
when to change policy after damage, lost visibility, or being stuck
when to stop after the match is finished
```

## Ready gate and opening intent

The match starts in:

```text
waiting_for_agents
```

Movement does not execute until both agents have:

```text
called set_participant_ready
submitted one opening set_participant_strategy in hierarchical mode, or one opening set_participant_intent in full mode
```

The opening intent is armed but held. Once both sides have ready signals and opening intents, the phase moves to:

```text
combat
```

This prevents Player 1 from moving before Player 2 is connected, or vice versa.

## Sequence numbers and stale intent behavior

Each agent should increment `sequence_number` on every intent.

Example:

```text
sequence_number=1 opening intent
sequence_number=2 first combat update
sequence_number=3 next combat update
```

Doom prefers the newest valid intent. A higher `sequence_number` overrides an older intent immediately, even if the older intent has not expired.

If an intent expires before the next chat response arrives, Doom can mark it:

```text
intent_status=stale
```

That is not the same as stopping. A stale policy is retained so the character does not freeze while the LLM is still producing the next tool call. Agents should replace stale policies quickly with a higher `sequence_number`.

## Regular action schema

The regular schema exposes the four engine-visible intent names directly:

```text
engage_opponent
strafe_attack
hold
search
```

The agent can also set all tactical fields directly:

```text
style
target_id
preferred_distance
aggression
duration_ms
strafe_direction
movement_bias
fire_policy
distance_policy
replan_if
sequence_number
decision_cadence_ms
aim_tolerance
fire_burst_ms
min_fire_alignment
min_distance
max_distance
retreat_if_closer_than
push_if_farther_than
los_lost_action
stuck_recovery_strategy
movement_primitive
turn_policy
navigation_target
fire_mode
rationale
```

Use the regular schema when you want to evaluate detailed tactical policy control. It gives the model more ways to express intent, but also more ways to send contradictory or low-quality parameters.

## Low-level controls

Low-level controls bypass the high-level intent/autopilot benchmark loop. There are two families:

```text
set_player_input / stop_player
set_participant_input / stop_participant
```

`set_player_input` and `stop_player` are the older single-player arena controls. They are normally advertised by the MCP server because the project still supports older arena flows and helper tools such as `attack_enemy`.

`set_participant_input` and `stop_participant` are debug-only direct controls for duel participants. They are hidden unless low-level participant MCP tools are exposed locally:

```powershell
$env:DOOM_ARENA_EXPOSE_LOW_LEVEL_MCP="1"
```

Both low-level families send direct values:

```text
forward: -1 | 0 | 1
strafe: -1 | 0 | 1
turn: -1 | 0 | 1
attack: true | false
use: true | false
duration_ms
```

These values are closer to frame input than tactical policy. They do not ask the Doom autopilot to choose spacing, search behavior, fire policy, or stale-intent recovery. They directly request movement/fire controls for a short duration.

Do not use these for normal benchmark runs. Normal hierarchical duel runs should use:

```text
set_participant_strategy
```

Full-mode/backward-compatible duel runs can use:

```text
set_participant_intent
```

Use low-level tools only when debugging engine control, validating movement plumbing, or testing legacy arena modes.

## Practical agent loop

A normal hierarchical single-round agent loop is:

```text
1. set_participant_ready
2. get_participant_observation
3. set_participant_strategy with sequence_number=1
4. wait_for_match_start
5. get_participant_observation
6. set_participant_strategy with category/action/intensity/objective/target_zone/reasoning and sequence_number=2
7. repeat observe -> strategy with increasing sequence_number
8. when get_match_result says phase=finished and has_next_round=false, call stop_participant_intent once and stop
```

In full control mode, replace `set_participant_strategy` with `set_participant_intent` and send the detailed tactical fields directly.

For multi-round sessions:

```text
1. If phase=finished and has_next_round=true, keep polling get_match_result.
2. When run_id changes, call set_participant_ready again.
3. Reset sequence_number to 1 for the new round.
4. Repeat the opening flow.
```

## MCP command logs, total commands, and decision latency

The UI separates three related concepts:

1. `Total MCP commands`
2. visible MCP command log rows
3. decision latency

`Total MCP commands` is the count of all MCP tool calls made by that participant. It is not only the number of combat decisions.

These all count as MCP commands:

```text
set_participant_ready
get_participant_observation
set_participant_strategy
set_participant_intent
wait_for_match_start
get_match_result
stop_participant_intent
```

Errors also count. That is intentional because tool-call reliability is part of what the benchmark is measuring. A model that makes malformed or rejected MCP calls should show that in the command totals.

The visible MCP command logs are backed by `stats.calls`. Each entry represents one MCP request/response pair. Common fields are:

```json
{
  "call_id": "call_000012",
  "request_index": 12,
  "run_id": "run_abc123",
  "scenario_id": "duel_e1m8",
  "tool_name": "set_participant_strategy",
  "participant_id": "player_1",
  "started_at_ms": 18420,
  "completed_at_ms": 18492,
  "latency_ms": 72,
  "status": "completed",
  "is_error": false,
  "request_chars": 1400,
  "response_chars": 900
}
```

This means a player can show `Total MCP commands: 5` even if only two of those calls are actual tactical intent decisions. A short run may look like this:

```text
Total MCP commands: 5

set_participant_ready
get_participant_observation
set_participant_strategy    Decision latency: 12300ms
  category=position action=flank_left intensity=medium objective=clear_side target_zone=right_side reasoning="enemy hidden, checking unvisited side"
get_participant_observation
set_participant_strategy    Decision latency: 8900ms
  category=engage action=strafe_fight intensity=high objective=force_fight target_zone=enemy_side reasoning="enemy visible, pressuring now"
```

The old mismatch was that the total counted every MCP call, but the visible list only showed intent lifecycle rows. That made the count look wrong. The correct behavior is to show every MCP command row and add decision latency only where it applies.

### MCP latency

`latency_ms` is MCP/server latency. It measures how long the local MCP tool call took after the client sent it.

This is mostly infrastructure and server speed:

```text
MCP client sends request -> Doom Arena MCP server handles it -> MCP response returns
```

Examples:

```text
get_participant_observation latency_ms = 20ms
set_participant_intent latency_ms = 80ms
```

This does not tell us how long the model took to think. It only tells us how long the MCP request itself took once sent.

### Decision latency

Decision latency estimates how long the model/controller took to choose the next tactical action after seeing an observation.

It is inferred from `stats.inferred_decision_turns`:

```text
decision latency = next set_participant_strategy or set_participant_intent started_at_ms - previous get_participant_observation completed_at_ms
```

Example:

```json
{
  "participant_id": "player_1",
  "observation_call_id": "call_000010",
  "intent_call_id": "call_000011",
  "observation_completed_at_ms": 10000,
  "intent_started_at_ms": 15600,
  "inferred_decision_latency_ms": 5600,
  "intent": "strafe_attack",
  "sequence_number": 4
}
```

That means Player 1 took about `5600ms` between receiving the observation and sending the next intent.

Decision latency is shown beside tactical decision rows: `set_participant_strategy` in hierarchical mode and `set_participant_intent` in full mode. Calls like `set_participant_ready`, `wait_for_match_start`, and `get_match_result` are protocol/setup/read calls, not tactical choices. The UI command log intentionally shows only the model-facing MCP call: category, action, intensity, optional objective, optional target zone, and short reasoning. It does not show the expanded Doom intent fields in the visible row.

If an intent has no preceding observation, decision latency may be blank. That can happen during startup, recovery, malformed sequences, or if an agent sends an intent without first observing.

### Intent lifecycle rows

Accepted intent commands also get lifecycle telemetry in `stats.intent_lifecycles`.

These rows describe what happened to a tactical policy after it was submitted:

```json
{
  "call_id": "call_000011",
  "intent_id": "intent_player_1_4",
  "participant_id": "player_1",
  "intent": "strafe_attack",
  "style": "aggressive",
  "sequence_number": 4,
  "duration_ms": 8000,
  "strategy_source": "hierarchical",
  "strategy_category": "position",
  "strategy_action": "flank_left",
  "strategy_intensity": "medium",
  "strategy_objective": "clear_side",
  "strategy_target_zone": "right_side",
  "strategy_reasoning": "enemy hidden, checking unvisited side",
  "issued_at_ms": 15600,
  "expires_at_ms": 40600,
  "mcp_call_latency_ms": 80,
  "superseded_before_expiry": true,
  "effective_duration_ms": 4200,
  "unused_duration_ms": 20800
}
```

Useful lifecycle fields:

```text
sequence_number
intent
style
duration_ms
mcp_call_latency_ms
superseded_before_expiry
effective_duration_ms
unused_duration_ms
gap_after_previous_expiry_ms
sticky_after_expiry
stale_extension_ms
```

These fields show whether the model kept updating policies quickly, let old policies go stale, or replaced policies before their lease expired.

### Aggregate stats

`stats.by_tool` summarizes MCP calls by tool name:

```json
{
  "set_participant_strategy": {
    "count": 12,
    "completed": 12,
    "errors": 0,
    "average_latency_ms": 75,
    "max_latency_ms": 130
  }
}
```

`stats.strategy_category_distribution`, `stats.strategy_action_distribution`, `stats.strategy_objective_distribution`, and `stats.strategy_target_zone_distribution` summarize which hierarchical decisions the models chose across the run.

`stats.by_participant` summarizes MCP calls by participant:

```json
{
  "player_1": {
    "count": 20,
    "completed": 19,
    "errors": 1,
    "average_latency_ms": 60,
    "max_latency_ms": 180
  }
}
```

Good evaluation should look at both decision quality and operational quality:

```text
Total MCP commands: tool-use volume
Intent count: number of tactical decisions submitted
MCP latency: local server/tool-call speed
Decision latency: model/controller thinking time between observe and act
MCP errors: malformed, rejected, or failed tool use
Superseded intents: how often the model refreshed policy before expiry
Stale extensions: where old policy had to keep running because no fresh policy arrived
```

## How to read policy telemetry

The state includes both requested and executed values.

Requested fields come from the model's policy:

```text
requested_fire_policy
requested_distance_policy
requested_strafe_direction
requested_los_lost_action
requested_stuck_recovery_strategy
requested_movement_primitive
requested_turn_policy
requested_navigation_target
requested_fire_mode
```

Executed fields come from Doom's autopilot decision:

```text
executed_fire_action
executed_movement_action
executed_strafe_direction
executed_turn_policy
executed_navigation_target
executed_fire_mode
```

Use this comparison to diagnose failures:

```text
Model asked to fire, but executed_fire_action=hold_fire
```

Likely causes:

```text
no line of sight
no ammo
aim error too high
fire_policy=hold_fire
fire_mode=hold_fire
opponent already dead
```

```text
Model asked to push, but executed_movement_action=retreat
```

Likely causes:

```text
distance below retreat threshold
distance_policy=kite
strict spacing triggered
stuck recovery took over
movement_primitive overrode normal motion
```

```text
Model asked for combat, but autopilot_action starts with lost_los
```

Likely cause:

```text
Doom line-of-sight check failed, so los_lost_action took over.
```

That distinction matters: the MCP agent chooses tactical intent, but Doom remains responsible for whether movement and firing are physically valid in the current frame.









