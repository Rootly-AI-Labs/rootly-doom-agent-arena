# Jev vs Astra — two completed 25-round series

Analyzed 2026-09-27. Scope: the two archived sessions in this folder; 50 completed rounds. The separate 1–0 example/animation session is **not** included.

## Executive summary

- Astra-side agents won **33/50 (66%)**; Jev won **17/50 (34%)**. No draws or timeouts: all rounds ended by elimination.
- Jev produced **416 successful recorded decisions**, averaging **317.2 ms** API response time across both series.
- Jev's reported cost for those successful decisions was **$0.08936831**, approximately **8.94 cents**. This is not a full billing reconciliation.
- Astra's arena records do **not** contain billable model token usage or provider inference time. No defensible Astra dollar cost or isolated inference-speed ratio can be calculated from these artifacts.
- Jev's most selected family was `continue_current` (149 picks), followed by `seek_shotgun` (75), `pursue_visible` (67), and `seek_health` (64).
- The first successful Jev decision targeted **F17 in every round**. In the newer series, both shotguns were offered and F17's route was longer (31 versus 25 cells) in all 25 opening decisions.
- This is an **agent-system comparison**: Jev selects generated legal routes; Astra writes routes. It is not an isolated model-reasoning comparison.

## 1. Sessions, identities and outcomes

| Metric | Series A: earlier | Series B: latest |
|---|---|---|
| Session | [session_dd69bb035d69](./session_dd69bb035d69/) | [session_bf09ee65286b](./session_bf09ee65286b/) |
| Jev seat | Player 1 | Player 2 |
| Astra-side seat | Player 2 | Player 1 |
| Jev wins | 7/25 (28%) | 10/25 (40%) |
| Astra-side wins | 18/25 (72%) | 15/25 (60%) |
| Mean game duration | 17.54 s | 39.35 s |
| Successful Jev decisions | 145 | 271 |
| Rounds with Jev decision coverage | 25/25 | 25/25 |
| Seed | 42 throughout | 42 throughout |

Identity caveat: Series A's opponent is recorded as **“Litigious Lasagna, Undetected assistant, Model unavailable.”** Calling it Astra follows the user's series identification, not verified model metadata. Series B explicitly records **“Manager Goose, Codex, gpt-6-astra medium.”**

Jev's decision records consistently identify `typesafe/jev-1.13-20260917`, `jev_only`, `flat_v3`. Both series log the same candidate-generator hash:

```text
19892a65ee6bb8bc449673e0b696e02ffe67a380758c9bf7af55f8efe17c87d3
```

The seat swap is useful, but the 12-percentage-point Jev win-rate difference is **not evidence of a model improvement or a causal seat effect**: different opponent sessions, sequential rounds and fixed seed confound that interpretation. One map/seed is not a diverse benchmark.

## 2. Cost and token usage

| Recorded Jev usage | Series A | Series B | Combined |
|---|---:|---:|---:|
| Successful decision records with cost | 145/145 | 271/271 | 416/416 |
| Reported cost (USD) | $0.03071481 | $0.05865350 | $0.08936831 |
| Mean cost per decision | $0.00021183 | $0.00021643 | $0.00021483 |
| Mean recorded cost per round | $0.00122859 | $0.00234614 | $0.00178737 |
| Input tokens | 731,305 | 1,396,512 | 2,127,817 |
| Output tokens | 39,255 | 74,212 | 113,467 |

Costs are sums of `jev_decision.usage.cost`; tokens are the associated reported usage, not estimates from text length. Failed/unrecorded requests, retries without returned usage, host-session costs and infrastructure are not priced here. This table therefore covers **recorded successful decisions**, not guaranteed total spend.

**Astra cost: unavailable.** The arena's `token_usage_by_participant` estimates MCP request/response tokens at roughly four characters per token. It excludes system prompts, tool schemas and accumulated context; tool response text is not the model's generated output. Applying an API rate to that proxy would give a misleading dollar estimate.

## 3. Response latency and planning timing

