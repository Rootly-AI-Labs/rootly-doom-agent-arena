# Benchmark Normalization Validation Report

Generated at: `2026-05-19T13:58:34+00:00`

## Summary

- Total discovered rounds: **120**
- Pair folders: **6**
- Missing rounds: **0**
- Corrupted rounds: **0**
- Incomplete rounds: **0**
- Mirrored coverage validation: **PASS**

## Rounds Per Pair

- `pair-01`: 20
- `pair-02`: 20
- `pair-03`: 20
- `pair-04`: 20
- `pair-05`: 20
- `pair-06`: 20

## Rounds Per Model

- `gpt-5-3-codex`: 60
- `gpt-5-3-codex-spark`: 60
- `gpt-5-4-mini`: 60
- `gpt-5-5`: 60

## Pair Validation

### `pair-01__gpt-5-5-vs-gpt-5-3-codex`

- Pair ID: `pair-01`
- Model A: `gpt-5-5`
- Model B: `gpt-5-3-codex`
- Mirrored POV folders: `PASS`
- POV folders discovered: `pov1-gpt-5-3-codex__pov2-gpt-5-5`, `pov1-gpt-5-5__pov2-gpt-5-3-codex`
- Round folders discovered: 20

### `pair-02__gpt-5-5-vs-gpt-5-3-codex-spark`

- Pair ID: `pair-02`
- Model A: `gpt-5-5`
- Model B: `gpt-5-3-codex-spark`
- Mirrored POV folders: `PASS`
- POV folders discovered: `pov1-gpt-5-3-codex-spark__pov2-gpt-5-5`, `pov1-gpt-5-5__pov2-gpt-5-3-codex-spark`
- Round folders discovered: 20

### `pair-03__gpt-5-5-vs-gpt-5-4-mini`

- Pair ID: `pair-03`
- Model A: `gpt-5-5`
- Model B: `gpt-5-4-mini`
- Mirrored POV folders: `PASS`
- POV folders discovered: `pov1-gpt-5-4-mini__pov2-gpt-5-5`, `pov1-gpt-5-5__pov2-gpt-5-4-mini`
- Round folders discovered: 20

### `pair-04__gpt-5-3-codex-vs-gpt-5-3-codex-spark`

- Pair ID: `pair-04`
- Model A: `gpt-5-3-codex`
- Model B: `gpt-5-3-codex-spark`
- Mirrored POV folders: `PASS`
- POV folders discovered: `pov1-gpt-5-3-codex-spark__pov2-gpt-5-3-codex`, `pov1-gpt-5-3-codex__pov2-gpt-5-3-codex-spark`
- Round folders discovered: 20

### `pair-05__gpt-5-3-codex-vs-gpt-5-4-mini`

- Pair ID: `pair-05`
- Model A: `gpt-5-3-codex`
- Model B: `gpt-5-4-mini`
- Mirrored POV folders: `PASS`
- POV folders discovered: `pov1-gpt-5-3-codex__pov2-gpt-5-4-mini`, `pov1-gpt-5-4-mini__pov2-gpt-5-3-codex`
- Round folders discovered: 20

### `pair-06__gpt-5-3-codex-spark-vs-gpt-5-4-mini`

- Pair ID: `pair-06`
- Model A: `gpt-5-3-codex-spark`
- Model B: `gpt-5-4-mini`
- Mirrored POV folders: `PASS`
- POV folders discovered: `pov1-gpt-5-3-codex-spark__pov2-gpt-5-4-mini`, `pov1-gpt-5-4-mini__pov2-gpt-5-3-codex-spark`
- Round folders discovered: 20

## Round Issues

No round-level issues detected.

## Schema Differences

