# Doom Arena official model benchmark analysis

## Executive summary

- Official dataset: 120 matches across 12 directed folders and 4 models.
- Top score: gpt-5.5 with 66.667% score using draw = 0.5.
- Total public route plans analyzed: 2223.
- Model thinking is analyzed only from public `objective`, `reasoning`, `plan_note`, and route fields. Hidden chain-of-thought is not available or claimed.
- Decision latency is reported separately from local MCP/server latency.

## Data quality

- Official folders found: 12/12.
- Round counts by folder: `{"player1-gpt-5-3-codex-spark__player2-gpt-5-4": 10, "player1-gpt-5-3-codex-spark__player2-gpt-5-4-mini": 10, "player1-gpt-5-3-codex-spark__player2-gpt-5-5": 10, "player1-gpt-5-4-mini__player2-gpt-5-3-codex-spark": 10, "player1-gpt-5-4-mini__player2-gpt-5-4": 10, "player1-gpt-5-4-mini__player2-gpt-5-5": 10, "player1-gpt-5-4__player2-gpt-5-3-codex-spark": 10, "player1-gpt-5-4__player2-gpt-5-4-mini": 10, "player1-gpt-5-4__player2-gpt-5-5": 10, "player1-gpt-5-5__player2-gpt-5-3-codex-spark": 10, "player1-gpt-5-5__player2-gpt-5-4": 10, "player1-gpt-5-5__player2-gpt-5-4-mini": 10}`.
- Missing folders: `[]`.
- Missing `analysis_summary.json`: `[]`.
- Missing `stats.json`: `[]`.
- `benchmarks/results/legacy/` was explicitly excluded.
- The thought-process map uses a local bag-of-words/SVD projection, not an external embedding API.

## Overall leaderboard

| label | total_matches | wins | losses | draws | score_pct | avg_damage_diff | avg_decision_latency_ms | mcp_error_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gpt-5.5 | 60 | 38 | 18 | 4 | 66.667 | 22.5 | 6884.967 | 0.01451 |
| gpt-5.4 | 60 | 25 | 22 | 13 | 52.5 | 13.917 | 8063.274 | 0.00838 |
| gpt-5.3-codex-spark | 60 | 17 | 27 | 16 | 41.667 | -15.917 | 6601.702 | 0.00633 |
| gpt-5.4-mini | 60 | 19 | 32 | 9 | 39.167 | -20.5 | 11776.196 | 0.0231 |


## Head-to-head results

Final model-vs-model results combine both POV directions. Directed folders are used only for side-bias diagnostics.

| model | opponent | matches | wins | losses | draws | score_pct | damage_diff_total | binomial_p_excluding_draws |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gpt-5-3-codex-spark | gpt-5-4 | 20 | 8 | 4 | 8 | 60.0 | 25.0 | 0.3877 |
| gpt-5-3-codex-spark | gpt-5-4-mini | 20 | 1 | 12 | 7 | 22.5 | -925.0 | 0.00342 |
| gpt-5-3-codex-spark | gpt-5-5 | 20 | 8 | 11 | 1 | 42.5 | -55.0 | 0.64761 |
| gpt-5-4 | gpt-5-3-codex-spark | 20 | 4 | 8 | 8 | 40.0 | -25.0 | 0.3877 |
| gpt-5-4 | gpt-5-4-mini | 20 | 15 | 3 | 2 | 80.0 | 1190.0 | 0.00754 |
| gpt-5-4 | gpt-5-5 | 20 | 6 | 11 | 3 | 37.5 | -330.0 | 0.33231 |
| gpt-5-4-mini | gpt-5-3-codex-spark | 20 | 12 | 1 | 7 | 77.5 | 925.0 | 0.00342 |
| gpt-5-4-mini | gpt-5-4 | 20 | 3 | 15 | 2 | 20.0 | -1190.0 | 0.00754 |
| gpt-5-4-mini | gpt-5-5 | 20 | 4 | 16 | 0 | 20.0 | -965.0 | 0.01182 |
| gpt-5-5 | gpt-5-3-codex-spark | 20 | 11 | 8 | 1 | 57.5 | 55.0 | 0.64761 |
| gpt-5-5 | gpt-5-4 | 20 | 11 | 6 | 3 | 62.5 | 330.0 | 0.33231 |
| gpt-5-5 | gpt-5-4-mini | 20 | 16 | 4 | 0 | 80.0 | 965.0 | 0.01182 |


## Directed POV and side-bias notes