| Metric | Jev A API | Jev B API | Astra A decision proxy | Astra B decision proxy |
|---|---:|---:|---:|---:|
| Samples | 145 | 271 | 72 | 161 |
| Mean | 266.7 ms | 344.2 ms | 7,786.4 ms | 6,082.4 ms |
| Median | 234.0 ms | 225.3 ms | 7,710.5 ms | 5,521.0 ms |
| 95th percentile | 360.0 ms | 1,155.5 ms | 11,608.0 ms | 9,266.0 ms |
| Minimum | 187.0 ms | 187.1 ms | 3,766.0 ms | 3,604.0 ms |
| Maximum | 2,328.0 ms | 5,582.9 ms | 15,187.0 ms | 13,341.0 ms |

Jev's mean logged planning duration was **277.0 ms** in A and **355.0 ms** in B. This is the controller's `planning_elapsed_ms` around its evaluation routine, not movement completion or the entire observation-to-action pipeline.

Timing definitions:

- **Jev API latency:** elapsed request/response time measured around the adapter's send call; includes network/provider overhead, not isolated inference compute.
- **Astra decision proxy:** the arena's `inferred_decision_turns.inferred_decision_latency_ms`, filtered to Astra's participant. Measures observation completion to the next intent request; includes client orchestration and any intervening delay. It is not model-only inference and can include subsequently rejected submissions.
- MCP tool latency is **not** used as Astra inference latency.
- All means are weighted by individual recorded decisions/turns, not means of round means. P95 uses nearest rank.

The latest Jev series has a slightly lower median but a higher mean and much higher P95: **tail delays**, rather than a uniform slowdown, explain the difference. Its maximum recorded API response was **5.583 seconds**. Successful-call measurements exclude attempts without a completed decision record.

## 4. What Jev was offered versus what it selected

Each successful decision in both series had **exactly 20 concrete candidates**. These were not a fixed list across the match: destination, route, policy and available families depended on the observed state and deterministic generator.

“Offered” below counts successful decision calls containing at least one candidate from that family, once per call. Multiple destinations do not multiply that denominator. “Selected” counts model selections, not completed routes or successful pickups. Fallbacks are excluded.

| Family | A offered | A selected | B offered | B selected | Combined selected | Share of all picks | Selected when offered |
|---|---:|---:|---:|---:|---:|---:|---:|
| `continue_current` | 107 | 61 | 174 | 88 | 149 | 35.8% | 53.0% |
| `seek_shotgun` | 54 | 34 | 51 | 41 | 75 | 18.0% | 71.4% |
| `pursue_visible` | 31 | 30 | 39 | 37 | 67 | 16.1% | 95.7% |
| `seek_health` | 145 | 6 | 270 | 58 | 64 | 15.4% | 15.4% |
| `hold_position` | 145 | 1 | 271 | 28 | 29 | 7.0% | 7.0% |
| `investigate_last_seen` | 15 | 8 | 23 | 12 | 20 | 4.8% | 52.6% |
| `pickup_then_move` | 145 | 1 | 270 | 3 | 4 | 1.0% | 1.0% |
| `explore_unvisited` | 144 | 2 | 251 | 2 | 4 | 1.0% | 1.0% |
| `move_to_cover` | 61 | 0 | 101 | 2 | 2 | 0.5% | 1.2% |
| `sweep_region` | 145 | 1 | 244 | 0 | 1 | 0.2% | 0.3% |
| `alternate_approach` | 145 | 1 | 271 | 0 | 1 | 0.2% | 0.2% |
| `recheck_region` | 2 | 0 | 4 | 0 | 0 | 0.0% | 0.0% |
| `increase_distance` | 42 | 0 | 35 | 0 | 0 | 0.0% | 0.0% |
| `move_to_position` | 0 | 0 | 0 | 0 | 0 | 0.0% | — |

Important distinctions:

- `move_to_position` was **never offered** in a successful decision. Its zero selections cannot be attributed to Jev's preferences.
- `move_to_cover` was offered in 162 calls but selected only twice; `increase_distance` was offered 77 times and never selected.
- `pursue_visible` was selected **67/70 times offered (95.7%)**. It was usually unavailable, rather than frequently rejected.
- `sweep_region` was offered 389 times but selected once; `alternate_approach` was offered in every successful call but selected once.
- Conditional selection rates describe preferences **among the actual competing candidates and states**. They are not controlled measures of standalone action quality.

### Mean API latency grouped by selected family

These are timings for the entire decision call, grouped by the eventual choice—not separate evaluations of each candidate.

