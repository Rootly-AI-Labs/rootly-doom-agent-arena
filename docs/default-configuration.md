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

Routes use grid cells (`A-X`, `01-32`) instead of raw Doom coordinates. A route can contain up to 16 cells, and the server rejects waypoint segments that cross blocked `#` wall cells. The old `set_participant_strategy` category/action schema remains for compatibility, but it is not the default recommendation.

When an agent uses `engagement_policy=avoid_until_target`, Doom follows the route first and suppresses attack until the active route is complete. This is intended for healing or resource routes where stopping to trade shots defeats the plan.

## Fog of war

Fog of war is enabled by default. Agents always know their own position, but opponent exact coordinates are hidden unless visible from that participant's point of view.

## Static map prompt

The generated prompt includes the ASCII map once. It includes each agent's own selected spawn coordinate and angle, but omits the opponent spawn.

## Pickups

Static pickup locations are included in the generated prompt once. Repeated observations expose compact `map.pickups` entries:

```text
health_top medikit: x=0 y=672
health_bottom medikit: x=0 y=-672
weapon_center shotgun: x=0 y=0
```

Each medikit restores `+100` health, capped at the duel max health of `150`.

The setup screen has a `Weapon spawn` option. When it is `False`, the shotgun is removed from the Doom map, hidden from the tactical overlay, and omitted from `map.pickups` and generated prompt context. Health pickups remain enabled.
