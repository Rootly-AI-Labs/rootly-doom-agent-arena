# MCP Duel Runbook

This is the current setup for a real Codex-vs-Claude Doom Arena duel.

## Terminal Layout

Use four active surfaces:

- Terminal 1: arena server
- Browser: Doom/WASM duel tab
- Terminal 2: orchestrator
- Chat/terminal 3 and 4: Codex and Claude agents

## Clean Start

Optional cleanup if port `8001` is already occupied:

```powershell
Get-NetTCPConnection -LocalPort 8001 -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty OwningProcess -Unique |
  ForEach-Object { Stop-Process -Id $_ -Force }
```

## Terminal 1: Server

```powershell
py scripts\doom_arena_server.py --port 8001
```

Keep this terminal running.

The server prints the MCP client command and exposes it at:

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8001/api/arena/mcp-config
```

## Browser

Open and keep this tab running:

```text
http://127.0.0.1:8001/?duel=1
```

Do not click `Start Duel` again after the orchestrator resets a run. The browser exports WASM state into `src/arena_game_state.local.tsv`.

## Terminal 2: Orchestrator

```powershell
py scripts\doom_arena_mcp_duel_orchestrator.py `
  --server-url http://127.0.0.1:8001 `
  --player-1-model codex `
  --player-2-model claude `
  --round 1 `
  --seed 42 `
  --timeout-seconds 120 `
  --decision-interval-ms 750 `
  --decision-cadence-ms 750 `
  --intent-duration-ms 2500 `
  --max-steps 190 `
  --state-wait-timeout-seconds 60
```

The orchestrator resets the duel and prints paths like:

```text
benchmarks/results/<run_id>/player_1_mcp_instructions.md
benchmarks/results/<run_id>/player_2_mcp_instructions.md
benchmarks/results/<run_id>/controller_tokens.json
```

It also writes:

```text
src/arena_controller_tokens.local.json
```

## Chat 3: Codex

Open a Codex chat with the repo-level `doom-arena` MCP server connected. Paste the generated `player_1_mcp_instructions.md`, then say:

```text
Run the MCP loop using your assigned instructions until the match finishes.
```

## Chat 4: Claude

Open Claude Code separately in the repo:

```powershell
cd C:\Users\muhha\OneDrive\Desktop\doom-wasm
claude
```

Confirm `/mcp` shows `doom-arena`, paste `player_2_mcp_instructions.md`, then say:

```text
Run the MCP loop using your assigned instructions until the match finishes.
```

## MCP Tool Check

Both agents should see these normal control tools:

```text
get_participant_observation
set_participant_intent
stop_participant_intent
get_match_result
get_duel_events
```

Low-level movement tools are hidden by default. For local debugging only, expose them by launching the MCP server with:

```powershell
$env:DOOM_ARENA_EXPOSE_LOW_LEVEL_MCP="1"
```

## Ready Gate

The duel starts in:

```text
phase=waiting_for_agents
```

Doom freezes both participants until both agents have active `set_participant_intent` rows. This prevents one agent from moving before the other is connected.

## One-Command Bootstrap

This starts the server, opens the browser, runs the orchestrator, and keeps the server alive:

```powershell
py scripts\start_doom_arena_duel.py --keep-server
```

It still does not self-play by default. Use this only for local scripted smoke testing without real LLMs:

```powershell
py scripts\start_doom_arena_duel.py --keep-server --rolling-control
```

## Run-Id Mismatch Fix

If you see a mismatch like:

```text
expected run_id: run_A
latest state run_id: run_B
```

Do this:

1. Stop extra servers/orchestrators on `8001`.
2. Hard refresh `http://127.0.0.1:8001/?duel=1`.
3. Rerun the orchestrator.
4. Use only the newly printed instruction files and tokens.

Do not reuse older prompts after a reset.
