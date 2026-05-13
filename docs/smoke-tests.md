# Smoke Tests

These checks cover the server, MCP tools, Doom intent parser, autopilot logic, browser/WASM path, and rolling-loop timing.

## Python Compile

```powershell
py -m py_compile `
  scripts\doom_arena_mcp.py `
  scripts\doom_arena_mcp_duel_orchestrator.py `
  scripts\doom_arena_server.py `
  scripts\start_doom_arena_duel.py `
  scripts\smoke_duel_autopilot.py `
  scripts\smoke_rolling_tactical_loop.py
```

## Parser And Autopilot

```powershell
py scripts\smoke_participant_intents_parser.py
py scripts\smoke_participant_autopilot.py
```

## Server-Backed API/MCP

Start the server:

```powershell
py scripts\doom_arena_server.py --port 8001
```

Then run:

```powershell
py scripts\smoke_participant_intents_api.py --server-url http://127.0.0.1:8001
py scripts\smoke_mcp_participant_intents.py --server-url http://127.0.0.1:8001
py scripts\smoke_duel_participant_commands.py --server-url http://127.0.0.1:8001
```

## Browser-Backed Autopilot

This starts a local server if needed and opens a headless browser:

```powershell
py scripts\smoke_duel_autopilot.py --server-url http://127.0.0.1:8001 --timeout-seconds 60
```

It verifies:

- browser/WASM state export
- `waiting_for_agents` ready gate
- one intent alone does not start combat
- both intents start autopilot
- state export includes intent/autopilot fields
- clear/stop returns to fallback mode
- wrong controller token is rejected
- low-level debug path still works after clearing intents

## Rolling Loop Timing

```powershell
py scripts\smoke_rolling_tactical_loop.py
```

This simulates decision latencies:

```text
100ms
750ms
1500ms
3000ms
```

It verifies that Doom keeps an active intent while model decisions are pending and that stale responses are discarded when multiple decisions are in flight.

## Full MCP Duel E2E

With a browser tab open:

```powershell
py scripts\smoke_mcp_duel_e2e.py --server-url http://127.0.0.1:8001 --timeout-seconds 30
```

If you are managing the browser yourself:

```powershell
py scripts\smoke_mcp_duel_e2e.py --server-url http://127.0.0.1:8001 --timeout-seconds 30 --no-open-browser
```
