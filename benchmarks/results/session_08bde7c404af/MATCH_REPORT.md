# Match Report: Jev Only vs GPT-5.6 Sol

Generated from the completed 50-round arena session `session_08bde7c404af` on 2026-09-22.

## Executive summary

**Jev Only finished 47-1-2 against GPT-5.6 Sol: 47 Jev wins, one GPT win, and two draws.** Jev eliminated GPT in 46 rounds and won one additional round on timeout health. GPT's only win was an elimination. Both draws were full-length timeout draws.

Jev produced 47.3 tactical decisions per combat minute, 8.83x GPT's 5.36 inferred decisions per minute. Direct Jev inference averaged 284 ms versus a 7.77-second operational decision interval for GPT, a 27.4x average-latency difference. Jev also dealt 2.78x as much damage, registered 92.4% shot accuracy versus 62.9%, and traveled 2.30x as far.

The Jev provider reported $0.156 in direct inference cost. Including the GPT-5.6 Sol Codex host that operated the Jev sidecar raises the Jev system's API-equivalent cost estimate to $7.61, versus $34.32 for the standalone GPT controller session. That is a 77.8% end-to-end reduction. The host did not make tactical decisions or receive Jev handoffs in `jev_only` mode; its cost is benchmark orchestration overhead.

The 47-1-2 result is **not a clean model-only comparison**. Jev chose among legal routes generated from the arena topology. GPT had to construct exact grid routes, but the separately generated UI Map Reference was not pasted into the Player 2 terminal used for this session. Its prompt contained grid conventions and pickup cells but not the wall layout. GPT consequently had 112 rejected plans out of 302 attempts (37.1%) and collected no shotguns, while Jev collected one in 46 rounds. This session is best described as an end-to-end comparison of the Jev candidate-route controller against a raw GPT route-writing controller without the separate map reference.

## Benchmark configuration

| Field | Value |
|---|---|
| Session | `session_08bde7c404af` |
| Matchup | Player 1: Jev Only; Player 2: GPT-5.6 Sol |
| Arena aliases | Player 1: `Jev Solo`; Player 2: `NachoIntern` |
| Rounds | 50 completed |
| Scenario | `duel_e1m8_blind_spawn` |
| Seed | 42 |
| Timeout | 180 seconds |
| Enemy position | Hidden / fog of war enabled |
| Weapon pickups | Enabled |
| Role assignment | Fixed; no side swap |
| Jev model | `typesafe/jev-1.13-20260917` through TypeSafe |
| Jev control mode | `jev_only`; no strategic handoffs |
| Jev Codex host | `gpt-5.6-sol`, medium reasoning, default speed tier |
| Player 2 controller | `gpt-5.6-sol`, medium reasoning, default speed tier |
| Player 2 map context | Gameplay prompt only; separate UI Map Reference was not pasted |

Arena summaries recorded both coding assistants and model identities as unavailable. Correlated local Codex rollout logs identify both terminal sessions as GPT-5.6 Sol at medium reasoning. On Player 1, that model hosted the Jev MCP loop and benchmark lifecycle but did not choose tactics. Jev received the fixed combat directive and executed its own selected candidate in every decision cycle.

## Match result

| Metric | Jev Only | GPT-5.6 Sol |
|---|---:|---:|
| Wins | **47** | 1 |
| Win rate across all rounds | **94.0%** | 2.0% |
| Win rate among decisive rounds | **97.9%** | 2.1% |
| Elimination wins | **46** | 1 |
| Timeout-health wins | 1 | 0 |
| Draws | 2 | 2 |
| Average match duration when winning | 57.1 s | 47.6 s |
| Average surviving health when winning | **97.1** | 50.0 |

Jev's margin was +46 wins, with 47 wins for every loss. A descriptive 95% Wilson interval for the 94% all-round win rate is 83.8%-97.9%. This interval describes the observed session; it does not remove the route-interface, map-context, role, or resource confounds.

## Match timing

