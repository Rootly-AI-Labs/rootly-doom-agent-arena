from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import pytest


PLUGIN_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(PLUGIN_SCRIPTS))

import candidate_routes as routes  # noqa: E402


class FakeArenaError(RuntimeError):
    pass


class FakeArena:
    PLAN_ROUTE_MAX_WAYPOINTS = 8
    PLAN_ROUTE_WALL_CLEARANCE_UNITS = 24
    PLAN_ENGAGEMENT_POLICIES = {
        "engage_if_visible",
        "avoid_until_target",
        "hold_fire",
        "force_fight",
    }
    DoomArenaError = FakeArenaError

    def __init__(self, ascii_map: str) -> None:
        self.rows = tuple(line for line in ascii_map.splitlines() if line)
        self.width = max(len(row) for row in self.rows)
        self.normalization_calls: list[tuple[str, tuple[str, ...]]] = []

    def load_geometry_blueprint(self, scenario_id: str) -> dict[str, Any]:
        return {
            "scenario_id": scenario_id,
            "ascii_map": "\n".join(self.rows),
            "cell_size": 64,
            "bounds": {
                "x_min": -(self.width * 32),
                "x_max": self.width * 32,
                "y_min": -(len(self.rows) * 32),
                "y_max": len(self.rows) * 32,
            },
        }

    def normalize_grid_cell(self, value: Any) -> str:
        if isinstance(value, (list, tuple)) and len(value) == 2:
            text = f"{str(value[0]).strip().upper()}{int(value[1]):02d}"
        else:
            text = str(value).strip().upper()
        if not re.fullmatch(r"[A-Z]\d{2}", text):
            raise FakeArenaError("invalid cell")
        row = ord(text[0]) - ord("A")
        col = int(text[1:]) - 1
        if not (0 <= row < len(self.rows) and 0 <= col < self.width):
            raise FakeArenaError("cell outside map")
        return text

    def xy_to_grid_cell(self, x: Any, y: Any) -> str:
        row = max(0, min(len(self.rows) - 1, int(y)))
        col = max(0, min(self.width - 1, int(x)))
        return f"{chr(ord('A') + row)}{col + 1:02d}"

    def wall_clearance_cells_near_segment(self, start: str, end: str) -> list[str]:
        return []

    def normalize_plan_route(
        self,
        route: list[str],
        *,
        start_cell: str = "",
        **_kwargs: Any,
    ) -> tuple[str, list[str]]:
        cells = [self.normalize_grid_cell(cell) for cell in route]
        if not cells or len(cells) > self.PLAN_ROUTE_MAX_WAYPOINTS:
            raise FakeArenaError("invalid route length")
        previous = start_cell
        for cell in cells:
            if self._is_wall(cell):
                raise FakeArenaError("blocked cell")
            if previous:
                previous_row, previous_col = self._row_col(previous)
                row, col = self._row_col(cell)
                if previous_row != row and previous_col != col:
                    raise FakeArenaError("diagonal segment")
            previous = cell
        self.normalization_calls.append((start_cell, tuple(cells)))
        return ";".join(cells), cells

    def _row_col(self, cell: str) -> tuple[int, int]:
        return ord(cell[0]) - ord("A"), int(cell[1:]) - 1

    def _is_wall(self, cell: str) -> bool:
        row, col = self._row_col(cell)
        return self.rows[row][col] == "#"


def make_engine(
    ascii_map: str,
    *,
    blocked_edges: set[tuple[str, str]] | None = None,
) -> tuple[routes.CandidateRouteEngine, FakeArena, list[tuple[str, str, int]]]:
    arena = FakeArena(ascii_map)
    calls: list[tuple[str, str, int]] = []
    blocked = {tuple(sorted(edge)) for edge in (blocked_edges or set())}

    def clearance(start: str, end: str, units: int) -> bool:
        calls.append((start, end, units))
        return tuple(sorted((start, end))) not in blocked

    return (
        routes.CandidateRouteEngine(arena, clearance_checker=clearance),
        arena,
        calls,
    )


def test_graph_is_four_neighbor_stable_and_applies_24_unit_clearance() -> None:
    engine, _arena, clearance_calls = make_engine(
        "...\n.#.\n...",
        blocked_edges={("A01", "A02")},
    )

    graph = engine.build_graph("test_map")

    assert "B02" not in graph.walkable_cells
    assert graph.neighbors["A01"] == ("B01",)
    assert graph.neighbors["A03"] == ("A02", "B03")
    assert "C02" not in graph.neighbors["A01"]
    assert clearance_calls
    assert {units for _start, _end, units in clearance_calls} == {24}


def test_bfs_uses_stable_lexical_tie_breaking() -> None:
    engine, _arena, _calls = make_engine("...\n...\n...")
    graph = engine.build_graph("test_map")

    assert routes.shortest_path(graph, "A01", "C03") == [
        "A01",
        "A02",
        "A03",
        "B03",
        "C03",
    ]


def test_collinear_compression_keeps_only_turns_and_destination() -> None:
    assert routes.compress_collinear_path(
        ["A01", "A02", "A03", "B03", "C03", "C04"]
    ) == ["A03", "C03", "C04"]
    assert routes.compress_collinear_path(["B02"]) == ["B02"]


def test_route_accepts_arena_supported_tuple_cells() -> None:
    engine, _arena, _calls = make_engine("...")
    graph = engine.build_graph("test_map")

    assert engine.route_to(graph, ["A", 1], ("A", 3)) == ["A03"]


def test_route_over_eight_compressed_waypoints_is_not_offered() -> None:
    engine, arena, _calls = make_engine(
        "....\n"
        "###.\n"
        "....\n"
        ".###\n"
        "....\n"
        "###.\n"
        "....\n"
        ".###\n"
        "....\n"
        "###.\n"
        "...."
    )
    graph = engine.build_graph("snake")

    assert engine.route_to(graph, "A01", "K01") is None
    assert arena.normalization_calls == []


def test_arena_normalizer_is_the_final_route_authority() -> None:
    arena = FakeArena("...")

    def reject_final_cell(route: list[str], *, start_cell: str = "") -> tuple[str, list[str]]:
        if route[-1] == "A03":
            raise FakeArenaError("arena rejected route")
        return arena.normalize_plan_route(route, start_cell=start_cell)

    engine = routes.CandidateRouteEngine(
        arena,
        route_normalizer=reject_final_cell,
        clearance_checker=lambda _start, _end, units: units == 24,
    )
    graph = engine.build_graph("test_map")

    assert engine.route_to(graph, "A01", "A03") is None


