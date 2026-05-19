# Paper Update Summary

Updated `docs/benchmark-paper-draft.md` to integrate the finalized analysis CSVs and generated figures.

## Inputs Used

- `benchmarks/analysis/model_aggregate_metrics.csv`
- `benchmarks/analysis/pairwise_matchup_matrix.csv`
- `benchmarks/analysis/tactical_behavior_by_model.csv`
- `benchmarks/analysis/intent_lifecycle_by_model.csv`
- `benchmarks/analysis/tool_reliability_by_model.csv`
- `benchmarks/analysis/reproducibility_metadata.md`
- `benchmarks/analysis/figure_manifest.md`
- `benchmarks/figures/*.png`

## Main Changes

- Replaced placeholder results with measured 120-round benchmark results.
- Added the finalized experimental setup: 6 mirrored pairings, 4 evaluated models, seed `[42]`, `duel_e1m8`, `timeout_seconds=120`, `intent_duration_ms=25000`, and `decision_cadence_ms=750`.
- Added reproducibility metadata summary and explicitly listed unavailable fields as `UNKNOWN`.
- Added mirrored win-rate ranking, Elo-style ranking, pairwise matchup table, side-bias findings, reliability findings, tactical behavior findings, and intent lifecycle findings.
- Added inline figure references and academic-style captions for architecture, mirrored win rate, Elo ranking, pairwise heatmap, side bias, reliability, latency, tactical distribution, intent cadence, stale policy exposure, and damage differential.
- Added an explicit tactical action-space table listing accepted `set_participant_intent` parameters, allowed enum values/ranges, and the decision role for each field.
- Added Discussion, Limitations, Future Work, and appendix placeholders.

## Key Integrated Results

- Primary ranking by mirrored win rate:
  - `gpt-5-5`: 58.3%
  - `gpt-5-4-mini`: 56.7%
  - `gpt-5-3-codex`: 46.7%
  - `gpt-5-3-codex-spark`: 38.3%
- Elo-style ordering:
  - `gpt-5-5`: 1542.2
  - `gpt-5-4-mini`: 1533.7
  - `gpt-5-3-codex`: 1483.3
  - `gpt-5-3-codex-spark`: 1440.8
- Raw side bias:
  - `player_1`: 25.8%
  - `player_2`: 74.2%
  - side-bias analysis reported `p < 1e-6`
- Lowest model-attributed MCP/tool error rate:
  - `gpt-5-3-codex-spark`: 5.86%
- Lowest aggregate inferred decision latency:
  - `gpt-5-3-codex-spark`: 3437.6 ms

## Caveats Preserved

- Mirrored win rate is preferred over raw win rate because of strong side bias.
- Exact model build IDs, reasoning settings, browser/runtime environment, Docker/native execution mode, starting health, and map name beyond `duel_e1m8` remain `UNKNOWN`.
- Local MCP/tool latency is not model reasoning latency.
- Decision latency distributions are not available in finalized CSVs; only aggregate mean and P95 are used.
- Stale continuation metrics are partially round-level and not directly participant-attributed.

No benchmark defaults were changed and no benchmark results were regenerated.
