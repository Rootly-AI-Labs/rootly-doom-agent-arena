# Match Report: Jev Only vs GPT-5.6 Sol

Generated from the completed 50-round arena session `session_171019429660` on 2026-09-22.

## Executive summary

**Jev Only won 27-23 against GPT-5.6 Sol: 54% to 46%.** All 50 rounds ended by elimination, with no draws, timeout decisions, or incomplete rounds. The margin is small: Jev's 54% observed win rate has a 95% Wilson interval of 40.4%-67.0%, and a two-sided exact binomial test against 50/50 gives `p=0.672`.

This is materially fairer than the earlier 47-1-2 Jev-only session. Player 2 received the complete ASCII map and blocked-cell list, both controllers used the same primary combat objective, and weapon access was nearly balanced: Jev acquired a shotgun in 47 rounds and GPT in 46. In the 44 rounds where both acquired one, Jev led only 24-20.

Jev still had a large real-time control advantage. It produced 65.0 decisions per combat minute versus GPT's 4.30 inferred decisions per minute, a 15.1x difference. Direct Jev inference averaged 290 ms versus a 9.23-second operational observation-to-plan interval for GPT, a 31.8x difference. Jev dealt 11.2% more damage, traveled 1.80x as far, and registered 92.2% accuracy versus 83.1%.

Health control favored GPT. `seek_health` was available in every Jev decision but selected only five times, producing two confirmed medikit pickups. GPT collected 19 medikits. GPT won 12 of the 18 rounds where it alone collected a medikit, while Jev won 20 of the 30 rounds where neither side collected one.

Direct Jev decision inference cost $0.123372. Trace-attributed GPT plan-producing turns cost an estimated $8.922212, 72.3x the Jev total, although the two controllers had different action interfaces and context growth. Full harness-inclusive session estimates were $3.17 for the Jev system and $31.10 for GPT, 89.8% lower for the Jev system.

## Benchmark configuration

| Field | Value |
|---|---|
| Session | `session_171019429660` |
| Matchup | Player 1: Jev Only; Player 2: GPT-5.6 Sol |
| Rounds | 50 completed |
| Scenario | `duel_e1m8_blind_spawn` |
| Seed | 42 |
| Timeout | 180 seconds |
| Enemy position | Hidden / fog of war enabled |
| Weapon pickups | Enabled |
| Randomized spawns | Disabled |
| Jev model | `typesafe/jev-1.13-20260917` through TypeSafe |
| Jev control mode | `jev_only`; zero host tactical handoffs |
| Jev Codex host | `gpt-5.6-sol`, medium reasoning, default speed tier |
| Player 2 controller | `gpt-5.6-sol`, medium reasoning, default speed tier |
| Player 2 map context | Full ASCII map, resource locations, and blocked-cell list supplied |

Arena summaries recorded the coding assistants and model identities as unavailable. Correlated dedicated Codex rollout logs identify both terminal sessions as GPT-5.6 Sol at medium reasoning. On Player 1, GPT hosted the Jev sidecar and benchmark lifecycle but made no tactical decisions. Jev received the fixed combat directive and executed its own selected candidate in every decision cycle.

Both sides were told to eliminate the opponent, establish contact, acquire a viable weapon, pursue, avoid passive camping, sweep center after 15-20 seconds without contact, and force engagement in the final 20 seconds unless protecting a meaningful lead.

## Match result

| Metric | Jev Only | GPT-5.6 Sol |
|---|---:|---:|
| Wins | **27** | 23 |
| Win rate | **54.0%** | 46.0% |
| Elimination wins | **27** | 23 |
| Timeout-health wins | 0 | 0 |
| Draws | 0 | 0 |
| Longest win streak | **11** | 4 |
| Average winning-round duration | 34.3 s | 37.4 s |

The round sequence was `WLWLWLWWWWWWWWWWWLLLLWLLWLLWWLWWLLWWLWLLLLWWLLLLWW`. Jev built an 11-match lead after Round 17, but GPT recovered enough late rounds to finish only four wins behind.

