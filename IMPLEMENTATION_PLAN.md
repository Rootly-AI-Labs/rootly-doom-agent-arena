# Benchmark Quality Improvements — 4-Phase Plan (v2)

## Context

The Doom Arena benchmark currently pits MCP agents against each other on E1M8
with a 4-action × 25-parameter intent schema, pistol-only fights, and no shared
spatial context. Hamza's 4-model reference run (120 rounds) showed:

- 50-point P1/P2 swing per model — spawn position dominates model skill.
- Only 2 of 6 matchups statistically significant (the rest are coin flips).
- Models send ~3.14 intents/round vs ~20 theoretical capacity — LLM generation
  latency is the dominant bottleneck.

Recent work (this branch) landed: spawn randomization, multi-spawn variants on
E1M8, rationale logging, token tracking, UI polish, fog-of-war. This plan
covers the next four phases agreed in the 2026-05-22 meeting (Sylvain + Hamza)
and incorporates the 2026-05-22 design-review pushback.

**Every phase ships behind an Advanced-panel feature flag.** Default off so
historical benchmarks remain reproducible and A/B comparison is clean. The
full flag matrix is at the end of this document.

---

## Phase 0 — Telemetry instrumentation

**Why this exists**: the proposed validation metrics in subsequent phases
(stuck-recovery count, time-to-first-LOS, intent-diversity, win-rate adaptation
across rounds) are not all emitted by `stats.json` today. Instrument first so
the comparisons in Phases 1/3/4 are measurable on day one rather than
"figure out the metric after running 80 matches."

**Scope**

- Emit `stuck_recovery_invocations` counter per participant per round (already
  tracked internally via `stuck_recovery_strategy` parameter; needs to surface
  in `stats.json`).
- Emit `time_to_first_los_ms` per round (timestamp when each participant's
  `line_of_sight=1` first appears in the arena state TSV).
- Emit `intent_diversity_score` per participant — Shannon entropy of the
  intent-string distribution across the round. **Computes over `intent_raw`,
  not `intent`**, so Phase 2's expanded action surface remains measurable in
  the telemetry rather than being collapsed back to the 4 legacy intents
  before counting (see Phase 2 "Schema preserves what the LLM emitted").
- Emit `distance_policy_switches` per participant per round.
- Add a `match_seed` and `scenario_id` to every `stats.json` so A/B runs can
  be paired deterministically.

**Files**: `scripts/doom_arena_server.py` (`build_mcp_stats_payload_locked`
and the per-tick state ingestion path).

**Risk**: low. Pure additive telemetry, no behavior change.

---

## Phase 1 — Multi-round learning context

**Flag**: `enable_cross_round_recap` (Advanced panel checkbox).

**Hypothesis**: Telling the agent it's in a multi-round session and giving it
a structured recap of prior rounds will let it adapt strategy across the
session. Currently each round starts blind.

**Scope**

- Server: build `previous_round_recap` from `summary.json` + per-round intent
  stats. Fields: winner, your final health, hit rate, damage delta, opponent's
  prevailing intent / style / fire-policy frequencies, death-location coarse
  bucket (n/s/e/w quadrant), spawn variant used.
- Server: surface as a `previous_rounds` array (last N rounds, N configurable,
  default 2) on `get_participant_observation`.
- Prompt: append a "Cross-round learning" section in
  `scripts/doom_arena_duel_prompts.py`. **Always present (cache-friendly)** —
  body says "n/a, first round" on round 1, populated thereafter. Do not
  conditionally include the section based on round number; that's still a
  cache miss.
- **Add post-finish stop instruction** to the same prompt: "When `phase=finished`
  and `has_next_round=false`, stop calling tools immediately. When `phase=finished`
  and `has_next_round=true`, call only `get_match_result` until `run_id` changes."
  This is a free win that addresses the ~32% post-finish-rejection failure rate
  observed in local runs.
- Fog-of-war stays intact: recap is summary-level, no per-tick opponent
  positions surface retroactively.

**Files**

- `scripts/doom_arena_server.py` — recap builder + observation surface.
- `scripts/doom_arena_duel_prompts.py` — cross-round section + post-finish
  stop rule.
- `src/index.html` — `arena-enable-recap` checkbox in Advanced.
- `tests/test_benchmark_improvements.py` — recap-build unit tests.

**Validation**

Real metric is **per-round win-probability delta for the trailing model**
vs a control run with the same seeds and matchup. "Intent diversity rises"
is a *compliance* signal (the model started talking about prior rounds because
the prompt mentioned them), not a *learning* signal. Discard it as a primary
metric.

