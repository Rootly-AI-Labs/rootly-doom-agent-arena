# Codex Spark vs GPT-5.5 Doom Arena Benchmark Analysis

Generated from two switched-side benchmark folders:
- `benchmarks\results\player1-codex-spark-player2-gpt-5-5` - Codex Spark as Player 1 vs GPT-5.5 as Player 2
- `benchmarks\results\player1-gpt-5-5-player2-codex-park` - GPT-5.5 as Player 1 vs Codex Spark as Player 2
- Note: Folder name uses codex-park; analyzed as Codex Spark based on the requested side-swap pair.

## Executive summary

- GPT-5.5 won 19 of 20 decisive matches; Codex Spark won 1. Exact two-sided binomial p=0.0000.
- Player 1 won 11 and Player 2 won 9 of 20 decisive matches. Exact two-sided side-bias p=0.8238.
- Side-assignment interaction Fisher exact p=1.0000 for the 2x2 table of model wins by side assignment.
- The dominant tactical divider was center/shotgun control. The model that reached or contested the shotgun more often usually converted that into higher damage.
- Positioning metrics are more informative than raw shots fired. Repeated side-lane holding can produce many shots but lower damage conversion.
- MCP/tool latency was small compared with inferred chat decision latency. This benchmark mostly measures model decision time and planning quality, not HTTP/tool overhead.

## Figures

- Wins by model: `figures/wins_by_model.svg`
![Wins by model](figures/wins_by_model.svg)

- Wins by side assignment: `figures/wins_by_side_assignment.svg`
![Wins by side assignment](figures/wins_by_side_assignment.svg)

- Core metrics by model: `figures/core_metrics_by_model.svg`
![Core metrics by model](figures/core_metrics_by_model.svg)

- Positioning by model: `figures/positioning_by_model.svg`
![Positioning by model](figures/positioning_by_model.svg)

- Plan objective usage: `figures/plan_objective_usage.svg`
![Plan objective usage](figures/plan_objective_usage.svg)

- Autopilot action usage: `figures/autopilot_action_usage.svg`
![Autopilot action usage](figures/autopilot_action_usage.svg)

- Decision latency by match: `figures/decision_latency_by_match.svg`
![Decision latency by match](figures/decision_latency_by_match.svg)

- MCP errors by match: `figures/mcp_errors_by_match.svg`
![MCP errors by match](figures/mcp_errors_by_match.svg)

- Path density heatmap: `figures/position_heatmap_by_model.svg`
![Path density heatmap](figures/position_heatmap_by_model.svg)

## Aggregate scoreboard

| Model | Rounds | Wins | Losses | Draws | Win rate | Avg damage | Avg damage taken | Accuracy | Shotgun pickups | Avg decision latency | MCP errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Codex Spark | 20 | 1 | 19 | 0 | 5.0% | 67.5 | 151.2 | 62.8% | 1 | 1740.9 ms | 35 |
| GPT-5.5 | 20 | 19 | 1 | 0 | 95.0% | 151.2 | 67.5 | 58.3% | 19 | 5334.8 ms | 20 |

## Side-switch results

| Assignment | GPT-5.5 wins | Codex Spark wins | Draws | Player 1 wins | Player 2 wins |
| --- | --- | --- | --- | --- | --- |
| Codex Spark as Player 1 vs GPT-5.5 as Player 2 | 9 | 1 | 0 | 1 | 9 |
| GPT-5.5 as Player 1 vs Codex Spark as Player 2 | 10 | 0 | 0 | 10 | 0 |

## Statistical read

- Model win test: GPT-5.5 won 19 of 20 decisive matches; Codex Spark won 1. Exact two-sided binomial p=0.0000.
- Side-only win test: Player 1 won 11 and Player 2 won 9 of 20 decisive matches. Exact two-sided side-bias p=0.8238.
- Side-switch interaction: Side-assignment interaction Fisher exact p=1.0000 for the 2x2 table of model wins by side assignment.
- Interpretation: treat these p-values as descriptive because rounds are not fully independent. Agents adapt across rounds, reuse chat context, and share deterministic map structure.

## Positioning and map-control metrics

| Model | Center presence | Shotgun-area presence | Left-wall presence | Right-wall presence | Avg path length | Stuck recoveries |
| --- | --- | --- | --- | --- | --- | --- |
| Codex Spark | 25.5% | 22.0% | 5.9% | 6.2% | 2527.1 | 51 |
| GPT-5.5 | 48.7% | 44.3% | 11.1% | 0.0% | 1790.9 | 24 |

