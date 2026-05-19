# Reproducibility Metadata

Generated at: `2026-05-19T14:42:08+00:00`

This freezes metadata for the already-analyzed 120-round benchmark. No benchmark defaults were changed and no results were regenerated.

## Result Set

- Results root: `benchmarks/results`
- Total rounds: **120**
- Pair count: **6**
- Exact model labels from folder structure: `gpt-5-3-codex`, `gpt-5-3-codex-spark`, `gpt-5-4-mini`, `gpt-5-5`
- Seed policy: `single recorded seed reused for all rounds`
- Seed list: `[42]`
- Scenario ID: `duel_e1m8`
- Arena mode: `duel`

## Recorded Parameters

- `timeout_seconds`: `[120]`
- `intent_duration_ms`: `[25000]`
- `decision_cadence_ms`: `[750]`
- Starting health: `UNKNOWN`
- Starting health note: Starting health is not explicitly recorded in config.json or summary.json for these run artifacts.
- Config `total_rounds` note: config.json total_rounds varies because some POV batches were run/resumed in chunks; validated folder coverage is 10 rounds per POV and 120 total rounds.

## Unknown Fields

- `model_version_or_build_ids`
- `reasoning_setting_by_model`
- `browser_runtime_environment`
- `docker_or_native_execution_mode_recorded_in_results`
- `starting_health`
- `map_or_arena_name beyond scenario_id`

## Prompt Template

- Source file: `scripts/doom_arena_duel_prompts.py`
- Source SHA256: `4662B0BF217D67F129AF0D0A097ECA67AE8C6A27C23F8A4127B45738865C2A3B`
- Source function: `instructions(...) in scripts/doom_arena_duel_prompts.py`
- Generated prompt files: **240**
- Redacted prompt hash variants: **2**
- Token-bearing prompt text is not duplicated here; controller tokens are redacted before prompt hashing.

## Git State

- Backend commit hash: `5a30d39399c310fe8e85f651f2d6c870d2c58ece`
- Working tree state: `dirty`
- Analysis script commit hash: `UNCOMMITTED_OR_UNTRACKED`

### Git Status

```text
M .dockerignore
 M Dockerfile
 M README.md
 M docs/build.md
 M docs/docker.md
 M docs/smoke-tests.md
 D scripts/build.sh
 D scripts/clean.sh
 D scripts/print_latest_mcp_instructions.py
 D scripts/smoke_arena_api.py
 M scripts/smoke_docker_setup.py
 D scripts/smoke_mcp_duel_tools.py
 M src/doom/arena_duel.c
 M src/doom/arena_enemies.c
 M src/index.html
?? analysis/
?? docs/benchmark-paper-draft.md
?? scripts/generate_paper_results.py
?? scripts/normalize_benchmark_results.py
```

## Script Versions

- `scripts/normalize_benchmark_results.py`: `D26DB3E9F546D7603F4E59F2CE4865D4C3798F270CFD430D5A2FB2346A2B9F04`
- `scripts/generate_paper_results.py`: `E2314AC0B67314D194EB68744EF1A95D9FAB33E25F0D0E24418215655ADAF67D`
- `scripts/doom_arena_server.py`: `C06F6DC1EC9B878631A3EB3D8C3F5BA17D30EBBA4DA9F7B9C9DE25F00295A12D`
- `scripts/doom_arena_duel_prompts.py`: `4662B0BF217D67F129AF0D0A097ECA67AE8C6A27C23F8A4127B45738865C2A3B`
- `scripts/doom_arena_mcp.py`: `3CFC378C5C8BC542131C7544167FD73D8A3F57F056CBB95E55EE04FC2472C57E`

## Runtime Assets

- `src/index.html`: `AF7BC80212A80E8547F4201E71FA992990E8A5DD6BF742861BDC7305312572E0`
- `src/websockets-doom.html`: `2EF69C4E6FFD07C5827AE74440635334A52FE7157A216C962CB5FE1B4770AE26`
- `src/websockets-doom.js`: `2738B7694A24872BD8DE62CC4BD81EAF5B15FC063778B1156337AACA56260DCE`
- `src/websockets-doom.wasm`: `A017847C9887B48DD5708A6EB91490029F969946AEC7643C89DE8779376FAD79`
- `Dockerfile`: `92108C5FACBC2E63A87634637E599643DA46C559C37650FA96EF6BA400E2290E`
- `docker-compose.yml`: `17C17599DE0C954BAFC858496A18BD54343DECD6D7EA9FF786A6C2092C079400`

