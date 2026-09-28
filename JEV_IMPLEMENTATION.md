# Jev Quick Start

This is the shortest supported workflow for running either:

- **Jev-only** against a regular LLM.
- **Jev + LLM** against a regular LLM.

## The Simple Mental Model

### Shared benchmark instructions (`neutral_v1`)

`scripts/benchmark_game_prompt.txt` is the single source for the game setup,
objective, victory/timeout rules and resource mechanics. The LLM prompt includes
this text verbatim; the Jev controller records it in `game_instructions` and the
adapter places it verbatim before the Jev-specific Choice instructions in each
request. It is not merely a prompt for the host Codex session.

Neither side is told to acquire a weapon, avoid camping, sweep the center or
force a late engagement. Jev no longer receives a separate "safest plan" objective.
LLMs retain their route-writing/tool instructions; Jev retains candidate selection.
Controller-authored candidate justifications and quips are excluded from actionable
Choice descriptions, while concrete routes, objectives and policies remain.
Candidate generation, legality filters and fallbacks still constrain Jev; this is
an agent-setup comparison, not an identical-action-space model test. Hybrid plan overrides remain additional assistance and should be
reported separately from Jev-only benchmark results.

Mechanics verified against `src/doom/arena_duel.c`: pistol damage 5/10/15;
shotgun seven spread pellets of 5/10/15 each, with 12/28-tick cooldowns;
medikits +100 capped at 150; timeout uses remaining health, not damage dealt.
Use fresh generated prompts and a new plugin session after updating. Historical
copied prompts and already-running MCP/server processes are not rewritten.

Use two Codex windows:

| Window | Controls | What you paste |
|---|---|---|
| Window A | Jev participant, normally `player_1` | One token-free prompt from this guide |
| Window B | Regular LLM, normally `player_2` | The browser-generated Player 2 prompt |

Jev never receives a controller token. The plugin loads it internally.

The two Jev modes differ in only one important way:

| Mode | Behavior |
|---|---|
| `jev_only` | Jev's valid choice is executed directly. No host strategy or LLM handoff. |
| `jev_hybrid` | Jev handles normal choices; the host LLM handles low-confidence or explicit handoffs. |

## 1. Add the OpenRouter Key Once

Put `OPENROUTER_API_KEY=your-key` in the repository-root `.env` (never commit it).
The plugin loads this internally; do not put the key in an agent prompt.

### Default: Jev-only neutral route menu (`flat_v3`)

Only `flat_v3` is supported in Jev-only and hybrid modes, using the versioned `neutral_v1` generator in
`plugins/jev-doom-player/scripts/neutral_candidates.py`. Use
`planner_version: "flat_v3"` explicitly for benchmark reproducibility. Make a
new Codex session after reinstalling. Both modes receive the shared game prompt
directly. The free-text strategy input has been removed from the API.

The 14 families are `continue_current`, `pursue_visible`,
`investigate_last_seen`, `seek_shotgun`, `seek_health`, `pickup_then_move`,
`sweep_region`, `explore_unvisited`, `recheck_region`, `alternate_approach`,
`move_to_cover`, `increase_distance`, `move_to_position`, and `hold_position`.
One Choice call selects a concrete route-policy pair; no goal-selection call.

Health, score, elapsed time and visibility do not gate search, center movement,
cover or retreat. A known/remembered threat position is still required for
threat-relative geometry, and visible pursuit requires visible contact.
Unavailable/unknown pickups and invalid routes are excluded. Failed search
destinations are not cooldown-suppressed; the last eight plan outcomes are
included as history. Legacy planners and their tactical menus have been removed.

Moving routes default to `engage_if_visible`. The shared server requires a
stationary hold to use `hold_fire`; this is not a special Jev ability. Explicit
`avoid_until_target`, `hold_fire` and `force_fight` variants can occupy spare
menu slots after default routes, within the same single Choice request.

**Frozen generation and selection rule:** five reachable geometric anchors
(center and quadrant centers); two-anchor sweeps; pickup routes to those anchors
or two nearby junctions; up to four geometrically occluded cover destinations;
one alternate path per eligible target by excluding a middle baseline edge.
All routes pass the existing arena validator and eight-waypoint bound.
Candidates are selected in the published family order, round-robin across
destinations, then policy variants. Exact route-policy duplicates are removed;
the first 20 distinct candidates are offered. This is fixed allocation, not a
utility/win-probability ranking. Not every family or policy is present each turn.

`candidate_menu` logs the full offered menu and generated-but-omitted candidates,
including invalid routes, unavailable pickups, duplicates and budget exclusions.
It records generator version/hash and the selection rule. It does not enumerate
every possible route on the map. Freeze the source, geometry, configuration and
prompt version for a benchmark; do not tune the menu on evaluation rounds.

**Assistance disclosure:** this remains an agent-system comparison. Jev gets
prevalidated BFS routes, geometric path lengths/cover tests, regional anchors and
controller-maintained sampled-cell/outcome history. These derive from public
geometry and allowed observations, not hidden opponent state. Cover is a grid
occlusion test, not a guarantee of safety; an unvisited anchor is not proof that
an entire region is unexplored. Astra authors its own routes; identical raw input
formatting, memory processing, and model-only reasoning parity are not claimed.
Existing server movement, firing and material-change signals are unchanged.