Seed-paired run: same matchup, same map, same `match_seed` per round
position. Run twice — once with flag on, once with flag off. The trailing
model's round-N win probability should rise faster across rounds in the
flag-on condition.

**Risk**: low. Pure Python + prompt change, no WASM rebuild.

---

## Phase 2 — Action / parameter rebalance (server-side translator)

**Flag**: `enable_simplified_actions` (Advanced panel checkbox).

**Hypothesis**: 4 actions × 25+ parameters is the wrong cognitive ratio for an
LLM. Models pick one of four actions but then must reason about ~25 tactical
knobs, most of which are redundant given the action choice. Inverting to ~10
actions × ~7 parameters reduces output tokens (faster generation → more
decisions per match — directly attacks the bottleneck).

**Critical design change vs v1 of this plan**: implement as a **server-side
translator**, not an engine change. The autopilot in
`src/doom/arena_participant_autopilot.c` dispatches on a 4-way `strcmp`
against the existing intent strings. The new action set is just a presentation
layer that rewrites to the existing 4 actions + parameter bundles. **No WASM
rebuild required.** Backward compat is free because the engine surface never
changed.

**New action set** (each action absorbs the parameters it implies)

| New action | Translates to (server-side) |
|---|---|
| `push_opponent` | `engage_opponent` + `distance_policy=close` + `movement_bias=direct` |
| `flank_left` / `flank_right` | `engage_opponent` + `movement_bias=circle` + `strafe_direction=left/right` |
| `circle_strafe_left` / `circle_strafe_right` | `strafe_attack` + `strafe_direction=left/right` + `movement_bias=circle` |
| `kite` | `strafe_attack` + `distance_policy=kite` + `movement_bias=evasive` |
| `hold_position` | `hold` |
| `camp_los` | `hold` + `fire_policy=only_when_aligned` + `turn_policy=face_last_seen` |
| `patrol_last_seen` | `search` + `navigation_target=last_seen_enemy` |
| `retreat_and_regroup` | `search` + `distance_policy=kite` + `movement_bias=cautious` |

**Reduced LLM-facing parameter set**: `target_id`, `aggression` (0–1),
`fire_policy` (hold / aimed / suppressive), `duration_ms`, `sequence_number`,
`rationale`. All other parameters are filled by the translator from the action
preset.

### Precedence rule: preset wins, conflicts rejected

When the LLM emits a new action together with a parameter the preset would
also set, **the preset is authoritative**. The whole point of Phase 2 is
reducing the 25-knob cognitive load; letting the LLM silently shadow a preset
reintroduces it.

Concrete rule:

- If the LLM omits a parameter the preset sets → preset value is used. No
  validation error.
- If the LLM supplies a parameter the preset *also* sets, and the values
  match → accepted.
- If the LLM supplies a parameter the preset *also* sets, and the values
  conflict → reject with `400` and an explanatory error
  (`"flank_left fixes movement_bias=circle; cannot override to evasive"`).
  Failed intents do not advance `sequence_number` in stats.
- LLM-supplied parameters that are *not* in the preset (e.g. `aggression`,
  `fire_policy`, `target_id`, `duration_ms`) pass through unchanged. These
  are the "Reduced LLM-facing parameter set" above — they're orthogonal to
  the preset.

Enforcement lives in `normalize_participant_intent`. Each entry in the new
action table has an explicit `locked_params: { ... }` map; the translator
diffs the incoming row against it.

### Schema preserves what the LLM emitted: `intent_raw`

Without this change, simplified-actions is **invisible in its own
telemetry**. The translator rewrites `flank_left` → `engage_opponent` before
the TSV row is stored, so `stats.json` intent histograms, `events.jsonl`,
`rationales.jsonl`, and Phase 0's `intent_diversity_score` all see only the
4 legacy intents.

Mitigation: introduce a new TSV column `intent_raw` that records what the
LLM emitted *before* translation. The existing `intent` column continues to
hold the legacy-action string that the engine consumes. When the flag is
off, `intent_raw == intent`. When the flag is on, `intent_raw` is one of the
new actions (e.g. `flank_left`) and `intent` is the rewritten legacy
(`engage_opponent`).

Consumers updated:

- `stats.json` — bucket intents by `intent_raw` *and* `intent`. Histograms
  surface both.