- `config.json`: 1 schema variant(s)
- `controller_tokens.json`: 1 schema variant(s)
- `events.jsonl`: 1 schema variant(s)
- `stats.json`: 53 schema variant(s)
  - `0269546057c9` count=1 example=`benchmarks\results\pair-01__gpt-5-5-vs-gpt-5-3-codex\pov1-gpt-5-3-codex__pov2-gpt-5-5\round_07_run_db1aaf89f3a7`
  - `055fcd65a462` count=1 example=`benchmarks\results\pair-04__gpt-5-3-codex-vs-gpt-5-3-codex-spark\pov1-gpt-5-3-codex__pov2-gpt-5-3-codex-spark\round_06_run_4427012e55c1`
  - `08ce8f7a25fc` count=1 example=`benchmarks\results\pair-05__gpt-5-3-codex-vs-gpt-5-4-mini\pov1-gpt-5-3-codex__pov2-gpt-5-4-mini\round_09_run_8036a990ba9f`
  - `0a50bec750cf` count=2 example=`benchmarks\results\pair-06__gpt-5-3-codex-spark-vs-gpt-5-4-mini\pov1-gpt-5-4-mini__pov2-gpt-5-3-codex-spark\round_01_run_6877e36cf52e`
  - `1774ba8987f0` count=1 example=`benchmarks\results\pair-03__gpt-5-5-vs-gpt-5-4-mini\pov1-gpt-5-4-mini__pov2-gpt-5-5\round_08_run_93783caf6a59`
  - `192419de0bbd` count=1 example=`benchmarks\results\pair-02__gpt-5-5-vs-gpt-5-3-codex-spark\pov1-gpt-5-3-codex-spark__pov2-gpt-5-5\round_10_run_3cec84cc9310`
  - `19d7864da23f` count=1 example=`benchmarks\results\pair-06__gpt-5-3-codex-spark-vs-gpt-5-4-mini\pov1-gpt-5-3-codex-spark__pov2-gpt-5-4-mini\round_10_run_73bcb99bef70`
  - `2c96097c213f` count=1 example=`benchmarks\results\pair-04__gpt-5-3-codex-vs-gpt-5-3-codex-spark\pov1-gpt-5-3-codex__pov2-gpt-5-3-codex-spark\round_01_run_c35c169d0d90`
  - `2d46dc5dc3c1` count=1 example=`benchmarks\results\pair-06__gpt-5-3-codex-spark-vs-gpt-5-4-mini\pov1-gpt-5-4-mini__pov2-gpt-5-3-codex-spark\round_10_run_0ee7d4784cb2`
  - `443eb26d9e08` count=5 example=`benchmarks\results\pair-01__gpt-5-5-vs-gpt-5-3-codex\pov1-gpt-5-5__pov2-gpt-5-3-codex\round_03_run_9c3ace6644c8`
  - `450e11e643ad` count=1 example=`benchmarks\results\pair-04__gpt-5-3-codex-vs-gpt-5-3-codex-spark\pov1-gpt-5-3-codex-spark__pov2-gpt-5-3-codex\round_08_run_6263eddd5dc9`
  - `53fbcb266cbf` count=1 example=`benchmarks\results\pair-02__gpt-5-5-vs-gpt-5-3-codex-spark\pov1-gpt-5-3-codex-spark__pov2-gpt-5-5\round_09_run_9f0679ae0a73`
  - `5b08a658d002` count=4 example=`benchmarks\results\pair-02__gpt-5-5-vs-gpt-5-3-codex-spark\pov1-gpt-5-5__pov2-gpt-5-3-codex-spark\round_01_run_2eaf4daa8320`
  - `60eb6b486c7a` count=1 example=`benchmarks\results\pair-05__gpt-5-3-codex-vs-gpt-5-4-mini\pov1-gpt-5-3-codex__pov2-gpt-5-4-mini\round_10_run_95cb42613e30`
  - `61cc01da5a93` count=1 example=`benchmarks\results\pair-03__gpt-5-5-vs-gpt-5-4-mini\pov1-gpt-5-4-mini__pov2-gpt-5-5\round_10_run_d2d24ce0aa48`
  - `6d221f00a417` count=1 example=`benchmarks\results\pair-04__gpt-5-3-codex-vs-gpt-5-3-codex-spark\pov1-gpt-5-3-codex__pov2-gpt-5-3-codex-spark\round_10_run_a32e1cd21996`
  - `6ec33525ee37` count=2 example=`benchmarks\results\pair-03__gpt-5-5-vs-gpt-5-4-mini\pov1-gpt-5-4-mini__pov2-gpt-5-5\round_02_run_552e35670869`
  - `715d32753949` count=1 example=`benchmarks\results\pair-02__gpt-5-5-vs-gpt-5-3-codex-spark\pov1-gpt-5-5__pov2-gpt-5-3-codex-spark\round_07_run_9db79dd9b764`
  - `72f7a97afcc6` count=1 example=`benchmarks\results\pair-03__gpt-5-5-vs-gpt-5-4-mini\pov1-gpt-5-4-mini__pov2-gpt-5-5\round_09_run_708b76c47d46`
  - `761f5fb7618c` count=9 example=`benchmarks\results\pair-02__gpt-5-5-vs-gpt-5-3-codex-spark\pov1-gpt-5-5__pov2-gpt-5-3-codex-spark\round_02_run_87df713f8ac8`
  - `7751261360f0` count=4 example=`benchmarks\results\pair-02__gpt-5-5-vs-gpt-5-3-codex-spark\pov1-gpt-5-3-codex-spark__pov2-gpt-5-5\round_01_run_4e59c2b09285`
  - `78c17c83c3a4` count=1 example=`benchmarks\results\pair-02__gpt-5-5-vs-gpt-5-3-codex-spark\pov1-gpt-5-5__pov2-gpt-5-3-codex-spark\round_09_run_d3a771ecfb06`
  - `7cdd77e8d3ed` count=1 example=`benchmarks\results\pair-05__gpt-5-3-codex-vs-gpt-5-4-mini\pov1-gpt-5-3-codex__pov2-gpt-5-4-mini\round_03_run_3fb565f27bcc`
  - `804b098deaa6` count=3 example=`benchmarks\results\pair-02__gpt-5-5-vs-gpt-5-3-codex-spark\pov1-gpt-5-5__pov2-gpt-5-3-codex-spark\round_06_run_f9accada17be`
  - `828349e57b5b` count=1 example=`benchmarks\results\pair-03__gpt-5-5-vs-gpt-5-4-mini\pov1-gpt-5-5__pov2-gpt-5-4-mini\round_04_run_d5f0f9a46d4f`
  - `870bed22a8d5` count=2 example=`benchmarks\results\pair-01__gpt-5-5-vs-gpt-5-3-codex\pov1-gpt-5-5__pov2-gpt-5-3-codex\round_10_run_43fcef4843bd`
  - `88d7c4268cc7` count=1 example=`benchmarks\results\pair-05__gpt-5-3-codex-vs-gpt-5-4-mini\pov1-gpt-5-3-codex__pov2-gpt-5-4-mini\round_08_run_55087a206459`
  - `8cb160a04206` count=1 example=`benchmarks\results\pair-02__gpt-5-5-vs-gpt-5-3-codex-spark\pov1-gpt-5-3-codex-spark__pov2-gpt-5-5\round_03_run_5e285673ccc4`
  - `8f3a57455be0` count=1 example=`benchmarks\results\pair-06__gpt-5-3-codex-spark-vs-gpt-5-4-mini\pov1-gpt-5-3-codex-spark__pov2-gpt-5-4-mini\round_09_run_44b834308a0f`
  - `8f7e38fc68af` count=1 example=`benchmarks\results\pair-04__gpt-5-3-codex-vs-gpt-5-3-codex-spark\pov1-gpt-5-3-codex__pov2-gpt-5-3-codex-spark\round_02_run_21169cec43cb`
  - `a0f922e520bb` count=2 example=`benchmarks\results\pair-01__gpt-5-5-vs-gpt-5-3-codex\pov1-gpt-5-3-codex__pov2-gpt-5-5\round_05_run_92675153319c`
  - `a3fb0ec0c5a9` count=3 example=`benchmarks\results\pair-04__gpt-5-3-codex-vs-gpt-5-3-codex-spark\pov1-gpt-5-3-codex-spark__pov2-gpt-5-3-codex\round_02_run_5b3b7caf303b`
  - `a5fac4d7a590` count=1 example=`benchmarks\results\pair-01__gpt-5-5-vs-gpt-5-3-codex\pov1-gpt-5-5__pov2-gpt-5-3-codex\round_01_run_77dfc3d6098e`
  - `a751e121813f` count=2 example=`benchmarks\results\pair-06__gpt-5-3-codex-spark-vs-gpt-5-4-mini\pov1-gpt-5-4-mini__pov2-gpt-5-3-codex-spark\round_05_run_c02f48a5c510`
  - `a7924eab6e22` count=5 example=`benchmarks\results\pair-02__gpt-5-5-vs-gpt-5-3-codex-spark\pov1-gpt-5-5__pov2-gpt-5-3-codex-spark\round_10_run_6bf1f1132c16`
  - `adb8574bc4fa` count=1 example=`benchmarks\results\pair-01__gpt-5-5-vs-gpt-5-3-codex\pov1-gpt-5-3-codex__pov2-gpt-5-5\round_06_run_ce30e6860a28`
  - `aff13c9f9222` count=9 example=`benchmarks\results\pair-03__gpt-5-5-vs-gpt-5-4-mini\pov1-gpt-5-4-mini__pov2-gpt-5-5\round_07_run_a37065ecc456`
  - `b2a481803f18` count=1 example=`benchmarks\results\pair-02__gpt-5-5-vs-gpt-5-3-codex-spark\pov1-gpt-5-3-codex-spark__pov2-gpt-5-5\round_04_run_87fb166f0141`
  - `b7b3678c3f31` count=2 example=`benchmarks\results\pair-01__gpt-5-5-vs-gpt-5-3-codex\pov1-gpt-5-3-codex__pov2-gpt-5-5\round_02_run_a8837d6afe36`
  - `ce6a5d5ebafe` count=1 example=`benchmarks\results\pair-02__gpt-5-5-vs-gpt-5-3-codex-spark\pov1-gpt-5-3-codex-spark__pov2-gpt-5-5\round_07_run_1568800276ac`
  - `cf16cd654906` count=2 example=`benchmarks\results\pair-02__gpt-5-5-vs-gpt-5-3-codex-spark\pov1-gpt-5-3-codex-spark__pov2-gpt-5-5\round_02_run_151fe4f4664e`
  - `d2d56ecf904e` count=1 example=`benchmarks\results\pair-06__gpt-5-3-codex-spark-vs-gpt-5-4-mini\pov1-gpt-5-3-codex-spark__pov2-gpt-5-4-mini\round_07_run_3d39d2007d0a`
  - `d3b0df2910a9` count=1 example=`benchmarks\results\pair-02__gpt-5-5-vs-gpt-5-3-codex-spark\pov1-gpt-5-3-codex-spark__pov2-gpt-5-5\round_06_run_403c7c9ea2e2`
  - `d6587d5f6cef` count=1 example=`benchmarks\results\pair-04__gpt-5-3-codex-vs-gpt-5-3-codex-spark\pov1-gpt-5-3-codex__pov2-gpt-5-3-codex-spark\round_08_run_cc2d52babe1c`
  - `d6e46d68ef44` count=1 example=`benchmarks\results\pair-03__gpt-5-5-vs-gpt-5-4-mini\pov1-gpt-5-5__pov2-gpt-5-4-mini\round_09_run_f9bde5da490a`
  - `d9cf2ba0dc1c` count=3 example=`benchmarks\results\pair-01__gpt-5-5-vs-gpt-5-3-codex\pov1-gpt-5-3-codex__pov2-gpt-5-5\round_04_run_dbf1c39d78f2`
  - `d9e98d9951f3` count=1 example=`benchmarks\results\pair-02__gpt-5-5-vs-gpt-5-3-codex-spark\pov1-gpt-5-5__pov2-gpt-5-3-codex-spark\round_08_run_5e7f8e292e7b`
  - `e348381bd42c` count=1 example=`benchmarks\results\pair-04__gpt-5-3-codex-vs-gpt-5-3-codex-spark\pov1-gpt-5-3-codex__pov2-gpt-5-3-codex-spark\round_03_run_e93c0acc3f36`
  - `e59746b8523e` count=1 example=`benchmarks\results\pair-04__gpt-5-3-codex-vs-gpt-5-3-codex-spark\pov1-gpt-5-3-codex__pov2-gpt-5-3-codex-spark\round_04_run_aef8a7d264d1`
  - `e7afe1e33836` count=1 example=`benchmarks\results\pair-05__gpt-5-3-codex-vs-gpt-5-4-mini\pov1-gpt-5-4-mini__pov2-gpt-5-3-codex\round_09_run_dd7a4c04e6f8`
  - `ecc8277b0450` count=1 example=`benchmarks\results\pair-04__gpt-5-3-codex-vs-gpt-5-3-codex-spark\pov1-gpt-5-3-codex-spark__pov2-gpt-5-3-codex\round_01_run_fa896c430fe6`
  - `f2ae17005ac1` count=25 example=`benchmarks\results\pair-01__gpt-5-5-vs-gpt-5-3-codex\pov1-gpt-5-3-codex__pov2-gpt-5-5\round_01_run_89bc9ee7f178`
  - `f70197a93ccf` count=1 example=`benchmarks\results\pair-04__gpt-5-3-codex-vs-gpt-5-3-codex-spark\pov1-gpt-5-3-codex__pov2-gpt-5-3-codex-spark\round_09_run_9d7e871d6020`
- `summary.json`: 1 schema variant(s)