## 2. Start the Arena

From PowerShell:

```powershell
Set-Location 'C:\Users\muhha\OneDrive\Desktop\doom-test\rootly-doom-agent-arena'
.\scripts\start-docker.ps1
```

Open:

```text
http://127.0.0.1:8001/
```

Choose the available map, pickups, and number of matches, then click **Start Benchmark** once.

## 3. Start Window A: Jev

Open a fresh PowerShell window:

```powershell
Set-Location 'C:\Users\muhha\OneDrive\Desktop\doom-test\rootly-doom-agent-arena'
$repo = (Resolve-Path .).Path
$env:DOOM_ARENA_REPO_ROOT = $repo
$env:DOOM_ARENA_BASE_URL = 'http://127.0.0.1:8001'
Remove-Item Env:JEV_DOOM_CONTROL_MODE -ErrorAction SilentlyContinue
codex --enable plugins -C $repo -s read-only -a on-request -c 'mcp_servers.doom-arena.enabled=false' --no-alt-screen
```

Run `/mcp`. Confirm that `jev-doom-player` is connected and `doom-arena` is disabled or absent.

Now choose exactly one prompt.

### Option A: Jev-Only

Paste this into Window A:

```text
Use the jev-doom-player skill. Control only player_1. Call prepare_jev_player once with participant_id="player_1", agent_name="Jev Jockey", control_mode="jev_only". Call run_jev_player with max_run_ms=45000. The shared game prompt is automatic. If running, repeat run_jev_player until finished or failed. Never downgrade, re-prepare, use resume_jev_player, control player_2, expose tokens, or use regular doom-arena tools.
```

That is the standalone baseline. The fixed combat objective is supplied to Jev, but the host Codex session only keeps the plugin running; it does not adapt tactics or handle decisions.

### Option B: Jev + LLM

Paste this into Window A instead:

```text
Use the jev-doom-player skill. Control only player_1. Call prepare_jev_player once with participant_id="player_1", agent_name="Jev Hybrid", control_mode="jev_hybrid". Call run_jev_player with max_run_ms=45000. If running, repeat the call. If awaiting_opus, inspect the filtered handoff and call resume_jev_player with an optional legal override_plan and max_run_ms=45000. Without an override, Jev resumes using the shared prompt and current state. Continue until finished or failed. Never control player_2, expose tokens, reset the duel, or use regular doom-arena tools.
```

The host can be Opus, GPT, Astra, or another LLM. `awaiting_opus` is only the legacy name for the hybrid handoff state.

## 4. Start Window B: The Opposing LLM

Open a second fresh PowerShell window:

```powershell
Set-Location 'C:\Users\muhha\OneDrive\Desktop\doom-test\rootly-doom-agent-arena'
$repo = (Resolve-Path .).Path
codex --disable plugins -m gpt-5.6-sol -C $repo -c 'mcp_servers.doom-arena.enabled=true' --no-alt-screen
```

Change `gpt-5.6-sol` to the model you want to test.

Run `/mcp`. Confirm that Window B has `doom-arena` and does not have `jev-doom-player`.

Click **Copy Player 2 Prompt** in the browser and paste it into Window B. Do not paste the Player 1 browser prompt into Window A; that prompt contains a controller token the Jev plugin already loads internally.

To put Jev on `player_2` instead, swap the participant IDs and give the regular LLM the browser-generated Player 1 prompt.

## Rules to Remember

1. One participant gets one controller. Never run Jev and regular Doom tools for the same participant.
2. `status=running` means call `run_jev_player` again in the same Window A.
3. Use `resume_jev_player` only for `jev_hybrid` after `status=awaiting_opus`.
4. For every automatically started new round, call `prepare_jev_player` again because the run ID changed.
5. After changing or reinstalling the plugin, open a fresh Codex session; do not use `codex resume`.
6. Use Jev telemetry to verify the real controller mode. The spectator nameplate may display the host Codex identity.

## Exact Recorded Jev-Only Example

This example comes from `run_03ecb904dc0b`; it is not hypothetical.

At `112.742` seconds into `duel_e1m8_blind_spawn`:

- Player 1 was near cell `Q08`, around `(-576, -342)`.
- Player 2 was no longer visible, but the controller retained the last-seen location.
- Reachable health and shotgun choices existed.
- The current plan used `avoid_until_target`.
- No handoff or host-authored strategy was available.

Jev received these choices:

| Option | Probability |
|---|---:|
| `disengage` | **44%** |
| `seek_health` | 21% |
| `hold_position` | 18% |
| `continue_current` | 9% |
| `seek_shotgun` | 4% |
| `pursue_last_seen` | 2% |
| `flank_left` | 1% |
| `flank_right` | 1% |

Jev returned:

```text
choice: disengage
confidence: 0.37
```

The controller executed it directly:

```text
Route: Q14 -> T14 -> T33 -> W33
Policy: hold_fire
Reason: This route increases distance from the known threat.
```

