# Match Report: Jev + GPT-5.6 Sol vs GPT-5.6 Sol

Generated from the completed 50-round arena session `session_933d3f9560b1` on 2026-09-22.

## Executive summary

**Jev Hybrid + GPT-5.6 Sol won 36-14 (72% to 28%) against GPT-5.6 Sol alone.** Every match ended by elimination: there were no draws, timeout decisions, or incomplete rounds.

The hybrid side produced 74.6 Jev decisions per minute, about 9.5x the GPT-only side's 7.9 inferred decisions per minute. Jev inference averaged 258 ms versus 7.08 seconds for GPT-only decision turns. Recovered usage logs put the hybrid's combined reported/estimated model cost at $5.51 versus an estimated $20.41 for Player 2, or 73.0% lower. The hybrid side also dealt 1.74x as much damage, achieved 91.3% registered-shot accuracy versus 70.8%, and traveled 1.94x as far.

The main Jev concern is repetition rather than raw speed. Only 14.1% of consecutive Jev decisions changed action, 830 exact active plans were locally deduplicated, and the longest action streak was 81 consecutive `patrol_center` selections. The new deduplication layer prevented those repeated choices from becoming 830 redundant arena plan writes.

The main benchmark confound is resource access: Player 1 collected a shotgun in all 50 rounds, while Player 2 collected one in only two. Because spawns and roles were not randomized, the 36-14 result should not be attributed to Jev alone without a mirrored side-swap run.

## Benchmark configuration

| Field | Value |
|---|---|
| Session | `session_933d3f9560b1` |
| Matchup | Player 1: Jev Hybrid + GPT-5.6 Sol; Player 2: GPT-5.6 Sol |
| Rounds | 50 completed |
| Scenario | `duel_e1m8_blind_spawn` |
| Seed | 42 |
| Timeout | 180 seconds |
| Enemy position | Hidden / fog of war enabled |
| Weapon pickups | Enabled |
| Randomized spawns | Disabled |
| Jev model | `typesafe/jev-1.13-20260917` through TypeSafe |
| Hybrid GPT host | `gpt-5.6-sol`, medium reasoning |
| Player 2 controller | `gpt-5.6-sol`; benchmark turn began at high reasoning, with medium applied about four minutes later |

Arena summaries recorded Player 1 as `Jev Hybrid` and Player 2 as `Taco Apologist`, but reported the coding assistant and host model as unavailable. Correlated local Codex rollout logs identify both controller sessions as `gpt-5.6-sol`. The hybrid host used medium reasoning throughout. Player 2's long benchmark turn began at high reasoning, but a medium setting was applied about four minutes into that same turn; because later requests lack per-request effort markers, its exact reasoning-effort mix cannot be reconstructed. This difference and ambiguity are important cost and latency confounds. The internal Jev choice name `handoff_to_opus` is legacy wording; the handoffs went to the GPT-5.6 Sol model hosting the Jev session.

## Match result

| Metric | Jev + GPT-5.6 Sol | GPT-5.6 Sol |
|---|---:|---:|
| Wins | **36** | 14 |
| Win rate | **72.0%** | 28.0% |
| Eliminations | **36** | 14 |
| Draws / timeout decisions | 0 | 0 |
| Average match duration when winning | 39.2 s | 32.2 s |
| Average surviving health when winning | 107.5 | 55.0 |

The hybrid side's win margin was +22 matches, or 2.57 wins per loss. A descriptive 95% Wilson interval for its 72% win rate is 58.3%-82.5%. Under a simple independent 50/50 binomial model, 36 or more wins has a two-sided probability of approximately 0.0026. This is descriptive rather than causal because all rounds used the same map, seed, role assignment, and non-randomized spawn configuration.

## Match timing

| Metric | Value |
|---|---:|
| Total combat time | 1,859.9 s (30m 59.9s) |
| Average match | 37.2 s |
| Median match | 29.8 s |
| P95 match | 90.3 s |
| Fastest match | 14.6 s, Round 41, hybrid win |
| Longest match | 103.2 s, Round 7, hybrid win |
| Average time to first damage | 24.3 s |
| Median time to first damage | 14.6 s |
| P95 time to first damage | 88.5 s |

