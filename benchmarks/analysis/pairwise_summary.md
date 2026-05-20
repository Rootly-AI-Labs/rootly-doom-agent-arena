# Pairwise Summary

Mirrored win rate is the primary competitive metric. It averages a model's score rate from both side assignments within the pair, with draws counted as half a point.

| Pair | Model A | Model B | Rounds | A Wins | B Wins | Draws | A Mirrored WR | B Mirrored WR | P1 Side WR | P2 Side WR | Mean Duration | Mean Damage Diff |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| pair-01 | gpt-5-5 | gpt-5-3-codex | 20 | 17 | 3 | 0 | 85.0% | 15.0% | 35.0% | 65.0% | 20.69 | 49.5 |
| pair-02 | gpt-5-5 | gpt-5-3-codex-spark | 20 | 11 | 9 | 0 | 55.0% | 45.0% | 25.0% | 75.0% | 32.13 | 4.25 |
| pair-03 | gpt-5-5 | gpt-5-4-mini | 20 | 7 | 13 | 0 | 35.0% | 65.0% | 25.0% | 75.0% | 24.82 | -23.25 |
| pair-04 | gpt-5-3-codex | gpt-5-3-codex-spark | 20 | 17 | 3 | 0 | 85.0% | 15.0% | 35.0% | 65.0% | 10.89 | 37.25 |
| pair-05 | gpt-5-3-codex | gpt-5-4-mini | 20 | 8 | 12 | 0 | 40.0% | 60.0% | 10.0% | 90.0% | 11.16 | -0.25 |
| pair-06 | gpt-5-3-codex-spark | gpt-5-4-mini | 20 | 11 | 9 | 0 | 55.0% | 45.0% | 25.0% | 75.0% | 9.295 | 1.5 |

## Side Bias

- Player 1 wins: **31**
- Player 2 wins: **89**
- Draws: **0**
- Player 1 score rate: **25.8%**
- Player 2 score rate: **74.2%**
- Two-sided binomial check against 50/50 side wins: **p=<1e-6**

The aggregate side split is statistically meaningful under a simple binomial check. Mirrored evaluation is therefore important for interpreting model strength.

## Outliers

### Longest Rounds

| Round | P1 | P2 | Winner | duration |
| --- | --- | --- | --- | --- |
| pair-02 pov1-gpt-5-5__pov2-gpt-5-3-codex-spark round 8 (run_5e7f8e292e7b) | gpt-5-5 | gpt-5-3-codex-spark | gpt-5-3-codex-spark | 206.2 |
| pair-03 pov1-gpt-5-5__pov2-gpt-5-4-mini round 4 (run_d5f0f9a46d4f) | gpt-5-5 | gpt-5-4-mini | gpt-5-4-mini | 120.5 |
| pair-02 pov1-gpt-5-5__pov2-gpt-5-3-codex-spark round 9 (run_d3a771ecfb06) | gpt-5-5 | gpt-5-3-codex-spark | gpt-5-5 | 120.2 |
| pair-01 pov1-gpt-5-5__pov2-gpt-5-3-codex round 1 (run_77dfc3d6098e) | gpt-5-5 | gpt-5-3-codex | gpt-5-3-codex | 120 |
| pair-03 pov1-gpt-5-5__pov2-gpt-5-4-mini round 2 (run_2b8410c034af) | gpt-5-5 | gpt-5-4-mini | gpt-5-4-mini | 96.7 |

### Shortest Rounds

| Round | P1 | P2 | Winner | duration |
| --- | --- | --- | --- | --- |
| pair-01 pov1-gpt-5-3-codex__pov2-gpt-5-5 round 4 (run_dbf1c39d78f2) | gpt-5-3-codex | gpt-5-5 | gpt-5-5 | 5.6 |
| pair-05 pov1-gpt-5-4-mini__pov2-gpt-5-3-codex round 7 (run_fcb29d6dda06) | gpt-5-4-mini | gpt-5-3-codex | gpt-5-3-codex | 5.6 |
| pair-04 pov1-gpt-5-3-codex__pov2-gpt-5-3-codex-spark round 10 (run_a32e1cd21996) | gpt-5-3-codex | gpt-5-3-codex-spark | gpt-5-3-codex | 5.7 |
| pair-01 pov1-gpt-5-3-codex__pov2-gpt-5-5 round 7 (run_db1aaf89f3a7) | gpt-5-3-codex | gpt-5-5 | gpt-5-5 | 5.8 |
| pair-01 pov1-gpt-5-3-codex__pov2-gpt-5-5 round 6 (run_ce30e6860a28) | gpt-5-3-codex | gpt-5-5 | gpt-5-5 | 5.9 |

### Largest Damage Blowouts

| Round | P1 | P2 | Winner | damage_gap |
| --- | --- | --- | --- | --- |
| pair-04 pov1-gpt-5-3-codex-spark__pov2-gpt-5-3-codex round 7 (run_78feffa1cb1a) | gpt-5-3-codex-spark | gpt-5-3-codex | gpt-5-3-codex | 125 |
| pair-03 pov1-gpt-5-5__pov2-gpt-5-4-mini round 2 (run_2b8410c034af) | gpt-5-5 | gpt-5-4-mini | gpt-5-4-mini | 115 |
| pair-01 pov1-gpt-5-5__pov2-gpt-5-3-codex round 9 (run_e043d2b3faa3) | gpt-5-5 | gpt-5-3-codex | gpt-5-5 | 110 |
| pair-01 pov1-gpt-5-5__pov2-gpt-5-3-codex round 5 (run_679ba9c92eeb) | gpt-5-5 | gpt-5-3-codex | gpt-5-5 | 100 |
| pair-01 pov1-gpt-5-5__pov2-gpt-5-3-codex round 6 (run_b6067c0d3e37) | gpt-5-5 | gpt-5-3-codex | gpt-5-5 | 100 |