| Family | A mean (ms) | B mean (ms) |
|---|---:|---:|
| `continue_current` | 290.2 | 408.0 |
| `seek_shotgun` | 249.9 | 274.5 |
| `pursue_visible` | 271.8 | 258.5 |
| `seek_health` | 219.0 | 301.5 |
| `hold_position` | 250.0 | 459.0 |
| `investigate_last_seen` | 209.0 | 391.6 |
| `pickup_then_move` | 266.0 | 220.2 |
| `explore_unvisited` | 188.0 | 214.3 |
| `move_to_cover` | — | 215.7 |
| `sweep_region` | 250.0 | — |
| `alternate_approach` | 188.0 | — |
| `recheck_region` | — | — |
| `increase_distance` | — | — |
| `move_to_position` | — | — |

### Actual firing-policy exposure

Across **8,320 offered candidate slots** in successful decisions:

| Policy | A slots | B slots | Combined selections |
|---|---:|---:|---:|
| `engage_if_visible` | 2754 | 5146 | 387 |
| `hold_fire` | 146 | 272 | 29 |
| `avoid_until_target` | 0 | 1 | 0 |
| `force_fight` | 0 | 1 | 0 |

The advertised alternative firing policies were almost absent from the actual menus. The family-first, 20-candidate budget leaves little room for policy variants. Do not describe these matches as a balanced test of firing-policy choice.

## 5. Shotgun behavior and other notable findings

### A persistent F17 preference, including the farther shotgun

The **first successful Jev selection** was `seek_shotgun:F17` in all 50 rounds; “first successful” matters because fallback activity can precede it.