## Match timing

| Metric | Value |
|---|---:|
| Total combat time | 1,787.7 s / 29m 47.7s |
| Average match duration | 35.8 s |
| Median match duration | 30.5 s |
| P95 match duration | 84.1 s |
| Fastest match | 13.4 s |
| Longest match | 99.9 s |
| Rounds with a registered hit | 50 / 50 |
| Average time to first registered hit | 27.9 s |
| Median time to first registered hit | 23.0 s |
| P95 time to first registered hit | 73.6 s |

## Combat, movement, and resources

| Metric | Jev Only | GPT-5.6 Sol | Difference |
|---|---:|---:|---:|
| Total damage | **7,025** | 6,315 | Jev +11.2% |
| Damage per match | **140.5** | 126.3 | Jev +14.2 |
| Shots fired | 219 | 231 | Jev 5.2% fewer |
| Registered hits | **202** | 192 | Jev +10 |
| Registered-shot accuracy | **92.2%** | 83.1% | Jev +9.1 points |
| Average final health | 29.1 | **32.2** | GPT +3.1 |
| Distance traveled | **296,924.4** | 165,317.1 | Jev 1.80x |
| Confirmed shotgun pickups | **47** | 46 | nearly balanced |
| Confirmed medikit pickups | 2 | **19** | GPT +17 |

Pickup totals use only explicit `pickup:` events. Jev's first shotgun averaged 5.59 seconds and had a 5.20-second median. GPT's averaged 6.59 seconds with a 5.03-second median; a late 74.9-second pickup increased its mean.

| Shotgun availability outcome | Rounds | Jev wins | GPT wins |
|---|---:|---:|---:|
| Both acquired a shotgun | 44 | **24** | 20 |
| Only Jev acquired one | 3 | **3** | 0 |
| Only GPT acquired one | 2 | 0 | **2** |
| Neither acquired one | 1 | 0 | **1** |

Weapon asymmetry perfectly predicted the winner in the five rounds where exactly one side acquired a shotgun. The 24-20 Jev score when both were armed is a better description of the balanced-weapon matchup than the overall resource totals alone.

| Medikit availability outcome | Rounds | Jev wins | GPT wins |
|---|---:|---:|---:|
| Both collected a medikit | 1 | **1** | 0 |
| Only Jev collected one | 1 | 0 | **1** |
| Only GPT collected one | 18 | 6 | **12** |
| Neither collected one | 30 | **20** | 10 |

The medikit split is descriptive, not causal: losing health makes healing more likely to become useful. It nevertheless shows a real tactical difference between the controllers.

## Decision and latency comparison

| Metric | Jev Only | GPT-5.6 Sol | Ratio |
|---|---:|---:|---:|
| Tactical/model plan turns | 1,938 Jev decisions | 142 GPT plan-producing turns | 13.65x count |
| Inferred observation-to-plan decisions | Not applicable | 128 | - |
| Decisions per combat minute | **65.04** | 4.30 | **15.1x** |
| Average latency | **290 ms** direct inference | 9,229 ms operational | **31.8x** |
| Median latency | **265 ms** | 8,661 ms | **32.7x** |
| P95 latency | **390 ms** | 14,518 ms | **37.3x** |
| Maximum latency | 2,559 ms | 20,664 ms | 8.1x |
| Summed measured intervals | 561.6 s | 1,181.3 s | GPT 2.10x total |

Jev made 13.7x as many direct tactical choices while accumulating less than half the summed inference/decision-wait time. The latency definitions differ: Jev latency is measured directly around the TypeSafe endpoint, while GPT latency is inferred from observation completion to plan submission and includes model reasoning plus client and tool orchestration.

## Usage and cost coverage

### Decision-inference cost

