# Intent Lifecycle Summary

Lifecycle metrics are attributed by participant when the raw record contains participant IDs. Supersession and expiry-before-next are computed from accepted intent timestamps for the same participant.

Model-level MCP/tool reliability excludes run-level calls that cannot be attributed to `player_1` or `player_2`.

The recorded stale continuation fields in `stats.json` are round-level summaries, not participant-level fields. The CSV therefore marks stale continuation as `round_level_not_participant_attributed`.

## Per-Model Lifecycle

### gpt-5-3-codex

- Accepted intents: **94**; superseded before expiry: **33**.
- Mean unused duration after supersession: **41687.03 ms**.
- Expired-before-next count: **1**; mean gap after expiry: **4161.00 ms**.
- Participant-specific `intent_expired` events: **1**.
- Invalid sequence count: **4**.
- MCP/tool error rate: **15.31%**; post-finish rejections: **60**.
- Mean MCP/tool latency: **4.519 ms**.

### gpt-5-3-codex-spark

- Accepted intents: **329**; superseded before expiry: **268**.
- Mean unused duration after supersession: **41019.43 ms**.
- Expired-before-next count: **1**; mean gap after expiry: **1520.00 ms**.
- Participant-specific `intent_expired` events: **2**.
- Invalid sequence count: **1**.
- MCP/tool error rate: **5.86%**; post-finish rejections: **46**.
- Mean MCP/tool latency: **5.286 ms**.

### gpt-5-4-mini

- Accepted intents: **180**; superseded before expiry: **119**.
- Mean unused duration after supersession: **39994.92 ms**.
- Expired-before-next count: **1**; mean gap after expiry: **5961.00 ms**.
- Participant-specific `intent_expired` events: **1**.
- Invalid sequence count: **3**.
- MCP/tool error rate: **11.43%**; post-finish rejections: **72**.
- Mean MCP/tool latency: **4.925 ms**.

### gpt-5-5

- Accepted intents: **150**; superseded before expiry: **88**.
- Mean unused duration after supersession: **27720.49 ms**.
- Expired-before-next count: **2**; mean gap after expiry: **17682.50 ms**.
- Participant-specific `intent_expired` events: **3**.
- Invalid sequence count: **1**.
- MCP/tool error rate: **11.39%**; post-finish rejections: **62**.
- Mean MCP/tool latency: **4.740 ms**.

## Safest Behavioral Findings For The Paper

- Total invalid sequence count across model-attributed accepted intents/errors: **9**.
- Total post-finish rejections: **240**; these are endpoint lifecycle rejections after the match had already finished, not necessarily arena failures.
- Overlapping MCP calls recorded: **0**.
- Participant-specific `intent_expired` events recorded: **7**.
- Lowest MCP/tool error rate in this aggregate: **gpt-5-3-codex-spark** at **5.86%**.
- Lowest mean MCP/tool latency in this aggregate: **gpt-5-3-codex** at **4.519 ms**.

## Tentative Findings

- Supersession rates are meaningful as a measure of how often agents refreshed active tactical policies before expiry.
- Expired-before-next and stale continuation are rare, but stale duration should be treated cautiously because stale extension duration is only recorded at round level.

## Appendix-Only Metrics

- Round-level stale continuation counts and mean stale time are suitable for appendix diagnostics, not model ranking.
- Local MCP/tool latency is server/proxy latency, not model think time; it is a reliability/control-plane metric.
- Post-finish rejections should be reported as lifecycle hygiene rather than model quality.
