# Model-vs-Model Side Breakdown

Each side assignment contains 10 rounds. Results below show who won most overall and how each matchup changed when the models swapped `player_1` / `player_2`.

| Pair | Overall Winner | Model A as `player_1` | Model B as `player_1` |
| --- | ---: | ---: | ---: |
| `gpt-5-5` vs `gpt-5-3-codex` | `gpt-5-5` 17-3 | `gpt-5-5` 7, `gpt-5-3-codex` 3 | `gpt-5-3-codex` 0, `gpt-5-5` 10 |
| `gpt-5-5` vs `gpt-5-3-codex-spark` | `gpt-5-5` 11-9 | `gpt-5-5` 3, `gpt-5-3-codex-spark` 7 | `gpt-5-3-codex-spark` 2, `gpt-5-5` 8 |
| `gpt-5-5` vs `gpt-5-4-mini` | `gpt-5-4-mini` 13-7 | `gpt-5-5` 1, `gpt-5-4-mini` 9 | `gpt-5-4-mini` 4, `gpt-5-5` 6 |
| `gpt-5-3-codex` vs `gpt-5-3-codex-spark` | `gpt-5-3-codex` 17-3 | `gpt-5-3-codex` 7, `gpt-5-3-codex-spark` 3 | `gpt-5-3-codex-spark` 0, `gpt-5-3-codex` 10 |
| `gpt-5-3-codex` vs `gpt-5-4-mini` | `gpt-5-4-mini` 12-8 | `gpt-5-3-codex` 0, `gpt-5-4-mini` 10 | `gpt-5-4-mini` 2, `gpt-5-3-codex` 8 |
| `gpt-5-3-codex-spark` vs `gpt-5-4-mini` | `gpt-5-3-codex-spark` 11-9 | `gpt-5-3-codex-spark` 3, `gpt-5-4-mini` 7 | `gpt-5-4-mini` 2, `gpt-5-3-codex-spark` 8 |

## Side Pattern

`player_2` had a large advantage across the benchmark.

| Model | Wins as `player_1` | Wins as `player_2` | Total Wins |
| --- | ---: | ---: | ---: |
| `gpt-5-5` | 11/30 | 24/30 | 35 |
| `gpt-5-4-mini` | 8/30 | 26/30 | 34 |
| `gpt-5-3-codex` | 7/30 | 21/30 | 28 |
| `gpt-5-3-codex-spark` | 5/30 | 18/30 | 23 |

The strongest pairwise results are the ones where a model wins both mirrored side assignments:

- `gpt-5-5` over `gpt-5-3-codex`
- `gpt-5-3-codex` over `gpt-5-3-codex-spark`
- `gpt-5-4-mini` over `gpt-5-5`

