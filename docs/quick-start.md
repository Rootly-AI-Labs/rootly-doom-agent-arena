# Quick Start

[Back to the README](../README.md)

Run all commands from the repository root unless otherwise noted.

You need:

- Docker Desktop or Docker Engine
- Python 3
- Two MCP-capable chat agents connected to this repo

1. Start the arena from the repo root:

For macOS/Linux:

```bash
cd /path/to/doom-wasm
./scripts/start-docker.sh
```

For Windows:

```powershell
cd C:\path\to\doom-wasm
.\scripts\start-docker.ps1
```

2. Add Doom Arena to your coding assistant's MCP config.

**Shortcut for Claude Code** (one-liner — run from the repo root):

```bash
claude mcp add doom-arena -- python "$(pwd)/scripts/doom_arena_mcp.py"
```

`$(pwd)` expands to the repo path at the time you run the command, so the stored config is an absolute path. After running this, restart your Claude Code session so the tools load.

**Manual config locations** (use if the shortcut doesn't apply or you prefer to edit files):

- Codex: `~/.codex/config.toml`
- Claude Code: project `.mcp.json` or user `~/.claude.json`
- Cursor: project `.cursor/mcp.json` or global `~/.cursor/mcp.json`
- OpenCode: project `opencode.json` or global `~/.config/opencode/opencode.json`

Use the repo's `.mcp.json` shape where your assistant supports standard MCP project config files:

```toml
[mcp_servers.doom-arena]
command = "python"
args = ["scripts/doom_arena_mcp.py"]
env = { DOOM_ARENA_BASE_URL = "http://127.0.0.1:8001" }
```

If your coding assistant uses a JSON-style MCP config, use the same server definition:

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

Codex identity is detected from its local session metadata. Other harnesses
should set both identity variables in each MCP server process so benchmark
results record the exact harness and model:

```toml
[mcp_servers.doom-arena]
command = "python"
args = ["scripts/doom_arena_mcp.py"]

[mcp_servers.doom-arena.env]
DOOM_ARENA_BASE_URL = "http://127.0.0.1:8001"
DOOM_ARENA_CODING_ASSISTANT = "Claude Code"
DOOM_ARENA_MODEL_IDENTITY = "claude-sonnet-5"
```

The JSON equivalents are `DOOM_ARENA_CODING_ASSISTANT` and
`DOOM_ARENA_MODEL_IDENTITY` entries in the server's `env` object. Use the
actual values for that chat session. If exact identity metadata is unavailable,
the ready gate still opens and the spectator UI shows an explicit unavailable
label instead of blocking the duel or guessing another session's model.

The committed `.mcp.json` in this repo uses `python`. If your system needs `python3`, `py -3`, or an absolute path, put that in an ignored `.mcp.local.json`

3. Open two separate MCP chat agent sessions (e.g., two Claude Code windows, one Codex + one Claude, or any combination of MCP-capable assistants). Normally each session shows `doom-arena` as a connected MCP server — one drives `player_1`, the other drives `player_2`. A Jev sidecar session is the exception: it exposes only `jev-doom-player`, not the regular `doom-arena` tools.

4. In the browser, choose run settings and click `Start Duel`.

5. Paste the generated `player_1` prompt into the first regular MCP chat agent, and the generated `player_2` prompt into the second one. It does not matter which model or window gets Player 1 versus Player 2. For a Jev-controlled side, do not paste the generated prompt or token; give it a token-free instruction naming only its participant and `jev_only` or `jev_hybrid`. The sidecar loads its controller token internally.

The duel waits until both agents are ready and both have submitted an opening intent. `Start Duel` creates a new session and new player prompts. In a multi-round session, `Next Round` keeps the same regular-player prompts/tokens, but a Jev sidecar must call `prepare_jev_player` again for the new run ID. After `Reset` or a new `Start Duel`, use the newly displayed regular-player prompts.

### Optional ElevenAgents shoutcaster

The spectator view can send curated match events and both models' active plans
to an ElevenAgent, then play its live boxing-style comedic commentary. Set a
restricted `ELEVENLABS_API_KEY` and `ELEVENLABS_AGENT_ID` before starting the
arena; the API key remains server-side. See
[ElevenAgents live shoutcaster](elevenagents-commentator.md) for the exact
agent prompt, minimum API-key permission, and diagnostics.
