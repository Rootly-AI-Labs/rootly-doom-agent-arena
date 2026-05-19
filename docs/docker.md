# Docker Runtime

Docker is a runtime wrapper for Doom Arena. It runs the arena web/API server and serves the existing prebuilt browser assets from `src/`. MCP stays host-side as a stdio server so Codex, Claude, and other desktop MCP clients can launch it normally.

```text
Codex / Claude
  -> host-side stdio MCP
  -> DOOM_ARENA_BASE_URL=http://127.0.0.1:<port>
  -> Docker arena backend
```

## Quick Start

Start Docker Desktop or Docker Engine first, then run the launcher from the repo root.

Windows PowerShell:

```powershell
cd C:\path\to\doom-wasm
.\scripts\start-docker.ps1
```

macOS/Linux:

```bash
cd /path/to/doom-wasm
bash scripts/start-docker.sh
```

Both launchers:

- start `docker compose up -d --build`
- wait for `GET /api/arena/health`
- open `http://127.0.0.1:8001/`
- print the MCP backend environment variable

After the browser opens, click `Start Duel`, then manually paste the generated Player 1 and Player 2 prompts into two separate MCP agents. Use fresh prompts after every `Next Round`.

The prompt handoff is manual by design in the current architecture. Docker runs the arena backend and the browser generates round-specific prompts and controller tokens, but the two chat agents still live outside the arena so the setup stays provider-neutral.

Use a different port when needed:

```powershell
.\scripts\start-docker.ps1 -Port 8010
```

```bash
DOOM_ARENA_PORT=8010 bash scripts/start-docker.sh
```

Inside Docker, the arena server binds to `0.0.0.0`. The host port is published on `127.0.0.1`.

Stop the backend with:

```bash
docker compose -f docker/docker-compose.yml down
```

## MCP Stdio Setup

Set the MCP backend URL to the Docker-published localhost URL:

```text
DOOM_ARENA_BASE_URL=http://127.0.0.1:8001
```

The MCP command still runs on the host:

```text
python scripts/doom_arena_mcp.py
```

Example Codex-style stdio config from the repo root:

```toml
[mcp_servers.doom-arena]
command = "python"
args = ["scripts/doom_arena_mcp.py"]
env = { DOOM_ARENA_BASE_URL = "http://127.0.0.1:8001" }
```

Example Claude-style command from the repo root:

```bash
DOOM_ARENA_BASE_URL=http://127.0.0.1:8001 claude mcp add doom-arena -- python scripts/doom_arena_mcp.py
```

If an MCP client needs an absolute command path, keep that in an ignored local config such as `.mcp.local.json`. On Windows, `scripts\doom_arena_mcp.cmd` can be used as a local wrapper, but committed config should stay path-neutral. Keep the Docker backend running while the MCP client is connected.

The repo `.mcp.json` is configured for this host-side stdio shape and defaults to:

```text
DOOM_ARENA_BASE_URL=http://127.0.0.1:8001
```

## Prebuilt WASM Limitation

The v1 Docker image is runtime-only. It uses the existing files:

```text
src/websockets-doom.html
src/websockets-doom.js
src/websockets-doom.wasm
```

It does not install Emscripten and does not rebuild WASM. If those files are missing or stale, rebuild them locally with the WSL/Emscripten flow in [Build](build.md), then restart Docker.

## Developer Asset Flow

Normal Docker runs copy `src/` into the image so users get a stable runtime.

If you are locally rebuilding browser/WASM assets and want Docker to serve your current working tree, use dev mode:

```powershell
.\scripts\start-docker.ps1 -Dev
```

```bash
bash scripts/start-docker.sh --dev
```

Dev mode adds:

```yaml
./src:/app/src
```

That mount is for development only. It lets locally rebuilt `websockets-doom.{html,js,wasm}` files take effect after a browser hard refresh.

## Controller-Token Sync

The committed `docker/docker-compose.yml` bind-mounts `src/arena_controller_tokens.local.json` into the container so the in-container arena server's per-run token writes reach the host MCP server. Don't remove that volume entry.

## Results And Logs

Docker and non-Docker runs share:

```text
benchmarks/results
```

The Compose mount is:

```yaml
./benchmarks/results:/app/benchmarks/results
```

Browser-created duel sessions write:

```text
benchmarks/results/session_*/round_NN_run_*
```

Each round can include `config.json`, `controller_tokens.json`, generated MCP prompts, `stats.json`, `events.jsonl`, and `summary.json`.

View backend logs with:

```bash
docker compose -f docker/docker-compose.yml logs -f arena
```

The host-side stdio MCP log defaults to:

```text
src/arena_mcp_stdio.log
```

Set `DOOM_ARENA_MCP_LOG` to override or disable it.

## Smoke Check

Run:

```powershell
py scripts\smoke_docker_setup.py
```

or:

```bash
python3 scripts/smoke_docker_setup.py
```

The smoke check verifies Docker startup, the browser route, the arena API, host-side stdio MCP connectivity, and result persistence under `benchmarks/results`.
