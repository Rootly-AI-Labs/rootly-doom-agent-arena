# Doom Arena map blueprint guide

This folder defines the simple editable duel map format.

## Files

- `duel_e1m8_ascii.txt` is the source of truth for map geometry.
- `duel_e1m8_variants.json` defines scenario IDs, map labels, spawn variants, and player angles.

## ASCII legend

Each character in `duel_e1m8_ascii.txt` is one map cell.

- `.` = walkable floor.
- `#` = solid wall cell. The generated Doom map should give this collision and a visible wall texture.
- `1` = default Player 1 spawn marker.
- `2` = default Player 2 spawn marker.

Current cell size is defined in `duel_e1m8_variants.json`:

```json
"cell_size": 64
```

So one ASCII cell is `64 x 64` Doom map units.

## Coordinates

The ASCII grid is centered around Doom world coordinate `(0, 0)`.

For a 32-column by 24-row map with `cell_size=64`:

- `x=-1056..1056`
- `y=-736..736`
- top row is north / `+y`
- bottom row is south / `-y`
- left side is west / `-x`
- right side is east / `+x`

A cell's center is used for spawn markers.

## Editing walls

To add a wall, change `.` to `#` in `duel_e1m8_ascii.txt`.

Example:

```text
................#...............
................#...............
................#...............
```

Connected `#` cells are grouped into wall components by the Python map loader.

Important current limitation: the WAD generator currently supports an open room, one connected rectangular wall component, or two connected rectangular wall components. If you add more separate wall boxes, update `scripts/generate_duel_room_wad.py` to generate all wall components as real Doom sectors before expecting every box to have collision and visible textures.

## Editing spawns

You can place default spawn markers directly in `duel_e1m8_ascii.txt`:

- `1` for Player 1
- `2` for Player 2

For scenario-specific spawn variants, edit `duel_e1m8_variants.json` instead:

```json
"duel_e1m8": {
  "map_id": "duel_e1m8",
  "label": "Open sight spawn",
  "spawns": {
    "player_1": {"x": -608, "y": 544, "angle_deg": 0},
    "player_2": {"x": 672, "y": 544, "angle_deg": 180}
  }
}
```

`angle_deg=0` faces east / `+x`.
`angle_deg=90` faces north / `+y`.
`angle_deg=180` faces west / `-x`.
`angle_deg=270` faces south / `-y`.

Scenario JSON spawn values override ASCII `1` and `2` markers.

## Regenerating the Doom map

After editing `duel_e1m8_ascii.txt` or `duel_e1m8_variants.json`, regenerate the WAD:

```powershell
$env:DOOM_ARENA_OUTPUT_IWAD='C:\tmp\doom1-arena.wad'
py scripts\generate_duel_room_wad.py
Move-Item -LiteralPath 'C:\tmp\doom1-arena.wad' -Destination 'src\doom1-arena.wad' -Force
```

Then rebuild/relaunch Docker:

```powershell
docker compose -f docker\docker-compose.yml build --no-cache
docker compose -f docker\docker-compose.yml up -d --force-recreate
```

If you only change Python prompt/server metadata and not C/WASM, you do not need to rebuild WASM.

If you change Doom C files under `src/doom`, rebuild the WASM bundle before Docker:

```powershell
$wslRepo = (wsl -d Ubuntu-24.04 -e wslpath -a (Get-Location).Path).Trim()
wsl -d Ubuntu-24.04 -e bash -lc "cd '$wslRepo/src/doom' && source /root/emsdk/emsdk_env.sh >/dev/null && make -f Makefile -o Makefile libdoom.a"
wsl -d Ubuntu-24.04 -e bash -lc "cd '$wslRepo/src' && source /root/emsdk/emsdk_env.sh >/dev/null && make -f Makefile -o Makefile -o doom/Makefile websockets-doom.html"
```

## How prompts use this map

`doom_arena_map_blueprints.py` loads the ASCII map and variants JSON.

It provides:

- map bounds
- ASCII map text
- wall components
- spawn coordinates
- scenario labels

The MCP prompt generator uses that data so agents can understand the map structure without reading the full Doom WAD.

## Checklist for map edits

1. Edit `duel_e1m8_ascii.txt` for geometry.
2. Edit `duel_e1m8_variants.json` for spawn variants and labels.
3. Regenerate `src/doom1-arena.wad`.
4. Rebuild/relaunch Docker.
5. Hard-refresh the browser if old assets appear cached.
