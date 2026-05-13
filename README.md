# Doom Agent Arena

Local Doom WASM benchmark arena for Codex-vs-Claude duels.

The current MVP focuses on duel mode: `player_1` is controlled by Codex, `player_2` is controlled by Claude, and both agents send high-level MCP intents while Doom executes real-time movement, aiming, firing, and safety behavior.

## Quick Start

Use this flow for a real LLM-vs-LLM comparison:

1. Start the arena server:

```powershell
py scripts\doom_arena_server.py --port 8001
```

2. Open the browser and keep it open:

```text
http://127.0.0.1:8001/?duel=1
```

3. Start the orchestrator in a second terminal:

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

4. Paste the generated `player_1_mcp_instructions.md` into Codex.
5. Paste the generated `player_2_mcp_instructions.md` into Claude.

The duel waits in `phase=waiting_for_agents` until both agents have sent their first high-level intent. Do not reuse old prompt files or tokens after a reset.

## MCP Setup

Start the arena server first; it hosts the MCP endpoint at:

```text
http://127.0.0.1:8001/mcp
```

You can verify the advertised MCP config with:

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8001/api/arena/mcp-config
```

For Claude Code, add the project MCP server from this repo:

```powershell
cd C:\Users\muhha\OneDrive\Desktop\doom-wasm
claude mcp add --transport http doom-arena http://127.0.0.1:8001/mcp
claude
```

Then run `/mcp` in Claude and confirm `doom-arena` is connected.

For Codex, configure the repo-level MCP server to use the same HTTP endpoint:

```toml
[mcp_servers.doom-arena]
url = "http://127.0.0.1:8001/mcp"
```

Then restart Codex in this repo and check `/mcp`. Both Codex and Claude should expose:

```text
get_participant_observation
set_participant_intent
stop_participant_intent
get_match_result
get_duel_events
```

Do not manually run `py scripts\doom_arena_mcp.py` for normal play. That stdio MCP path is only for debugging; HTTP MCP is preferred on native Windows.

## Control Split

- **Codex/Claude MCP agents:** choose high-level tactical policies with `set_participant_intent`.
- **Doom-side autopilot:** executes low-level movement, aiming, firing, LOS handling, and stuck recovery every tick.
- **Orchestrator:** resets runs, writes fresh tokens/prompts, monitors state, and does not self-play unless `--rolling-control` is explicitly passed.

See [Control Architecture](docs/control-architecture.md) for the full split.

## Docs

- [MCP Duel Runbook](docs/mcp-duel-runbook.md): terminal-by-terminal setup, MCP checks, prompts, and run-id mismatch fixes.
- [Control Architecture](docs/control-architecture.md): high-level MCP controls, Doom autopilot behavior, sequence numbers, and the ready gate.
- [Build](docs/build.md): WSL/Emscripten rebuild commands and browser cache notes.
- [Smoke Tests](docs/smoke-tests.md): API, MCP, browser-backed, and rolling-loop smoke commands.

## Important Rules

- Do not run `scripts\doom_arena_mcp.py` manually in a terminal for normal play; Codex/Claude should connect to the arena server's HTTP MCP endpoint.
- Do not click `Start Duel` after the orchestrator resets a run.
- Keep one browser tab and one orchestrator run active for a comparison.
- Use `--rolling-control` only for local scripted smoke testing without real LLMs.

## License

Chocolate Doom and this port are distributed under the GNU GPL. See [COPYING.md](COPYING.md).