| folder | player_1_wins | player_2_wins | draws | player_1_avg_damage | player_2_avg_damage |
| --- | --- | --- | --- | --- | --- |
| player1-gpt-5-5__player2-gpt-5-4 | 5 | 2 | 3 | 76.5 | 61.0 |
| player1-gpt-5-4__player2-gpt-5-5 | 4 | 6 | 0 | 126.5 | 144.0 |
| player1-gpt-5-5__player2-gpt-5-4-mini | 7 | 3 | 0 | 132.5 | 76.0 |
| player1-gpt-5-4-mini__player2-gpt-5-5 | 1 | 9 | 0 | 113.0 | 153.0 |
| player1-gpt-5-5__player2-gpt-5-3-codex-spark | 6 | 4 | 0 | 120.5 | 101.5 |
| player1-gpt-5-3-codex-spark__player2-gpt-5-5 | 4 | 5 | 1 | 119.5 | 106.0 |
| player1-gpt-5-4__player2-gpt-5-4-mini | 8 | 0 | 2 | 143.0 | 36.0 |
| player1-gpt-5-4-mini__player2-gpt-5-4 | 3 | 7 | 0 | 94.0 | 106.0 |
| player1-gpt-5-4__player2-gpt-5-3-codex-spark | 4 | 5 | 1 | 112.0 | 128.5 |
| player1-gpt-5-3-codex-spark__player2-gpt-5-4 | 3 | 0 | 7 | 5.5 | 19.5 |
| player1-gpt-5-4-mini__player2-gpt-5-3-codex-spark | 9 | 1 | 0 | 173.0 | 72.0 |
| player1-gpt-5-3-codex-spark__player2-gpt-5-4-mini | 0 | 3 | 7 | 20.0 | 11.5 |


## Resource control

| model | first_shotgun_pickups | first_health_pickups | total_shotgun_pickups | total_health_pickups | win_rate_when_getting_first_shotgun |
| --- | --- | --- | --- | --- | --- |
| gpt-5-3-codex-spark | 5 | 12 | 21 | 170 | 0.0 |
| gpt-5-4 | 26 | 17 | 852 | 259 | 50.0 |
| gpt-5-4-mini | 10 | 10 | 21 | 44 | 100.0 |
| gpt-5-5 | 15 | 34 | 330 | 973 | 80.0 |


## Route-planning reliability

| model | valid_plans | rejected_plans | invalid_route_rate | waypoint_in_wall_cell | route_diagonal_segment | stuck_recovery_count | avg_unique_cells_visited |
| --- | --- | --- | --- | --- | --- | --- | --- |
| gpt-5-3-codex-spark | 532 | 198 | 0.27123 | 117 | 49 | 550 | 0.0 |
| gpt-5-4 | 416 | 110 | 0.20913 | 80 | 21 | 416 | 0.0 |
| gpt-5-4-mini | 304 | 74 | 0.19577 | 33 | 28 | 304 | 0.0 |
| gpt-5-5 | 456 | 133 | 0.22581 | 99 | 21 | 456 | 0.0 |


## Public model planning behavior

Plans were classified into resource control, engagement/combat, evasion/recovery, and map control/exploration using public plan fields only.

| model | total_plans | resource control_pct | engagement/combat_pct | evasion/recovery_pct | map control/exploration_pct |
| --- | --- | --- | --- | --- | --- |
| gpt-5-3-codex-spark | 730 | 31.918 | 22.055 | 10.685 | 35.342 |
| gpt-5-4 | 526 | 49.43 | 21.483 | 4.943 | 24.144 |
| gpt-5-4-mini | 378 | 42.857 | 30.952 | 5.82 | 20.37 |
| gpt-5-5 | 589 | 64.346 | 19.525 | 5.433 | 10.696 |


## Per-plan timing

| model | plans | decision_mean_ms | decision_median_ms | decision_p95_ms | mcp_mean_ms |
| --- | --- | --- | --- | --- | --- |
| gpt-5-3-codex-spark | 730 | 7496.599 | 5564.5 | 17562.0 | 41.962 |
| gpt-5-4 | 526 | 8683.027 | 6736.5 | 20116.0 | 30.203 |
| gpt-5-4-mini | 378 | 11723.619 | 8672.5 | 25800.0 | 36.929 |
| gpt-5-5 | 589 | 7620.219 | 5590.0 | 19301.0 | 26.389 |


## Selected plan-note examples

