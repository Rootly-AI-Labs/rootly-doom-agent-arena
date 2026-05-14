# Doom Agent Arena

Local Doom WASM benchmark arena for Codex-vs-Claude duels.

The current MVP focuses on duel mode: `player_1` is controlled by Codex, `player_2` is controlled by Claude, and both agents send high-level MCP intents while Doom executes real-time movement, aiming, firing, and safety behavior.


<img width="1095" height="560" alt="Screenshot 2026-05-13 161902" src="https://github.com/user-attachments/assets/4b2d2ea5-de23-4f25-b674-4758644d11a5" />
<img width="1018" height="770" alt="Screenshot 2026-05-13 161918" src="https://github.com/user-attachments/assets/af5d10d1-7d5d-4b25-83bb-7a36619cd961" />

## Quick Start

Use this flow for a manual MCP chat comparison:

1. Start the arena server and open the browser:

```powershell
py scripts\start_doom_arena_duel.py
```

Or run the server directly and open the browser yourself:

```powershell
py scripts\doom_arena_server.py --port 8001
```

```text
http://127.0.0.1:8001/
```

2. Pick the run settings in the browser, then click `Start Duel`.
3. Copy the generated Codex prompt from the Player 1 panel and paste it into Codex.
4. Copy the generated Claude prompt from the Player 2 panel and paste it into Claude.

The browser writes fresh controller tokens and instruction files for each run.
Each run folder under `benchmarks/results/run_*` also gets `stats.json`, which records HTTP MCP tool-call latency and whether participant intents were superseded before their duration expired.

The duel waits in `phase=waiting_for_agents` until both agents have signaled readiness and both have submitted their opening high-level intent. Doom holds both opening intents and starts executing them on the same tick. Do not reuse old prompt files or tokens after a reset.

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
set_participant_ready
wait_for_match_start
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
- **Browser/server session:** resets runs, writes fresh tokens/prompts, and shows copyable MCP prompts.

See [Control Architecture](docs/control-architecture.md) for the full split.

## Docs

- [MCP Duel Runbook](docs/mcp-duel-runbook.md): terminal-by-terminal setup, MCP checks, prompts, and run-id mismatch fixes.
- [Control Architecture](docs/control-architecture.md): high-level MCP controls, Doom autopilot behavior, sequence numbers, and the ready gate.
- [Build](docs/build.md): WSL/Emscripten rebuild commands and browser cache notes.
- [Smoke Tests](docs/smoke-tests.md): API, MCP, and browser-backed smoke commands.

## Important Rules

- Do not run `scripts\doom_arena_mcp.py` manually in a terminal for normal play; Codex/Claude should connect to the arena server's HTTP MCP endpoint.
- Click `Start Duel` once per comparison, then use only the newly generated prompts.
- Keep one browser tab active for a comparison.

## License

Chocolate Doom and this port are distributed under the GNU GPL. See [COPYING.md](COPYING.md).
