# Results and Discussion Merge Summary

Updated `docs/benchmark-paper-draft.md` to merge the former standalone Results and Discussion sections into a single integrated `## 7. Results and Discussion` section.

Changes made:

- Renamed the section to `## 7. Results and Discussion`.
- Reorganized result subsections into:
  - `7.1 Overall Competitive Performance`
  - `7.2 Pairwise Matchup Structure`
  - `7.3 Side Bias and Mirrored Evaluation`
  - `7.4 Reliability and Latency Tradeoffs`
  - `7.5 Tactical Behavior and Policy Diversity`
  - `7.6 Intent Lifecycle`
  - `7.7 Damage Differential`
- Moved non-duplicated interpretation from the old Discussion section into the relevant result subsections.
- Preserved existing numeric results, tables, figure references, and captions.
- Added immediate interpretation and caveats after each core result table.
- Emphasized mirrored win rate as the primary metric because of the measured player-side bias.
- Clarified that mirrored evaluation balances side exposure but does not remove the underlying arena asymmetry.
- Clarified that `gpt-5-3-codex-spark` had the strongest latency/reliability profile but weakest combat performance.
- Clarified that local MCP/tool latency is not model reasoning latency.
- Framed tactical diversity, intent cadence, and lifecycle behavior as separate dimensions from raw combat performance.
- Renumbered the remaining sections:
  - `## 8. Limitations`
  - `## 9. Future Work`
  - `## 10. Conclusion`

No benchmark results, defaults, analysis CSVs, or generated figures were regenerated or modified.