## Environment

- OS: `{'Caption': 'Microsoft Windows 11 Home', 'Version': '10.0.26200', 'BuildNumber': '26200', 'OSArchitecture': '64-bit', 'TotalVisibleMemorySize': 16615136}`
- CPU: `{'Name': 'Intel(R) Core(TM) i5-14400F', 'NumberOfCores': 10, 'NumberOfLogicalProcessors': 16, 'MaxClockSpeed': 2500}`
- Python: `Python 3.12.10`
- Docker available now: `Docker version 29.1.3, build f52814d`
- Docker Compose available now: `Docker Compose version v5.0.0-desktop.1`
- Browser/runtime environment used for benchmark: `UNKNOWN`
- Docker/native execution mode recorded in results: `UNKNOWN`

## Result Folder Paths

- `benchmarks/results/pair-01__gpt-5-5-vs-gpt-5-3-codex` (20 rounds)
  - `benchmarks/results/pair-01__gpt-5-5-vs-gpt-5-3-codex/pov1-gpt-5-3-codex__pov2-gpt-5-5` (10 rounds)
  - `benchmarks/results/pair-01__gpt-5-5-vs-gpt-5-3-codex/pov1-gpt-5-5__pov2-gpt-5-3-codex` (10 rounds)
- `benchmarks/results/pair-02__gpt-5-5-vs-gpt-5-3-codex-spark` (20 rounds)
  - `benchmarks/results/pair-02__gpt-5-5-vs-gpt-5-3-codex-spark/pov1-gpt-5-3-codex-spark__pov2-gpt-5-5` (10 rounds)
  - `benchmarks/results/pair-02__gpt-5-5-vs-gpt-5-3-codex-spark/pov1-gpt-5-5__pov2-gpt-5-3-codex-spark` (10 rounds)
- `benchmarks/results/pair-03__gpt-5-5-vs-gpt-5-4-mini` (20 rounds)
  - `benchmarks/results/pair-03__gpt-5-5-vs-gpt-5-4-mini/pov1-gpt-5-4-mini__pov2-gpt-5-5` (10 rounds)
  - `benchmarks/results/pair-03__gpt-5-5-vs-gpt-5-4-mini/pov1-gpt-5-5__pov2-gpt-5-4-mini` (10 rounds)
- `benchmarks/results/pair-04__gpt-5-3-codex-vs-gpt-5-3-codex-spark` (20 rounds)
  - `benchmarks/results/pair-04__gpt-5-3-codex-vs-gpt-5-3-codex-spark/pov1-gpt-5-3-codex-spark__pov2-gpt-5-3-codex` (10 rounds)
  - `benchmarks/results/pair-04__gpt-5-3-codex-vs-gpt-5-3-codex-spark/pov1-gpt-5-3-codex__pov2-gpt-5-3-codex-spark` (10 rounds)
- `benchmarks/results/pair-05__gpt-5-3-codex-vs-gpt-5-4-mini` (20 rounds)
  - `benchmarks/results/pair-05__gpt-5-3-codex-vs-gpt-5-4-mini/pov1-gpt-5-3-codex__pov2-gpt-5-4-mini` (10 rounds)
  - `benchmarks/results/pair-05__gpt-5-3-codex-vs-gpt-5-4-mini/pov1-gpt-5-4-mini__pov2-gpt-5-3-codex` (10 rounds)
- `benchmarks/results/pair-06__gpt-5-3-codex-spark-vs-gpt-5-4-mini` (20 rounds)
  - `benchmarks/results/pair-06__gpt-5-3-codex-spark-vs-gpt-5-4-mini/pov1-gpt-5-3-codex-spark__pov2-gpt-5-4-mini` (10 rounds)
  - `benchmarks/results/pair-06__gpt-5-3-codex-spark-vs-gpt-5-4-mini/pov1-gpt-5-4-mini__pov2-gpt-5-3-codex-spark` (10 rounds)

Full round-folder inventory is stored in `analysis/reproducibility_metadata.json`.