Player 1 immediately moved toward `Q14`. About `0.6` seconds later another Jev decision replaced the plan. Player 2 hit Player 1 at `113.342` seconds, and Jev selected `disengage` again.

Three seconds earlier, while Player 2 was visible, Jev was explicitly offered an attack:

```text
continue_current  29%  <- selected
seek_health       27%
disengage         16%
hold_position     16%
pursue_visible     8%
seek_shotgun       2%
flank_left         1%
flank_right        1%
```

`pursue_visible` was available, but Jev rated `continue_current` more highly.

Across the full run, Jev selected:

| Choice | Count |
|---|---:|
| `disengage` | 71 |
| `hold_position` | 27 |
| `seek_health` | 17 |
| `continue_current` | 11 |

There were 126 successful Jev decisions, five additional deterministic safety fallbacks, and no LLM handoff. Player 2 won on timeout with 150 health versus Jev's 134.

Local evidence:

- [`benchmarks/results/run_03ecb904dc0b/jev_player_1.jsonl`](benchmarks/results/run_03ecb904dc0b/jev_player_1.jsonl)
- [`benchmarks/results/session_a1d8c632f575/round_01_run_03ecb904dc0b/summary.json`](benchmarks/results/session_a1d8c632f575/round_01_run_03ecb904dc0b/summary.json)

These result paths are local and ignored by Git. Never commit controller-token files, generated participant prompts, or `.env`.

## Historical Recorded Jev + LLM Example

This section documents an older run, not the current API. Free-text strategy
input has since been removed. Current hybrid intervention uses `override_plan`;
resuming without a plan simply lets Jev reconsider.

This example comes from `run_6cbe2e9e48eb`; it shows how the same Jev decision is handled differently in standalone and hybrid modes.

### Jev-Only

- Receives the filtered game state and legal choices.
- Returns a choice with probabilities and confidence.
- The controller executes a valid choice even when confidence is low.
- There is no `handoff_to_opus`, host strategy, or `resume_jev_player` step.

### Jev + LLM (`jev_hybrid`)

- Receives the same filtered state and legal choices, plus `handoff_to_opus`.
- If Jev explicitly requests help or confidence is below `0.65`, the controller retains a safe plan and asks the host LLM for guidance.
- The host LLM can provide a strategic directive, after which Jev decides again.
- The host LLM can optionally provide a validated `override_plan` when direct intervention is needed.

This recorded run used GPT-5.6-sol directives only. It did not use a direct GPT-authored override plan.

On Player 1's opening evaluation, Jev received:

| Option | Probability |
|---|---:|
| `seek_health` | **35%** |
| `hold_position` | 33% |
| `handoff_to_opus` | 18% |
| `seek_shotgun` | 14% |

Jev returned:

```text
choice: seek_health
confidence: 0.14
```

In `jev_only`, the controller would have executed `seek_health` immediately despite the `0.14` confidence.

In `jev_hybrid`, `0.14` was below the `0.65` handoff threshold, so the controller instead:

1. Installed a safe `hold_position` plan.
2. Sent the sanitized handoff state to GPT-5.6-sol.
3. Received this strategic directive:

   ```text
   Prioritize the F17 shotgun while no opponent is visible;
   avoid unnecessary engagement en route.
   ```

4. Asked Jev to reconsider its legal choices with that directive included in the filtered state.

Later, after Player 1 collected the F17 shotgun, GPT-5.6-sol repeatedly advised leaving F17 and patrolling toward L10. Jev continued requesting another handoff. Because GPT was restricted to directives and did not submit an `override_plan`, the controller safely refreshed the current F17 plan instead of allowing GPT to directly choose a route.

Across the run:

| Hybrid event | Count |
|---|---:|
| Successful Jev decisions | 34 |
| Jev handoffs | 27 |
| Explicit GPT-5.6-sol resumes | 27 |
| Direct GPT override plans | 0 |

The practical distinction is that Jev-only directly follows Jev's valid choice, while hybrid can ask an LLM to advise or override when Jev is uncertain. A directive influences Jev's next decision; it does not force a particular route. Use `override_plan` when the host must directly submit a currently legal plan.

This run ended in a timeout draw. A transient `state_not_ready` snapshot also required Player 1 to be re-prepared, so use it as an implementation example rather than a performance comparison.

Local evidence:

- [`benchmarks/results/run_6cbe2e9e48eb/jev_player_1.jsonl`](benchmarks/results/run_6cbe2e9e48eb/jev_player_1.jsonl)
- [`benchmarks/results/session_1d61789edf71/round_01_run_6cbe2e9e48eb/summary.json`](benchmarks/results/session_1d61789edf71/round_01_run_6cbe2e9e48eb/summary.json)

These result paths are local and ignored by Git.

## If Something Fails

- **Missing API key:** confirm `.env` is in the repository root and Window A exported `DOOM_ARENA_REPO_ROOT`.
- **Waiting for agents:** make sure both windows prepared/submitted an opening plan.
- **Wrong tools in Window A:** relaunch it with `mcp_servers.doom-arena.enabled=false`.
- **Old plugin behavior:** reinstall/cache-bust the plugin and start a new Codex session.