- `events.jsonl` — include `intent_raw` on intent events.
- `rationales.jsonl` — include `intent_raw`.
- Phase 0 `intent_diversity_score` — compute on `intent_raw` so the
  experiment is measurable.

This is a TSV schema change (one new column). Cheap now; painful later if
deferred. The C engine ignores columns beyond what it parses
(`ARENA_PARTICIPANT_INTENT_FIELD_COUNT = 32`), so adding column 33 doesn't
require a WASM rebuild — same pattern as the deferred-rationale work
already in this branch.

**Scope**

- MCP: extend `VALID_PARTICIPANT_INTENTS` in `scripts/doom_arena_mcp.py:45`.
- MCP: update the per-row validation in `parse_participant_intent_rows`
  around `scripts/doom_arena_mcp.py:1288`.
- MCP: simplify `participant_intent_schema()` to expose only the 6-param
  surface when the flag is on. (Schema is generated server-side; agent sees
  the appropriate variant via `tool_definitions`.)
- Server: update `ALLOWED_PARTICIPANT_INTENTS` in
  `scripts/doom_arena_server.py:1905`.
- Server: in `normalize_participant_intent`, if intent is a new action,
  apply the precedence rule (preset wins, conflicts rejected), record the
  original action as `intent_raw`, rewrite `intent` to the legacy action,
  then store the row. The engine sees only the 4 legacy actions.
- TSV: add `intent_raw` column to `PARTICIPANT_INTENT_HEADER` (one column
  after `participant_id`). Update header constant in both
  `doom_arena_mcp.py` and `doom_arena_server.py`.
- Stats / events / rationales: include `intent_raw` in all written
  artifacts.
- Prompt: replace the intent policy table with the new action list. Prune
  surrounding text (~30 % shorter prompt). Gated by flag — old prompt still
  rendered when flag is off.
- Tests: action-translation coverage; conflict-rejection test; verify TSV
  that hits the engine still has one of the 4 legacy `intent` values, and
  `intent_raw` carries the new action name; verify `intent_raw == intent`
  when flag is off.

**Validation**

Same matchup, same map, same seed, 10 mirrored rounds, flag off vs flag on:

- Intents/round — should rise (less to think about → faster generation).
- Output-token consumption per intent call — should fall ~30 %.
- Win-rate ordering — should remain consistent or slightly tighten.
- `intent_raw` distribution — when the flag is on, models should actually
  use the expanded vocabulary. If 90 %+ of `intent_raw` values still cluster
  on the 4 legacy strings, the new actions aren't earning their keep and
  the experiment is null.

**Risk**: medium. Schema change is the biggest behavior surface. But because
the engine never sees the new actions, there's no WASM risk and the change
is fully reversible by toggling the flag. The conflict-rejection precedence
rule means an LLM emitting an inconsistent intent gets a 400 — verify
agents handle the error path gracefully and don't loop, before running the
full validation matrix.

---

## Phase 3 — Simpler map + map blueprint

### Part A — Simpler map (no flag — just a new dropdown option)

- New scenario `duel_e1m8_open_arena` — both players spawn in the outer
  triangular open zone of E1M8 (the area Hamza already validated as a clean
  smoke-test surface). No interior cover, no walls between spawns.
- Coordinates: hand-tuned via Hamza's recipe (estimate from map view, drop
  test pillar, iterate). Capture in `src/doom/p_mobj.c` + `src/doom/arena_duel.c`
  alongside the existing four variants.
- Add to `DUEL_SCENARIOS` in `scripts/doom_arena_server.py`. **Requires WASM
  rebuild.**
- New map appears as a dropdown option in the existing Map dropdown — no new
  flag needed since spawn variant selection is already user-controlled.

### Part B — Map blueprint

**Flag**: `enable_map_blueprint` (Advanced panel checkbox).

**Hypothesis**: Agents currently get `(x, y, angle)` in absolute coordinates
but no information about playable bounds, obstacles, or sightlines. A
structured blueprint in the prompt lets them reason about positioning instead
of guessing.

**Format change vs v1**: ship both an **ASCII grid overlay** *and* compact
JSON metadata. LLMs reason far better about ASCII spatial representations
than raw coordinates. The ASCII grid is the primary representation; JSON
is supplementary for precise coords the model needs to compare against its
own observed position.

**Format** (~400–600 tokens per scenario, hand-authored once):