| Metric | Jev Only | GPT-5.6 Sol gameplay |
|---|---:|---:|
| Model decision/plan turns | 1,938 | 142 |
| Input tokens | 2,937,429 | 19,709,155 attributed |
| Cached input tokens | Not separately reported | 19,498,880 |
| Uncached input tokens | Not separately reported | 210,275 |
| Output tokens | 131,708 | 14,078 attributed |
| Reasoning tokens, included in output | Not separately reported | 400 |
| Decision-inference cost | **$0.123372 provider-reported** | **$8.922212 API-equivalent estimate** |
| Cost per model decision/plan turn | **$0.0000637** | $0.0628325 |
| Cost per match | **$0.002467** | $0.178444 |
| Cost comparison | **98.6% lower** | **72.3x the Jev total** |
| GPT handoff inference | **0 turns / $0** | Not applicable |

The GPT gameplay estimate sums the 142 recorded model-usage entries whose emitted action directly called `set_participant_plan`. It includes each turn's complete context and response but excludes observation-only, readiness, result-polling, and benchmark-lifecycle turns. It is a trace-based attribution estimate rather than an invoice. GPT's context accumulated across the 50-round terminal session, while Jev received a compact filtered state on each decision; that architectural difference is part of the measured cost gap.

### Full benchmark-session cost (harness-inclusive)

| Metric | Jev provider layer | Non-tactical GPT host | Jev full benchmark system | GPT-only full controller session |
|---|---:|---:|---:|---:|
| Total input tokens | 2,937,429 | 5,899,895 | 8,837,324 across providers | 70,391,264 |
| Cached input tokens | Not separately reported | 5,816,576 | 5,816,576 GPT tokens; Jev split unavailable | 69,981,184 |
| Uncached input tokens | Not separately reported | 83,319 | 83,319 GPT tokens; Jev split unavailable | 410,080 |
| Output tokens | 131,708 | 19,544 | 151,252 across providers | 73,303 |
| Reasoning tokens, included in output | Not separately reported | 4,381 | 4,381 GPT tokens | 16,513 |
| Full session cost | $0.123372 reported | $3.050786 API-equivalent | **$3.174158 reported + estimated** | **$31.098854 API-equivalent** |
| Full session cost per match | $0.002467 | $0.061016 | **$0.063483** | **$0.621977** |
| Harness-level comparison | - | - | **89.8% lower ($27.925 less)** | **9.80x the Jev system total** |

The GPT totals come from cumulative `token_count` events in the two dedicated Codex rollout logs. They include system context, cached context, tool orchestration, status checks, and round control. The host cost is not tactical inference: Jev Only performed zero strategic handoffs and the host did not choose plans.

