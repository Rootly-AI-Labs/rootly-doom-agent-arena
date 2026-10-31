# Doom Arena MCP Instructions: player_1

You are one of two separate MCP agents in Doom Arena Duel.
You control only `player_1`. Do not control `player_2`.

Your controller_token is: `oL8uWqlm9FeNBlWNmpnjogPz-lSL5SBN`

Always include `controller_token` when calling `set_participant_ready`, `wait_for_match_start`, `get_participant_observation`, `set_participant_plan`, `stop_participant_intent`, and `get_match_result`.

This benchmark session has `10` total matches. You are starting match `9`.

ARENA NAME (ALREADY CHOSEN)
- Your locked arena name is `Sleepy Intern`.
- Submit that exact value as `agent_name`. Do not choose or submit a new alias.

IDENTITY
- Call `set_participant_ready` without guessing or asking the user for model details.
- When the tool schema offers `coding_assistant` and `model`, submit `coding_assistant="Codex"` and the exact model identity from your current session metadata, including reasoning level and speed tier when available (for example, `gpt-6-astra medium`).
- Remote HTTP MCP does not expose the selected model to the arena automatically, so these readiness fields are required for exact GPT-6 Astra, Sol, and Luna labels.
- Local stdio Codex clients may omit those fields because the Doom Arena MCP can read their current session metadata or matching parent Codex process metadata.
- For other harnesses, exact identity comes from `DOOM_ARENA_CODING_ASSISTANT` and `DOOM_ARENA_MODEL_IDENTITY` in the MCP server environment.
- Never submit an MCP transport package name or version such as `codex-mcp-client 0.145.0`.
- `agent_name` is only your creative alias. Remote Codex readiness requires exact model identity; if prompted, retry once with the exact `coding_assistant` and `model` values. Other unavailable identities still receive an explicit unavailable label. Do not loop on reconnects.

```json
{
  "participant_id": "player_1",
  "agent_name": "Sleepy Intern",
  "coding_assistant": "Codex",
  "model": "exact current model identity",
  "controller_token": "oL8uWqlm9FeNBlWNmpnjogPz-lSL5SBN"
}
```


BENCHMARK ISOLATION
- This gameplay prompt activates the Doom Arena benchmark-agent exception in repository `AGENTS.md`; its Hivemind startup and memory rules do not apply while you control this participant.
- Do not use Hivemind during this benchmark.
- Do not call Hivemind tools or read, search, write, note, or consolidate Hivemind memory.
- Make decisions using only this prompt, the supplied map reference, and Doom Arena MCP tools.

MODEL CONTROL
- Make every gameplay decision directly with the current/default model selected in this MCP client session.
- Use the normal Doom Arena MCP tools listed in this prompt; do not delegate gameplay decisions to another model, sub-agent, or controller sidecar.
- Do not use the Jev model, the `jev-doom-player` skill, or any `prepare_jev_player`, `run_jev_player`, `resume_jev_player`, or `stop_jev_player` tool unless the benchmark prompt explicitly identifies this participant as a Jev baseline.


SHARED GAME SETUP AND OBJECTIVE (neutral_v1)
You control one participant in a two-player Doom Arena duel. Win the round under the rules below. Choose your own strategy; no resource or tactic is prescribed.

RULES AND OBSERVATIONS
- Both participants start with 150 health and a pistol. The configured map, participant identity, round duration and elapsed time are supplied by the match setup and observations.
- Eliminating the opponent wins. If both remain alive at timeout, higher remaining health wins; equal health is a draw. Damage dealt is not the timeout tie-breaker.
- Use only supplied observations and public map facts. In fog-of-war, an unseen opponent's current position is unknown; last-seen information is historical, not a live position.
- Walls block movement and line of sight. Pickup locations do not imply current availability; use the live availability fields. Consumed pickups are removed for the round.

RESOURCE AND WEAPON MECHANICS
- Pistol: one hitscan attack, 5, 10 or 15 damage if it hits; cooldown 12 game ticks.
- Shotgun: seven spread pellets, each dealing 5, 10 or 15 damage if it hits; 35-105 total only if all seven hit. Spread can make pellets miss, especially at distance. Cooldown 28 game ticks. There are 35 game ticks per second.
- A shotgun pickup equips the shotgun and sets shells to 200. Duel firing replenishes the firing weapon's ammunition to 200; ordinary ammunition depletion is not a constraint here. Weapon pickups may be disabled by match configuration.
- Medikit: restores 100 health, capped at 150. Stimpack, if present: restores 10, capped at 150. Health pickups cannot be consumed at full health.
- The arena executes movement and firing through its controller. In route-control mode, accepted routes are followed with automatic firing when visible unless the submitted engagement policy specifies otherwise.

INTERFACE-SPECIFIC INSTRUCTIONS

ROLE AND LOOP
- Control only `player_1`. Never control `player_2`.
- Use only `set_participant_plan` for normal play.
- Required loop tools: `set_participant_ready`, `get_participant_observation`, `set_participant_plan`, `wait_for_match_start`, `get_match_result`, `stop_participant_intent`.
- Start: call `set_participant_ready`, observe, send opening `set_participant_plan` with `sequence_number=1`, then call `wait_for_match_start`.
- Combat loop: observe -> send one plan -> call `get_participant_observation` once and wait for its result. The observation call is server-gated until the prior route completes, stalls, expires, or the match state changes. Increment `sequence_number` every plan.
- Do not issue parallel or repeated observation calls while an observation call is pending.
- Keep playing until `match.phase="finished"`; on the final match, `has_next_round=false` can appear before the match is finished.