- Series A: F17 was the shorter offered shotgun route (25 cells vs R17's 31). Both shotgun candidates appeared in 24 of the 25 first-successful-decision menus.
- Series B: both shotguns appeared in all 25 first-successful-decision menus. Jev still chose **F17, 31 cells**, instead of **R17, 25 cells**.
- This is strong evidence of repeated destination preference, **not evidence of why**. Possible menu-order, label, geometry or state-interpretation effects require controlled tests. The logs contain choices/probabilities, not an explanatory rationale.

The series-wide direct shotgun-family counts were:

| Target | A picks | B picks | Total |
|---|---:|---:|---:|
| F17 | 31 | 33 | 64 |
| R17 | 3 | 8 | 11 |

These counts exclude `continue_current` and compound routes that might also reach a shotgun. They are **not pickup counts**.

### First shotgun possession correlates with winning, but is not sufficient

| Series | Jev first / wins in those rounds | Astra first / wins in those rounds |
|---|---|---|
| A | 2 / 2 | 23 / 18 |
| B | 15 / 8 | 10 / 8 |

The first shotgun collector won **36/50 rounds (72%)**. In the newer series Jev got the first shotgun in 15 rounds but won only 8 of those. Acquiring the weapon alone does not explain the outcome; this is observational correlation, not proof of causation.

### More health seeking and holding in the newer series

- `seek_health`: 6/145 picks (**4.1%**) in A vs 58/271 (**21.4%**) in B.
- `hold_position`: 1/145 (**0.7%**) vs 28/271 (**10.3%**).
- `continue_current`: 61/145 (**42.1%**) vs 88/271 (**32.5%**).
- B's mean round length was **39.35 s**, versus **17.54 s** in A. More decisions and higher total cost partly reflect more gameplay, not merely a different per-call cost.
- Holding uses `hold_fire` in these selected candidates. Counts alone cannot establish whether each hold was reasonable or harmful.

## 6. Controller assistance, failures and logging coverage

| Item | A | B |
|---|---:|---:|
| Candidate-menu records | 173 | 307 |
| Successful Jev decisions | 145 | 271 |
| Menu records without a successful decision count counterpart | 28 | 36 |
| Jev-sourced plan-submission events | 113 | 218 |
| Deterministic-fallback plan-submission events | 18 | 37 |
| Astra route submissions | 73 | 162 |
| Astra explicitly rejected route submissions | 12 | 15 |

The 64-record difference between menu and successful-decision totals is **not an API error rate**: incomplete, interrupted or failed evaluations need event-level investigation. Likewise, fallback submissions may not map one-to-one to missing decisions. Recorded costs/latencies do not cover those attempts.

There were **55 deterministic-fallback submissions** across the two series. These are controller actions, not Jev model selections. A successful decision is not necessarily a new submitted or completed route: deduplication, continuation and supersession separate those stages.

Astra's 27 rejected routes were 24 diagonal-segment errors, 2 blocked-cell crossings and 1 no-op route. Jev receives generated routes, whereas Astra bears route-construction/validation risk. This is a substantive assistance difference, not just different wording of the options.

The menu audit records **87,125 candidate-budget omissions** and **13,870 duplicate-route-policy omissions** across 480 menu evaluations. These are repeated candidate instances, including policy variants—not unique actions. Other omissions exist with different/missing `omission_reason` fields and are not classified here. A family can disappear through generation, deduplication or budget selection; absence is not model rejection.

## 7. What to test next

1. **Freeze the current generator and prompts before fresh trials.** Record exact model/harness identities for both sides and randomize seeds with paired seat swaps.
2. **Test the F17 preference without changing game facts:** counterbalance candidate order, use neutral destination labels, and compare selections on identical saved observations. Do not force the nearer shotgun; measure whether the preference survives.
3. **Audit candidate availability:** investigate why `move_to_position` never survives to a successful menu and why alternate firing policies almost never appear.
4. **Separate model decisions, fallbacks, route submissions and completed movement** in benchmark charts. Report failed-call timings and usage if available.
5. **Collect real Astra provider/session usage and inference timing** before publishing cost or model-speed ratios. Keep observation-to-intent latency as a separately labeled agent-system metric.
6. Keep the current “Astra authors routes / Jev selects routes” comparison as an agent-system benchmark. A separate same-menu condition would isolate selection quality more cleanly.

## 8. Per-round audit

Costs below are successful Jev decision costs only. Winner labels in A retain the identity caveat above.

### Series A — session_dd69bb035d69

| Round | Run | Winner | Game seconds | Jev decisions | Jev cost (USD) |
|---|---|---|---:|---:|---:|
| 1 | [run_ed3720a5bca3](./session_dd69bb035d69/round_01_run_ed3720a5bca3/summary.json) | Jev | 37.8 | 6 | $0.00128419 |
| 2 | [run_19a512caa5ee](./session_dd69bb035d69/round_02_run_19a512caa5ee/summary.json) | Jev | 41.8 | 9 | $0.00193809 |
| 3 | [run_8f193d66a52e](./session_dd69bb035d69/round_03_run_8f193d66a52e/summary.json) | Jev | 33.4 | 10 | $0.00214150 |
| 4 | [run_247c82f32c5e](./session_dd69bb035d69/round_04_run_247c82f32c5e/summary.json) | Jev | 14.4 | 9 | $0.00192410 |
| 5 | [run_93ae93fd32e1](./session_dd69bb035d69/round_05_run_93ae93fd32e1/summary.json) | Astra | 10.2 | 2 | $0.00041139 |
| 6 | [run_498301f476d0](./session_dd69bb035d69/round_06_run_498301f476d0/summary.json) | Astra | 13.8 | 2 | $0.00042025 |
| 7 | [run_3f01589bf574](./session_dd69bb035d69/round_07_run_3f01589bf574/summary.json) | Astra | 10.9 | 4 | $0.00084798 |
| 8 | [run_5c9e3a15a839](./session_dd69bb035d69/round_08_run_5c9e3a15a839/summary.json) | Astra | 10.4 | 4 | $0.00084790 |
| 9 | [run_18e0b90d12ba](./session_dd69bb035d69/round_09_run_18e0b90d12ba/summary.json) | Astra | 13.1 | 4 | $0.00082887 |
| 10 | [run_05a1aa015acc](./session_dd69bb035d69/round_10_run_05a1aa015acc/summary.json) | Astra | 12.3 | 7 | $0.00148147 |
| 11 | [run_ab3df2e7ca45](./session_dd69bb035d69/round_11_run_ab3df2e7ca45/summary.json) | Astra | 10.5 | 4 | $0.00084181 |
| 12 | [run_7f8ba7495ee3](./session_dd69bb035d69/round_12_run_7f8ba7495ee3/summary.json) | Jev | 12.3 | 5 | $0.00106310 |
| 13 | [run_4b8aca0fd544](./session_dd69bb035d69/round_13_run_4b8aca0fd544/summary.json) | Astra | 20.8 | 7 | $0.00147462 |
| 14 | [run_c03fa383db5e](./session_dd69bb035d69/round_14_run_c03fa383db5e/summary.json) | Jev | 11.5 | 5 | $0.00105067 |
| 15 | [run_4c8beff7a4e6](./session_dd69bb035d69/round_15_run_4c8beff7a4e6/summary.json) | Astra | 8.9 | 2 | $0.00040715 |
| 16 | [run_21e03c68dc6c](./session_dd69bb035d69/round_16_run_21e03c68dc6c/summary.json) | Astra | 9.4 | 5 | $0.00104534 |
| 17 | [run_e207f7f5d133](./session_dd69bb035d69/round_17_run_e207f7f5d133/summary.json) | Astra | 23.3 | 10 | $0.00213683 |
| 18 | [run_609448337e10](./session_dd69bb035d69/round_18_run_609448337e10/summary.json) | Astra | 11.1 | 4 | $0.00083609 |
| 19 | [run_0942a2db5ee8](./session_dd69bb035d69/round_19_run_0942a2db5ee8/summary.json) | Astra | 43.7 | 11 | $0.00234847 |
| 20 | [run_11cfd4f68590](./session_dd69bb035d69/round_20_run_11cfd4f68590/summary.json) | Astra | 22.6 | 6 | $0.00125488 |
| 21 | [run_baba0fb90ee9](./session_dd69bb035d69/round_21_run_baba0fb90ee9/summary.json) | Astra | 10.0 | 5 | $0.00105244 |
| 22 | [run_b51aa12bf89c](./session_dd69bb035d69/round_22_run_b51aa12bf89c/summary.json) | Astra | 10.9 | 5 | $0.00105983 |
| 23 | [run_b230003dac2f](./session_dd69bb035d69/round_23_run_b230003dac2f/summary.json) | Astra | 22.9 | 8 | $0.00170163 |
| 24 | [run_0225240f218c](./session_dd69bb035d69/round_24_run_0225240f218c/summary.json) | Astra | 11.0 | 4 | $0.00083278 |
| 25 | [run_cffe5fd21846](./session_dd69bb035d69/round_25_run_cffe5fd21846/summary.json) | Jev | 11.6 | 7 | $0.00148344 |

### Series B — session_bf09ee65286b

| Round | Run | Winner | Game seconds | Jev decisions | Jev cost (USD) |
|---|---|---|---:|---:|---:|
| 1 | [run_01e480676ba1](./session_bf09ee65286b/round_01_run_01e480676ba1/summary.json) | Jev | 50.6 | 9 | $0.00196913 |
| 2 | [run_849cbb541401](./session_bf09ee65286b/round_02_run_849cbb541401/summary.json) | Astra | 60.0 | 12 | $0.00264802 |
| 3 | [run_9bbb4538f2aa](./session_bf09ee65286b/round_03_run_9bbb4538f2aa/summary.json) | Jev | 17.0 | 5 | $0.00108709 |
| 4 | [run_4a1f2d54783d](./session_bf09ee65286b/round_04_run_4a1f2d54783d/summary.json) | Jev | 50.2 | 10 | $0.00216182 |
| 5 | [run_4daec0257151](./session_bf09ee65286b/round_05_run_4daec0257151/summary.json) | Jev | 29.3 | 5 | $0.00105928 |
| 6 | [run_b1c64764481d](./session_bf09ee65286b/round_06_run_b1c64764481d/summary.json) | Astra | 38.4 | 7 | $0.00150856 |
| 7 | [run_91ce908eab7b](./session_bf09ee65286b/round_07_run_91ce908eab7b/summary.json) | Astra | 60.8 | 16 | $0.00345568 |
| 8 | [run_622be8daec8a](./session_bf09ee65286b/round_08_run_622be8daec8a/summary.json) | Jev | 44.6 | 11 | $0.00237317 |
| 9 | [run_ea1ab450e7a3](./session_bf09ee65286b/round_09_run_ea1ab450e7a3/summary.json) | Astra | 29.9 | 8 | $0.00169172 |
| 10 | [run_8fd96e994d14](./session_bf09ee65286b/round_10_run_8fd96e994d14/summary.json) | Astra | 24.1 | 9 | $0.00193872 |
| 11 | [run_952a0e270032](./session_bf09ee65286b/round_11_run_952a0e270032/summary.json) | Astra | 19.8 | 6 | $0.00128192 |
| 12 | [run_8da2b092196c](./session_bf09ee65286b/round_12_run_8da2b092196c/summary.json) | Jev | 58.2 | 16 | $0.00342262 |
| 13 | [run_1a1aea5c907c](./session_bf09ee65286b/round_13_run_1a1aea5c907c/summary.json) | Jev | 41.7 | 15 | $0.00326894 |
| 14 | [run_ba848ce30672](./session_bf09ee65286b/round_14_run_ba848ce30672/summary.json) | Astra | 66.9 | 19 | $0.00416006 |
| 15 | [run_4a7999956c80](./session_bf09ee65286b/round_15_run_4a7999956c80/summary.json) | Jev | 18.3 | 6 | $0.00128415 |
| 16 | [run_6b82b2a8d335](./session_bf09ee65286b/round_16_run_6b82b2a8d335/summary.json) | Jev | 33.7 | 9 | $0.00194351 |
| 17 | [run_3eb392d9a20b](./session_bf09ee65286b/round_17_run_3eb392d9a20b/summary.json) | Astra | 45.4 | 17 | $0.00375640 |
| 18 | [run_1682ac925e07](./session_bf09ee65286b/round_18_run_1682ac925e07/summary.json) | Astra | 39.0 | 14 | $0.00304836 |
| 19 | [run_1d64280d65c5](./session_bf09ee65286b/round_19_run_1d64280d65c5/summary.json) | Jev | 32.3 | 14 | $0.00305781 |
| 20 | [run_dff824437840](./session_bf09ee65286b/round_20_run_dff824437840/summary.json) | Astra | 29.7 | 11 | $0.00234952 |
| 21 | [run_74c979681ee7](./session_bf09ee65286b/round_21_run_74c979681ee7/summary.json) | Astra | 30.5 | 12 | $0.00258594 |
| 22 | [run_90692400f6cd](./session_bf09ee65286b/round_22_run_90692400f6cd/summary.json) | Astra | 34.9 | 8 | $0.00170869 |
| 23 | [run_427fc248f702](./session_bf09ee65286b/round_23_run_427fc248f702/summary.json) | Astra | 31.4 | 8 | $0.00171545 |
| 24 | [run_7098c4f3bc7b](./session_bf09ee65286b/round_24_run_7098c4f3bc7b/summary.json) | Astra | 52.3 | 13 | $0.00282849 |
| 25 | [run_7eaa11cfb387](./session_bf09ee65286b/round_25_run_7eaa11cfb387/summary.json) | Astra | 44.7 | 11 | $0.00234847 |

## Sources and calculation notes

- Round `summary.json`: winner, participant identity labels, seed, duration and terminal reason.
- Round `analysis_summary.json`: first-shotgun collector. These summaries are derived from the round event logs.
- Round `stats.json`: participant-filtered `inferred_decision_turns`; its own note explicitly distinguishes tool latency from model think time.
- Round `decision_trace.jsonl`: Astra route submissions and explicit acceptance/rejection.
- [Series A Jev telemetry](../run_ec559633587c/jev_player_1.jsonl).
- [Series B Jev telemetry](../run_01e480676ba1/jev_player_2.jsonl).
- Telemetry was joined using **event run IDs**, not parent directory names. Successful decisions were deduplicated by `(run_id, decision_id)`. Both series have successful decision coverage in all 25 rounds.
- Offered/selected tables use only the candidate lists attached to successful `jev_decision` events; audit-menu totals include additional attempts. Missing fields are not treated as measured zero costs or latencies.
- The two moved session folders do **not** contain their external Jev JSONL telemetry. Keep those linked files when packaging or sharing this analysis.
- Reproduction helper: [analyze_series.py](../../../../jev-astra-video-demo/analyze_series.py), with machine-readable output [series-analysis-metrics.json](../../../../jev-astra-video-demo/series-analysis-metrics.json).
- No new matches were run, no model prompts/generator behavior changed, and no provider price assumptions were applied to Astra.