## Combat and movement

| Metric | Jev + GPT-5.6 Sol | GPT-5.6 Sol | Hybrid advantage |
|---|---:|---:|---:|
| Total damage | **6,920** | 3,985 | 1.74x |
| Damage per match | **138.4** | 79.7 | +73.7% |
| Shots fired | 172 | 528 | 67.4% fewer |
| Registered hits | 157 | 374 | — |
| Accuracy | **91.3%** | 70.8% | +20.5 pp |
| Damage per registered hit | **44.1** | 10.7 | 4.14x |
| Average final health | **77.4** | 15.4 | +62.0 |
| Distance traveled | **243,958.7** | 125,585.5 | 1.94x |
| Average unique cells visited | **33.5** | 24.7 | +35.5% |
| Confirmed shotgun pickups | **50** | 2 | major fixed-role asymmetry |
| Confirmed health pickups | 3 | 2 | — |

These totals come from explicit `pickup:` events, not textual references to pickups inside route explanations. Player 1 acquired the shotgun in every round; Player 2 acquired it only in Rounds 36 and 40. The hybrid side's high damage per registered hit is therefore consistent with near-universal shotgun access, while the GPT-only side normally fought without one. This resource imbalance is large enough to prevent a clean controller-only interpretation of the score.

## Decision and latency comparison

| Metric | Jev tactical inference | GPT-5.6 Sol hybrid host | Jev + GPT-5.6 Sol hybrid | GPT-5.6 Sol only (Player 2) |
|---|---:|---:|---:|---:|
| Recorded decision events | 2,313 decisions | 262 handoff events | 2,313 Jev cycles; 262 handoff events | 244 inferred decisions |
| Event rate per combat minute | **74.6 decisions** | 8.45 handoffs | 74.6 Jev cycles; 8.45 host handoffs | 7.9 decisions |
| Average decision / inference latency | **258 ms direct** | Not isolated | Not fully captured | 7.08 s inferred |
| Median / P95 latency | **246 / 360 ms direct** | Not isolated | Not fully captured | 3.05 / 22.56 s inferred |
| Cumulative measured decision time | 596.9 s | Not isolated | At least 596.9 s measured | 1,727.8 s |
| Arena plan writes | — | — | 894 submitted, 894 accepted | 275 attempted, 209 accepted |
| Rejected plans | — | — | 0 | 66 (24.0%) |
| Exact active plans deduplicated locally | 830 | — | 830 | 0 |

Jev produced 9.48x as many tactical decision cycles per combat minute as Player 2. Its directly measured average inference was 27.4x faster and its P95 was 62.8x faster than the inferred GPT-only decision interval. Those ratios compare Jev endpoint latency with Player 2's operational decision interval; they do not represent full hybrid latency because GPT-5.6 Sol handoff latency was not separately timestamped.

### Usage and cost coverage

| Metric | Jev inference | GPT-5.6 Sol hybrid host | Jev + GPT-5.6 Sol hybrid total | GPT-5.6 Sol only (Player 2) |
|---|---:|---:|---:|---:|
| Decisions / handoffs | 2,313 decisions | 262 handoffs | 2,313 Jev decisions + 262 handoffs | 244 inferred decisions |
| Total input tokens | 3,566,869 | 10,617,850 | 14,184,719 across providers | 41,415,093 |
| Cached input tokens | Not separately reported | 10,416,256 | 10,416,256 GPT tokens; Jev cache split unavailable | 40,918,656 |
| Uncached input tokens | Not separately reported | 201,594 | 201,594 GPT tokens; Jev cache split unavailable | 496,437 |
| Output tokens | 194,949 | 19,455 | 214,404 across providers | 102,986 |
| Reasoning tokens (included in output tokens) | Not separately reported | 5,906 | 5,906 GPT tokens | 19,864 |
| Tokens per event | 1,542 input / 84 output per decision | 40,526 input / 74 output per handoff | Mixed event types | 169,734 input / 422 output per inferred decision |
| Model cost | **$0.149808 provider-reported** | **$5.361978 API-equivalent** | **$5.511787 reported + estimated** | **$20.412930 API-equivalent** |
| Session cost amortized per event | $0.0000648 / decision | $0.02047 / recorded handoff | $0.002383 / Jev decision cycle | $0.08366 / inferred decision |
| Cost per match | $0.002996 Jev layer | $0.1072 host session | **$0.1102 total** | **$0.4083** |
| Overall cost comparison | — | — | **73.0% lower ($14.901 less)** | **3.70x the hybrid total** |

