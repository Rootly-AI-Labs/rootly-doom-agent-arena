# GPT-6.1 Sol vs GPT-6 Astra

Session: `session_8734a932dd37` (September 29, 2026).

| Side | Agent | Verified session model | Reasoning | Wins |
|---|---|---|---|---:|
| Player 1 | Stapler Boss | `gpt-6.1-sol` | medium | 8 |
| Player 2 | Panic Ravioli | `gpt-6-astra` | medium | 2 |

All 10 rounds completed by elimination; no draws. This series has only one
player orientation, not the full mirrored 20-match pairing. It is supplemental
to the original 60-match GPT-6 comparison, not included in its published table.

## Model identity correction

Panic Ravioli incorrectly reported `gpt-6-sol` in readiness calls. That incorrect
label propagated into the original summaries and logs. The actual Codex
`turn_context` records identify **GPT-6 Astra, medium reasoning**.

Verified against these local rollout files in `.codex/sessions/2026/09/29/`:

- Player 1: `rollout-2026-09-29T13-33-22-01a0ee3a-6c73-7060-b768-8f0194337202.jsonl`
- Player 2: `rollout-2026-09-29T13-33-30-01a0ee3a-8b82-74c0-b0fe-cdf982e15d81.jsonl`

Original artifacts were moved without rewriting their recorded model labels. Use the
corrected identities in `session_metadata.json` when analyzing this series;
do not count these as GPT-6 Sol matches. No private rollout files were copied.

Moved from `benchmarks/results/session_8734a932dd37/` without changing round
or run IDs.

The running arena continued appending post-finish events during archival and
recreated an `events.jsonl` under the original round-10 path. That live telemetry
remains there; the ten completed round summaries are archived here. A full-file
hash comparison during the move detected concurrent changes, so this is not
claimed to be an atomic snapshot of live telemetry.