| Metric | Value |
|---|---:|
| Total combat time | 3,090.7 s (51m 30.7s) |
| Average match | 61.8 s |
| Median match | 51.5 s |
| P95 match | 180.2 s |
| Fastest match | 11.1 s, Round 39, Jev elimination win |
| Longest matches | 180.9 s, Round 3 draw and Round 40 Jev timeout-health win |
| Average time to first registered hit | 31.5 s |
| Median time to first registered hit | 20.0 s |
| P95 time to first registered hit | 91.7 s |

Time-to-first-hit statistics cover the 49 rounds containing at least one registered hit. Round 3 ended 150-150 without damage.

## Combat, movement, and resources

| Metric | Jev Only | GPT-5.6 Sol | Jev advantage |
|---|---:|---:|---:|
| Total damage | **7,355** | 2,645 | 2.78x |
| Damage per match | **147.1** | 52.9 | +178.1% |
| Shots fired | 251 | 418 | 40.0% fewer |
| Registered hits | 232 | 263 | - |
| Accuracy | **92.4%** | 62.9% | +29.5 pp |
| Damage per registered hit | **31.7** | 10.1 | 3.15x |
| Average final health | **97.3** | 9.2 | +88.1 |
| Distance traveled | **469,416.7** | 203,975.5 | 2.30x |
| Average unique cells visited | **36.7** | 23.9 | +53.6% |
| Confirmed shotgun pickups | **46** | 0 | severe resource asymmetry |
| Confirmed health pickups | 0 | 5 | - |

Pickup totals use only explicit `pickup:` events, not route text mentioning weapons or health. Jev acquired a shotgun in 46 of 50 rounds, averaging 9.0 seconds to its first shotgun in those rounds. GPT never completed a shotgun pickup. The resulting weapon disparity explains part of Jev's accuracy and damage-per-hit advantage.

## Decision and latency comparison

| Metric | Jev tactical inference | GPT-5.6 Sol only |
|---|---:|---:|
| Recorded decision events | **2,436** | 276 inferred decisions |
| Decisions per combat minute | **47.29** | 5.36 |
| Average decision latency | **283.62 ms direct** | 7.77 s inferred |
| Median latency | **263.00 ms direct** | 7.73 s inferred |
| P95 latency | **385.78 ms direct** | 23.30 s inferred |
| Cumulative measured decision time | **690.89 s** | 2,144.46 s |
| Arena plan attempts | 1,319 submissions | 302 attempts |
| Accepted arena plans | **1,319 (100%)** | 190 (62.9%) |
| Rejected arena plans | **0** | 112 (37.1%) |
| Exact active plans deduplicated locally | 1,151 | 3 |
| Stalled-observation wakeups | Sidecar-managed | 108 |
| Stale-intent extensions | Sidecar-managed | 132, totaling 2,363.4 reported seconds |

Jev produced 8.83x as many tactical decisions per combat minute. Its average direct inference was 27.4x faster, while its P95 was 60.4x faster than GPT's operational interval. Despite making almost nine times as many decisions, Jev accumulated only 32.2% as much measured inference/decision time.

The latency definitions are not identical. Jev latency is measured directly around the TypeSafe decision endpoint. GPT latency is inferred from observation completion to the next plan call and includes model reasoning plus client and tool orchestration. It is still the interval during which the live controller could not submit its next plan.

## Usage and cost coverage