The GPT figures come from `token_count` events in the two correlated local Codex rollout logs. They cover each dedicated controller session in full, including system context, cached context, tool orchestration, and round-control overhead; the $5.361978 hybrid-host amount is therefore the host session's total allocated across 262 handoffs, not an isolated price for the handoff payloads alone. The API-equivalent estimates apply the official GPT-5.6 Sol rates of $4.00 per million uncached input tokens, $0.40 per million cached input tokens, and $20.00 per million output tokens. They are reproducible estimates, not invoice or subscription-billing totals. See [GPT-5.6 Sol pricing](https://developers.openai.com/api/docs/models/gpt-5.6-sol).

The hybrid token total is an arithmetic sum across two providers and may combine different tokenizers, so cost is the more meaningful aggregate comparison. The arena also recorded 33,117 request-token-equivalent and 337,536 response-token-equivalent units for Player 2's MCP traffic. Those character-derived payload estimates are not model billing tokens and are excluded from the table.

## Jev-specific metrics

### Inference and confidence

| Metric | Value |
|---|---:|
| Decisions | 2,313 |
| Decisions per minute | 74.62 |
| Average latency | 258.06 ms |
| Median latency | 245.51 ms |
| P95 latency | 359.50 ms |
| Total Jev inference time | 596.88 s |
| Average confidence | 0.456 |
| Median confidence | 0.420 |
| P05 confidence | 0.270 |
| Decisions below the 0.65 handoff threshold | 1,988 (85.95%) |

### Selected actions

| Jev action | Count | Share |
|---|---:|---:|
| `seek_shotgun` | 806 | 34.85% |
| `continue_current` | 740 | 31.99% |
| `patrol_center` | 419 | 18.12% |
| `hold_position` | 205 | 8.86% |
| `seek_health` | 32 | 1.38% |
| `take_cover` | 29 | 1.25% |
| `pursue_visible` | 28 | 1.21% |
| `finish_opponent` | 22 | 0.95% |
| `handoff_to_opus` | 20 | 0.86% |
| `disengage` | 10 | 0.43% |
| `pursue_last_seen` | 2 | 0.09% |

Weapon acquisition and route continuation accounted for 66.8% of all Jev choices. Explicit pursuit and finishing actions were rare at 2.25% combined, but they were sufficient to help produce 36 eliminations because Doom continued frame-level attack behavior while executing routes.

### Health and weapon behavior

| Metric | Health | Shotgun |
|---|---:|---:|
| Candidate offered | 2,313 (100%) | 2,288 (98.9%) |
| Candidate selected | 32 (1.38%) | 806 (34.85%) |
| Average probability | 3.46% | 30.04% |
| Median probability | 1% | 31% |
| P95 probability | 17% | 61% |
| Maximum probability | 93% | 87% |
| Confirmed Player 1 pickups | 3 | 50 |

The restored always-eligible health rule worked: `seek_health` was present in every Jev choice set. Jev selected it 32 times but completed only three confirmed health pickups. This shows that candidate selection and successful pickup collection are materially different metrics.

### Handoffs to the GPT-5.6 Sol host

| Metric | Count | Share of Jev decisions |
|---|---:|---:|
| Actual handoffs | 262 | 11.33% |
| Explicit `handoff_to_opus` selections | 20 | 0.86% |
| Suppressed handoff conditions | 1,328 | 57.41% |

Actual handoff reasons:

| Reason | Count |
|---|---:|
| Jev confidence below threshold | 239 |
| Jev or plan failure | 13 |
| Plan rejection | 8 |
| Explicit Jev handoff request | 1 |
| Opening Jev failure | 1 |

Most host intervention was caused by the controller's 0.65 confidence policy, not Jev explicitly selecting the handoff option. The 15-second cooldown, 30-second duplicate suppression, and 0.45 hysteresis threshold prevented 1,328 additional handoff conditions from repeatedly interrupting the host.

