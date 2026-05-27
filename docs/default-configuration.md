# Default configuration

Doom Arena currently defaults to a route-planning duel setup.

## Main defaults

```text
mode: duel
control mode: hierarchical route planning
primary action tool: set_participant_plan
spawn variant: blind spawn
fog of war: enabled
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
  "objective": "pick_up_shotgun",
  "route": ["M05", "G05", "G12", "M17"],
  "engagement_policy": "engage_if_visible",
  "reasoning": "take center weapon before forcing a fight",
  "sequence_number": 1
}
```

Routes use grid cells (`A-X`, `01-32`) instead of raw Doom coordinates. A route can contain up to 16 cells, and the server rejects waypoint segments that cross blocked `#` wall cells. The old `set_participant_strategy` category/action schema remains for compatibility, but it is not the default recommendation.

## Fog of war

Fog of war is enabled by default. Agents always know their own position, but opponent exact coordinates are hidden unless visible from that participant's point of view.

## Static map prompt

The generated prompt includes the ASCII map once. It includes each agent's own selected spawn coordinate and angle, but omits the opponent spawn.

## Pickups

Current pickups are exposed in `map.pickups`:

```text
health_top medikit: x=0 y=672
health_bottom medikit: x=0 y=-672
weapon_center shotgun: x=0 y=0
```