| Metric | Jev inference | GPT host for Jev sidecar | Jev system total | GPT-5.6 Sol only |
|---|---:|---:|---:|---:|
| Tactical decisions | 2,436 | 0 host tactical handoffs | 2,436 Jev decisions | 276 inferred decisions |
| Total input tokens | 3,721,181 | 16,095,589 | 19,816,770 across providers | 77,191,710 |
| Cached input tokens | Not separately reported | 15,943,680 | 15,943,680 GPT tokens; Jev split unavailable | 76,777,344 |
| Uncached input tokens | Not separately reported | 151,909 | 151,909 GPT tokens; Jev split unavailable | 414,366 |
| Output tokens | 171,289 | 23,363 | 194,652 across providers | 97,373 |
| Reasoning tokens, included in output | Not separately reported | 6,547 | 6,547 GPT tokens | 19,230 |
| Tokens per tactical decision | 1,528 input / 70 output | Not applicable | Mixed providers and orchestration | 279,680 input / 353 output per inferred decision |
| Model/session cost | **$0.156290 reported** | **$7.452368 API-equivalent** | **$7.608658 reported + estimated** | **$34.315862 API-equivalent** |
| Cost per tactical event | $0.0000642 / Jev decision | Not applicable | $0.003123 / Jev cycle, including host | $0.1243 / inferred decision |
| Cost per match | $0.00313 Jev layer | $0.14905 host session | **$0.15217 total** | **$0.68632** |
| End-to-end comparison | - | - | **77.8% lower ($26.71 less)** | **4.51x the Jev system total** |

The two GPT token totals come from cumulative `token_count` events in the dedicated Codex rollout logs. They include system context, cached context, tool orchestration, and round-control overhead. The host amount is therefore not a handoff cost: Jev Only performed zero strategic handoffs. It is the cost of keeping the Jev sidecar attached across 50 rounds.

The API-equivalent estimates apply the official GPT-5.6 Sol rates of $4.00 per million uncached input tokens, $0.40 per million cached input tokens, and $20.00 per million output tokens. No recorded request crossed the model page's 272K-token long-context pricing threshold; the largest inputs were 107,577 tokens for the Jev host and 244,706 for Player 2. These are reproducible estimates, not invoice or subscription-billing totals. See [GPT-5.6 Sol pricing](https://developers.openai.com/api/docs/models/gpt-5.6-sol).

The combined Jev token total adds two providers that may use different tokenizers, so cost is the more meaningful end-to-end aggregate. The direct $0.156 Jev cost and the $34.32 GPT session estimate should not be described as a 219x model-price comparison: the GPT figure includes its entire agent harness, while Jev's direct figure excludes the required Codex host. The fairer system-level comparison is $7.61 versus $34.32.

## Jev-specific metrics

### Inference and confidence

| Metric | Value |
|---|---:|
| Decisions | 2,436 |
| Decisions per minute | 47.29 |
| Average latency | 283.62 ms |
| Median latency | 263.00 ms |
| P95 latency | 385.78 ms |
| Total Jev inference time | 690.89 s |
| Average confidence | 0.618 |
| Median confidence | 0.670 |
| P05 confidence | 0.290 |
| Decisions below 0.65 confidence | 1,181 (48.48%) |
| Strategic handoffs | 0 |

Low-confidence decisions remained with Jev because this session used `jev_only`, not `jev_hybrid`. The GPT host did not inspect handoff packets or provide adaptive tactical directives.

### Selected actions

| Jev action | Count | Share |
|---|---:|---:|
| `seek_shotgun` | 1,073 | 44.05% |
| `patrol_center` | 1,070 | 43.92% |
| `continue_current` | 100 | 4.11% |
| `pursue_visible` | 72 | 2.96% |
| `hold_position` | 64 | 2.63% |
| `finish_opponent` | 25 | 1.03% |
| `force_fight` | 17 | 0.70% |
| `pursue_last_seen` | 14 | 0.57% |
| `take_cover` | 1 | 0.04% |

Weapon acquisition and center patrol accounted for 87.97% of Jev's selections. Explicit pursuit, finishing, and forced-fight actions accounted for 5.25%, although Doom continued frame-level firing whenever targets became visible during other routes.

### Health and weapon behavior

| Metric | Health | Shotgun |
|---|---:|---:|
| Candidate offered | 2,436 (100%) | 2,436 (100%) |
| Candidate selected | 0 | 1,073 (44.05%) |
| Average probability | 1.53% | 31.53% |
| Median probability | 0% | 25% |
| P95 probability | 8% | 76% |
| Maximum probability | 21% | 96% |
| Confirmed Player 1 pickups | 0 | 46 |