### Repetition and plan stability

| Metric | Value |
|---|---:|
| Unique filtered state hashes | 1,146 / 2,313 |
| Repeated filtered states | 50.45% |
| Action switches | 320 / 2,263 transitions (14.14%) |
| Exact active plans deduplicated locally | 830 (35.88% of decisions) |
| Arena plan submissions | 894 |
| Accepted arena submissions | 894 (100%) |
| Arena-observed exact plan repetitions | 68 |

Longest same-action streaks:

| Round | Action | Consecutive decisions |
|---:|---|---:|
| 10 | `patrol_center` | 81 |
| 7 | `patrol_center` | 51 |
| 23 | `continue_current` | 38 |
| 50 | `continue_current` | 36 |
| 2 | `patrol_center` | 33 |

The deduplication implementation materially reduced arena churn: 830 repeated active plans were recognized locally rather than resubmitted. However, repeated model selections remain common and should be analyzed separately from repeated plan writes.

## Win/loss behavior split

| Metric | Hybrid wins | Hybrid losses |
|---|---:|---:|
| Matches | 36 | 14 |
| Average duration | 39.2 s | 32.2 s |
| Average Jev decisions per match | 47.0 | 44.4 |
| Handoff rate | 11.23% | 11.59% |
| Local plan-dedup rate | 35.70% | 36.39% |
| `seek_health` selections | 20 | 12 |
| `patrol_center` selections | 413 | 6 |
| `take_cover` selections | 11 | 18 |
| `disengage` selections | 1 | 9 |

Handoff and dedup rates were almost identical between wins and losses. The clearest behavioral difference was tactical posture: winning rounds contained nearly all center patrols and every visible-opponent pursuit/finish choice, while losses had substantially more cover and disengagement relative to their smaller decision count. This is correlation, not proof that those actions caused the result; low health and losing fights naturally make defensive candidates available.

## Key findings

1. **The hybrid won decisively without timeout artifacts.** All 50 rounds ended in an elimination, eliminating the previous draw-heavy failure mode from this session.
2. **The result is heavily confounded by shotgun access.** Player 1 collected the shotgun in 50/50 rounds; Player 2 did so in only 2/50. A mirrored side-swap is required before treating 36-14 as Jev's isolated lift.
3. **Inference speed translated into much higher control frequency.** Jev evaluated state 9.48x as often as the GPT-only controller, without imposing comparable-decision gating.
4. **Recovered usage showed lower reported/estimated spend.** Jev inference plus the GPT host totaled $5.51 versus $20.41 for Player 2, a 73.0% reduction, although Player 2's ambiguous reasoning-effort mix prevents a controlled cost attribution.
5. **The hybrid converted combat more efficiently.** It dealt 73.7% more damage with 67.4% fewer registered shots and a 20.5-point accuracy advantage, though universal shotgun access explains part of that gap.
6. **Health eligibility worked but was rarely preferred or completed.** Health was offered on every Jev decision, selected 1.38% of the time, and resulted in three confirmed Player 1 pickups.
7. **Handoffs were mostly threshold-driven.** Only one actual handoff was caused by an explicit Jev request; 239 were caused by low confidence.
8. **Repetition remains the main Jev behavior issue.** Deduplication protected the arena from redundant writes, but long `patrol_center` and `continue_current` decision streaks remain visible in Jev telemetry.
9. **The GPT-only controller had a route-validity cost.** It submitted 66 rejected plans, or 24.0% of its 275 plan attempts, while all 894 Jev-side arena submissions were accepted.

## Limitations

