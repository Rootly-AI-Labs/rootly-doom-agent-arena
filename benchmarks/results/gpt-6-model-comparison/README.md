# GPT-6 Model Comparison: Astra, Sol and Luna in Doom

## TL;DR

We benchmarked GPT-6 Astra, Sol and Luna in **60 head-to-head Doom matches**, all at medium reasoning effort.

- **Luna delivered the most wins per dollar.** It won 25% of its matches, but cost about **$0.02 per match**. Across the benchmark, that worked out to **5.6× as many wins per dollar as Sol and 9.8× as many as Astra**.
- **Astra won the most matches:** 33 out of 40 (**82.5%**), at about **$0.63 per match**.
- **Sol made the fastest decisions:** **5.34 seconds** from observation to plan on average. It won **42.5%** of its matches, at about **$0.19 per match**.

The model that wins most often can be different from the one that gives you the most wins for your money. Which matters more depends on what a failed attempt costs you.

**How the matches worked:** Astra played Sol, Astra played Luna, and Sol played Luna. Each pair played 20 matches, swapping player positions after 10. That gives 60 matches total and 40 appearances per model. Every match ended in elimination; there were no draws.

Costs are estimates at Standard API rates for all logged session requests, including losing matches. Wins per dollar means total wins divided by that full-session cost. Decision times include host/orchestration time, not just model inference.

## Leaderboard

| Rank | Model | Win rate | Wins-Losses | Decision speed | Accuracy | Damage diff | Win rate / cost |
|---|---|---:|---:|---:|---:|---:|---:|
| 1 | GPT-6 Astra | **82.5%** | **33–7** | 6.33 s | **83.2%** | **+86.25** | 0.10× |
| 2 | GPT-6 Sol | 42.5% | 17–23 | **5.34 s** | 57.6% | −24.50 | 0.18× |
| 3 | GPT-6 Luna | 25.0% | 10–30 | 7.57 s | 52.4% | −61.75 | **1.00×** |

Bold values mark the category leader. All three models used medium reasoning, verified from the corresponding Codex rollout contexts.

- **Win rate:** wins divided by matches played. Draw-adjusted scoring would count a draw as half a win; no draws occurred here.
- **Decision speed:** mean time from observation completion to the next plan submission, pooled across individual `stats.json` inferred decision turns. This includes host/orchestration time and is not a direct measurement of model-server inference latency.
- **Accuracy:** total hits divided by total shots fired, rather than the average of per-round percentages.
- **Damage diff:** total damage dealt minus opponent damage dealt, divided by 40 matches.
- **Win rate / cost:** win rate divided by full-session API-equivalent cost, normalized so the best model (Luna) equals 1.00×. Uses unrounded costs of $25.381772 for Astra, $7.4822548 for Sol, and $0.7836947 for Luna. All models played 40 matches. This uses logged usage costs, unlike the older main README's output-token-price metric; the two efficiency columns are not directly comparable.
- **Cost:** standard-rate API-equivalent estimates from logged model usage across each model's 40 matches. Plan inference includes requests that emitted a plan submission; full session includes all recorded requests. These are not Codex subscription charges. See cost coverage below.

## Head-to-head results

Cells show the row model's wins–losses against the column model, combining both player orientations.

| Model | Astra | Sol | Luna |
|---|---:|---:|---:|
| Astra | — | **18–2** | **15–5** |
| Sol | 2–18 | — | **15–5** |
| Luna | 5–15 | 5–15 | — |

## Combat and decision totals

| Metric | Astra | Sol | Luna |
|---|---:|---:|---:|
| Damage dealt | 6,175 | 3,920 | 3,270 |
| Opponent damage dealt | 2,725 | 4,900 | 5,740 |
| Hits / shots | 178 / 214 | 179 / 311 | 193 / 368 |
| Inferred decision turns | 236 | 211 | 196 |
| Player 1 wins (20 matches) | 19 | 10 | 9 |
| Player 2 wins (20 matches) | 14 | 7 | 1 |

Astra won both head-to-head pairings and led accuracy and damage differential. Sol had the shortest observed decision time, but finished below Astra on wins. Luna's results differed substantially by player side: 45% wins as Player 1 versus 5% as Player 2. Across all models, Player 1 won 38/60 matches (63.3%); the mirrored design balances side exposure, but these totals alone do not establish the cause of the side difference.