Jev was strongly weapon-oriented and never selected `seek_health`, despite health being offered on every decision. It still survived with an average final health of 97.3 because most rounds ended before recovery became necessary.

### Repetition and plan stability

| Metric | Value |
|---|---:|
| Unique filtered state hashes | 1,589 / 2,436 |
| Repeated filtered states | 34.77% |
| Action switches | 305 / 2,435 transitions (12.53%) |
| Exact active plans deduplicated locally | 1,151 (47.25% of decisions) |
| Arena plan submissions | 1,319 |
| Accepted arena submissions | 1,319 (100%) |

Longest same-action streaks:

| Round | Action | Consecutive decisions |
|---:|---|---:|
| 3 | `patrol_center` | 108 |
| 4 | `seek_shotgun` | 86 |
| 37 | `patrol_center` | 77 |
| 20 | `patrol_center` | 56 |
| 6 | `patrol_center` | 50 |

The local deduplication layer prevented 1,151 repeated active plans from becoming redundant arena writes. Repeated model choices remain a behavioral issue, however. Round 3's 108-selection `patrol_center` streak ended in a 150-150 timeout draw.

## GPT route-construction failure analysis

| Route result | Count | Share of 302 attempts |
|---|---:|---:|
| Accepted | 190 | 62.9% |
| Rejected: crossed blocked cell | 44 | 14.6% |
| Rejected: diagonal segment | 28 | 9.3% |
| Rejected: waypoint in wall | 26 | 8.6% |
| Rejected after match finished | 13 | 4.3% |
| Rejected: missing plan note | 1 | 0.3% |

Player 2's copied gameplay prompt explained the grid orientation and stated that `#` cells were walls, but it did not contain the ASCII map or blocked-cell list. The UI generated those in a separate collapsed Map Reference panel with a separate copy button. That reference was not part of the prompt pasted into the Player 2 controller session.

Repeated observations exposed the current cell, visible or last-seen opponent cell, pickup cells and approximate distances, and prior-plan feedback. They did not expose the complete wall topology. GPT therefore guessed Manhattan-style routes and learned about blockers only through validation errors or `stuck` feedback. Jev's sidecar instead loaded the ASCII topology internally and offered legal actionable routes.

GPT authored 17 objectives mentioning a shotgun or weapon. Eight reached a numbered plan submission, while nine were rejected or otherwise lacked an accepted sequence number. None resulted in a shotgun pickup. This interface asymmetry is large enough that the session should not be used to claim an isolated 47-1 model-quality advantage for Jev.

## Outcome behavior split

| Metric | Jev wins | Jev loss | Draws |
|---|---:|---:|---:|
| Matches | 47 | 1 | 2 |
| Average duration | 57.1 s | 47.6 s | 180.6 s |
| Average Jev decisions per match | 48.0 | 50.0 | 64.0 |
| Local plan-dedup rate | 47.8% | 54.0% | 34.4% |
| `seek_shotgun` selections | 1,049 | 13 | 11 |
| `patrol_center` selections | 936 | 26 | 108 |
| Pursuit / finish / force-fight selections | 117 | 3 | 8 |

The two draws contained disproportionate center-patrol repetition and very little shotgun selection. With only one loss and two draws, this split is descriptive rather than a reliable causal comparison.

## Key findings

