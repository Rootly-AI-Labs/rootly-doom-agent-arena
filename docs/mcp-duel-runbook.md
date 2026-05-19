# MCP Duel Runbook

This is the current setup for a real two-agent Doom Arena MCP duel.

## Terminal Layout

Use Docker as the default arena backend. Use the native Python launcher only for debugging or if Docker is unavailable.

Use three active surfaces:

- Terminal 1: arena server/browser launcher
- Browser: Doom/WASM duel tab with copyable MCP prompts
- Chat/terminal 2 and 3: Player 1 and Player 2 MCP chat agents

## Clean Start

Optional cleanup if port `8001` is already occupied:

```powershell
Get-NetTCPConnection -LocalPort 8001 -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty OwningProcess -Unique |
  ForEach-Object { Stop-Process -Id $_ -Force }
```

## Terminal 1: Docker Server And Browser

Start Docker Desktop, then run:

```powershell
.\scripts\start-docker.ps1
```

macOS/Linux:

```bash
bash scripts/start-docker.sh
```

Native fallback:

```powershell
py scripts\start_doom_arena_duel.py
```

Keep the backend running. The launchers start the arena server and open the browser.

The backend URL for host-side stdio MCP is:

```text
DOOM_ARENA_BASE_URL=http://127.0.0.1:8001
```

The server advertises MCP setup details at:

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8001/api/arena/mcp-config
```

Direct native server-only equivalent:

```powershell
py scripts\doom_arena_server.py --port 8001
```

## Browser

Open and keep this tab running:

```text
http://127.0.0.1:8001/
```

Choose the run settings, then click `Start Duel`. The browser/server will reset the duel, write fresh controller tokens, generate both instruction files, and show copyable prompts in the Player 1 and Player 2 panels. The generated prompts identify the agents as `player_1` and `player_2`; model labels are metadata only.

The next step is still manual in the current flow: copy each prompt from the browser into its matching external MCP chat agent. This boundary is intentional for now so the arena can work with different MCP-capable clients instead of one built-in agent runner.

The browser exports WASM state into `src/arena_game_state.local.tsv`.

Browser sessions write a parent folder under:

```text
benchmarks/results/session_*
```

Each round writes a child folder such as:

```text
benchmarks/results/session_*/round_01_run_*
```

One-off legacy/debug runs may still write directly under `benchmarks/results/run_*`. A round folder contains:

```text
config.json
controller_tokens.json
events.jsonl
player_1_mcp_instructions.md
player_2_mcp_instructions.md
stats.json
summary.json after the browser reports phase=finished
```

`stats.json` is updated as MCP calls arrive. It includes per-tool latency, per-participant latency, inferred chat decision latency, error status, in-flight overlap, and intent lifecycle data such as `superseded_before_expiry`, `unused_duration_ms`, gap after expiry, and stale continuation after nominal expiry. Browser-created chatbot runs preserve `events.jsonl` in each round folder. Use these files to tune `Intent Duration MS`; the browser default is intentionally long enough to cover slow chatbot turns.

## Chat 2: Player 1 Agent

Open the first chat agent with the repo-level `doom-arena` stdio MCP server connected. Copy the Player 1 prompt from the browser and paste it into that agent.

## Chat 3: Player 2 Agent

Open the second chat agent separately in the repo. For Claude Code, for example:

```powershell
cd C:\path\to\doom-wasm
$env:DOOM_ARENA_BASE_URL="http://127.0.0.1:8001"
claude
```

Confirm `/mcp` shows `doom-arena`, then copy the Player 2 prompt from the browser and paste it into the second agent.

Example Codex-style stdio config from the repo root:

```toml
[mcp_servers.doom-arena]
command = "python"
args = ["scripts/doom_arena_mcp.py"]
env = { DOOM_ARENA_BASE_URL = "http://127.0.0.1:8001" }
```

If an MCP client needs an absolute command path, keep that in an ignored local config such as `.mcp.local.json`. On Windows, `scripts\doom_arena_mcp.cmd` can be used as a local wrapper, but committed config should stay path-neutral.

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

`set_participant_intent` accepts the tactical policy fields shown in the generated prompt, including optional `movement_primitive`, `turn_policy`, `navigation_target`, `fire_mode`, spacing bounds, LOS-loss behavior, and stuck-recovery strategy. These are still high-level policies; Doom converts them into per-frame movement and attack inputs. Do not send `movement_primitive` by default; use it only as a short one-policy override and do not keep repeating `circle_left` or `circle_right` after line of sight is lost.

Low-level movement tools are hidden by default. For local debugging only, expose them by launching the MCP server with:

```powershell
$env:DOOM_ARENA_EXPOSE_LOW_LEVEL_MCP="1"
```

## Ready Gate

The duel starts in:

```text
phase=waiting_for_agents
```

Doom freezes both participants until both agents have signaled readiness through `set_participant_ready` and both agents have submitted an opening `set_participant_intent`. The opening intent is no longer forced to `hold`; each agent should observe the waiting state and choose the best first high-level action. The opening intents are held until both are present, then Doom starts executing both on the same tick. This prevents one agent from moving before the other is connected or before the other agent has chosen its first high-level action.

## One-Command Bootstrap

This starts the Docker runtime, opens the browser, and prints the stdio MCP backend URL:

```powershell
.\scripts\start-docker.ps1
```

Native equivalent:

```powershell
py scripts\start_doom_arena_duel.py
```

Stop the Docker backend with:

```powershell
docker compose down
```

## Multi-Round Sessions

Set `Rounds` before clicking `Start Duel` if you want a multi-round session. After a round reaches `phase=finished`, click `Next Round`. This preserves the same `session_*` parent folder, creates the next `round_NN_run_*` child folder, writes fresh prompts/tokens, and returns directly to the duel prompt view.

Use the new prompts after every `Next Round`. Do not keep using prompts from the previous round because the controller tokens and run id are round-specific.

Click `Start Duel` again only when you want a new session.

## Prompt Recovery

If a prompt panel is blank after reload or after `Next Round`, do not start a new duel immediately. Hard refresh the current duel URL first. The server can recover the current round prompt text from memory or from the round folder files:

```text
player_1_mcp_instructions.md
player_2_mcp_instructions.md
```

If the browser still does not show a prompt, verify that the current URL is the duel prompt view and that the active round folder contains those instruction files. Starting a new duel creates a new session and should be reserved for intentional resets.

## Run-Id Mismatch Fix

If you see a mismatch like:

```text
expected run_id: run_A
latest state run_id: run_B
```

Do this:

1. Stop extra servers on `8001`.
2. Hard refresh `http://127.0.0.1:8001/`.
3. Click `Start Duel` for a new session, or `Next Round` if the existing session is finished and has remaining rounds.
4. Use only the newly generated browser prompts.

Do not reuse older prompts after a reset.

## Controller-Token Mismatch

If agents get `Controller token file is for run_id X, but MCP client is on run_id Y`, your `docker/docker-compose.yml` is missing the `arena_controller_tokens.local.json` bind-mount. Restart Docker with the committed compose and it'll work.
