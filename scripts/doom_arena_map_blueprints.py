"""Shared ASCII map and spawn-variant loading for Doom Arena."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


MAP_BLUEPRINTS_DIR = Path(__file__).resolve().parent / "map_blueprints"
VARIANTS_PATH = MAP_BLUEPRINTS_DIR / "duel_e1m8_variants.json"


def load_variants_config() -> dict[str, Any]:
    return json.loads(VARIANTS_PATH.read_text(encoding="utf-8-sig"))


def resolve_variant_config(scenario_id: str | None) -> tuple[str, dict[str, Any], str, dict[str, Any]]:
    config = load_variants_config()
    variants = config.get("variants", {})
    variant_id = scenario_id or config.get("default_variant") or "duel_e1m8"
    if variant_id not in variants:
        variant_id = config.get("default_variant") or "duel_e1m8"
    variant = variants[variant_id]
    map_id = variant.get("map_id") or config.get("default_map") or "duel_e1m8"
    map_config = config.get("maps", {}).get(map_id, {})
    return variant_id, variant, map_id, map_config


def load_ascii_grid(map_config: dict[str, Any] | None = None) -> list[str]:
    config = load_variants_config()
    if map_config is None:
        map_config = config.get("maps", {}).get(config.get("default_map", "duel_e1m8"), {})
    ascii_name = map_config.get("ascii", "duel_e1m8_ascii.txt")
    path = MAP_BLUEPRINTS_DIR / ascii_name
    rows = [line.rstrip("\r\n") for line in path.read_text(encoding="utf-8").splitlines()]
    rows = [row for row in rows if row.strip()]
    if not rows:
        return []
    width = max(len(row) for row in rows)
    return [row.ljust(width, ".") for row in rows]


def ascii_cell_rect(row_index: int, col_index: int, row_count: int, col_count: int, cell_size: int) -> tuple[int, int, int, int]:
    map_width = col_count * cell_size
    map_height = row_count * cell_size
    x_min = -(map_width // 2)
    y_max = map_height // 2
    left = x_min + col_index * cell_size
    right = left + cell_size
    top = y_max - row_index * cell_size
    bottom = top - cell_size
    return left, bottom, right, top


def _ascii_marker_spawns(rows: list[str], cell_size: int) -> dict[str, dict[str, int]]:
    if not rows:
        return {}
    row_count = len(rows)
    col_count = len(rows[0])
    spawns: dict[str, dict[str, int]] = {}
    for row_index, row in enumerate(rows):
        for col_index, char in enumerate(row):
            if char not in ("1", "2"):
                continue
            left, bottom, right, top = ascii_cell_rect(row_index, col_index, row_count, col_count, cell_size)
            spawns[f"player_{char}"] = {
                "x": (left + right) // 2,
                "y": (bottom + top) // 2,
                "angle_deg": 0 if char == "1" else 180,
            }
    return spawns


def _ascii_wall_obstacles(rows: list[str], cell_size: int) -> list[dict[str, Any]]:
    if not rows:
        return []
    row_count = len(rows)
    col_count = len(rows[0])
    obstacles: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows):
        for col_index, char in enumerate(row):
            if char != "#":
                continue
            left, bottom, right, top = ascii_cell_rect(row_index, col_index, row_count, col_count, cell_size)
            obstacles.append(
                {
                    "kind": "wall",
                    "label": f"wall_r{row_index}_c{col_index}",
                    "x": (left + right) // 2,
                    "y": (bottom + top) // 2,
                    "width": right - left,
                    "height": top - bottom,
                    "bounds": {"x_min": left, "x_max": right, "y_min": bottom, "y_max": top},
                }
            )
    return obstacles
def load_geometry_blueprint(scenario_id: str | None = "duel_e1m8") -> dict[str, Any]:
    config = load_variants_config()
    cell_size = int(config.get("cell_size", 64))
    variant_id, variant, map_id, map_config = resolve_variant_config(scenario_id)
    rows = load_ascii_grid(map_config)
    row_count = len(rows)
    col_count = len(rows[0]) if rows else 0
    map_width = col_count * cell_size
    map_height = row_count * cell_size
    x_min = -(map_width // 2)
    x_max = x_min + map_width
    y_min = -(map_height // 2)
    y_max = y_min + map_height
    obstacles = _ascii_wall_obstacles(rows, cell_size)
    spawns = _ascii_marker_spawns(rows, cell_size)
    spawns.update(variant.get("spawns", {}))
    summary = f"{map_config.get('label', map_id)} generated from {map_config.get('ascii', 'duel_e1m8_ascii.txt')}."
    if not obstacles:
        summary += " No wall cells are present."
    return {
        "map_id": map_id,
        "scenario_id": variant_id,
        "variant_label": variant.get("label", variant_id),
        "summary": summary,
        "cell_size": cell_size,
        "ascii_file": map_config.get("ascii", "duel_e1m8_ascii.txt"),
        "ascii_map": "\n".join(rows),
        "bounds": {"x_min": x_min, "x_max": x_max, "y_min": y_min, "y_max": y_max},
        "compass": {"north": "+y", "east": "+x"},
        "obstacles": obstacles,
        "sightlines": [{"label": obstacle["label"], "blocked_by": "wall"} for obstacle in obstacles],
        "spawns": spawns,
        "notes": [
            f"Map geometry comes from scripts/map_blueprints/{map_config.get('ascii', 'duel_e1m8_ascii.txt')}.",
            "Spawn variants come from scripts/map_blueprints/duel_e1m8_variants.json.",
            f"Each ASCII cell is {cell_size} x {cell_size} Doom units.",
        ],
    }


def format_map_blueprint_prompt(scenario_id: str | None = "duel_e1m8") -> str:
    blueprint = load_geometry_blueprint(scenario_id)
    spawns = blueprint.get("spawns", {})
    player_1 = spawns.get("player_1", {})
    player_2 = spawns.get("player_2", {})
    obstacles = blueprint.get("obstacles", [])
    if obstacles:
        obstacle_lines = [
            f"- {item['label']}: x={item['bounds']['x_min']}..{item['bounds']['x_max']}, y={item['bounds']['y_min']}..{item['bounds']['y_max']}"
            for item in obstacles
        ]
    else:
        obstacle_lines = ["- none"]
    return "\n".join(
        [
            f"Map: {blueprint['map_id']} ({blueprint['variant_label']})",
            f"Cell size: {blueprint['cell_size']} Doom units",
            f"Bounds: x={blueprint['bounds']['x_min']}..{blueprint['bounds']['x_max']}, y={blueprint['bounds']['y_min']}..{blueprint['bounds']['y_max']}",
            "ASCII map:",
            blueprint["ascii_map"],
            "Spawns:",
            f"- player_1: x={player_1.get('x')}, y={player_1.get('y')}, angle={player_1.get('angle_deg')}",
            f"- player_2: x={player_2.get('x')}, y={player_2.get('y')}, angle={player_2.get('angle_deg')}",
            "Obstacles:",
            *obstacle_lines,
        ]
    )