1. **Jev won the raw session 47-1-2.** Forty-six wins were eliminations, one was a timeout-health decision, and two rounds were draws.
2. **The map-reference omission is the dominant validity problem.** GPT had to construct exact routes without the separately generated wall topology, while Jev received prevalidated legal candidates.
3. **Route failures materially suppressed GPT.** It lost 37.1% of its plan attempts to validation, including 70 wall/blocked-cell errors and 28 diagonal-route errors.
4. **Weapon control was overwhelmingly asymmetric.** Jev collected 46 shotguns; GPT collected none, despite writing 17 weapon-related objectives.
5. **Inference speed translated into control frequency.** Jev evaluated state 8.83x as often and averaged 27.4x lower measured latency.
6. **Jev converted combat more efficiently.** It dealt 2.78x the damage with 40% fewer shots and a 29.5-point accuracy advantage, although shotgun access explains part of the difference.
7. **End-to-end estimated cost was lower.** Jev inference plus its non-tactical Codex host totaled $7.61 versus $34.32 for Player 2, a 77.8% reduction.
8. **Jev remained highly repetitive.** Only 12.53% of consecutive selections changed action, and one center-patrol streak lasted 108 decisions. Local deduplication prevented repeated selections from flooding the arena.
9. **Jev ignored health completely.** `seek_health` was always available but never selected; Jev instead concentrated 44.05% of decisions on shotgun acquisition.
10. **The session supports an architecture result, not a pure model result.** Fast choice among legal routes decisively beat slow free-form route construction without topology. A fair model comparison requires equal map information and route affordances.

## Limitations

- The Player 2 terminal received the player prompt but not the UI's separately copied Map Reference. GPT knew pickup cells and grid orientation but not the complete `#` layout.
- Jev chose among candidate routes generated from the arena topology, while GPT had to author exact routes. This combines tactical reasoning, navigation support, and inference speed into one result.
- Roles, spawn variant, seed, and map were fixed. No mirrored side-swap session was run.
- Jev acquired a shotgun in 46 rounds while GPT acquired none. Resource access is inseparable from the observed combat margin.
- GPT decision latency is inferred from observation completion to plan submission and includes reasoning and client/tool orchestration. Jev latency is direct provider endpoint latency.
- The Jev system's $7.61 cost includes its GPT Codex host, even though the host made no tactical decisions. GPT's $34.32 estimate likewise includes its complete controller session. These are API-equivalent estimates, not invoices.
- Combined token totals span TypeSafe and OpenAI tokenizers. Provider-level cost is more meaningful than adding raw token counts.
- Fixed candidate generation is part of the Jev system under test. It should be held constant or shared if the intended claim is about model choice rather than agent architecture.
- Pickup counts come from explicit `pickup:` events because analysis summaries can overcount textual mentions of resources.
- Confidence is Jev provider-reported confidence, not a calibrated probability that the selected action will win.

## Round-by-round results

Terminal values are shown as Jev / GPT.

