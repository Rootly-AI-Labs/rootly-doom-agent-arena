# Rootly Incident Doom

Doom WASM becomes a Rootly incident arena: incidents spawn as severity-coded monsters, labels show incident context, and Codex/Claude can control incident monsters through a local MCP wrapper.

Original project notes are preserved in [old-README.md](old-README.md).

## Safety

Rootly tokens stay server-side.

- Browser never calls Rootly.
- `ROOTLY_API_TOKEN` is not written to HTML, WASM, TSV, logs, or browser requests.
- `src/rootly_incidents.local.tsv` is generated locally and gitignored.
- `src/rootly_incidents.mock.tsv` is committed for demos.

## Run The Game

Mock data, no Rootly token:

```powershell
cd C:\Users\muhha\OneDrive\Desktop\doom-wasm
py scripts\rootly_dev_server.py --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

Click `Load Mock Data`.

Live Rootly data from the last week:

```powershell
cd C:\Users\muhha\OneDrive\Desktop\doom-wasm
$env:ROOTLY_API_TOKEN="your-rootly-token"
py scripts\rootly_dev_server.py --port 8000
```

Open `http://127.0.0.1:8000`, click `Load Last Week`, then start the game.

## Data Files

- `src/rootly_incidents.mock.tsv`: demo incident data.
- `src/rootly_incidents.local.tsv`: generated Rootly data, gitignored.
- `src/agentic_game_state.local.tsv`: exported player and monster state, gitignored.
- `src/agentic_monster_commands.local.tsv`: MCP/manual monster commands, gitignored.

Severity mapping:

```text
SEV0 -> MT_BRUISER
SEV1 -> MT_SHADOWS
SEV2 -> MT_SERGEANT
SEV3 -> MT_TROOP
SEV4 -> MT_SHOTGUY
SEV5 -> MT_POSSESSED
```

If more than 8 incidents load, the game groups by severity, for example `SEV3: 7 incidents`.

## MCP Enemy Control

MCP wrapper:

```text
scripts/doom_control_mcp.py
```

It talks to:

```text
http://127.0.0.1:8000
```

Tools:

```text
get_game_state
set_monster_command
set_severity_command
clear_all_monster_commands
```

Commands:

```text
normal            -> default Doom AI
hold              -> stop incident monster chase movement
chase_player      -> target the player
fight_each_other  -> target another live incident monster
```

Codex/Claude MCP config:

```json
{
  "mcpServers": {
    "agentic-doom": {
      "command": "py",
      "args": [
        "C:\\Users\\muhha\\OneDrive\\Desktop\\doom-wasm\\scripts\\doom_control_mcp.py",
        "--server-url",
        "http://127.0.0.1:8000"
      ]
    }
  }
}
```

Restart the MCP client after adding this.

Example prompts:

```text
Use agentic-doom. Set every severity to chase_player.
Use agentic-doom. Make SEV0 and SEV1 hold.
Use agentic-doom. Set every severity to fight_each_other.
Use agentic-doom. Clear all monster commands.
```

## Manual Testing

Read game state:

```powershell
(Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/agentic/state" -UseBasicParsing).Content
```

Make all severities chase you:

```powershell
$body = "target_type`ttarget`tcommand`nseverity`tSEV0`tchase_player`nseverity`tSEV1`tchase_player`nseverity`tSEV2`tchase_player`nseverity`tSEV3`tchase_player`nseverity`tSEV4`tchase_player`nseverity`tSEV5`tchase_player`n"
Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/agentic/commands" -Method POST -Body $body -ContentType "text/tab-separated-values"
```

Clear commands:

```powershell
$body = "target_type`ttarget`tcommand`n"
Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/agentic/commands" -Method POST -Body $body -ContentType "text/tab-separated-values"
```

## Rebuild

After C changes:

```powershell
wsl -d Ubuntu-24.04 -e bash -lc "cd /mnt/c/Users/muhha/OneDrive/Desktop/doom-wasm && source ~/emsdk/emsdk_env.sh >/dev/null && make"
```

Hard refresh the browser after rebuilding. Existing tabs keep running old WASM until reloaded.

## Troubleshooting

Check commands:

```powershell
Get-Content C:\Users\muhha\OneDrive\Desktop\doom-wasm\src\agentic_monster_commands.local.tsv
```

Check exported state:

```powershell
(Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/agentic/state" -UseBasicParsing).Content
```

## Screenshots / GIF

Placeholder: add an arena screenshot or short GIF here.

## License

Chocolate Doom and this port are distributed under the GNU GPL. See [COPYING.md](COPYING.md).
