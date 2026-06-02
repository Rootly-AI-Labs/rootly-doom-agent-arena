# Models analysis plan

This is a planning checklist for the model round-robin analysis. It does not generate the figures yet.

## Data sources

Use the directed matchup folders under `benchmarks/results/`.

Per round, the main files are:

- `summary.json`: winner, terminal reason, elapsed time, final health, damage, shots fired, shots hit.
- `stats.json`: MCP calls, MCP latency, inferred decision latency, tool errors, intent/plan lifecycle, token estimates, plan calls.
- `analysis_summary.json`: combat summary, pickup/resource summary, routing metrics, latency summary, errors, lifecycle, fairness, and reasoning samples.

## Core questions

- Which model wins most often across both POV directions?
- Does either player slot have a systematic advantage?
- Do models improve across rounds in the same 10-round run?
- Do matches get shorter as models adapt?
- Do MCP/tool errors decrease across rounds?
- Does lower latency correlate with winning, or does planning quality matter more?
- Which models use resources better, especially shotgun and health pickups?
- Which models produce better route plans with fewer invalid cells, wall collisions, or stuck events?
- Which models show useful adaptation in `reasoning` / `plan_note` across rounds?

## Primary tables

### Table 1: Overall leaderboard

Columns:

- model
- total matches
- wins
- losses
- draws
- win rate excluding draws
- score with draw = 0.5
- average damage dealt
- average damage taken
- average final health
- average match time
- average decision latency
- MCP error rate

### Table 2: Head-to-head matrix

Rows and columns are models.

Each cell:

- wins-losses-draws
- score percentage
- total damage differential
- average match time

This should combine both POV folders for the same pair.

### Table 3: Directed POV results

One row per directed folder.

Columns:

- folder
- player_1 model
- player_2 model
- player_1 wins
- player_2 wins
- draws
- player_1 average damage
- player_2 average damage
- player_1 average decision latency
- player_2 average decision latency
- player_1 MCP errors
- player_2 MCP errors

Purpose: detect side bias.

### Table 4: Resource control summary

Columns:

- model
- first shotgun pickups
- first health pickups
- total shotgun pickups
- total health pickups
- win rate when getting first shotgun
- win rate when opponent gets first shotgun
- average time/tick to first shotgun if available

### Table 5: Route-planning reliability

Columns:

- model
- valid plans
- rejected plans
- invalid route rate
- `waypoint_in_wall_cell` count
- `route_diagonal_segment` count
- route rebase count
- route repair count
- stuck recovery count
- average unique cells visited
- average distance traveled
- revisited-cell rate

### Table 6: Reasoning and plan-note examples

Columns:

- model
- matchup
- round
- participant
- objective
- route
- reasoning
- plan_note
- outcome
- why it matters

Use this table for qualitative examples of clever planning, prediction, adaptation, or mistakes.

### Table 7: Per-plan decision timing

One row per `set_participant_plan` call.

Columns:

- model
- matchup
- round
- participant
- sequence number
- objective
- route
- reasoning
- plan_note
- inferred decision latency ms
- MCP latency ms
- accepted/rejected
- rejection reason if any

Definitions:

- inferred decision latency = next `set_participant_plan.started_at_ms` minus previous same-participant `get_participant_observation.completed_at_ms`
- MCP latency = local tool/server call duration for `set_participant_plan`

Purpose: separate actual model thinking time from local MCP/server execution time.

## Primary figures

### Figure 1: Overall model win-rate bar chart

X-axis: model.

Y-axis: win rate or score percentage.

Include error bars or confidence intervals if possible.

### Figure 2: Head-to-head heatmap

Rows: model A.

Columns: model B.

Cell color: model A score percentage against model B across both POVs.

### Figure 3: Directed side-bias chart

For each model, show win rate as:

- player_1
- player_2

This checks whether a model is only winning because of side/slot advantage.

### Figure 4: Match time over rounds

X-axis: round number.

Y-axis: `elapsed_time_seconds`.

Groupings:

- line per directed matchup, or
- average line per model, split by POV.

Add a trend line.

Purpose: see whether match duration decreases as models adapt across rounds.

### Figure 5: MCP error count over rounds

X-axis: round number.

Y-axis: MCP errors per round.

Fields:

- `stats.summary.errored_mcp_calls`
- `analysis_summary.errors`
- optionally by tool from `stats.by_tool`.