| Round | Run ID | Jev result | Terminal reason | Duration | Final health | Damage | Accuracy |
|---:|---|:---:|---|---:|---:|---:|---:|
| 1 | `run_7a66846d172e` | W | GPT eliminated | 74.5 s | 90 / 0 | 155 / 60 | 80.0% / 38.5% |
| 2 | `run_cc2b566cce50` | W | GPT eliminated | 38.2 s | 130 / 0 | 150 / 20 | 75.0% / 40.0% |
| 3 | `run_6d7fd3b132cb` | D | Timeout draw | 180.9 s | 150 / 150 | 0 / 0 | 0% / 0% |
| 4 | `run_71fd17c021ab` | W | GPT eliminated | 38.9 s | 130 / 0 | 150 / 20 | 75.0% / 40.0% |
| 5 | `run_78d180a5ef30` | W | GPT eliminated | 91.3 s | 110 / 0 | 150 / 40 | 100.0% / 57.1% |
| 6 | `run_9ff608ebbf0f` | W | GPT eliminated | 131.2 s | 95 / 0 | 160 / 55 | 85.7% / 40.0% |
| 7 | `run_4ac3bc59ea78` | D | Timeout draw | 180.2 s | 150 / 150 | 30 / 0 | 100.0% / 0% |
| 8 | `run_3dffbd06c9cd` | W | GPT eliminated | 39.6 s | 105 / 0 | 150 / 45 | 100.0% / 83.3% |
| 9 | `run_f86fb4265dc2` | W | GPT eliminated | 102.1 s | 85 / 0 | 150 / 65 | 75.0% / 63.6% |
| 10 | `run_79df96cc586d` | W | GPT eliminated | 52.4 s | 110 / 0 | 195 / 40 | 100.0% / 50.0% |
| 11 | `run_7f2905138996` | W | GPT eliminated | 59.2 s | 80 / 0 | 150 / 70 | 85.7% / 54.5% |
| 12 | `run_ab6e376f017b` | W | GPT eliminated | 66.5 s | 75 / 0 | 210 / 75 | 100.0% / 57.1% |
| 13 | `run_059c954f3532` | W | GPT eliminated | 48.4 s | 130 / 0 | 150 / 20 | 100.0% / 33.3% |
| 14 | `run_314fd1ad8318` | W | GPT eliminated | 40.2 s | 125 / 0 | 180 / 25 | 100.0% / 15.8% |
| 15 | `run_ce8aa533804d` | W | GPT eliminated | 48.1 s | 100 / 0 | 150 / 50 | 80.0% / 66.7% |
| 16 | `run_2bd5523893cb` | W | GPT eliminated | 54.6 s | 85 / 0 | 155 / 65 | 100.0% / 75.0% |
| 17 | `run_45e3a471f457` | W | GPT eliminated | 74.5 s | 125 / 0 | 160 / 25 | 75.0% / 50.0% |
| 18 | `run_6ae038e01a63` | W | GPT eliminated | 113.5 s | 105 / 0 | 150 / 45 | 75.0% / 46.2% |
| 19 | `run_a5aaa71836aa` | W | GPT eliminated | 56.9 s | 125 / 0 | 160 / 25 | 100.0% / 42.9% |
| 20 | `run_8ea824cbf0e6` | W | GPT eliminated | 93.8 s | 110 / 0 | 150 / 40 | 100.0% / 80.0% |
| 21 | `run_5d85c5649cf5` | W | GPT eliminated | 51.5 s | 115 / 0 | 150 / 35 | 75.0% / 100.0% |
| 22 | `run_7c4002932dd1` | W | GPT eliminated | 56.9 s | 120 / 0 | 150 / 30 | 75.0% / 50.0% |
| 23 | `run_49c6e910b891` | W | GPT eliminated | 70.3 s | 85 / 0 | 155 / 65 | 60.0% / 81.8% |
| 24 | `run_4e767d2fae58` | W | GPT eliminated | 59.9 s | 100 / 0 | 150 / 50 | 100.0% / 50.0% |
| 25 | `run_76f7d8d90615` | W | GPT eliminated | 48.7 s | 70 / 0 | 150 / 80 | 75.0% / 100.0% |
| 26 | `run_7040670fb4a7` | W | GPT eliminated | 46.5 s | 115 / 0 | 150 / 35 | 80.0% / 62.5% |
| 27 | `run_a21bb547ed0e` | W | GPT eliminated | 80.2 s | 65 / 0 | 150 / 85 | 100.0% / 69.2% |
| 28 | `run_7182eaed76a4` | W | GPT eliminated | 51.0 s | 100 / 0 | 155 / 50 | 100.0% / 83.3% |
| 29 | `run_831fa5e6c18c` | W | GPT eliminated | 45.8 s | 55 / 0 | 155 / 95 | 100.0% / 100.0% |
| 30 | `run_918639e70c51` | W | GPT eliminated | 51.0 s | 95 / 0 | 150 / 55 | 100.0% / 63.6% |
| 31 | `run_310f436c0251` | L | Jev eliminated | 47.6 s | 0 / 50 | 100 / 160 | 100.0% / 85.7% |
| 32 | `run_0ee4b3eeabf3` | W | GPT eliminated | 49.3 s | 110 / 0 | 150 / 40 | 100.0% / 23.5% |
| 33 | `run_d81731825c91` | W | GPT eliminated | 51.8 s | 135 / 0 | 150 / 15 | 100.0% / 40.0% |
| 34 | `run_f58438996432` | W | GPT eliminated | 51.9 s | 140 / 0 | 155 / 10 | 100.0% / 33.3% |
| 35 | `run_5e97bdcc9f5a` | W | GPT eliminated | 53.7 s | 90 / 0 | 150 / 60 | 100.0% / 85.7% |
| 36 | `run_d77c0df5b42c` | W | GPT eliminated | 65.0 s | 45 / 0 | 160 / 105 | 71.4% / 72.7% |
| 37 | `run_b92b5fe62b05` | W | GPT eliminated | 129.0 s | 90 / 0 | 160 / 60 | 80.0% / 55.6% |
| 38 | `run_1f41f12b1004` | W | GPT eliminated | 44.8 s | 80 / 0 | 160 / 70 | 100.0% / 100.0% |
| 39 | `run_16c9edd16827` | W | GPT eliminated | 11.1 s | 120 / 0 | 150 / 30 | 100.0% / 50.0% |
| 40 | `run_de0be0c7903d` | W | Timeout health | 180.9 s | 135 / 110 | 40 / 15 | 100.0% / 100.0% |
| 41 | `run_f4a203daf10c` | W | GPT eliminated | 15.3 s | 95 / 0 | 160 / 55 | 100.0% / 50.0% |
| 42 | `run_c68936696a08` | W | GPT eliminated | 16.8 s | 75 / 0 | 160 / 75 | 100.0% / 100.0% |
| 43 | `run_dec43dc133fc` | W | GPT eliminated | 17.7 s | 90 / 0 | 155 / 60 | 100.0% / 55.6% |
| 44 | `run_5c9924fdaf80` | W | GPT eliminated | 16.4 s | 120 / 0 | 155 / 30 | 100.0% / 33.3% |
| 45 | `run_f6a3d8dc79fb` | W | GPT eliminated | 72.3 s | 75 / 0 | 160 / 75 | 100.0% / 100.0% |
| 46 | `run_758e89ef0e6c` | W | GPT eliminated | 12.3 s | 80 / 0 | 160 / 70 | 100.0% / 100.0% |
| 47 | `run_f7d703269c9d` | W | GPT eliminated | 11.8 s | 10 / 0 | 155 / 140 | 100.0% / 100.0% |
| 48 | `run_11c2934296b7` | W | GPT eliminated | 22.9 s | 65 / 0 | 150 / 85 | 100.0% / 100.0% |
| 49 | `run_0932065f5540` | W | GPT eliminated | 50.4 s | 105 / 0 | 155 / 45 | 100.0% / 85.7% |
| 50 | `run_2b2628082cd0` | W | GPT eliminated | 22.9 s | 70 / 0 | 150 / 80 | 75.0% / 100.0% |

