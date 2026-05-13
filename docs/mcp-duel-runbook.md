# MCP Duel Runbook

This is the current setup for a real Codex-vs-Claude Doom Arena duel.

## Terminal Layout

Use three active surfaces:

- Terminal 1: arena server/browser launcher
- Browser: Doom/WASM duel tab with copyable MCP prompts
- Chat/terminal 2 and 3: Codex and Claude agents

## Clean Start

Optional cleanup if port `8001` is already occupied:

```powershell
Get-NetTCPConnection -LocalPort 8001 -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty OwningProcess -Unique |
  ForEach-Object { Stop-Process -Id $_ -Force }
```

## Terminal 1: Server And Browser

```powershell
py scripts\start_doom_arena_duel.py
```

Keep this terminal running. It starts the server and opens the browser.

The server exposes MCP at:

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8001/api/arena/mcp-config
```

Direct server-only equivalent:

```powershell
py scripts\doom_arena_server.py --port 8001
```

## Browser

Open and keep this tab running:

```text
http://127.0.0.1:8001/
```

Choose the run settings, then click `Start Duel`. The browser/server will reset the duel, write fresh controller tokens, generate both instruction files, and show copyable prompts in the Player 1 and Player 2 panels.

The browser exports WASM state into `src/arena_game_state.local.tsv`.

## Chat 2: Codex

Open a Codex chat with the repo-level `doom-arena` MCP server connected. Copy the Player 1/Codex prompt from the browser and paste it into Codex.

## Chat 3: Claude

Open Claude Code separately in the repo:

```powershell
cd C:\Users\muhha\OneDrive\Desktop\doom-wasm
claude
```

Confirm `/mcp` shows `doom-arena`, then copy the Player 2/Claude prompt from the browser and paste it into Claude.

## MCP Tool Check

Both agents should see these normal control tools:

```text
set_participant_ready
wait_for_match_start
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

Doom freezes both participants until both agents have signaled readiness through `set_participant_ready`. This prevents one agent from moving before the other is connected.

## One-Command Bootstrap

This starts the server, opens the browser, and keeps the server alive:

```powershell
py scripts\start_doom_arena_duel.py
```

## Run-Id Mismatch Fix

If you see a mismatch like:

```text
expected run_id: run_A
latest state run_id: run_B
```

Do this:

1. Stop extra servers on `8001`.
2. Hard refresh `http://127.0.0.1:8001/`.
3. Click `Start Duel`.
4. Use only the newly generated browser prompts.

Do not reuse older prompts after a reset.