- Arena artifacts did not contain GPT-5.6 Sol model usage. Token counts were recovered from correlated local Codex rollout logs, while costs are API-equivalent estimates rather than confirmed billing totals.
- The hybrid host ran at medium reasoning. Player 2's benchmark turn began at high reasoning, but medium was applied about four minutes later and the log does not expose per-request effort thereafter. Cost, output-token, and latency differences may therefore combine controller architecture with an unknown reasoning-effort mix.
- GPT-5.6 Sol host latency during the 262 hybrid handoffs was not separately recorded, so a complete combined hybrid-latency distribution cannot be reported.
- GPT-only decision latency is inferred from observation completion to the next plan call; it includes model reasoning and client/tool orchestration.
- Jev latency is direct TypeSafe decision-endpoint latency. The two latency measures are operationally useful but not perfectly identical.
- The fixed seed, fixed role assignment, non-randomized spawns, and single map produced a severe resource asymmetry: Player 1 obtained the shotgun in every round and Player 2 in only two. A mirrored side-swap session is needed to isolate controller quality from Player 1/map advantage.
- `analysis_summary.json` pickup counters overcounted because they treated plan text mentioning a pickup as a pickup event. This report uses only explicit `pickup:` events from `events.jsonl`.
- Confidence is provider-reported Jev confidence, not the probability of the selected candidate.

## Round-by-round results

All terminal reasons were elimination. Health and damage columns are Player 1–Player 2.