## Data sources and calculation notes

- Match outcomes, timing, health, damage, shots, and hits: each round's `summary.json`.
- Confirmed resource pickups and first-hit timing: explicit records in each round's `events.jsonl`.
- Route attempts, route errors, movement, unique cells, stale extensions, and stall wakeups: each round's `analysis_summary.json` and `stats.json`.
- Jev actions, candidates, confidence, latency, usage, cost, plan submissions, and local deduplication: `benchmarks/results/run_7a66846d172e/jev_player_1.jsonl`, filtered to the session's 50 run IDs.
- GPT model identity, reasoning level, token usage, and API-equivalent costs: cumulative `token_count` events from the two correlated dedicated Codex rollout logs.
- Player 2 map-context verification: the copied controller prompt captured in its Codex rollout contained the sentence that the ASCII map was separate, but did not contain the map or blocked-cell list.
- GPT API-equivalent cost: uncached input, cached input, and output totals multiplied by the published [GPT-5.6 Sol pricing](https://developers.openai.com/api/docs/models/gpt-5.6-sol).
- Percentiles use the nearest-rank method.
- Decisions per minute divide decision counts by summed in-match combat duration.
- Accuracy is total registered hits divided by total registered shots, not the unweighted mean of per-round percentages.
- Cost estimates use full dedicated controller-session totals so both sides include their Codex orchestration overhead.