```
Map: duel_e1m8_open_arena
North is up. P=your spawn, E=enemy spawn, #=wall/blocked, .=open.
. . . . . . . . . . . . . . . . . . . .
. . . . . . . . . . . . . . . . . . E .
. . . . . . . . . . . . . . . . . . . .
. . . . . . . . . . . . . . . . . . . .
. . . . . . . . . . . . . . . . . . . .
. . . . . . . . . . . . . . . . . . . .
. . . . . . . . . . . . . . . . . . . .
. P . . . . . . . . . . . . . . . . . .
. . . . . . . . . . . . . . . . . . . .

bounds: x∈[-800,1600] y∈[1900,4200], 1 grid cell ≈ 120 units
landmarks:
  - center_floor: open, no cover, full LOS between spawns
notes:
  - Diagonal spawn-to-spawn distance ~2400 units. No LOS breakers.
  - Floor is flat; no height advantage.
```

The JSON form (for the small number of agents that prefer structured data)
ships alongside:

```json
{
  "map_id": "duel_e1m8_open_arena",
  "bounds": { "x_min": -800, "x_max": 1600, "y_min": 1900, "y_max": 4200 },
  "compass": { "north": "+y", "east": "+x" },
  "obstacles": [],
  "named_landmarks": [],
  "spawns": {
    "player_1": { "x": -500, "y": 2200, "angle_deg": 45 },
    "player_2": { "x": 1300, "y": 3900, "angle_deg": 225 }
  }
}
```

Inclusion rule: only what changes a movement or shooting decision. Skip
decorative geometry, floor bumps, and walls implicit in `bounds`. Hand-author
once per scenario — resist the temptation to dump every linedef from the WAD.

**Scope**

- Data: ship `map_blueprints/{scenario_id}.{txt,json}` for the 5 scenarios.
- Server: include the active scenario's blueprint (ASCII + JSON) in the
  rendered system prompt. Static per scenario, prompt-cache friendly.
- Prompt: new "Map blueprint" section explaining how to read it.
- Re-render prompt when scenario changes between rounds (randomize /
  rotate-all-maps). Don't change mid-session for the same scenario.
- UI: `arena-enable-map-blueprint` checkbox in Advanced.
- Tests: blueprint-injection coverage.

**Validation**

Three runs of the same matchup on `duel_e1m8_open_arena`, with Phase 0
telemetry in place:

1. Control: no blueprint.
2. Blueprint only.
3. Blueprint + Phase 1 cross-round recap.

Measure:

- `stuck_recovery_invocations` per round (should drop).
- `time_to_first_los_ms` (should drop).
- Win-rate variance across 10 mirrored rounds (should tighten).

If stuck-recoveries don't drop, the blueprint isn't being consumed. Revisit
format (richer named landmarks, denser grid, or both).

**Risk**: low-medium. Part A needs WASM rebuild but mechanically identical to
existing spawn variants. Part B is pure data + prompt change.

---

## Phase 4 — Weapon pickups

**Flag**: `enable_weapon_pickups` (Advanced panel checkbox).

**Hypothesis**: Pistol-only fights don't test tactical literacy. Adding 1–2
weapon pickups creates a real "go for it vs hold spawn" decision that
differentiates aggressive vs defensive models.

**Bias model**: Mirroring (each pair plays N rounds A=P1 + N rounds A=P2)
neutralizes positional asymmetry at the *pair* level. Weapon placement doesn't
have to be geometrically symmetric — asymmetric placements force a *real*
tradeoff. **This makes mirroring load-bearing for fairness in Phase 4,** so
the mirroring helper (previously listed as a side ask) is now in scope.

### Phase 4.0 — Engine spike (1 day, before scoping the rest)

The plan's earlier claim "Doom's pickup machinery just works" is **not safe**.
Specific risks identified in code review:

- The duel does **not** run in deathmatch mode. `deathmatch` is only set by
  argv flags; `arena_duel.c` never sets it. `P_GiveWeapon` (`p_inter.c:617,
  646`) branches on `deathmatch == 2`.
- `arena_duel.c:1074` clears `MF_PICKUP | MF_NOTDMATCH` on the player_2 mobj
  because the duel uses a custom spawn path.
- `P_TouchSpecialThing` requires the toucher to have a `player_t*`.
  `arena_duel.c:1102` notes "only one player slot exists." Player_2 may
  have no `player_t*` to receive the weapon, in which case touch
  short-circuits silently.

**Spike**: spawn a single `MT_SHOTGUN` mobj at known coords on
`duel_e1m8_open_arena`, walk player_2 over it, instrument
`P_TouchSpecialThing` entry. Three possible outcomes:

1. Pickup just works → great, continue with the rest of Phase 4 as written.
2. Pickup fires but player_2's lack of `player_t*` causes a no-op → write
   a custom `ArenaDuel_TouchPickup` that handles the
   `mobj->arena_entity_index == ARENA_MAX_ENEMIES` case.
3. `P_TouchSpecialThing` doesn't even fire because of mobj flags / spawn
   path → restructure player_2 spawn to attach a minimal `player_t*` or
   intercept the touch upstream.

Output of spike: a 1-page note on which case we're in and what the actual
Phase 4.1+ scope is.

### Phase 4.1 — Weapon spawn + per-scenario placement

(Contingent on spike outcome.)

- Engine: new `ArenaDuel_SpawnPickups()` called after player spawn in
  `arena_duel.c`. Spawns weapon mobjs at deterministic-per-scenario
  coordinates. **Requires WASM rebuild.**
- Server: each `DUEL_SCENARIOS` entry gets an optional `pickups` list.
  Randomize / rotate flags shuffle scenarios but not pickup positions
  *within* a scenario — mirroring needs determinism.
- Observation: add `weapon`, `ammo_<type>` to `self`. Add
  `pickups: [{ id, kind, x, y, taken_by, taken_at_ms }]` global field.
  **`taken_by` is global, not LOS-gated** — once a weapon is picked up,
  both agents know, otherwise the unaware agent walks toward a phantom
  magnet. This is a deliberate fog-of-war policy choice: pickup events are
  globally observable (like "shots fired"), positions are not.
- Intents: extend `navigation_target` enum to accept `pickup_<id>`. No new
  action needed.
- Blueprint: add `pickups` array with name + coords + short tactical hint
  ("shotgun: close-range high damage"; "chaingun: sustained fire").
- UI: `arena-enable-weapon-pickups` checkbox in Advanced.

### Phase 4.2 — Mirrored-session helper

Promoted from side ask to in-scope because asymmetric weapon placement
makes mirroring required for fair pair-level comparison.