Position definitions:
- Center presence: path samples within 192 Doom units of `(0, 0)`.
- Shotgun-area presence: path samples inside `abs(x)<=96` and `abs(y)<=96`.
- Wall presence: path samples near the left or right vertical wall bands.

## Latency and MCP stability

| Model | Avg inferred decision latency | Avg MCP latency | Plan calls | MCP errors |
| --- | --- | --- | --- | --- |
| Codex Spark | 1740.9 ms | 918.8 ms | 51 | 35 |
| GPT-5.5 | 5334.8 ms | 9.2 ms | 24 | 20 |

Notes:
- Inferred decision latency is now participant-specific: for each successful `set_participant_plan`, it uses that same participant's most recent completed `get_participant_observation`.
- MCP latency and MCP errors are now counted per participant/model instead of duplicated from the round-level summary.
- MCP errors include early round state-file races and post-finish calls. They should be separated from model tactical quality.

## Round-by-round outcomes

| Folder | Round | Winner model | Winner side | Duration | Player 1 damage | Player 2 damage | Player 1 pickups | Player 2 pickups |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| player1-codex-spark-player2-gpt-5-5 | 1 | GPT-5.5 | player_2 | 6.0s | Codex Spark 60 | GPT-5.5 160 | Codex Spark: none | GPT-5.5: 3457ms:shotgun |
| player1-codex-spark-player2-gpt-5-5 | 2 | Codex Spark | player_1 | 8.6s | Codex Spark 150 | GPT-5.5 80 | Codex Spark: 8028ms:shotgun | GPT-5.5: none |
| player1-codex-spark-player2-gpt-5-5 | 3 | GPT-5.5 | player_2 | 5.5s | Codex Spark 50 | GPT-5.5 160 | Codex Spark: none | GPT-5.5: 3457ms:shotgun |
| player1-codex-spark-player2-gpt-5-5 | 4 | GPT-5.5 | player_2 | 7.8s | Codex Spark 90 | GPT-5.5 160 | Codex Spark: none | GPT-5.5: 3457ms:shotgun |
| player1-codex-spark-player2-gpt-5-5 | 5 | GPT-5.5 | player_2 | 5.8s | Codex Spark 65 | GPT-5.5 160 | Codex Spark: none | GPT-5.5: 3457ms:shotgun |
| player1-codex-spark-player2-gpt-5-5 | 6 | GPT-5.5 | player_2 | 14.1s | Codex Spark 60 | GPT-5.5 155 | Codex Spark: none | GPT-5.5: 3457ms:shotgun |
| player1-codex-spark-player2-gpt-5-5 | 7 | GPT-5.5 | player_2 | 7.8s | Codex Spark 70 | GPT-5.5 150 | Codex Spark: none | GPT-5.5: 3457ms:shotgun |
| player1-codex-spark-player2-gpt-5-5 | 8 | GPT-5.5 | player_2 | 7.2s | Codex Spark 50 | GPT-5.5 160 | Codex Spark: none | GPT-5.5: 3457ms:shotgun |
| player1-codex-spark-player2-gpt-5-5 | 9 | GPT-5.5 | player_2 | 8.3s | Codex Spark 60 | GPT-5.5 155 | Codex Spark: none | GPT-5.5: 3457ms:shotgun |
| player1-codex-spark-player2-gpt-5-5 | 10 | GPT-5.5 | player_2 | 8.4s | Codex Spark 90 | GPT-5.5 160 | Codex Spark: none | GPT-5.5: 3457ms:shotgun |
| player1-gpt-5-5-player2-codex-park | 1 | GPT-5.5 | player_1 | 10.8s | GPT-5.5 160 | Codex Spark 65 | GPT-5.5: 3314ms:shotgun | Codex Spark: none |
| player1-gpt-5-5-player2-codex-park | 2 | GPT-5.5 | player_1 | 6.4s | GPT-5.5 155 | Codex Spark 60 | GPT-5.5: 3314ms:shotgun | Codex Spark: none |
| player1-gpt-5-5-player2-codex-park | 3 | GPT-5.5 | player_1 | 6.0s | GPT-5.5 150 | Codex Spark 70 | GPT-5.5: 3314ms:shotgun | Codex Spark: none |
| player1-gpt-5-5-player2-codex-park | 4 | GPT-5.5 | player_1 | 5.8s | GPT-5.5 150 | Codex Spark 60 | GPT-5.5: 3314ms:shotgun | Codex Spark: none |
| player1-gpt-5-5-player2-codex-park | 5 | GPT-5.5 | player_1 | 5.7s | GPT-5.5 150 | Codex Spark 60 | GPT-5.5: 3314ms:shotgun | Codex Spark: none |
| player1-gpt-5-5-player2-codex-park | 6 | GPT-5.5 | player_1 | 7.6s | GPT-5.5 160 | Codex Spark 50 | GPT-5.5: 3314ms:shotgun | Codex Spark: none |
| player1-gpt-5-5-player2-codex-park | 7 | GPT-5.5 | player_1 | 5.2s | GPT-5.5 150 | Codex Spark 60 | GPT-5.5: 3314ms:shotgun | Codex Spark: none |
| player1-gpt-5-5-player2-codex-park | 8 | GPT-5.5 | player_1 | 5.3s | GPT-5.5 150 | Codex Spark 60 | GPT-5.5: 3314ms:shotgun | Codex Spark: none |
| player1-gpt-5-5-player2-codex-park | 9 | GPT-5.5 | player_1 | 6.0s | GPT-5.5 150 | Codex Spark 60 | GPT-5.5: 3314ms:shotgun | Codex Spark: none |
| player1-gpt-5-5-player2-codex-park | 10 | GPT-5.5 | player_1 | 5.1s | GPT-5.5 150 | Codex Spark 60 | GPT-5.5: 3314ms:shotgun | Codex Spark: none |

