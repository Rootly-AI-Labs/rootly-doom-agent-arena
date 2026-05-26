# Default Configuration

This document describes the default Doom Arena duel setup used by the web UI and generated MCP prompts.

## Launch defaults

- Mode: Duel benchmark
- URL: `http://127.0.0.1:8001/?duel=1`
- Default map variant: `Blind spawn`
- Scenario id: `duel_e1m8_blind_spawn`
- Default rounds: `1`
- Control mode: `hierarchical`
- Fog of war: enabled

## Fog of war

Fog of war is enabled by default and is not exposed as a UI toggle.

With fog of war enabled:

- Each agent always sees its own position, angle, health, ammo, and tactical state.
- Opponent coordinates and angle are hidden unless that participant has line of sight to the opponent.
- Visibility is directional. If Player 1 sees Player 2, that does not automatically mean Player 2 sees Player 1.
- If a player is shot or hit, the observation can expose recent combat/contact information, but it does not turn the mode into full shared-state vision.
- The intent is to force agents to remember map structure, track last contact, and search rather than relying on perfect opponent coordinates.

## MCP control mode

The default control path is hierarchical strategy control.

Agents should call:

- `set_participant_ready`
- `get_participant_observation`
- `set_participant_strategy`
- `wait_for_match_start`
- `get_match_result`
- `stop_participant_intent`

Agents should not use low-level movement tools or detailed `set_participant_intent` parameters during normal play.

## Strategy schema

The generated MCP prompt asks each agent to submit one compact strategy:

```json
{
  "participant_id": "player_1",
  "controller_token": "...",
  "category": "engage",
  "action": "strafe_fight",
  "intensity": "medium",
  "objective": "clear_side",
  "target_zone": "right_side",
  "reasoning": "enemy hidden, checking unvisited side",
  "sequence_number": 1
}
```

The server expands this compact strategy into the full Doom autopilot intent consumed by the game loop.

## Policy timing

- Agents do not choose `commit_ms`.
- The server applies an internal `8000 ms` policy lease by default.
- The lease is not a sleep timer.
- Newer strategy calls with higher `sequence_number` override older ones immediately.
- Agents should continue the observe -> strategy -> observe loop as quickly as the chat environment allows.

## Static map context

The generated starting prompt includes static map context once so repeated observations stay compact.

The prompt includes:

- ASCII map layout
- Cell size
- Map bounds
- Coordinate frame
- Wall/collision legend
- The agent's own selected spawn coordinate and angle

The prompt intentionally omits:

- Opponent spawn coordinate
- Player markers on the ASCII map
- Repeated full map blueprints in every observation

Repeated observations reference the initial prompt map using fields like `static_map_source`.

## Tactical overlay

The tactical overlay uses the Doom automap-style view for the active duel map.

It shows:

- Player 1 and Player 2 positions
- Player facing angle/POV
- Smooth movement trails behind each player
- Hover coordinates for the overlay

The overlay is a visualization tool for the human user. Agents receive game state through MCP observations, not through the browser overlay.

## Advanced options currently shown

The visible advanced options are limited to controls that remain user-selectable.

Removed or fixed defaults:

- Fog of war is always enabled.
- Map blueprint prompt control is removed because static map context is now built into the generated prompt.
- Simplified action schema control is removed because hierarchical strategy control is now the default.

## Current intent

The default setup is designed to benchmark agent control quality under partial information:

- Can the model reason from compact observations?
- Can it remember the static map from the initial prompt?
- Can it search and recover without perfect opponent position?
- Can it use MCP tools cleanly with low latency?
