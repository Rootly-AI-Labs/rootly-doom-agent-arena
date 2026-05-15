# Smoke Tests

These checks cover the server, MCP tools, Doom intent parser, autopilot logic, and browser/WASM path.

## Python Compile

```powershell
py -m py_compile `
  scripts\doom_arena_mcp.py `
  scripts\doom_arena_duel_prompts.py `
  scripts\doom_arena_server.py `
  scripts\start_doom_arena_duel.py `
  scripts\smoke_participant_intents_api.py `
  scripts\smoke_mcp_participant_intents.py `
  scripts\smoke_duel_autopilot.py
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

`smoke_mcp_participant_intents.py` also verifies that HTTP MCP intent calls are captured in `stats.json`. Browser sessions write this under `benchmarks/results/session_*/round_NN_run_*/stats.json`; one-off runs may write under `benchmarks/results/run_*/stats.json`.

## Browser-Backed Autopilot

This starts a local server if needed and opens a headless browser:

```powershell
py scripts\smoke_duel_autopilot.py --server-url http://127.0.0.1:8001 --timeout-seconds 60
```

It verifies:

- browser/WASM state export
- `waiting_for_agents` ready/opening-intent gate
- one ready signal or one opening intent alone does not start combat
- both intents start autopilot
- state export includes intent/autopilot fields, including MCP-selected fire, distance, LOS-loss, stuck recovery, movement primitive, turn policy, navigation target, and fire mode controls
- expired intents continue as stale MCP policies until replaced or cleared
- post-finish participant intents are rejected
- browser event logs are preserved as `events.jsonl`
- clear/stop returns to fallback mode
- wrong controller token is rejected
- low-level debug path still works after clearing intents

## Full MCP Duel E2E

With a browser tab open:

```powershell
py scripts\smoke_mcp_duel_e2e.py --server-url http://127.0.0.1:8001 --timeout-seconds 30
```

If you are managing the browser yourself:

```powershell
py scripts\smoke_mcp_duel_e2e.py --server-url http://127.0.0.1:8001 --timeout-seconds 30 --no-open-browser
```
