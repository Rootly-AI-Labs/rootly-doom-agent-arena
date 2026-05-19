# Model Summary

Strongest model by mirrored win rate: **gpt-5-5** (58.3%).
Best simple latency-performance ratio: **gpt-5-3-codex-spark**. This ratio uses mirrored win rate divided by average inferred decision latency, so it is only a first-pass heuristic.
Strongest MCP reliability by lowest error rate: **gpt-5-3-codex-spark** (5.9%).

## Aggregate Metrics

| Model | Rounds | Wins | Losses | Draws | Raw WR | Mirrored WR | P1 WR | P2 WR | Avg Dmg Diff | Avg Final HP | Timeout Rate | Best Matchup | Worst Matchup | Elo-Style |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gpt-5-5 | 60 | 35 | 25 | 0 | 58.3% | 58.3% | 36.7% | 80.0% | 10.167 | 29.75 | 6.7% | gpt-5-3-codex (85.0%) | gpt-5-4-mini (35.0%) | 1542.2 |
| gpt-5-4-mini | 60 | 34 | 26 | 0 | 56.7% | 56.7% | 26.7% | 86.7% | 7.333 | 20.917 | 1.7% | gpt-5-5 (65.0%) | gpt-5-3-codex-spark (45.0%) | 1533.7 |
| gpt-5-3-codex | 60 | 28 | 32 | 0 | 46.7% | 46.7% | 23.3% | 70.0% | -4.167 | 16.917 | 1.7% | gpt-5-3-codex-spark (85.0%) | gpt-5-5 (15.0%) | 1483.3 |
| gpt-5-3-codex-spark | 60 | 23 | 37 | 0 | 38.3% | 38.3% | 16.7% | 60.0% | -13.333 | 10.75 | 3.3% | gpt-5-4-mini (55.0%) | gpt-5-3-codex (15.0%) | 1440.8 |

## Reliability

Stale intent counts and durations are model stale-exposure values because the normalized CSV stores stale policy metrics at the round level, not exact per-agent attribution.

| Model | MCP Calls | Completed | Errors | Error Rate | Stale Exposure | Stale Duration ms | Avg Decision ms | P95 Decision ms |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gpt-5-3-codex | 405 | 343 | 62 | 15.3% | 3 | 24177 | 8444.043 | 28214 |
| gpt-5-3-codex-spark | 972 | 915 | 57 | 5.9% | 4 | 29815 | 3437.623 | 14250 |
| gpt-5-4-mini | 630 | 558 | 72 | 11.4% | 2 | 32422 | 7054.294 | 24612 |
| gpt-5-5 | 562 | 498 | 64 | 11.4% | 5 | 71452 | 6513.93 | 14120 |

## Codex-Specialized vs General

In cross-family rounds, codex-specialized models won **31** and general models won **49**.
Codex-specialized cross-family win rate: **38.8%**.

## Latency and Failure Outliers

### High Latency Rounds

| Round | P1 | P2 | Winner | max_p95_latency |
| --- | --- | --- | --- | --- |
| pair-05 pov1-gpt-5-3-codex__pov2-gpt-5-4-mini round 2 (run_8ca2e1afb66a) | gpt-5-3-codex | gpt-5-4-mini | gpt-5-4-mini | 66058 |
| pair-03 pov1-gpt-5-5__pov2-gpt-5-4-mini round 2 (run_2b8410c034af) | gpt-5-5 | gpt-5-4-mini | gpt-5-4-mini | 49628 |
| pair-06 pov1-gpt-5-4-mini__pov2-gpt-5-3-codex-spark round 8 (run_6502adb77361) | gpt-5-4-mini | gpt-5-3-codex-spark | gpt-5-4-mini | 40509 |
| pair-05 pov1-gpt-5-4-mini__pov2-gpt-5-3-codex round 9 (run_dd7a4c04e6f8) | gpt-5-4-mini | gpt-5-3-codex | gpt-5-4-mini | 32674 |
| pair-05 pov1-gpt-5-3-codex__pov2-gpt-5-4-mini round 9 (run_8036a990ba9f) | gpt-5-3-codex | gpt-5-4-mini | gpt-5-4-mini | 28214 |

### High MCP Failure Rounds

| Round | P1 | P2 | Winner | mcp_errors |
| --- | --- | --- | --- | --- |
| pair-06 pov1-gpt-5-4-mini__pov2-gpt-5-3-codex-spark round 10 (run_0ee7d4784cb2) | gpt-5-4-mini | gpt-5-3-codex-spark | gpt-5-3-codex-spark | 6 |
| pair-06 pov1-gpt-5-3-codex-spark__pov2-gpt-5-4-mini round 1 (run_350b09b50a27) | gpt-5-3-codex-spark | gpt-5-4-mini | gpt-5-4-mini | 5 |
| pair-01 pov1-gpt-5-5__pov2-gpt-5-3-codex round 2 (run_7ee902da7593) | gpt-5-5 | gpt-5-3-codex | gpt-5-3-codex | 4 |
| pair-02 pov1-gpt-5-5__pov2-gpt-5-3-codex-spark round 1 (run_2eaf4daa8320) | gpt-5-5 | gpt-5-3-codex-spark | gpt-5-3-codex-spark | 4 |
| pair-02 pov1-gpt-5-5__pov2-gpt-5-3-codex-spark round 5 (run_d0fdab713de5) | gpt-5-5 | gpt-5-3-codex-spark | gpt-5-3-codex-spark | 4 |

