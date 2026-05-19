# Doom Agent Arena

Benchmark model duels in Doom.

An MCP-native arena for real-time model-vs-model evaluations.

<img width="1018" height="770" alt="Screenshot 2026-05-13 161918" src="https://github.com/user-attachments/assets/af5d10d1-7d5d-4b25-83bb-7a36619cd961" />

## Leaderboard

| Rank | Model | Win rate | Wins-Losses | Best matchup | Worst matchup |
|---|---|---:|---:|---|---|
| 1 | gpt-5.5 | 58.3% | 35-25 | vs gpt-5.3-codex (85%) | vs gpt-5.4-mini (35%) |
| 2 | gpt-5.4-mini | 56.7% | 34-26 | vs gpt-5.5 (65%) | vs gpt-5.3-codex-spark (45%) |
| 3 | gpt-5.3-codex | 46.7% | 28-32 | vs gpt-5.3-codex-spark (85%) | vs gpt-5.5 (15%) |
| 4 | gpt-5.3-codex-spark | 38.3% | 23-37 | vs gpt-5.4-mini (55%) | vs gpt-5.3-codex (15%) |

Each model was evaluated across 60 total rounds. Every pair played 20 mirrored rounds: 10 with Model A as `player_1` and 10 with Model B as `player_1`.

## Methodology

Each duel runs with two separate MCP agents, one for `player_1` and one for `player_2`. The browser starts a round, generates fresh prompts and controller tokens, and records the run under `benchmarks/results`. The agents observe match state and send high-level tactical intents through MCP. Doom executes those intents in real time.

The key design choice is the control split. Models do not drive frame-level inputs directly. Instead, they choose short-lived policies such as `engage_opponent`, `strafe_attack`, `hold`, or `search`, optionally with tactical parameters for spacing, fire policy, navigation target, LOS-loss behavior, and stuck recovery. A Doom-side autopilot handles low-level movement, aim, firing, and recovery every tick. This keeps the benchmark focused on tactical decision-making instead of testing which model can micro-manage a shooter at frame rate.

Rounds are synchronized with a ready gate so neither side starts moving before both agents have connected and submitted an opening intent.

Each round writes artifacts that can be inspected or reprocessed later, including prompts, config, `events.jsonl`, `stats.json`, and `summary.json`. The stats layer records MCP latency, intent lifecycle timing, overlap between calls, and other telemetry needed to study not just who won, but how the duel unfolded.

For a deeper breakdown of the control loop, see [Control Architecture](docs/control-architecture.md).

## Quick Start

Prerequisites:

- Docker Desktop or Docker Engine
- Python 3 on the host
- Two MCP-capable chat agents connected to this repo

1. Start the arena from the repo root:

```powershell
cd C:\path\to\doom-wasm
.\scripts\start-docker.ps1
```

macOS/Linux equivalent:

```bash
cd /path/to/doom-wasm
bash scripts/start-docker.sh
```

The launcher starts Docker Compose, waits for the health endpoint, opens `http://127.0.0.1:8001/`, and prints:

```text
DOOM_ARENA_BASE_URL=http://127.0.0.1:8001
```

2. Confirm your MCP client uses the host-side stdio server from the repo root:

```toml
[mcp_servers.doom-arena]
command = "python"
args = ["scripts/doom_arena_mcp.py"]
env = { DOOM_ARENA_BASE_URL = "http://127.0.0.1:8001" }
```

JSON-style clients can use the same shape:

```json
{
  "mcpServers": {
    "doom-arena": {
      "type": "stdio",
      "command": "python",
      "args": ["scripts/doom_arena_mcp.py"],
      "env": {
        "DOOM_ARENA_BASE_URL": "http://127.0.0.1:8001"
      }
    }
  }
}
```

The committed `.mcp.json` already uses this portable setup. If your MCP client needs an absolute command path, keep that machine-specific version in an ignored `.mcp.local.json`.

3. In the browser, choose run settings and click `Start Duel`.

4. Paste the generated `player_1` prompt into the first MCP chat agent, and the generated `player_2` prompt into the second one.

The duel waits until both agents are ready and both have submitted an opening high-level intent. Use fresh prompts after every `Start Duel` or `Next Round`.

## Common Commands

```powershell
.\scripts\start-docker.ps1 -NoOpenBrowser
.\scripts\start-docker.ps1 -Port 8010
.\scripts\start-docker.ps1 -Dev
py scripts\smoke_docker_setup.py
docker compose down
```

Native Python fallback:

```powershell
py scripts\start_doom_arena_duel.py
```

## Results

Docker serves the prebuilt `src/websockets-doom.{html,js,wasm}` files and writes benchmark artifacts to `benchmarks/results`.

Multi-round browser sessions are written under `benchmarks/results/session_*/round_NN_run_*`. Each round includes config, controller tokens, generated prompts, `stats.json`, `events.jsonl`, and a final `summary.json`.

## Control Split

- **Player MCP agents:** choose high-level tactical policies with `set_participant_intent`.
- **Doom-side autopilot:** executes low-level movement, aiming, firing, LOS handling, and stuck recovery every tick.
- **Sticky chatbot mode:** if a chat response is slow, Doom keeps executing the last LLM-authored intent as `stale` until a newer sequence number arrives.
- **Browser/server session:** starts sessions, advances rounds, writes fresh tokens/prompts, and shows copyable MCP prompts.

See [Control Architecture](docs/control-architecture.md) for the full split.

## Docs

- [MCP Duel Runbook](docs/mcp-duel-runbook.md): terminal-by-terminal setup, MCP checks, prompts, and run-id mismatch fixes.
- [Docker Runtime](docs/docker.md): runtime-only Docker setup, stdio MCP wiring, dev mounts, logs, and smoke checks.
- [Control Architecture](docs/control-architecture.md): high-level MCP controls, Doom autopilot behavior, sequence numbers, and the ready gate.
- [Build](docs/build.md): WSL/Emscripten rebuild commands and browser cache notes.
- [Smoke Tests](docs/smoke-tests.md): API, MCP, and browser-backed smoke commands.

## Important Rules

- Keep the arena backend running before starting MCP clients. Docker and native server modes both use `DOOM_ARENA_BASE_URL` for host-side stdio MCP.
- Click `Start Duel` to begin a new comparison session. Click `Next Round` only after `phase=finished` when continuing the same session.
- Use only the newly generated prompts and controller tokens for the current round.
- Keep one browser tab active for a comparison.

## License

Chocolate Doom and this port are distributed under the GNU GPL. See [COPYING.md](COPYING.md).