| model | round | objective | reasoning | plan_note | outcome | why_it_matters |
| --- | --- | --- | --- | --- | --- | --- |
| gpt-5-5 | 4 | hold long right lane | lead and health secured | Hold/patrol G24-L26, avoid deeper Q/T contact unless firing at range. | win | resource-aware plan |
| gpt-5-5 | 6 | upper lane timer patrol | avoid risky contact | Keep full health; no lower lane exposure. | draw | resource-aware plan |
| gpt-5-5 | 7 | take right health lane | controlled east position | Set up around G26 health and avoid deep Q24 unless contact is favorable. | win | resource-aware plan |
| gpt-5-5 | 6 | fall back after damage | avoid upper duel trap | Damage landed; fall back to Q26 health lane while firing if visible. | win | resource-aware plan |
| gpt-5-5 | 8 | return to Q26 hold | no contact, avoid L trap | Return to Q26/O26 health lane before opponent angles L24. | win | resource-aware plan |
| gpt-5-5 | 5 | backtrack from blocked mid | R08 blocked, reset angle | Backtrack through open mid row; avoid exposed T05 until contact is clearer. | win | map-aware rerouting |
| gpt-5-4-mini | 6 | re-enter the contact cell on the east side | Opponent last seen one step east | Single-cell move back to Q26 to force the fight open again. | loss | opponent-aware planning |
| gpt-5-4 | 1 | hold east mid opening | avoid blocked north cells | Hold the open O24-O27 lane and scan for opponent crossing from center. | win | map-aware rerouting |
| gpt-5-4-mini | 4 | take the left health pocket again | reset before the center fight | Use the left pocket as the first safe resource stop, then re-enter the central lanes. | loss | resource-aware plan |
| gpt-5-3-codex-spark | 1 | Get nearest health pickup | Re-route toward visible medkit | Avoid stuck state, descend to G08 health | draw | resource-aware plan |
| gpt-5-3-codex-spark | 10 | continue south toward Q23 contact trail | adjust path to avoid blocked Q15 | shorted Q-column climb | draw | map-aware rerouting |
| gpt-5-5 | 8 | reacquire lower contact | full health, likely lead | Probe back to N26 for line of sight, still avoiding deep Q24 commitment. | win | resource-aware plan |


## Figures

### fig01 overall win rate

![fig01 overall win rate](figures/fig01_overall_win_rate.png)

### fig02 head to head heatmap

![fig02 head to head heatmap](figures/fig02_head_to_head_heatmap.png)

### fig03 side bias

![fig03 side bias](figures/fig03_side_bias.png)

### fig04 match time over rounds

![fig04 match time over rounds](figures/fig04_match_time_over_rounds.png)

### fig05 mcp errors over rounds

![fig05 mcp errors over rounds](figures/fig05_mcp_errors_over_rounds.png)

### fig06 decision latency over rounds

![fig06 decision latency over rounds](figures/fig06_decision_latency_over_rounds.png)

### fig07 mcp latency over rounds

![fig07 mcp latency over rounds](figures/fig07_mcp_latency_over_rounds.png)

### fig07b plan thinking time distribution

![fig07b plan thinking time distribution](figures/fig07b_plan_thinking_time_distribution.png)

### fig07c decision vs mcp latency

![fig07c decision vs mcp latency](figures/fig07c_decision_vs_mcp_latency.png)

### fig08 damage differential

![fig08 damage differential](figures/fig08_damage_differential.png)

### fig09 accuracy combat efficiency

![fig09 accuracy combat efficiency](figures/fig09_accuracy_combat_efficiency.png)

### fig10 resource advantage outcomes

![fig10 resource advantage outcomes](figures/fig10_resource_advantage_outcomes.png)

### fig11 route error distribution

![fig11 route error distribution](figures/fig11_route_error_distribution.png)

### fig12 route cell heatmap

![fig12 route cell heatmap](figures/fig12_route_cell_heatmap.png)

### fig13 opening route diversity

![fig13 opening route diversity](figures/fig13_opening_route_diversity.png)

### fig14 plan note examples

![fig14 plan note examples](figures/fig14_plan_note_examples.png)

### fig15 planning intent distribution

![fig15 planning intent distribution](figures/fig15_planning_intent_distribution.png)

### fig16 planning intent over rounds

![fig16 planning intent over rounds](figures/fig16_planning_intent_over_rounds.png)

### fig17 outcome by planning intent

![fig17 outcome by planning intent](figures/fig17_outcome_by_planning_intent.png)

### fig18 plan quality score by model

![fig18 plan quality score by model](figures/fig18_plan_quality_score_by_model.png)

### fig19 reasoning action alignment

![fig19 reasoning action alignment](figures/fig19_reasoning_action_alignment.png)

### fig20 thought process embedding map

![fig20 thought process embedding map](figures/fig20_thought_process_embedding_map.png)

### fig21 thinking time vs plan quality

![fig21 thinking time vs plan quality](figures/fig21_thinking_time_vs_plan_quality.png)

### fig22 opening strategy flow

![fig22 opening strategy flow](figures/fig22_opening_strategy_flow.png)

### fig23 model personality radar

![fig23 model personality radar](figures/fig23_model_personality_radar.png)

### fig24 strategy trajectory over rounds

![fig24 strategy trajectory over rounds](figures/fig24_strategy_trajectory_over_rounds.png)

## Skipped figures and limitations

- No required figure was skipped. The embedding map is a local lexical projection because no external embedding service was used.
- Plan quality and intent labels are deterministic heuristics over public plan text and routes. They are useful for comparison but not a substitute for human review.
- Pickup counts come from recorded benchmark summaries; repeated pickup events may reflect engine-level event logging behavior.

## Completion audit

- `analysis.md` exists and summarizes the benchmark.
- Required tables were saved under `tables/` and key tables are embedded above.
- Required figures were saved under `figures/` and referenced above.
- Legacy results were excluded.
- Final model comparisons combine both POV directions.
- Decision latency and MCP/server latency are reported separately.
- Public model planning behavior uses `objective`, `reasoning`, `plan_note`, and route fields only.