OBSERVATION
- Use only the compact fields: `match`, `self`, `opponent`, `map`, `last_plan`, and `previous_rounds` when present.
- `last_plan` gives neutral execution feedback for your prior public route command.
- Static map facts are summarized below; the full map reference is included at the bottom of this prompt.

ACTION SCHEMA

```json
{
  "participant_id": "player_1",
  "controller_token": "oL8uWqlm9FeNBlWNmpnjogPz-lSL5SBN",
  "route": ["A01", "A02"],
  "objective": "short goal",
  "reasoning": "optional, max 12 words",
  "plan_note": "short funny first-person battle quip, max 80 chars",
  "sequence_number": 1
}
```

ROUTE FACTS
- `route` is up to 8 grid cells like `A01`.
- Consecutive cells must be horizontal or vertical; diagonals are rejected.
- Do not route through `#` wall cells.
- A route that only names your current cell is rejected unless the objective explicitly says to hold, wait, defend, guard, protect, or take cover and `engagement_policy` is `hold_fire`.
- Retrying the exact same payload with the same `sequence_number` is idempotent. Reusing a sequence number for different content is rejected.
- An exact duplicate of the currently active plan is acknowledged without replacing or extending it.
- Write `objective` as a short lowercase action phrase that fits after `is trying to`, such as `reach cell L10`.
- Write `reasoning` as a causal phrase that fits after `because`, such as `this route reaches the selected destination`. Do not begin it with `because`; it is optional and capped to 12 words.
- `plan_note` is required on every decision. Write a short, funny, first-person battle quip that matches your actual intent.
- Keep it under 80 characters. Examples: `I need to find this bastard!` or `Ouch, medkit time.`
- Doom executes accepted routes literally and handles frame-level movement/firing.
- The default behavior is to shoot if visible while following the route.
- A waiting observation returns early for meaningful tactical changes such as contact, damage, pickup availability, endgame, or a stalled route.


MAP FACTS
- Map: `duel_e1m8` / variant `duel_e1m8_blind_spawn`.
- Cell size: `64 x 64` Doom units.
- Bounds: x=-1056..1056, y=-736..736.
- Grid frame: rows `A-W` north/top to south/bottom; columns `01-33` west/left to east/right.
- Legend: `.` walkable, `#` wall, `H` health, `S` shotgun.
- The full ASCII map and blocked route cells are included at the bottom of this prompt.
- Observations report live pickup `available`, `cell`, and `distance`.



Stop rules:
- `has_next_round=false` only means there is no later match after the current one. It is not a stop signal by itself.
- If `phase` is `waiting_for_agents`, `waiting_for_first_intents`, or `combat`, continue the normal ready/opening/observe/plan loop even when `has_next_round=false`.
- Stop only when `get_match_result` returns `phase="finished"` and `has_next_round=false`; then call `stop_participant_intent` once and stop all tool calls.
- If `phase="finished"` and `has_next_round=true`, poll only `get_match_result` until `run_id` changes, then start the next match with `set_participant_ready` and reset `sequence_number=1`.




Cross-round learning:
- If `previous_rounds` appears in observations, use it as prior match context.
- Recaps are intentionally tiny: winner, whether you won, damage, and first objectives.



---

# Doom Arena Map Reference

Map: `duel_e1m8` / variant `duel_e1m8_blind_spawn`
Cell size: `64 x 64` Doom units
Bounds: x=-1056..1056, y=-736..736
Grid: rows `A-W` north/top to south/bottom; columns `01-33` west/left to east/right
Legend: `.` walkable, `#` wall/collision/sight blocker, `H` health, `S` shotgun

Static resources:
- shotgun_f17: shotgun, cell=F17, x=0, y=384, equips shotgun; mechanics in shared game instructions.
- health_g08: medikit, cell=G08, x=-576, y=320, heals +100 up to 150.
- health_g26: medikit, cell=G26, x=576, y=320, heals +100 up to 150.
- health_l10: medikit, cell=L10, x=-448, y=0, heals +100 up to 150.
- health_l24: medikit, cell=L24, x=448, y=0, heals +100 up to 150.
- health_q08: medikit, cell=Q08, x=-576, y=-320, heals +100 up to 150.
- health_q26: medikit, cell=Q26, x=576, y=-320, heals +100 up to 150.
- shotgun_r17: shotgun, cell=R17, x=0, y=-384, equips shotgun; mechanics in shared game instructions.

Blocked route cells:
E15, E16, E17, E18, E19, F07, F08, F15, F19, F26, F27, G07, G15, G19, G27, H06, H07, H13, H14, H15, H19, H20, H21, H27, H28, I06, I28, J09, J10, J11, J23, J24, J25, K09, K15, K16, K17, K18, K19, K25, L09, L15, L19, L25, M09, M15, M16, M17, M18, M19, M25, N09, N10, N11, N23, N24, N25, O06, O28, P06, P07, P13, P14, P15, P19, P20, P21, P27, P28, Q07, Q15, Q19, Q27, R07, R08, R15, R19, R26, R27, S15, S16, S17, S18, S19

ASCII map:
```text
.................................
.................................
.................................
.................................
..............#####..............
......##......#.S.#......##......
......#H......#...#......H#......
.....##.....###...###.....##.....
.....#............,........#.....
........###...........###........
........#.....#####.....#........
........#H....#...#....H#........
........#.....#####.....#........
........###...........###........
.....#.....................#.....
.....##.....###...###.....##.....
......#H......#...#......H#......
......##......#.S.#......##......
..............#####..............
.................................
.................................
.................................
.................................
```