Purpose: see whether agents become more stable or whether server/tool instability clusters late in sessions.

### Figure 6: Decision latency over rounds

X-axis: round number.

Y-axis: `analysis_summary.latency.decision_avg_ms`.

Add per-model trend lines.

Purpose: see if repeated rounds reduce thinking time or if context accumulation slows agents down.

### Figure 7: MCP latency over rounds

X-axis: round number.

Y-axis: `analysis_summary.latency.mcp_avg_ms`.

Separate from decision latency because MCP latency is local tool/server time, not model thinking time.

### Figure 7b: Per-plan thinking time distribution

Box plot or violin plot by model.

Y-axis: inferred decision latency for each `set_participant_plan`.

Group by:

- model
- matchup
- early rounds vs late rounds

Purpose: show how long models take to decide on each route plan.

### Figure 7c: Decision latency vs MCP latency scatter

X-axis: inferred decision latency.

Y-axis: `set_participant_plan` MCP latency.

Color: model.

Purpose: show that model thinking time and MCP/server time are different bottlenecks.

### Figure 8: Damage differential by model

X-axis: model.

Y-axis: average `damage_dealt - damage_taken`.

This catches cases where a model loses on timeout but still trades well.

### Figure 9: Accuracy and combat efficiency

Possible plots:

- shots hit / shots fired by model
- damage per shot fired
- damage per MCP plan
- damage per second

### Figure 10: Resource advantage outcomes

Two-panel figure:

- win rate when model gets first shotgun
- win rate when model gets first health

This tests whether agents understand pickups and convert resources into wins.

### Figure 11: Route error distribution

Stacked bar chart by model.

Categories:

- `waypoint_in_wall_cell`
- `route_diagonal_segment`
- other MCP/tool errors

### Figure 12: Path coverage heatmap

For each model or matchup:

- aggregate visited cells from routing/path logs
- show cell heatmap over the ASCII map

Purpose: show whether models explore the map, camp, repeat routes, or get stuck in specific corridors.

### Figure 13: Opening route diversity

For each model:

- count first objective / first route cells across rounds
- plot most common opening cells or route prefixes

Purpose: detect whether models learn a preferred opening or overfit to one route.

### Figure 14: Plan-note adaptation examples

Qualitative figure/table.

Show selected `plan_note` lines where models:

- predict opponent path
- avoid repeating failed routes
- choose health after taking damage
- fight around shotgun timing
- infer blocked path and reroute

### Figure 15: Planning intent distribution

Stacked bar chart by model.

Classify each `set_participant_plan` into one planning-intent category:

- resource control
- engagement/combat
- evasion/recovery
- map control/exploration

X-axis: model.

Y-axis: percentage of submitted plans.

Purpose: show the split of what each model is thinking about, rather than only who won.

### Figure 16: Planning intent over rounds

X-axis: round number.

Y-axis: percentage of plans by category.

Group by model or matchup.

Purpose: show whether models adapt across rounds. For example, after losing early fights, a model may shift from engagement to resource control or recovery.

### Figure 17: Outcome by planning intent

Bar chart or table.

For each planning-intent category, report:

- win rate
- average damage differential
- average final health
- average match time

Purpose: test whether certain planning styles actually correlate with better outcomes.

### Figure 18: Plan quality score by model

Use a rubric score from either a deterministic heuristic or an LLM judge.

Scores:

- route-objective alignment
- map awareness
- opponent awareness
- resource awareness
- adaptation from previous rounds

Plot average score by model with confidence intervals.

### Figure 19: Reasoning-action alignment

Measure whether the route matches the stated `objective`, `reasoning`, and `plan_note`.

Examples:

- objective says `take shotgun`, route ends near shotgun: aligned
- objective says `retreat`, route moves toward opponent: misaligned
- plan says `avoid wall`, route enters blocked cell: misaligned

Plot alignment rate by model.

## Statistical analyses

### Win-rate significance

Use binomial tests or Wilson confidence intervals for each head-to-head.

For each pair:

- exclude draws for strict win/loss test
- also report draw-as-half score

### Side-bias test

Compare model performance as player_1 vs player_2.

Useful checks:

- player_1 win rate across all matches
- player_2 win rate across all matches
- per-model side delta

### Match-time trend

For each directed folder:

- regress `elapsed_time_seconds` on round number
- report slope

Negative slope means matches are getting faster.

