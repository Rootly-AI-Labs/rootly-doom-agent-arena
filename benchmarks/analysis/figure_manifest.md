# Figure Manifest

All figures are generated from finalized analysis CSVs with a white-background academic style and saved as both PNG and PDF in `benchmarks/figures/`.

## benchmarks/figures/mirrored_win_rate.png

- Chart type: Horizontal bar chart
- Source CSVs: benchmarks/analysis/model_aggregate_metrics.csv
- Metrics shown: Mirrored win rate by model.
- Interpretation: gpt-5.5 has the highest mirrored win rate, followed closely by gpt-5.4-mini.
- Caveats/limitations: Use mirrored win rate as the primary metric because raw outcomes are affected by strong side bias.

## benchmarks/figures/elo_ranking.png

- Chart type: Horizontal bar chart
- Source CSVs: benchmarks/analysis/model_aggregate_metrics.csv
- Metrics shown: Elo-style score.
- Interpretation: The Elo-style ordering matches the mirrored win-rate ranking.
- Caveats/limitations: Elo-style scores are derived from the 120-round benchmark only and should not be treated as universal ratings.

## benchmarks/figures/player_side_bias.png

- Chart type: Two-bar comparison
- Source CSVs: benchmarks/analysis/pairwise_matchup_matrix.csv
- Metrics shown: player_1 and player_2 side win rates.
- Interpretation: player_2 wins far more often than player_1, showing strong side bias.
- Caveats/limitations: This figure is intentionally a warning: side bias can mislead raw model comparisons unless mirrored evaluation is used.

## benchmarks/figures/damage_differential_by_model.png

- Chart type: Horizontal bar chart
- Source CSVs: benchmarks/analysis/model_aggregate_metrics.csv
- Metrics shown: Average damage differential.
- Interpretation: Positive damage differential tracks the strongest models but should be secondary to mirrored win rate.
- Caveats/limitations: Damage differential is still affected by side and encounter dynamics.

## benchmarks/figures/decision_latency_by_model.png

- Chart type: Mean-to-P95 range plot
- Source CSVs: benchmarks/analysis/model_aggregate_metrics.csv
- Metrics shown: Average and P95 inferred decision latency.
- Interpretation: gpt-5.3-codex-spark has the lowest mean inferred decision latency in the aggregate table.
- Caveats/limitations: A true box plot was not generated because finalized CSV inputs contain aggregate mean/P95 values, not per-round latency distributions.

## benchmarks/figures/mcp_error_rate_by_model.png

- Chart type: Bar chart
- Source CSVs: benchmarks/analysis/tool_reliability_by_model.csv
- Metrics shown: MCP/tool error rate by model.
- Interpretation: gpt-5.3-codex-spark has the lowest model-attributed MCP/tool error rate.
- Caveats/limitations: Most errors are lifecycle/post-finish rejections, so this should be interpreted as control-plane hygiene rather than model quality.

## benchmarks/figures/tactical_intent_distribution.png

- Chart type: Stacked horizontal bar chart
- Source CSVs: benchmarks/analysis/tactical_behavior_by_model.csv
- Metrics shown: Accepted intent share: engage_opponent, strafe_attack, search, hold.
- Interpretation: gpt-5.5 shows the broadest mix of tactical modes, while gpt-5.3-codex is dominated by engage_opponent.
- Caveats/limitations: Intent mix reflects both model choice and game state exposure.

## benchmarks/figures/intents_per_round_by_model.png

- Chart type: Bar chart
- Source CSVs: benchmarks/analysis/intent_lifecycle_by_model.csv
- Metrics shown: Accepted intents per model-round.
- Interpretation: gpt-5.3-codex-spark refreshes policies most frequently.
- Caveats/limitations: Higher intent cadence is not automatically better; it may reflect reactivity or instability.

## benchmarks/figures/stale_policy_by_model.png

- Chart type: Grouped bar chart
- Source CSVs: benchmarks/analysis/intent_lifecycle_by_model.csv
- Metrics shown: Expired-before-next count and stale continuation exposure.
- Interpretation: Expiry and stale exposure are rare relative to total accepted intents.
- Caveats/limitations: Stale continuation exposure is round-level only and not directly participant-attributed.

## benchmarks/figures/pairwise_matchup_heatmap.png

- Chart type: Annotated heatmap
- Source CSVs: benchmarks/analysis/pairwise_matchup_matrix.csv
- Metrics shown: Pairwise mirrored win rates.
- Interpretation: The heatmap shows matchup-specific strengths, including gpt-5.5 over codex and gpt-5.4-mini over gpt-5.5 in this run.
- Caveats/limitations: Cells are based on 20 rounds per pair, so treat large differences as directional rather than definitive.

## benchmarks/figures/system_architecture_diagram.png

- Chart type: Architecture diagram
- Source CSVs: Benchmark design and generated analysis artifacts.
- Metrics shown: System components and data/control flow.
- Interpretation: The diagram shows the split between model-level MCP intent control and Doom-side low-level autopilot control.
- Caveats/limitations: Diagram is conceptual and does not encode per-run performance values.
