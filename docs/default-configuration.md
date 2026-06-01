# Default configuration

Doom Arena currently defaults to a route-planning duel setup.

## Main defaults

```text
mode: duel
control mode: hierarchical route planning
primary action tool: set_participant_plan
spawn variant: blind spawn
fog of war: enabled
weapon spawn: enabled
policy lease: 8000ms
map source: scripts/map_blueprints/duel_e1m8_ascii.txt
cell size: 64 x 64 Doom units
```

## Agent control

Agents should use:

```text
get_participant_observation -> set_participant_plan -> get_participant_observation
```

Default action schema:

```json
{
  "participant_id": "player_1",
  "controller_token": "...",
  "objective": "your_goal",
  "route": ["A01", "A02"],
  "engagement_policy": "engage_if_visible",
  "reasoning": "short reason",
  "sequence_number": 1
}
```

Routes use grid cells (`A-W`, `01-33`) instead of raw Doom coordinates. A route can contain up to 16 cells. Every consecutive segment must be horizontal or vertical, and the server rejects diagonal segments, blocked `#` wall cells, blocked-cell crossings, and segments that pass too close to wall corners. The old `set_participant_strategy` category/action schema remains for compatibility, but it is not the default recommendation.

When an agent uses `engagement_policy=avoid_until_target`, Doom follows the route first and suppresses attack until the active route is complete. This is intended for healing or resource routes where stopping to trade shots defeats the plan.

## Fog of war

Fog of war is enabled by default. Agents always know their own position. Opponent coordinates and live distance/health signals are exposed only while the opponent is currently visible from that participant's view cone and the ASCII map path between them does not cross a wall cell. After contact is lost behind a wall, observations keep only stale `last_seen` memory rather than live tracking.

## Static map prompt

The generated prompt includes the ASCII map once. It includes each agent's own selected spawn coordinate and angle, but omits the opponent spawn.

## Pickups

Pickup locations are derived from `H` and `S` markers in `scripts/map_blueprints/duel_e1m8_ascii.txt`. They are included in the generated prompt once, and repeated observations expose compact `map.pickups` entries with `id`, `available`, `cell`, and `distance`.

Each medikit restores `+100` health, capped at the duel max health of `150`.

The setup screen has a `Weapon spawn` option. When it is `False`, the shotgun is removed from the Doom map, hidden from the tactical overlay, and omitted from `map.pickups` and generated prompt context. Health pickups remain enabled.