## Usage and cost coverage

| Metric | Astra | Sol | Luna |
|---|---:|---:|---:|
| Full-session input tokens | 19,999,523 | 29,505,875 | 62,350,990 |
| Cached input tokens (included above) | 19,635,712 | 29,076,864 | 61,240,320 |
| Uncached input tokens | 363,811 | 429,011 | 1,110,670 |
| Output tokens (including reasoning) | 42,159 | 80,886 | 120,449 |
| Reasoning output tokens (included above) | 1,516 | 16,263 | 68,124 |
| Model requests, full session | 344 | 505 | 581 |
| Plan-producing model requests | 240 | 212 | 205 |
| Plan inference cost | $17.495074 | $3.220645 | $0.287834 |
| Other session requests | $7.886698 | $4.261610 | $0.495861 |
| **Full session cost** | **$25.381772** | **$7.482255** | **$0.783695** |
| Plan inference cost per match | $0.43738 | $0.08052 | $0.00720 |
| Full session cost per match | $0.63454 | $0.18706 | $0.01959 |

Across all 60 matches and both participants: **$21.003552 in plan-producing requests**, plus **$12.644169 in other session requests**, for **$33.647722 total**. Each model's per-match denominator is 40. Luna was cheapest, while Astra had the highest win rate.

### Rates and calculation

Standard USD per million tokens, checked September 22, 2026:

| Model | Uncached input | Cached input | Cache writes | Output |
|---|---:|---:|---:|---:|
| [GPT-6 Astra](https://developers.openai.com/api/docs/models/gpt-6-astra) | $10.00 | $1.00 | $12.50 | $50.00 |
| [GPT-6 Sol](https://developers.openai.com/api/docs/models/gpt-6-sol) | $2.00 | $0.20 | $2.50 | $10.00 |
| [GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna) | $0.10 | $0.01 | $0.125 | $0.50 |

The calculation deduplicates `token_usage_record` events by response ID and reconciles every rollout's token sums to its final cumulative `token_count`. Cost is `(uncached input × input rate + cached input × cache rate + cache-write input × write rate + output × output rate) / 1,000,000`. Reasoning is already included in output and is not charged twice. All logged cache-write counts are zero. No request exceeded the 272,000-input-token long-context threshold; maximum observed input was 227,725.

Service tier was not explicitly recorded in the inspected turn contexts, so these estimates assume Standard pricing. They do not claim to reproduce actual billed charges or any Fast/regional premiums.

Plan attribution uses the request that emitted an actual `set_participant_plan` call, including rejected submissions and retries. The entire request is counted when it batches a plan with another tool. It excludes separate observation/polling/setup/final-response requests, even though those can be necessary for gameplay; the full-session column includes them. It is therefore a narrower comparison, not the complete cost of operating an agent. Plan-request counts differ from arena inferred-decision counts because they measure different events.

| Session | P1 plan cost | P2 plan cost | P1 full cost | P2 full cost |
|---|---:|---:|---:|---:|
| 1 Astra–Sol | $4.242176 | $0.674097 | $6.359000 | $1.557319 |
| 2 Sol–Astra | $0.397815 | $3.290282 | $1.449272 | $5.058956 |
| 3 Astra–Luna | $4.191862 | $0.045267 | $6.561656 | $0.122081 |
| 4 Luna–Astra | $0.107419 | $5.770754 | $0.292143 | $7.402160 |
| 5 Sol–Luna | $1.042104 | $0.070402 | $2.759996 | $0.187542 |
| 6 Luna–Sol | $0.064746 | $1.106629 | $0.181929 | $1.715668 |

Reproduce with `python benchmarks/results/gpt-6-model-comparison/calculate_costs.py` on a machine with the twelve indexed Codex rollouts. [cost_analysis.json](cost_analysis.json) contains per-model and per-session usage and unrounded estimates; [calculate_costs.py](calculate_costs.py) contains the calculation. Neither artifact includes raw prompts or controller tokens.

## Session breakdown

| Setup | Folder | Original session | Player 1 | Player 2 | Completed | P1–P2 wins |
|---|---|---|---|---|---:|---:|
| 1 | [1_astra_sol](1_astra_sol/) | session_5c139c7953d1 | gpt-6-astra | gpt-6-sol | 10/10 | 9–1 |
| 2 | [2_sol_astra](2_sol_astra/) | session_764b53f87e17 | gpt-6-sol | gpt-6-astra | 10/10 | 1–9 |
| 3 | [3_astra_luna](3_astra_luna/) | session_928b0325aae5 | gpt-6-astra | gpt-6-luna | 10/10 | 10–0 |
| 4 | [4_luna_astra](4_luna_astra/) | session_dd0a79c5bab4 | gpt-6-luna | gpt-6-astra | 10/10 | 5–5 |
| 5 | [5_sol_luna](5_sol_luna/) | session_4ada8fbfec4f | gpt-6-sol | gpt-6-luna | 10/10 | 9–1 |
| 6 | [6_luna_sol](6_luna_sol/) | session_616d78af89cc | gpt-6-luna | gpt-6-sol | 10/10 | 4–6 |

Astra won 18 of the 20 completed matches against Sol. No draws; all matches ended in elimination. Each session has ten distinct run IDs, rounds 1–10, positive elapsed time, and matching config/summary run IDs. Original artifact contents and internal session IDs were preserved when the directories were moved.

## Model identity verification

Arena summaries label the assistant/model as undetected or unavailable. The model assignments above were independently verified from the corresponding local Codex rollout `turn_context.model` and player prompt. All twelve rollout contexts recorded medium reasoning.

| Setup/player | Local rollout filename |
|---|---|
| 1/player_1 (Astra) | rollout-2026-09-22T19-15-22-01a0cb67-0880-7b80-ac1f-19857c8eda23.jsonl |
| 1/player_2 (Sol) | rollout-2026-09-22T19-15-23-01a0cb67-0df4-7840-a424-88f391aa8a0b.jsonl |
| 2/player_1 (Sol) | rollout-2026-09-22T19-27-38-01a0cb72-4207-7f83-bace-18d6070c60ff.jsonl |
| 2/player_2 (Astra) | rollout-2026-09-22T19-27-40-01a0cb72-4ac9-7ef1-84ff-1a11e83c5f74.jsonl |
| 3/player_1 (Astra) | rollout-2026-09-22T19-42-27-01a0cb7f-d53b-7e71-85c2-abb556d115d5.jsonl |
| 3/player_2 (Luna) | rollout-2026-09-22T19-42-29-01a0cb7f-dcd1-7cf3-b40f-4c04c1d6b396.jsonl |
| 4/player_1 (Luna) | rollout-2026-09-22T19-56-36-01a0cb8c-ca55-7132-8f31-1b0b32c96909.jsonl |
| 4/player_2 (Astra) | rollout-2026-09-22T19-56-40-01a0cb8c-da54-7530-aac2-5b51e006d4a2.jsonl |
| 5/player_1 (Sol) | rollout-2026-09-22T20-53-00-01a0cbc0-6b10-77d3-a2d9-dff2d9d48f0b.jsonl |
| 5/player_2 (Luna) | rollout-2026-09-22T20-53-06-01a0cbc0-835d-7eb2-a0db-080a1f698fe5.jsonl |
| 6/player_1 (Luna) | rollout-2026-09-22T21-21-22-01a0cbda-63ed-7c00-9fb5-60980514d779.jsonl |
| 6/player_2 (Sol) | rollout-2026-09-22T21-21-19-01a0cbda-58f9-7261-87c1-a4c1536768c5.jsonl |

## Coverage and reproducibility

All 60 planned matches are complete, with 60 unique run IDs. Every match ended in elimination; there were no draws. Each model played 40 matches, equally split between player sides.

Only the six listed completed sessions are included. Earlier partial/restarted attempts remain outside this comparison; their results are not counted in these totals. Outcome and combat metrics come from each round's `summary.json`; decision timing comes from participant-attributed `inferred_decision_turns` in `stats.json`. Averages pool all recorded turns, rather than weighting each round equally. Decision counts reflect available inferred timing records, not necessarily every model request or attempted plan.

Resource pickup counts from `analysis_summary.json` are omitted: sampled records misclassify route text mentioning a shotgun as a pickup. A pickup comparison requires parsing explicit pickup events. A full controller reliability audit remains separate work.
