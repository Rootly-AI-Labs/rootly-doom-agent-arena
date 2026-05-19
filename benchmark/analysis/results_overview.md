# Results Overview

Generated at: `2026-05-19T14:14:57+00:00`

This is a first-pass paper results extraction from `analysis/normalized_round_metrics.csv`. It does not include plots and does not claim formal statistical significance beyond the side-bias binomial check.

## Complete Ranking by Mirrored Win Rate

| Rank | Model | Mirrored WR | Raw WR | Avg Dmg Diff | Avg Decision ms |
| --- | --- | --- | --- | --- | --- |
| 1 | gpt-5-5 | 58.3% | 58.3% | 10.167 | 6513.93 |
| 2 | gpt-5-4-mini | 56.7% | 56.7% | 7.333 | 7054.294 |
| 3 | gpt-5-3-codex | 46.7% | 46.7% | -4.167 | 8444.043 |
| 4 | gpt-5-3-codex-spark | 38.3% | 38.3% | -13.333 | 3437.623 |

## Elo-Style Ordering

Ratings are Bradley-Terry/Elo-style estimates with light smoothing, included only as an ordering aid.

| Rank | Model | Elo-Style Rating |
| --- | --- | --- |
| 1 | gpt-5-5 | 1542.2 |
| 2 | gpt-5-4-mini | 1533.7 |
| 3 | gpt-5-3-codex | 1483.3 |
| 4 | gpt-5-3-codex-spark | 1440.8 |

## Core Findings

- Strongest model overall by mirrored win rate: **gpt-5-5**.
- Player 1 side score rate: **25.8%**; Player 2 side score rate: **74.2%**.
- Side-bias binomial p-value: **<1e-6**.
- Mirrored evaluation coverage is balanced: every model has equal player_1 and player_2 exposure in the normalized dataset.
- Codex-specialized cross-family win rate: **38.8%**.

## Pairwise Results

| Pair | Model A | Model B | A Mirrored WR | B Mirrored WR | A Wins | B Wins | Draws |
| --- | --- | --- | --- | --- | --- | --- | --- |
| pair-01 | gpt-5-5 | gpt-5-3-codex | 85.0% | 15.0% | 17 | 3 | 0 |
| pair-02 | gpt-5-5 | gpt-5-3-codex-spark | 55.0% | 45.0% | 11 | 9 | 0 |
| pair-03 | gpt-5-5 | gpt-5-4-mini | 35.0% | 65.0% | 7 | 13 | 0 |
| pair-04 | gpt-5-3-codex | gpt-5-3-codex-spark | 85.0% | 15.0% | 17 | 3 | 0 |
| pair-05 | gpt-5-3-codex | gpt-5-4-mini | 40.0% | 60.0% | 8 | 12 | 0 |
| pair-06 | gpt-5-3-codex-spark | gpt-5-4-mini | 55.0% | 45.0% | 11 | 9 | 0 |

## Suspicious Anomalies

- Invalid sequence counts total **9** across **8** rounds; inspect those rounds before using sequence consistency as a headline metric.
- **66** rounds include negative final health, likely overkill damage after the lethal hit rather than necessarily corrupt data.
