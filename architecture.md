# Architecture

Rootly Incident Doom is a local browser game plus a local control plane. Rootly data is fetched server-side, converted to TSV, loaded into Doom WASM, and exposed to agents through a small MCP wrapper.

## High-Level Flow

```text
Rootly API
    |
    | server-side token only
    v
scripts/rootly_dev_server.py
    |
    | writes TSV
    v
src/rootly_incidents.local.tsv
    |
    | preloaded by browser into WASM FS
    v
Doom WASM Rootly Incident Mode
    |
    | exports state TSV
    v
src/agentic_game_state.local.tsv
    ^
    | command TSV
src/agentic_monster_commands.local.tsv
    ^
    | local HTTP endpoints
scripts/doom_control_mcp.py
    ^
    | MCP tools
Codex / Claude
```

## Main Components

### Browser / WASM

`src/index.html` starts the game, loads mock or local incident TSV data, and mirrors agentic files between the browser and the local dev server.

Responsibilities:

- Load `doom1.wad`.
- Load `rootly_incidents.mock.tsv` or `rootly_incidents.local.tsv`.
- Start Doom on the Rootly Incident Mode map.
- Poll `/api/agentic/commands` and write commands into the WASM filesystem.
- Read `agentic_game_state.local.tsv` from WASM and post it to `/api/agentic/state`.

### Local Dev Server

`scripts/rootly_dev_server.py` serves the browser files and exposes local-only APIs.

Endpoints:

```text
GET/POST /api/rootly/last-week
GET/POST /api/agentic/state
GET/POST /api/agentic/commands
```

Responsibilities:

- Serve `src/` on `http://127.0.0.1:8000`.
- Read `ROOTLY_API_TOKEN` from the server process environment.
- Fetch last-week Rootly incidents.
- Write `src/rootly_incidents.local.tsv`.
- Store latest game state TSV.
- Store latest monster command TSV.

### Rootly Ingest

`scripts/fetch_rootly_incidents.py` fetches incidents and sanitizes them for Doom.

Output columns:

```text
severity
mobj_type
label
rootly_id
rootly_url
created_at
status
```

The browser never receives the Rootly token.

### Doom Engine Changes

Rootly Incident Mode lives in the Doom C code.

Important files:

- `src/doom/rootly_incidents.c`: loads incident TSV, maps severities to monsters, spawns incident monsters, exports remaining counts.
- `src/doom/rootly_incidents.h`: incident loader API.
- `src/doom/agentic_control.c`: parses command TSV and exports game state TSV.
- `src/doom/agentic_control.h`: command enum and helper declarations.
- `src/doom/p_enemy.c`: applies agentic commands inside `A_Chase`.
- `src/doom/p_mobj.c`: player spawn and map thing filtering.
- `src/doom/r_things.c`: incident labels above monsters.

## Incident Data Model

Mock data:

```text
src/rootly_incidents.mock.tsv
```

Live local data:

```text
src/rootly_incidents.local.tsv
```

Severity mapping:

```text
SEV0 -> MT_BRUISER
SEV1 -> MT_SHADOWS
SEV2 -> MT_SERGEANT
SEV3 -> MT_TROOP
SEV4 -> MT_SHOTGUY
SEV5 -> MT_POSSESSED
```

Each spawned incident monster stores:

```text
incident_index
incident_label
```

Those fields connect rendering, state export, and agent commands.

## Agentic Control

The game exports state to:

```text
src/agentic_game_state.local.tsv
```

Columns:

```text
kind
incident_index
severity
label
x
y
pov
health
alive
command
```

Agents write commands to:

```text
src/agentic_monster_commands.local.tsv
```

Command format:

```tsv
target_type	target	command
severity	SEV0	hold
incident_index	2	chase_player
```

Supported commands:

```text
normal
hold
chase_player
fight_each_other
```

Behavior:

- `normal`: default Doom AI.
- `hold`: stop incident monster chase movement.
- `chase_player`: target the player, then continue normal Doom chase logic.
- `fight_each_other`: target another live incident monster.

Only monsters with `incident_index >= 0` obey these commands. Non-incident Doom monsters are unaffected.

## MCP Wrapper

`scripts/doom_control_mcp.py` is a stdio MCP server.

It exposes:

```text
get_game_state
set_monster_command
set_severity_command
clear_all_monster_commands
```

It does not read Rootly tokens and does not modify Doom memory. It only calls the local dev server endpoints and writes the existing TSV command format.

## Security Boundary

Token boundary:

```text
ROOTLY_API_TOKEN -> rootly_dev_server.py only
```

Browser boundary:

```text
Browser -> local TSV files only
```

Agent boundary:

```text
Codex/Claude -> MCP tools -> local dev server -> command TSV
```

No Rootly token should appear in:

- `index.html`
- WASM files
- TSV files
- browser network calls
- MCP calls
- logs

## Runtime Requirements

The normal local run has two active pieces:

```powershell
py scripts\rootly_dev_server.py --port 8000
```

and a browser tab open at:

```text
http://127.0.0.1:8000
```

For MCP control, Codex or Claude also launches:

```powershell
py scripts\doom_control_mcp.py --server-url http://127.0.0.1:8000
```

## Rebuild Boundary

Changes to JavaScript or Python usually only require a browser refresh or server restart.

Changes to Doom C files require a WASM rebuild:

```powershell
wsl -d Ubuntu-24.04 -e bash -lc "cd /mnt/c/Users/muhha/OneDrive/Desktop/doom-wasm && source ~/emsdk/emsdk_env.sh >/dev/null && make"
```

Then hard refresh the browser.