## Plan objective usage

| Model | Objective | Count |
| --- | --- | --- |
| Codex Spark | pick_up_shotgun | 45 |
| Codex Spark | heal | 4 |
| Codex Spark | force_fight | 2 |
| GPT-5.5 | pick_up_shotgun | 20 |
| GPT-5.5 | force_fight | 3 |
| GPT-5.5 | heal | 1 |

## Autopilot action usage

| Model | Executed action | Count |
| --- | --- | --- |
| Codex Spark | route_waypoint | 133 |
| Codex Spark | route_waypoint+attack | 121 |
| Codex Spark | route_complete | 43 |
| Codex Spark | route_complete+attack | 42 |
| GPT-5.5 | route_waypoint | 128 |
| GPT-5.5 | route_waypoint+attack | 126 |
| GPT-5.5 | route_complete+attack | 115 |
| GPT-5.5 | route_complete | 57 |

## Tactical interpretation

### Codex Spark

- Record: 1-19-0.
- Shotgun pickups: 1 of 20 participant-rounds.
- Average damage: 67.5; average damage taken: 151.2.
- Average center presence: 25.5%; shotgun-area presence: 22.0%.
- Most common objectives: pick_up_shotgun (45), heal (4), force_fight (2).

### GPT-5.5

- Record: 19-1-0.
- Shotgun pickups: 19 of 20 participant-rounds.
- Average damage: 151.2; average damage taken: 67.5.
- Average center presence: 48.7%; shotgun-area presence: 44.3%.
- Most common objectives: pick_up_shotgun (20), force_fight (3), heal (1).

## Appendix: full plan, intent, route, and reasoning list

This table lists every successful `set_participant_plan` call found in the two benchmark folders. `intent` is the expanded Doom-side intent generated from the coordinate plan.