| Round | Run ID | Hybrid result | Duration | Final health | Damage | Accuracy |
|---:|---|:---:|---:|---:|---:|---:|
| 1 | `run_def23db9c8aa` | W | 64.6 | 85–0 | 150–65 | 100.0%–100.0% |
| 2 | `run_e6ea2ca35488` | W | 90.3 | 130–0 | 150–20 | 100.0%–50.0% |
| 3 | `run_0734ce4362ed` | W | 29.5 | 100–0 | 160–50 | 100.0%–71.4% |
| 4 | `run_004728fe87d3` | W | 41.5 | 110–0 | 195–40 | 80.0%–23.1% |
| 5 | `run_3ebc7badfcfb` | W | 56.1 | 95–0 | 150–55 | 100.0%–38.5% |
| 6 | `run_213e989c0250` | W | 24.8 | 145–0 | 160–5 | 80.0%–10.0% |
| 7 | `run_f1d62c6ff1b3` | W | 103.2 | 70–0 | 160–80 | 100.0%–70.0% |
| 8 | `run_cfa5aabcac14` | W | 72.9 | 105–0 | 155–45 | 100.0%–55.6% |
| 9 | `run_533f8ae741c8` | W | 47.9 | 85–0 | 160–65 | 100.0%–54.5% |
| 10 | `run_5d70c8f0b792` | W | 52.5 | 120–0 | 160–30 | 100.0%–37.5% |
| 11 | `run_2a8bd24cba27` | L | 34.8 | 0–45 | 105–150 | 100.0%–100.0% |
| 12 | `run_563aec21c1a4` | W | 15.6 | 95–0 | 150–55 | 100.0%–83.3% |
| 13 | `run_4d83281c85da` | W | 39.0 | 100–0 | 160–50 | 75.0%–83.3% |
| 14 | `run_71e6d20217a9` | W | 51.4 | 145–0 | 160–5 | 100.0%–33.3% |
| 15 | `run_292a69694094` | W | 92.4 | 130–0 | 155–20 | 75.0%–50.0% |
| 16 | `run_353add7be244` | W | 17.2 | 130–0 | 160–20 | 100.0%–66.7% |
| 17 | `run_406b03794542` | W | 69.5 | 110–0 | 160–140 | 80.0%–85.0% |
| 18 | `run_d9fa2d59224d` | W | 16.3 | 110–0 | 150–40 | 100.0%–80.0% |
| 19 | `run_06bbeb57fe96` | L | 48.5 | 0–105 | 45–150 | 100.0%–92.3% |
| 20 | `run_5f128d9a2de3` | W | 29.3 | 115–0 | 150–35 | 75.0%–50.0% |
| 21 | `run_80d279ce25d4` | W | 29.8 | 135–0 | 155–15 | 100.0%–20.0% |
| 22 | `run_3a28cf5952ca` | L | 38.7 | 0–15 | 135–150 | 100.0%–93.3% |
| 23 | `run_3519b2d3d7e5` | L | 19.0 | 0–55 | 95–150 | 100.0%–86.7% |
| 24 | `run_128b7bde0c99` | W | 25.6 | 125–0 | 150–25 | 100.0%–60.0% |
| 25 | `run_4c1b1b58147a` | W | 19.3 | 115–0 | 150–35 | 75.0%–66.7% |
| 26 | `run_8db5afd1873a` | W | 16.2 | 115–0 | 150–35 | 100.0%–75.0% |
| 27 | `run_128478c2b6e2` | W | 52.5 | 110–0 | 150–140 | 100.0%–23.5% |
| 28 | `run_7892441af1c2` | L | 35.8 | 0–55 | 95–160 | 66.7%–94.4% |
| 29 | `run_f2219670efa3` | W | 22.2 | 130–0 | 150–20 | 100.0%–60.0% |
| 30 | `run_42c7d80d1401` | L | 18.3 | 0–105 | 45–150 | 100.0%–70.6% |
| 31 | `run_cc06be28a1d5` | W | 15.7 | 115–0 | 155–35 | 100.0%–80.0% |
| 32 | `run_564125b35330` | W | 45.1 | 130–0 | 150–20 | 100.0%–40.0% |
| 33 | `run_b046d5083871` | W | 16.4 | 25–0 | 150–125 | 100.0%–100.0% |
| 34 | `run_68773ac01029` | L | 22.8 | 0–35 | 115–150 | 75.0%–87.5% |
| 35 | `run_d4928a99d47b` | W | 24.7 | 120–0 | 150–30 | 80.0%–50.0% |
| 36 | `run_afbaa7707146` | L | 35.5 | 0–105 | 45–155 | 100.0%–85.7% |
| 37 | `run_97c4ae940163` | W | 15.8 | 110–0 | 160–40 | 100.0%–75.0% |
| 38 | `run_95edf78cb573` | W | 17.8 | 70–0 | 150–80 | 100.0%–87.5% |
| 39 | `run_14c592c0e799` | W | 14.9 | 80–0 | 160–70 | 100.0%–83.3% |
| 40 | `run_99ac6592c918` | W | 83.0 | 70–0 | 155–180 | 100.0%–76.2% |
| 41 | `run_ab7b12f46631` | W | 14.6 | 120–0 | 155–30 | 100.0%–66.7% |
| 42 | `run_7a6c4b3c62d6` | L | 20.7 | 0–15 | 135–155 | 100.0%–86.7% |
| 43 | `run_f359ef7cef74` | L | 38.5 | 0–65 | 85–155 | 66.7%–94.4% |
| 44 | `run_ac36556eaec2` | L | 18.9 | 0–45 | 105–150 | 40.0%–94.1% |
| 45 | `run_bea23e2d34eb` | W | 16.1 | 110–0 | 150–40 | 100.0%–80.0% |
| 46 | `run_3669f614a0a2` | L | 50.2 | 0–50 | 100–160 | 100.0%–100.0% |
| 47 | `run_e2cdef02ab16` | L | 51.6 | 0–25 | 125–160 | 100.0%–82.4% |
| 48 | `run_a191aff8f726` | L | 16.8 | 0–50 | 100–160 | 100.0%–85.7% |
| 49 | `run_eb7c2e274e60` | W | 32.5 | 95–0 | 155–55 | 75.0%–85.7% |
| 50 | `run_cbf1c9e75dcd` | W | 33.6 | 115–0 | 150–35 | 100.0%–100.0% |

## Data sources and calculation notes

- Match outcome and combat totals: each round's `summary.json`.
- Confirmed resource pickups: explicit `pickup:` records in each round's `events.jsonl`.
- Route, movement, and reliability totals: each round's `analysis_summary.json` and `stats.json`.
- Jev selections, confidence, latency, usage, costs, handoffs, and local deduplication: `benchmarks/results/run_def23db9c8aa/jev_player_1.jsonl`, filtered to the 50 session run IDs.
- GPT model identity, reasoning effort, and token usage: cumulative `token_count` events from the two correlated local Codex rollout logs.
- GPT API-equivalent cost: uncached input, cached input, and output token totals multiplied by the published [GPT-5.6 Sol pricing](https://developers.openai.com/api/docs/models/gpt-5.6-sol).
- Percentiles use the nearest-rank method.
- Decisions per minute divide decision count by summed in-match combat duration.
- Accuracy is total registered hits divided by total registered shots, not the unweighted mean of per-round percentages.