Also compute global trend across all 4-model round-robin runs.

### MCP-error trend

For each directed folder:

- regress `errored_mcp_calls` on round number
- report slope

Negative slope means tool stability improves over the session.

### Decision-latency trend

For each directed folder:

- regress `decision_avg_ms` on round number
- compare early rounds 1-3 vs late rounds 8-10

This can show whether models get faster due to repeated context or slower due to context growth.

### Per-plan thinking-time analysis

For every accepted or rejected `set_participant_plan`, compute:

```text
decision_latency_ms = set_participant_plan.started_at_ms - previous get_participant_observation.completed_at_ms
```

Use only same-participant pairs.

Report:

- mean
- median
- p95
- max
- count
- early-round average
- late-round average

Also compare against:

```text
mcp_latency_ms = set_participant_plan.latency_ms
```

This should be one of the main latency analyses because `set_participant_plan.latency_ms` is usually local MCP/server time, while inferred decision latency approximates model thinking time.

### Resource-to-win association

Test:

- first shotgun pickup -> win probability
- first health pickup -> win probability
- total health pickups -> survival/timeout wins

Use simple contingency tables first.

### Planning-quality association

Correlate:

- invalid route rate with loss rate
- stuck recovery count with loss rate
- unique cells visited with win rate
- route length with win rate
- decision latency with win rate

### Planning-intent association

Use the planning-intent labels to test:

- resource-control plan rate vs win rate
- evasion/recovery plan rate after taking damage vs survival
- map-control/exploration rate vs opponent contact time
- engagement/combat plan rate vs damage dealt

This helps separate model thinking style from raw combat outcome.

## Model-thinking classification plan

The benchmark should analyze public model planning, not hidden chain-of-thought.

Use these public fields:

- `objective`
- `reasoning`
- `plan_note`
- `route`
- `last_plan`
- current observation summary
- previous-round recap when present
- final outcome

Do not infer or claim access to hidden chain-of-thought.

### Planning-intent categories

Classify each accepted `set_participant_plan` into exactly one:

| Category | Meaning |
| --- | --- |
| Resource control | Plans around shotgun, health, pickup denial, sustain, or weapon advantage. |
| Engagement/combat | Plans to find, fight, chase, pressure, hold line of sight, or finish the opponent. |
| Evasion/recovery | Plans to retreat, break contact, recover health, escape damage, unstuck, or reset. |
| Map control/exploration | Plans to rotate, scout, flank, clear lanes, control corridors, or reposition. |

### Recommended classification method

Use a hybrid method:

1. Deterministic rule-based classifier for consistent labels.
2. LLM-as-judge for ambiguous plans or semantic validation.
3. Human-audited examples for the final writeup.

Rule-based classifier inputs:

- keywords in `objective`, `reasoning`, and `plan_note`
- route endpoint proximity to shotgun or health cells
- opponent visibility
- self health
- whether the plan follows damage taken, stuck state, or prior failed route

LLM judge inputs:

- public plan fields only
- compact observation summary
- route cells
- pickup availability summary
- prior-round summary if present

LLM judge output:

```json
{
  "intent_category": "resource_control",
  "route_objective_alignment": 4,
  "map_awareness": 5,
  "opponent_awareness": 3,
  "resource_awareness": 5,
  "adaptation": 2,
  "short_explanation": "Route moves toward available shotgun and matches stated objective."
}
```

Suggested score scale:

- `1`: poor or contradictory
- `2`: weak
- `3`: reasonable
- `4`: strong
- `5`: excellent

### LLM-as-judge caveats

Do not rely only on LLM judgment.

Report:

- deterministic label distribution
- LLM judge label distribution on a sample or ambiguous subset
- agreement rate between rule labels and LLM labels
- manually reviewed examples

This makes the analysis more credible than a pure LLM-judge result.

## Qualitative analysis sections

### Clever reasoning examples

Pull examples from `analysis_summary.reasoning`.

Look for:

- opponent path prediction
- shotgun denial
- health denial
- rerouting around blocked cells
- adapting from previous rounds
- fighting from range instead of blindly chasing

### Failure modes

Examples to collect:

- routes into wall cells
- diagonal route attempts
- repeated same-cell or backtracking loops
- shotgun/health ignored even when nearby
- high MCP error or stale intent periods
- long thinking while opponent is active
- correct plan but poor Doom execution

