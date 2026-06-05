# Benchmark analysis execution prompt

Read and execute this prompt as a goal until the benchmark analysis is complete.

## Goal

Analyze the Doom Arena model round-robin results and produce the full analysis described in:

```text
benchmarks/benchmark-analysis-official/models-analysis-plan.md
```

The goal is complete only when the planned tables, figures, and written analysis have been generated and saved in this folder.

## Input data

Use the current benchmark results in:

```text
benchmarks/results/
```

Use only the official 4-model round-robin folders:

```text
player1-gpt-5-5__player2-gpt-5-4
player1-gpt-5-4__player2-gpt-5-5
player1-gpt-5-5__player2-gpt-5-4-mini
player1-gpt-5-4-mini__player2-gpt-5-5
player1-gpt-5-5__player2-gpt-5-3-codex-spark
player1-gpt-5-3-codex-spark__player2-gpt-5-5
player1-gpt-5-4__player2-gpt-5-4-mini
player1-gpt-5-4-mini__player2-gpt-5-4
player1-gpt-5-4__player2-gpt-5-3-codex-spark
player1-gpt-5-3-codex-spark__player2-gpt-5-4
player1-gpt-5-4-mini__player2-gpt-5-3-codex-spark
player1-gpt-5-3-codex-spark__player2-gpt-5-4-mini
```

Ignore:

```text
benchmarks/results/legacy/
```

Each directed folder should contain 10 rounds. Each model pair should be analyzed across both POV directions, for 20 matches per pair.

## Output location

Write all outputs under:

```text
benchmarks/benchmark-analysis-official/
```

Recommended structure:

```text
benchmarks/benchmark-analysis-official/
  analysis.md
  tables/
  figures/
  data/
```

## Required data extraction

For every round, read:

```text
summary.json
stats.json
analysis_summary.json
```

Extract at minimum:

- matchup folder
- round
- run_id
- player_1 model
- player_2 model
- winner
- terminal_reason
- elapsed_time_seconds
- timeout_seconds
- final health
- damage dealt
- shots fired
- shots hit
- accuracy
- MCP calls
- MCP errors
- MCP latency
- inferred decision latency
- set_participant_plan calls
- accepted and rejected plans
- route errors
- stuck recovery counts
- pickup metrics
- first shotgun pickup
- first health pickup
- reasoning
- objective
- plan_note
- route cells

Use folder names to map participants to models.

Example:

```text
player1-gpt-5-5__player2-gpt-5-4
player_1 = gpt-5-5
player_2 = gpt-5-4
```

## Required analysis

Follow `models-analysis-plan.md`.

At minimum, produce:

1. Overall leaderboard table.
2. Head-to-head matrix.
3. Directed POV results table.
4. Resource control summary.
5. Route-planning reliability table.
6. Per-plan decision timing table.
7. Reasoning and plan-note examples table.
8. Overall win-rate chart.
9. Head-to-head heatmap.
10. Match time over rounds.
11. MCP error count over rounds.
12. Decision latency over rounds.
13. MCP latency over rounds.
14. Per-plan thinking time distribution.
15. Decision latency vs MCP latency scatter.
16. Damage differential by model.
17. Accuracy/combat efficiency chart.
18. Resource advantage outcome chart.
19. Route error distribution chart.
20. Planning intent distribution.
21. Thought-process embedding map if feasible.
22. Thinking time vs plan quality if feasible.
23. Opening strategy Sankey or equivalent flow chart if feasible.
24. Model personality radar chart if feasible.

If a figure is not feasible because the needed data is missing or dependencies are unavailable, document why in `analysis.md` and still produce the closest useful table.

## Planning-intent classification

Classify each `set_participant_plan` into exactly one:

- resource control
- engagement/combat
- evasion/recovery
- map control/exploration

Use public fields only:

- objective
- reasoning
- plan_note
- route
- observation/result metadata if available

Do not claim access to hidden chain-of-thought.

If using an LLM judge, use it only as a semantic classifier for public plan text. Report the rubric and limitations.

## Completion criteria

This goal is complete when:

- `analysis.md` exists and summarizes the benchmark.
- Required tables are saved under `tables/` or embedded in `analysis.md`.
- Required figures are saved under `figures/` and referenced from `analysis.md`.
- Any skipped figure has a clear reason documented.
- The analysis combines both POV directions for final model-vs-model results.
- The analysis excludes `benchmarks/results/legacy/`.
- The analysis clearly separates model decision latency from MCP/server latency.
- The analysis includes at least one section about public model planning behavior using `objective`, `reasoning`, and `plan_note`.

Do not stop after only extracting data. Continue until the written report, tables, and figures are complete.