- UI: new "Run mirrored pair" button in Advanced (or as a sibling of "Start
  Benchmark"). Configures N matches with the models in their declared roles,
  then N more with swapped roles, then surfaces a paired result.
- Server: `duel_session` payload gains `mirror_pair: true`. When set, after
  the first N rounds finish, the next N rounds automatically reverse
  `player_1_model` and `player_2_model` while keeping seeds aligned.
- Results: the end-of-session modal already shipped this session shows a
  per-pair tally.

**First cut**

- 2 weapons per scenario: shotgun and chaingun.
- Placed asymmetrically — distances roughly matched per spawn pair so neither
  side is strictly "better positioned" but each has a closer "preferred"
  weapon.
- No respawn — keep it a one-shot decision (Doom's 30s respawn behavior is
  gated on `deathmatch != 2`, which is already off here).

**Validation**

Same matchup, same map, 20 rounds (10 mirrored pairs):

- Pistol-only baseline vs weapons-enabled — pair-level win-rate variance
  comparison.
- "Rushed to weapon" telemetry: did model A pick `navigation_target=pickup_*`
  in its first 2 intents? Correlation with win.

**Risk**: medium. New engine code path (pickup spawning + possible custom
touch handler). Spike resolves the largest unknown before committing.

---

## Rollout order

**v2 ordering**: **2 → 1 → 3 → 4**

- **Phase 2 first**. Reframed as server-side translator, it has no engine
  risk and directly attacks the LLM generation-latency bottleneck. Every
  subsequent phase adds tokens (recap, blueprint, pickup state) — landing
  Phase 2 first unlocks the latency budget that makes those affordable.
- **Phase 1 second**. Builds on Phase 2's tighter prompt. Also includes the
  post-finish stop instruction, which fixes ~32 % of failed local runs.
- **Phase 3 third**. WASM rebuild for Part A, pure data/prompt for Part B.
  Establishes the cleaner test surface for Phase 4.
- **Phase 4 last**. Highest engine risk (pickup machinery), highest behavior
  richness. Lands on a stable benchmark surface from the prior three.

**Phase 0 (telemetry instrumentation) runs in parallel with Phase 2** — small
enough to land alongside.

---

## Feature-flag matrix

Every new behavior is gated by an Advanced-panel checkbox. Default off.
Persisted in `currentDuelSession`, sent on `POST /api/arena/duel-session`,
applied server-side per round. All flags surface in `stats.json` for
post-hoc analysis.

| Flag (UI id) | Server key | Phase | Default |
|---|---|---|---|
| `arena-hide-enemy-position` (shipped) | `hide_enemy_position` | prior | off |
| `arena-randomize-spawns` (shipped) | `randomize_spawns` | prior | off |
| `arena-rotate-all-maps` (shipped) | `rotate_all_maps` | prior | off |
| `arena-enable-simplified-actions` | `enable_simplified_actions` | 2 | off |
| `arena-enable-recap` | `enable_cross_round_recap` | 1 | off |
| `arena-recap-window` | `recap_window` | 1 | 2 |
| `arena-enable-map-blueprint` | `enable_map_blueprint` | 3b | off |
| `arena-enable-weapon-pickups` | `enable_weapon_pickups` | 4 | off |
| `arena-mirror-pair` | `mirror_pair` | 4 | off |

UI organization: extend the existing three Advanced sub-sections (Match
Setup / Bias Mitigation / Information Control) with a fourth: **Agent
behavior**, housing the recap, simplified-actions, and blueprint flags.
Pickups + mirror-pair go under **Match Setup** since they're game-rule
changes, not agent-side toggles.

**Flag-prompt interaction**: prompt sections (recap, blueprint, simplified
action list) are only included when their flag is on. This keeps the
cached prompt prefix stable for the default config and produces a separate,
also-cacheable prefix when flags are enabled. No conditional bodies inside
sections — the section either exists or doesn't.

---

## Cross-cutting concerns

- **Mirroring**: was manual (user runs two sessions with models swapped).
  Hamza's reference data is paired this way. Phase 4 promotes this to
  in-scope via the mirror-pair helper.
- **Prompt caching**: keep all static content (rules, schemas, blueprint,
  recap-section-with-or-without-body) above any dynamic content (current
  observation) in the system message. Lets providers that cache prefixes
  amortize cost without changing what the model decides.
- **Backward compatibility**: every phase preserves the prior default
  behavior. Hamza's 120-round reference data remains reproducible with all
  flags off.
- **WASM rebuilds needed**: Phase 3a, Phase 4.1. Phases 0, 1, 2, 3b are
  Python + prompt only.

---

## Validation cost budget

Rough estimate of LLM-API spend for validation runs:

| Phase | Matches | Notes |
|---|---|---|
| Phase 0 | 0 | Instrumentation only, no validation matches |
| Phase 2 | 40 | 10 mirrored rounds × 2 (flag off vs on) × 2 model pairs |
| Phase 1 | 40 | 10 mirrored rounds × 2 (off vs on) × 2 model pairs |
| Phase 3 | 60 | 10 mirrored × 3 conditions × 2 model pairs |
| Phase 4 | 80 | 10 mirrored × 2 (pistol vs weapons) × 4 weapon configurations |

**Total: ~220 validation matches.** At Hamza's reference rates (~3.14
intents/round, ~120s/match, mixed token costs across 4 OpenAI models), this
is in the low-hundreds-of-dollars range. State explicitly to the user before
each validation run.

---

## Open questions

1. **Phase 1** — recap window N=1, 2, or 3 rounds? Default 2 in this draft;
   confirm against token budget when Phase 1 prompt section is drafted.
2. **Phase 2** — translator emits stale legacy actions to the engine forever.
   No sunset needed. Confirm we never want to deprecate the 4-action engine
   surface (the answer is probably "no, never").
3. **Phase 3b** — hand-author blueprints (MVP) vs extract from WAD geometry
   (follow-up). MVP is right; the extractor is a separate side project.
4. **Phase 4** — one weapon or two for the first cut after the spike resolves?
   Two is more interesting but doubles the validation surface. Decide post-
   spike based on whether the touch handler needs to be custom.
5. **Mirror-pair helper** — automatically pair *all* multi-round sessions
   when `mirror_pair=true`, or surface it as an explicit second action the
   user triggers? UX vs control tradeoff.

## Resolved (v3, from second-pass review)

- **Phase 2 precedence rule** — preset wins, conflicts are rejected with 400.
  See "Precedence rule: preset wins, conflicts rejected" inside Phase 2.
- **Phase 2 log interpretability** — new `intent_raw` TSV column carries the
  LLM-emitted action; existing `intent` column carries the rewritten legacy
  action. Stats / events / rationales surface both. Phase 0's
  `intent_diversity_score` computes over `intent_raw`. See "Schema preserves
  what the LLM emitted: `intent_raw`" inside Phase 2.