| Folder | Round | Model | Side | Seq | Intent | Objective | Engagement | Route cells | Reasoning |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| player1-codex-spark-player2-gpt-5-5 | 1 | Codex Spark | player_1 | 1 | search | pick_up_shotgun | engage_if_visible | G02;G17;M17 | taking the center shotgun first while keeping route clear of blocked cells |
| player1-codex-spark-player2-gpt-5-5 | 1 | Codex Spark | player_1 | 2 | search | pick_up_shotgun | engage_if_visible | H17;M17 | close to center pickup, so tighten approach to shotgun while keeping pressure |
| player1-codex-spark-player2-gpt-5-5 | 1 | GPT-5.5 | player_2 | 1 | search | pick_up_shotgun | engage_if_visible | R31;R17;M17 | route around the right pillar to take center weapon safely |
| player1-codex-spark-player2-gpt-5-5 | 2 | Codex Spark | player_1 | 1 | search | pick_up_shotgun | engage_if_visible | G02;G17;M17 | take central upgrade early before chasing; route stays clear |
| player1-codex-spark-player2-gpt-5-5 | 2 | Codex Spark | player_1 | 2 | search | pick_up_shotgun | engage_if_visible | G07;G17;M17 | opponent is in view but advancing to center pickup remains highest leverage now |
| player1-codex-spark-player2-gpt-5-5 | 2 | Codex Spark | player_1 | 3 | search | pick_up_shotgun | engage_if_visible | M17 | we are one final segment from center pickup while trading, so finish objective route |
| player1-codex-spark-player2-gpt-5-5 | 2 | GPT-5.5 | player_2 | 1 | search | pick_up_shotgun | engage_if_visible | R31;R17;M17 | take center weapon via the open lower lane around the pillar |
| player1-codex-spark-player2-gpt-5-5 | 2 | GPT-5.5 | player_2 | 2 | engage_opponent | force_fight | force_fight | R31;R17;N17;O16;N17 | enemy is visible close and we need the safe pillar bypass preserved |
| player1-codex-spark-player2-gpt-5-5 | 3 | Codex Spark | player_1 | 1 | search | pick_up_shotgun | engage_if_visible | G02;G17;M17 | repeat fastest stable opening: secure center shotgun before forced duel |
| player1-codex-spark-player2-gpt-5-5 | 3 | GPT-5.5 | player_2 | 1 | search | pick_up_shotgun | engage_if_visible | R31;R17;M17 | center weapon remains the fastest power pickup from right spawn |
| player1-codex-spark-player2-gpt-5-5 | 4 | Codex Spark | player_1 | 1 | search | pick_up_shotgun | engage_if_visible | G02;G17;M17 | standard central tempo reset from left spawn |
| player1-codex-spark-player2-gpt-5-5 | 4 | Codex Spark | player_1 | 2 | search | pick_up_shotgun | engage_if_visible | G09;G17;M17 | already in lane with clear line to center, so arc to G row before pushing pickup |
| player1-codex-spark-player2-gpt-5-5 | 4 | Codex Spark | player_1 | 3 | engage_opponent | pick_up_shotgun | force_fight | M17 | combat is now close and trading, so finish the center objective under pressure |
| player1-codex-spark-player2-gpt-5-5 | 4 | GPT-5.5 | player_2 | 1 | search | pick_up_shotgun | engage_if_visible | R31;R17;M17 | use the lower open lane to reach center without crossing M27 |
| player1-codex-spark-player2-gpt-5-5 | 5 | Codex Spark | player_1 | 1 | search | pick_up_shotgun | engage_if_visible | G02;G17;M17 | standard center-first opening from left-side spawn |
| player1-codex-spark-player2-gpt-5-5 | 5 | Codex Spark | player_1 | 2 | search | pick_up_shotgun | engage_if_visible | G08;G17;M17 | advance on a clear path to center pickup after gaining LOS |
| player1-codex-spark-player2-gpt-5-5 | 5 | GPT-5.5 | player_2 | 1 | search | pick_up_shotgun | engage_if_visible | R31;R17;M17 | center shotgun route avoids the right wall column |
| player1-codex-spark-player2-gpt-5-5 | 6 | Codex Spark | player_1 | 1 | search | pick_up_shotgun | engage_if_visible | G02;G17;M17 | standard reset to central objective from initial spawn |
| player1-codex-spark-player2-gpt-5-5 | 6 | Codex Spark | player_1 | 2 | search | pick_up_shotgun | engage_if_visible | G03;G17;M17 | stabilize route from current left-side corridor while still pressing center upgrade |
| player1-codex-spark-player2-gpt-5-5 | 6 | Codex Spark | player_1 | 3 | engage_opponent | pick_up_shotgun | force_fight | M17 | currently dominant trade and within pickup radius, so force-fight while stepping into center objective |
| player1-codex-spark-player2-gpt-5-5 | 6 | Codex Spark | player_1 | 4 | search | heal | avoid_until_target | L04;G04;G07;H07;H17;G17;F17;E17;D17;C17;B17 | clear the I06/H06 wall-line by lateral detour, then climb for top medikit |
| player1-codex-spark-player2-gpt-5-5 | 6 | GPT-5.5 | player_2 | 1 | search | pick_up_shotgun | engage_if_visible | R31;R17;M17 | repeat the winning center pickup path around the pillar |
| player1-codex-spark-player2-gpt-5-5 | 6 | GPT-5.5 | player_2 | 2 | search | heal | engage_if_visible | Q17;T17;W17 | unstick by moving down the open center column toward the closer medikit |
| player1-codex-spark-player2-gpt-5-5 | 7 | Codex Spark | player_1 | 1 | search | pick_up_shotgun | engage_if_visible | G02;G17;M17 | repeat proven center-priority opener from the left lane |
| player1-codex-spark-player2-gpt-5-5 | 7 | Codex Spark | player_1 | 2 | search | pick_up_shotgun | engage_if_visible | G09;G17;M17 | align to the same central corridor used in prior successful openings |
| player1-codex-spark-player2-gpt-5-5 | 7 | Codex Spark | player_1 | 3 | engage_opponent | pick_up_shotgun | force_fight | M17 | close quartering trade favors pressure now while closing to pickup |
| player1-codex-spark-player2-gpt-5-5 | 7 | GPT-5.5 | player_2 | 1 | search | pick_up_shotgun | engage_if_visible | R31;R17;M17 | secure center weapon through the unblocked lower lane |
| player1-codex-spark-player2-gpt-5-5 | 8 | Codex Spark | player_1 | 1 | search | pick_up_shotgun | engage_if_visible | G02;G17;M17 | continue the same opening pattern for round 8 |
| player1-codex-spark-player2-gpt-5-5 | 8 | Codex Spark | player_1 | 2 | search | pick_up_shotgun | engage_if_visible | G04;G17;M17 | re-align to center corridor after losing LOS in round 8 |
| player1-codex-spark-player2-gpt-5-5 | 8 | Codex Spark | player_1 | 3 | engage_opponent | pick_up_shotgun | force_fight | G04;G07;G17;M17 | route via G07 avoids the blocked-column check and keeps pressure toward the center objective |
| player1-codex-spark-player2-gpt-5-5 | 8 | GPT-5.5 | player_2 | 1 | search | pick_up_shotgun | engage_if_visible | R31;R17;M17 | lower lane avoids the blocker while contesting the center weapon |
| player1-codex-spark-player2-gpt-5-5 | 9 | Codex Spark | player_1 | 1 | search | pick_up_shotgun | engage_if_visible | G02;G17;M17 | start round 9 with the consistent central control route |
| player1-codex-spark-player2-gpt-5-5 | 9 | Codex Spark | player_1 | 2 | search | pick_up_shotgun | engage_if_visible | G05;G17;M17 | re-center approach from current lane without crossing known blocked strip |
| player1-codex-spark-player2-gpt-5-5 | 9 | Codex Spark | player_1 | 3 | engage_opponent | pick_up_shotgun | force_fight | M17 | already at favorable close range with active enemy pressure, continue aggressive closure to objective |
| player1-codex-spark-player2-gpt-5-5 | 9 | Codex Spark | player_1 | 4 | search | pick_up_shotgun | engage_if_visible | G06;G07;G17;M17 | restore clear routing while preserving center-priority from the current left-side flank |
| player1-codex-spark-player2-gpt-5-5 | 9 | GPT-5.5 | player_2 | 1 | search | pick_up_shotgun | engage_if_visible | R31;R17;M17 | fast center control via the clear lower route is still the best opener |
| player1-codex-spark-player2-gpt-5-5 | 9 | GPT-5.5 | player_2 | 2 | engage_opponent | force_fight | force_fight | N17;O16;N17 | close visible contact with damage dealt calls for immediate pressure |
| player1-codex-spark-player2-gpt-5-5 | 10 | Codex Spark | player_1 | 1 | search | pick_up_shotgun | engage_if_visible | G02;G17;M17 | standard last-round center objective opener |
| player1-codex-spark-player2-gpt-5-5 | 10 | Codex Spark | player_1 | 2 | search | pick_up_shotgun | engage_if_visible | G05;G17;M17 | last-round path to center while preserving blocked-strip safety |
| player1-codex-spark-player2-gpt-5-5 | 10 | Codex Spark | player_1 | 3 | engage_opponent | pick_up_shotgun | force_fight | M17 | close combat state and final-round pressure, so finish the objective aggressively |
| player1-codex-spark-player2-gpt-5-5 | 10 | GPT-5.5 | player_2 | 1 | search | pick_up_shotgun | engage_if_visible | R31;R17;M17 | final round opener contests center weapon through the proven safe path |
| player1-gpt-5-5-player2-codex-park | 1 | Codex Spark | player_2 | 1 | search | pick_up_shotgun | engage_if_visible | M31;G31;G27;M17 | Secure the center shotgun first while advancing from the right spawn with a quick south detour around the blocked 27th-column barrier. |
| player1-gpt-5-5-player2-codex-park | 1 | Codex Spark | player_2 | 2 | search | pick_up_shotgun | engage_if_visible | G26;G27;M17 | Keep moving to the center shotgun, with the shortest remaining path that avoids blocked cells. |
| player1-gpt-5-5-player2-codex-park | 1 | Codex Spark | player_2 | 3 | engage_opponent | force_fight | force_fight | M17 | I have line of sight and close range, so I should stay centered and commit to trading while keeping mobility options open. |
| player1-gpt-5-5-player2-codex-park | 1 | Codex Spark | player_2 | 4 | search | heal | avoid_until_target | G26;B26;D26;D17;B17 | The direct center route to the medikit is blocked on row B at column 18, so this path routes around it before heading to the top pickup. |
| player1-gpt-5-5-player2-codex-park | 1 | GPT-5.5 | player_1 | 1 | search | pick_up_shotgun | engage_if_visible | M05;G05;G12;M17 | take center weapon before forcing a fight |
| player1-gpt-5-5-player2-codex-park | 1 | GPT-5.5 | player_1 | 2 | engage_opponent | force_fight | force_fight | M17;M19;N20;L20 | enemy is close and visible at center so hold the weapon area and commit |
| player1-gpt-5-5-player2-codex-park | 2 | Codex Spark | player_2 | 1 | search | pick_up_shotgun | engage_if_visible | M31;G31;G27;M17 | Repeat the center-first path from right spawn with a vertical detour to keep the route valid past the blocked 27th column. |
| player1-gpt-5-5-player2-codex-park | 2 | Codex Spark | player_2 | 2 | search | pick_up_shotgun | engage_if_visible | M31;G31;G27;M17 | Refresh the opening intent after round handoff so the match can start when the opponent also signals readiness. |
| player1-gpt-5-5-player2-codex-park | 2 | Codex Spark | player_2 | 3 | search | pick_up_shotgun | engage_if_visible | F29;F17;M17 | Continue closing to the central upgrade while cutting across open row F to minimize distance and avoid blocked columns. |
| player1-gpt-5-5-player2-codex-park | 2 | Codex Spark | player_2 | 4 | search | heal | avoid_until_target | J21;D21;D17;B17 | I’m at low health and currently under fire, so I’m disengaging to the top medikit using a wall-safe route. |
| player1-gpt-5-5-player2-codex-park | 2 | GPT-5.5 | player_1 | 1 | search | pick_up_shotgun | engage_if_visible | M05;G05;G12;M17 | take the center shotgun through the open upper lane before engaging |
| player1-gpt-5-5-player2-codex-park | 3 | Codex Spark | player_2 | 1 | search | pick_up_shotgun | engage_if_visible | M31;G31;G27;M17 | Restart round 3 with the same fast center-first lane control for first pickup before committing to fights. |
| player1-gpt-5-5-player2-codex-park | 3 | Codex Spark | player_2 | 2 | search | pick_up_shotgun | engage_if_visible | H25;H17;M17 | Keep pressure while closing from the right-side approach and collecting the center upgrade before deeper engagement. |
| player1-gpt-5-5-player2-codex-park | 3 | Codex Spark | player_2 | 3 | engage_opponent | force_fight | force_fight | L18;M17 | Stay in the center corridor and commit to trading while the opponent is in close LOS. |
| player1-gpt-5-5-player2-codex-park | 3 | GPT-5.5 | player_1 | 1 | search | pick_up_shotgun | engage_if_visible | M05;G05;G12;M17 | use the clear upper path to reach the center weapon quickly |
| player1-gpt-5-5-player2-codex-park | 4 | Codex Spark | player_2 | 1 | search | pick_up_shotgun | engage_if_visible | M31;G31;G27;M17 | Use the established valid route to center for a guaranteed first pickup opportunity. |
| player1-gpt-5-5-player2-codex-park | 4 | Codex Spark | player_2 | 2 | search | pick_up_shotgun | engage_if_visible | G26;G27;M17 | Resume the center run from our current waypoint to keep the opening objective clean and fast. |
| player1-gpt-5-5-player2-codex-park | 4 | GPT-5.5 | player_1 | 1 | search | pick_up_shotgun | engage_if_visible | M05;G05;G12;M17 | secure center weapon by routing around the left wall column |
| player1-gpt-5-5-player2-codex-park | 5 | Codex Spark | player_2 | 1 | search | pick_up_shotgun | engage_if_visible | M31;G31;G27;M17 | Reinitialize combat with the validated center pickup route after the round turnover. |
| player1-gpt-5-5-player2-codex-park | 5 | Codex Spark | player_2 | 2 | search | pick_up_shotgun | engage_if_visible | G27;M17 | Advance from the current position straight into the center objective lane. |
| player1-gpt-5-5-player2-codex-park | 5 | GPT-5.5 | player_1 | 1 | search | pick_up_shotgun | engage_if_visible | M05;G05;G12;M17 | route around the left blocker and arrive at shotgun with firing enabled |
| player1-gpt-5-5-player2-codex-park | 6 | Codex Spark | player_2 | 1 | search | pick_up_shotgun | engage_if_visible | M31;G31;G27;M17 | Repeat the established spawn-to-center route now that round 6 is active. |
| player1-gpt-5-5-player2-codex-park | 6 | Codex Spark | player_2 | 2 | search | pick_up_shotgun | engage_if_visible | F28;M17 | Push across the current clear row to the center pickup lane. |
| player1-gpt-5-5-player2-codex-park | 6 | Codex Spark | player_2 | 3 | search | heal | avoid_until_target | J21;D21;D17;B17 | Health is dropping in close range, so I’m disengaging toward the top medikit with a safe corridor path. |
| player1-gpt-5-5-player2-codex-park | 6 | GPT-5.5 | player_1 | 1 | search | pick_up_shotgun | engage_if_visible | M05;G05;G12;M17 | center weapon remains the fastest route to a favorable fight |
| player1-gpt-5-5-player2-codex-park | 7 | Codex Spark | player_2 | 1 | search | pick_up_shotgun | engage_if_visible | M31;G31;G27;M17 | Start round 7 with the same safe route to center pickup. |
| player1-gpt-5-5-player2-codex-park | 7 | GPT-5.5 | player_1 | 1 | search | pick_up_shotgun | engage_if_visible | M05;G05;G12;M17 | the upper approach avoids blocked cells and reaches the shotgun cleanly |
| player1-gpt-5-5-player2-codex-park | 8 | Codex Spark | player_2 | 1 | search | pick_up_shotgun | engage_if_visible | M31;G31;G27;M17 | Use the known-clear lane to center for round 8. |
| player1-gpt-5-5-player2-codex-park | 8 | Codex Spark | player_2 | 2 | search | pick_up_shotgun | engage_if_visible | M17 | Set a direct waypoint to the center objective while avoiding dependence on spawn-side row geometry checks. |
| player1-gpt-5-5-player2-codex-park | 8 | GPT-5.5 | player_1 | 1 | search | pick_up_shotgun | engage_if_visible | M05;G05;G12;M17 | repeat the reliable center route to meet contact with the weapon advantage |
| player1-gpt-5-5-player2-codex-park | 9 | Codex Spark | player_2 | 1 | search | pick_up_shotgun | engage_if_visible | M31;G31;G27;M17 | Continue the recurring round sequence: spawn-side approach to the center pickup. |
| player1-gpt-5-5-player2-codex-park | 9 | GPT-5.5 | player_1 | 1 | search | pick_up_shotgun | engage_if_visible | M05;G05;G12;M17 | take the proven center route to force contact on our terms |
| player1-gpt-5-5-player2-codex-park | 10 | Codex Spark | player_2 | 1 | search | pick_up_shotgun | engage_if_visible | M31;G31;G27;M17 | Final round startup: preserve the proven route to center to prioritize early power-up control. |
| player1-gpt-5-5-player2-codex-park | 10 | GPT-5.5 | player_1 | 1 | search | pick_up_shotgun | engage_if_visible | M05;G05;G12;M17 | final round still favors the center shotgun route before contact |