### Planning vs execution split

For each interesting failure, classify:

- model planning error
- MCP/tool error
- route validation error
- Doom autopilot execution issue
- combat/aiming issue

This is important because a model can reason correctly while the controller executes poorly.

## Data-quality checks

Before generating final figures:

- verify every directed folder has 10 `summary.json` files
- verify model names are inferred correctly from folder names
- exclude `benchmarks/results/legacy`
- check for missing `analysis_summary.json`
- check for rounds with `winner=draw`
- check for rounds with `elapsed_time_seconds` near timeout
- check for rounds with MCP internal errors
- separate server/tool errors from model errors

## Suggested report structure

1. Executive summary
2. Dataset and matchup setup
3. Overall leaderboard
4. Head-to-head results
5. Side-bias analysis
6. Latency and MCP reliability
7. Learning/adaptation across rounds
8. Resource control and pickup strategy
9. Route-planning quality
10. Combat performance
11. Qualitative reasoning examples
12. Failure modes and limitations
13. Conclusions

## Highest-priority outputs

If keeping the analysis compact, prioritize these first:

1. Overall leaderboard table.
2. Head-to-head heatmap.
3. Match time over rounds.
4. MCP errors over rounds.
5. Decision latency over rounds.
6. Resource control table.
7. Route error distribution.
8. Best reasoning examples table.

## High-value insight figures

These are the most useful figures for showing how models think differently, not just who won.

### Priority 1: Thought-process embedding map

This is the most important insight figure.

Use every `set_participant_plan` public planning text:

```text
objective + reasoning + plan_note
```

Embed each plan with a text embedding model, reduce to 2D with UMAP or t-SNE, and plot:

- each dot = one plan
- color = model
- shape = outcome: win, loss, draw
- optional outline = accepted vs rejected plan

Manually label clusters after inspection.

Likely clusters:

- resource rush
- health recovery
- shotgun denial
- direct engagement
- map exploration
- stuck recovery
- timeout survival
- opponent prediction

Why it matters:

- gives a one-figure view of model “thinking style”
- shows whether models occupy different strategy regions
- shows whether winning plans cluster separately from losing plans
- shows whether a model repeats one idea or uses diverse strategies

### Priority 2: Thinking time vs plan quality

X-axis:

```text
inferred decision latency per set_participant_plan
```

Y-axis:

```text
plan quality score
```

Color by model.

Plan quality can come from the hybrid rule/LLM-judge rubric:

- route-objective alignment
- map awareness
- opponent awareness
- resource awareness
- adaptation

Why it matters:

- tests whether slower thinking actually produces better plans
- can reveal models that think longer but do not improve plan quality
- separates speed from strategic quality

### Priority 3: Opening strategy Sankey

Use the first accepted `set_participant_plan` from each round.

Flow:

```text
model -> opening strategy category -> outcome
```

Opening categories:

- shotgun first
- health first
- edge rotate
- center contest
- direct search
- defensive hold

Why it matters:

- makes model strategy immediately understandable
- shows whether wins come from consistent openings
- shows whether models adapt openings across rounds

### Priority 4: Model personality radar chart

For each model, compute normalized behavioral dimensions:

- aggression: engagement/combat plans per total plans
- resource focus: resource-control plans per total plans
- caution: evasion/recovery plans per total plans
- exploration: map-control plans per total plans
- tool discipline: `1 - MCP error rate`
- spatial accuracy: `1 - invalid route rate`
- speed: inverse inferred decision latency
- combat efficiency: damage per shot

Why it matters:

- gives a compact behavioral profile per model
- useful for non-technical readers
- makes “model personality” visible

### Priority 5: Strategy trajectory over rounds

Use the same planning-text embeddings as the thought-process map.

For each model or directed matchup, draw arrows:

```text
round 1 -> round 2 -> ... -> round 10
```

Why it matters:

- shows whether a model converges on a winning strategy
- shows whether it oscillates, adapts, or repeats failed plans
- supports the cross-round learning story

### Optional: Surprise index

Automatically surface unusually clever plans.

Score each plan using:

```text
rarity within model behavior
+ led to win or damage swing
+ high plan-quality score
+ strong route/objective alignment
```

Use this to build a “most surprising model thoughts” table.

Why it matters:

- helps find examples like opponent prediction, resource denial, or clever reroutes
- supports qualitative storytelling without manually reading every run