API-equivalent estimates apply the official GPT-5.6 Sol rates of $4.00 per million uncached input tokens, $0.40 per million cached input tokens, and $20.00 per million output tokens. No recorded request crossed the 272K-token long-context threshold; the largest requests were 59,494 input tokens for the Jev host and 213,448 for Player 2. See [GPT-5.6 Sol pricing](https://developers.openai.com/api/docs/models/gpt-5.6-sol).

The arena separately recorded 18,899 request-token-equivalent and 188,068 response-token-equivalent units for Player 2 MCP traffic. Those are character-derived payload estimates, not model billing tokens, and are excluded from the cost tables.

## Jev-specific metrics

### Inference and confidence

| Metric | Value |
|---|---:|
| Jev decisions | 1,938 |
| Decisions per combat minute | 65.04 |
| Average latency | 289.790 ms |
| Median latency | 264.819 ms |
| P95 latency | 389.634 ms |
| Maximum latency | 2,559.044 ms |
| Total direct inference time | 561.612 s |
| Average confidence | 0.610 |
| Median confidence | 0.570 |
| Decisions below 0.65 | 1,115 / 1,938 (57.53%) |
| Input tokens | 2,937,429 |
| Output tokens | 131,708 |
| Provider-reported cost | $0.123372 |

Low confidence did not cause a host handoff in `jev_only` mode. Jev executed its selected legal candidate unless deterministic fallback was needed.

### Action distribution

| Jev action | Count | Share |
|---|---:|---:|
| `seek_shotgun` | 981 | 50.62% |
| `patrol_center` | 664 | 34.26% |
| `pursue_visible` | 97 | 5.01% |
| `continue_current` | 79 | 4.08% |
| `pursue_last_seen` | 34 | 1.75% |
| `hold_position` | 33 | 1.70% |
| `hold_chokepoint` | 27 | 1.39% |
| `take_cover` | 13 | 0.67% |
| `finish_opponent` | 5 | 0.26% |
| `seek_health` | 5 | 0.26% |

`seek_shotgun` was available in 1,222 decisions and selected 80.3% of those opportunities. `seek_health` was available in all 1,938 decisions but selected only five times. The dominant Jev policy was therefore weapon-first and center-patrol-heavy, with very little health control.

### Repetition, deduplication, and fallback

| Metric | Value |
|---|---:|
| Consecutive action changes | 204 / 1,888 pairs (10.81%) |
| Longest identical-action streak | 56 `patrol_center` decisions |
| Longest-streak round | Round 2, `run_02325e62897d` (Jev loss) |
| Arena plan submissions | 859 |
| Exact active plans deduplicated locally | 1,078 |
| Decisions absorbed by deduplication | 55.62% |
| Jev-sourced submissions | 787 |
| Deterministic fallback submissions | 72 |
| Fallback actions | 47 `hold_position`; 25 `continue_current` |

Deduplication prevented 806 repeated `seek_shotgun` plans, 193 repeated `patrol_center` plans, and 79 other exact active-plan repetitions from reaching the arena. Jev's output remained highly repetitive, but most identical active routes did not reset or extend arena execution.

## GPT route behavior and reliability

| Metric | Value |
|---|---:|
| Plan attempts | 142 |
| Rejected attempts | 22 (15.49%) |
| In-combat route-validation errors | 17 (11.97% of attempts) |
| Post-finish HTTP 409 writes | 5 |
| Diagonal-segment errors | 15 |
| Blocked-cell errors | 1 |
| Wall-cell errors | 1 |
| Accepted plans | 120 |
| Unique objective strings | 66 |
| Unique route strings | 73 |
| Stalled observation wakeups | 52 |
| Total stalled-observation wait | 85.1 s |

Supplying the map materially improved GPT routing: the prior map-omitted session rejected 112 of 302 plans (37.1%), while this session rejected 22 of 142 (15.5%). Excluding five post-finish writes, only 17 plans failed tactical route validation.

GPT repeated the objective `arm and stage behind cover` 37 times. Sixty-nine of its 142 accepted-or-attempted plan records mentioned healing, health, or a medikit, which aligns with its 19 confirmed medikit pickups. Exact active-plan repetition for Player 2 remained zero because its submitted route payloads changed.

## Outcome behavior split

| Jev action | Wins | Win share | Losses | Loss share |
|---|---:|---:|---:|---:|
| `seek_shotgun` | 536 | 51.64% | 445 | 49.44% |
| `patrol_center` | 368 | 35.45% | 296 | 32.89% |
| `pursue_visible` | 47 | 4.53% | 50 | 5.56% |
| `continue_current` | 37 | 3.56% | 42 | 4.67% |
| `pursue_last_seen` | 15 | 1.45% | 19 | 2.11% |
| `hold_position` | 12 | 1.16% | 21 | 2.33% |
| `hold_chokepoint` | 12 | 1.16% | 15 | 1.67% |
| `take_cover` | 6 | 0.58% | 7 | 0.78% |
| `finish_opponent` | 4 | 0.39% | 1 | 0.11% |
| `seek_health` | 1 | 0.10% | 4 | 0.44% |

Winning rounds were slightly more center-patrol and shotgun-heavy. Losing rounds contained more holding, continuation, last-seen pursuit, and health-seeking by share. These differences are descriptive and partly reflect state: losing fights make defensive and health actions relevant.

## Comparison with the earlier map-omitted Jev-only session

| Metric | Earlier `session_08bde7c404af` | This session |
|---|---:|---:|
| Result | Jev 47-1-2 | **Jev 27-23** |
| Player 2 full map reference | No | **Yes** |
| Shotgun rounds, Jev / GPT | 46 / 0 | **47 / 46** |
| Medikit pickups, Jev / GPT | 0 / 5 | 2 / 19 |
| GPT plan rejection rate | 112 / 302 (37.1%) | **22 / 142 (15.5%)** |
| Damage, Jev / GPT | 7,355 / 2,645 | **7,025 / 6,315** |

This change does not prove that the map reference alone caused the score shift, because the controller conversation and match trajectories also differed. It does confirm that the earlier 47-1-2 result was dominated by an interface asymmetry that prevented GPT from navigating to weapons reliably.

## Key findings

1. **Jev won, but narrowly.** The raw score was 27-23, and the 54% win rate is not statistically distinguishable from 50% at 50 rounds.
2. **The full map reference fixed the largest prior validity defect.** GPT acquired shotguns in 46 rounds and reduced plan rejection to 15.5%.
3. **Weapon-balanced rounds remained close.** When both sides acquired shotguns, Jev led 24-20.
4. **Inference speed still produced much higher control frequency.** Jev acted 15.1x as often and averaged 31.8x lower measured latency.
5. **Jev retained a modest combat-efficiency edge.** It dealt 11.2% more damage, fired 5.2% fewer shots, and led accuracy by 9.1 points.
6. **Health control was Jev's clearest tactical weakness.** Jev selected `seek_health` five times and collected two medikits; GPT collected 19.
7. **Jev remained repetitive.** Only 10.81% of consecutive choices changed action, with 1,078 exact active plans deduplicated locally.
8. **Trace-attributed decision inference strongly favored Jev on cost.** Jev cost $0.1234 versus an estimated $8.9222 for GPT plan-producing turns, though their action interfaces and context shapes differ.
9. **Full-session cost favored the Jev harness.** The harness-inclusive estimate was $3.17 versus $31.10, an 89.8% reduction.
10. **This is an architecture comparison, not a pure model bake-off.** Jev selected among topology-aware legal candidates; GPT authored exact routes from the supplied map.

## Limitations

- Roles, spawn variant, seed, and map were fixed. No mirrored side-swap session was run.
- Jev chose among candidate routes generated from arena topology, while GPT constructed exact routes from the supplied map. Navigation support and model choice remain coupled.
- GPT operational latency includes model reasoning, client latency, and tool orchestration; Jev latency is direct provider endpoint time.
- GPT gameplay cost is trace-attributed from plan-producing model turns, not invoice data. It includes those turns' full accumulated context.
- Full-session GPT estimates include system context, orchestration, status checks, and round lifecycle. They are not isolated tactical inference costs.
- Combined token totals span TypeSafe and OpenAI tokenizers, so raw cross-provider token sums are descriptive rather than directly comparable.
- The 27-23 result has wide sampling uncertainty. More rounds, multiple seeds, and mirrored roles are required for a stable win-rate estimate.
- Pickup counts use explicit `pickup:` records because analysis summaries can overcount resource words appearing in plan text.
- Confidence is provider-reported Jev confidence, not a calibrated probability that its chosen action will win.

## Round-by-round results

All terminal reasons were elimination. Health and damage columns are Jev / GPT.

| Round | Run ID | Jev result | Time | Final health J/G | Damage J/G | Accuracy J/G |
|---:|---|:---:|---:|---:|---:|---:|
| 1 | `run_ebaaf822f3ff` | W | 99.9 s | 95 / 0 | 150 / 55 | 100.0% / 71.4% |
| 2 | `run_02325e62897d` | L | 84.1 s | 0 / 10 | 140 / 150 | 100.0% / 77.8% |
| 3 | `run_024af9468037` | W | 66.2 s | 80 / 0 | 150 / 70 | 100.0% / 75.0% |
| 4 | `run_99ab0ea8c480` | L | 93.3 s | 0 / 150 | 0 / 150 | - / 100.0% |
| 5 | `run_4f1a2d50b272` | W | 41.6 s | 120 / 0 | 155 / 30 | 100.0% / 37.5% |
| 6 | `run_e40b476a30ca` | L | 33.8 s | 0 / 25 | 125 / 250 | 60.0% / 81.8% |
| 7 | `run_52eed756ad34` | W | 17.1 s | 130 / 0 | 155 / 20 | 100.0% / 33.3% |
| 8 | `run_6f889fe36951` | W | 14.2 s | 45 / 0 | 160 / 105 | 100.0% / 100.0% |
| 9 | `run_e2972af26445` | W | 35.3 s | 75 / 0 | 150 / 75 | 100.0% / 50.0% |
| 10 | `run_c3eaae8e039b` | W | 13.4 s | 80 / 0 | 155 / 70 | 100.0% / 100.0% |
| 11 | `run_14b5935f6fc6` | W | 14.0 s | 60 / 0 | 150 / 90 | 100.0% / 100.0% |
| 12 | `run_71cd116f2bf2` | W | 30.3 s | 55 / 0 | 155 / 95 | 100.0% / 66.7% |
| 13 | `run_b4b2f0d92fce` | W | 25.0 s | 10 / 0 | 185 / 140 | 100.0% / 100.0% |
| 14 | `run_73c3ab5ef634` | W | 25.3 s | 20 / 0 | 235 / 130 | 100.0% / 83.3% |
| 15 | `run_04ffed190324` | W | 30.0 s | 20 / 0 | 150 / 130 | 100.0% / 100.0% |
| 16 | `run_1a90989a9857` | W | 38.0 s | 55 / 0 | 205 / 195 | 100.0% / 85.7% |
| 17 | `run_8b57ce7a22e6` | W | 27.2 s | 105 / 0 | 150 / 45 | 100.0% / 66.7% |
| 18 | `run_351a9f1542d2` | L | 25.3 s | 0 / 100 | 100 / 160 | 66.7% / 100.0% |
| 19 | `run_5d9458d12b09` | L | 25.7 s | 0 / 90 | 135 / 150 | 100.0% / 100.0% |
| 20 | `run_e54f6b3d9a85` | L | 24.8 s | 0 / 85 | 65 / 155 | 66.7% / 100.0% |
| 21 | `run_3508594e9953` | L | 33.5 s | 0 / 25 | 125 / 160 | 100.0% / 100.0% |
| 22 | `run_6ed49d0011bf` | W | 32.5 s | 90 / 0 | 160 / 60 | 100.0% / 66.7% |
| 23 | `run_6c8d19509809` | L | 24.2 s | 0 / 90 | 60 / 150 | 66.7% / 100.0% |
| 24 | `run_e855019d2033` | L | 34.8 s | 0 / 10 | 140 / 150 | 100.0% / 60.0% |
| 25 | `run_8dc66d8f9667` | W | 29.7 s | 5 / 0 | 235 / 145 | 83.3% / 80.0% |
| 26 | `run_f4b16f5dc686` | L | 29.1 s | 0 / 85 | 95 / 155 | 100.0% / 100.0% |
| 27 | `run_d9476cb05019` | L | 25.0 s | 0 / 45 | 105 / 155 | 75.0% / 100.0% |
| 28 | `run_af3274bc12f9` | W | 50.7 s | 20 / 0 | 160 / 130 | 100.0% / 80.0% |
| 29 | `run_523654fa7329` | W | 30.1 s | 30 / 0 | 195 / 120 | 80.0% / 40.0% |
| 30 | `run_97e1b6380551` | L | 29.3 s | 0 / 40 | 110 / 150 | 100.0% / 100.0% |
| 31 | `run_97f7d754047a` | W | 26.1 s | 20 / 0 | 155 / 130 | 100.0% / 75.0% |
| 32 | `run_e6ddea3c69ab` | W | 31.8 s | 75 / 0 | 155 / 75 | 100.0% / 75.0% |
| 33 | `run_3aa2c02a45e5` | L | 28.0 s | 0 / 105 | 45 / 150 | 50.0% / 100.0% |
| 34 | `run_522562ce71bf` | L | 49.0 s | 0 / 20 | 180 / 150 | 100.0% / 75.0% |
| 35 | `run_84523d16f552` | W | 32.1 s | 30 / 0 | 160 / 120 | 100.0% / 100.0% |
| 36 | `run_40e3435067d9` | W | 30.5 s | 30 / 0 | 155 / 120 | 100.0% / 100.0% |
| 37 | `run_6c4345ce9de7` | L | 35.5 s | 0 / 70 | 125 / 155 | 100.0% / 75.0% |
| 38 | `run_0254cce26076` | W | 37.2 s | 45 / 0 | 150 / 105 | 100.0% / 100.0% |
| 39 | `run_18cdc302291a` | L | 34.4 s | 0 / 150 | 95 / 150 | 100.0% / 100.0% |
| 40 | `run_18b8a71549f8` | L | 32.0 s | 0 / 115 | 35 / 150 | 100.0% / 100.0% |
| 41 | `run_cdd18b35c96b` | L | 29.0 s | 0 / 40 | 155 / 155 | 100.0% / 80.0% |
| 42 | `run_16ee1fdd3083` | L | 41.4 s | 0 / 65 | 140 / 160 | 100.0% / 100.0% |
| 43 | `run_f82e61a62c89` | W | 30.6 s | 5 / 0 | 215 / 145 | 80.0% / 100.0% |
| 44 | `run_ea1e920a1ce2` | W | 60.4 s | 65 / 0 | 160 / 85 | 100.0% / 100.0% |
| 45 | `run_53f16b3ee88d` | L | 46.8 s | 0 / 50 | 150 / 155 | 100.0% / 80.0% |
| 46 | `run_89f9f3e4735d` | L | 24.2 s | 0 / 60 | 160 / 150 | 100.0% / 100.0% |
| 47 | `run_6fd7886cb8c4` | L | 51.2 s | 0 / 110 | 45 / 150 | 100.0% / 75.0% |
| 48 | `run_3b3217154e6b` | L | 26.8 s | 0 / 70 | 180 / 160 | 100.0% / 100.0% |
| 49 | `run_b114589c1261` | W | 25.1 s | 45 / 0 | 155 / 105 | 100.0% / 100.0% |
| 50 | `run_530292fedea5` | W | 32.2 s | 45 / 0 | 155 / 105 | 100.0% / 75.0% |

## Data sources and calculation notes

- Match outcomes, timing, health, damage, shots, and hits: each round's `summary.json`.
- Confirmed resource pickups and first-hit timing: explicit records in each round's `events.jsonl`.
- Route attempts, route errors, movement, stale extensions, and stall wakeups: each round's `analysis_summary.json` and `stats.json`.
- Jev actions, candidates, confidence, latency, usage, cost, plan submissions, and local deduplication: `benchmarks/results/run_ebaaf822f3ff/jev_player_1.jsonl`, filtered to this session's 50 run IDs.
- GPT model identity, reasoning level, token usage, and API-equivalent costs: cumulative `token_count` events from the two correlated dedicated Codex rollout logs.
- GPT gameplay-plan cost: sum of unique `last_token_usage` records associated with 142 model turns that directly emitted `set_participant_plan` calls; the initial tool-discovery request was excluded.
- GPT API-equivalent cost: uncached input, cached input, and output totals multiplied by the published [GPT-5.6 Sol pricing](https://developers.openai.com/api/docs/models/gpt-5.6-sol).
- Percentiles use the nearest-rank method.
- Decisions per minute divide decision counts by summed in-match combat duration.
- Accuracy is total registered hits divided by total registered shots, not the unweighted mean of per-round percentages.
- The 95% win-rate interval uses the Wilson score method; the reported `p` value is a two-sided exact binomial test against a 50% win probability.
