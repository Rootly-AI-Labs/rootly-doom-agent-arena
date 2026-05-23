#!/usr/bin/env python3

import struct
from pathlib import Path

from omg import Lump, MapEditor, Seg, Sidedef, SubSector, Thing, Vertex, WAD
from omg.mapedit import Linedef


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_IWAD = REPO_ROOT / "src" / "doom1.wad"
OUTPUT_IWAD = REPO_ROOT / "src" / "doom1-arena.wad"

ROOM_LEFT = -1024
ROOM_RIGHT = 1024
ROOM_BOTTOM = -768
ROOM_TOP = 768
DIVIDER_BOTTOM = -384
DIVIDER_TOP = 384


def build_blockmap(num_lines: int) -> bytes:
    block_origin_x = ROOM_LEFT
    block_origin_y = ROOM_BOTTOM
    block_width = (ROOM_RIGHT - ROOM_LEFT) // 128
    block_height = (ROOM_TOP - ROOM_BOTTOM) // 128
    offsets_count = block_width * block_height
    line_list = list(range(num_lines)) + [-1]
    list_offset = 4 + offsets_count
    offsets = [list_offset] * offsets_count

    return struct.pack(
        "<" + "h" * (4 + len(offsets) + len(line_list)),
        block_origin_x,
        block_origin_y,
        block_width,
        block_height,
        *offsets,
        *line_list,
    )


def seg_angle(v1: Vertex, v2: Vertex) -> int:
    dx = v2.x - v1.x
    dy = v2.y - v1.y
    if dx > 0 and dy == 0:
        return 0
    if dx < 0 and dy == 0:
        return 32768
    if dx == 0 and dy > 0:
        return 16384
    if dx == 0 and dy < 0:
        return 49152
    if dx > 0 and dy > 0:
        return 8192
    if dx < 0 and dy > 0:
        return 24576
    if dx < 0 and dy < 0:
        return 40960
    return 57344


def deathmatch_start(x: int, y: int, angle: int) -> Thing:
    thing = Thing(x=x, y=y, angle=angle, type=11)
    thing.easy = 1
    thing.medium = 1
    thing.hard = 1
    thing.multiplayer = 1
    return thing


def player_start(x: int, y: int, angle: int, player_num: int) -> Thing:
    thing = Thing(x=x, y=y, angle=angle, type=player_num)
    thing.easy = 1
    thing.medium = 1
    thing.hard = 1
    thing.multiplayer = 1
    return thing


def main() -> None:
    editor = MapEditor()
    wall_sidedef = Sidedef(tx_mid="STARTAN3", tx_up="-", tx_low="-")
    editor.draw_sector(
        [
            (ROOM_LEFT, ROOM_BOTTOM),
            (ROOM_RIGHT, ROOM_BOTTOM),
            (ROOM_RIGHT, ROOM_TOP),
            (ROOM_LEFT, ROOM_TOP),
        ],
        sidedef=wall_sidedef,
    )

    divider_start = len(editor.vertexes)
    editor.vertexes.append(Vertex(0, DIVIDER_BOTTOM))
    editor.vertexes.append(Vertex(0, DIVIDER_TOP))

    editor.sidedefs.append(Sidedef(tx_mid="STARTAN3", tx_up="-", tx_low="-", sector=0))
    editor.sidedefs.append(Sidedef(tx_mid="STARTAN3", tx_up="-", tx_low="-", sector=0))

    editor.linedefs.append(
        Linedef(vx_a=divider_start, vx_b=divider_start + 1, front=4, back=Linedef.NONE, flags=1)
    )
    editor.linedefs.append(
        Linedef(vx_a=divider_start + 1, vx_b=divider_start, front=5, back=Linedef.NONE, flags=1)
    )

    editor.things.extend(
        [
            player_start(-640, 520, 0, 1),
            player_start(640, 520, 180, 2),
            player_start(-320, -520, 0, 3),
            player_start(320, -520, 180, 4),
            deathmatch_start(-768, -512, 45),
            deathmatch_start(768, -512, 135),
            deathmatch_start(768, 512, 225),
            deathmatch_start(-768, 512, 315),
        ]
    )

    editor.segs = []
    for line_index, linedef in enumerate(editor.linedefs):
        v1 = editor.vertexes[linedef.vx_a]
        v2 = editor.vertexes[linedef.vx_b]
        editor.segs.append(
            Seg(
                vx_a=linedef.vx_a,
                vx_b=linedef.vx_b,
                angle=seg_angle(v1, v2),
                line=line_index,
                side=0,
                offset=0,
            )
        )

    editor.ssectors = [SubSector(numsegs=len(editor.segs), seg_a=0)]
    editor.nodes = []
    editor.reject = Lump(b"\x00")
    editor.blockmap = Lump(build_blockmap(len(editor.linedefs)))

    wad = WAD(str(SOURCE_IWAD))
    wad.maps["E1M8"] = editor.to_lumps()
    wad.to_file(str(OUTPUT_IWAD))
    print(f"Wrote {OUTPUT_IWAD}")


if __name__ == "__main__":
    main()
