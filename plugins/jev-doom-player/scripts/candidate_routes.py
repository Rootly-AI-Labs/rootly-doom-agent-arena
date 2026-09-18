"""Deterministic route candidates for the Jev Doom player.

The engine deliberately depends on an imported arena module instead of
duplicating arena state, token handling, or route-validation rules.  It only
consumes observations that have already passed through the arena's fog-of-war
filter.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence


WALL_CLEARANCE_UNITS = 24
DEFAULT_MAX_WAYPOINTS = 8

CANDIDATE_ORDER = (
    "continue_current",
    "pursue_visible",
    "pursue_last_seen",
    "flank_left",
    "flank_right",
    "seek_health",
    "seek_shotgun",
    "disengage",
    "hold_position",
    "handoff_to_opus",
)


class CandidateRouteError(ValueError):
    """Raised when the route engine cannot satisfy its local contract."""


@dataclass(frozen=True, slots=True)
class GridGraph:
    """A stable four-neighbour view of one arena blueprint."""

    scenario_id: str
    rows: tuple[str, ...]
    walkable_cells: tuple[str, ...]
    neighbors: Mapping[str, tuple[str, ...]]
    cell_size: int
    bounds: Mapping[str, int]


def _cell_label(row: int, col: int) -> str:
    if row < 0 or row >= 26:
        raise CandidateRouteError("ASCII maps with more than 26 rows are unsupported")
    return f"{chr(ord('A') + row)}{col + 1:02d}"


def _row_col(cell: str) -> tuple[int, int]:
    return ord(cell[0]) - ord("A"), int(cell[1:]) - 1


def shortest_path(graph: GridGraph, start_cell: str, target_cell: str) -> list[str] | None:
    """Return the deterministic BFS path, including both endpoints."""

    if start_cell not in graph.neighbors or target_cell not in graph.neighbors:
        return None
    if start_cell == target_cell:
        return [start_cell]

    previous, _distance = _shortest_path_tree(graph, start_cell, stop_at=target_cell)
    return _reconstruct_path(previous, target_cell)


def _shortest_path_tree(
    graph: GridGraph,
    start_cell: str,
    *,
    stop_at: str = "",
) -> tuple[dict[str, str | None], dict[str, int]]:
    if start_cell not in graph.neighbors:
        return {}, {}
    frontier: deque[str] = deque([start_cell])
    previous: dict[str, str | None] = {start_cell: None}
    distance = {start_cell: 0}
    while frontier:
        current = frontier.popleft()
        for neighbor in graph.neighbors[current]:
            if neighbor in previous:
                continue
            previous[neighbor] = current
            distance[neighbor] = distance[current] + 1
            if neighbor == stop_at:
                return previous, distance
            frontier.append(neighbor)
    return previous, distance


def _reconstruct_path(
    previous: Mapping[str, str | None],
    target_cell: str,
) -> list[str] | None:
    if target_cell not in previous:
        return None
    path = [target_cell]
    cursor = previous[target_cell]
    while cursor is not None:
        path.append(cursor)
        cursor = previous[cursor]
    path.reverse()
    return path


def compress_collinear_path(path: Sequence[str]) -> list[str]:
    """Compress a cell-by-cell path to turn points and the final waypoint.

    The first path cell is the actor's current cell and is omitted from a
    moving route.  A one-cell path becomes a one-waypoint hold route.
    """

    cells = list(path)
    if not cells:
        return []
    if len(cells) == 1:
        return [cells[0]]

    waypoints: list[str] = []
    previous_direction: tuple[int, int] | None = None
    for index in range(1, len(cells)):
        previous_row, previous_col = _row_col(cells[index - 1])
        row, col = _row_col(cells[index])
        direction = (row - previous_row, col - previous_col)
        if previous_direction is not None and direction != previous_direction:
            waypoints.append(cells[index - 1])
        previous_direction = direction
    waypoints.append(cells[-1])
    return waypoints


class CandidateRouteEngine:
    """Generate legal deterministic choices from a filtered observation."""

    def __init__(
        self,
        arena_module: Any,
        *,
        blueprint_loader: Callable[[str], Mapping[str, Any]] | None = None,
        route_normalizer: Callable[..., Any] | None = None,
        clearance_checker: Callable[[str, str, int], bool] | None = None,
    ) -> None:
        self.arena = arena_module
        self.blueprint_loader = blueprint_loader or self._required_helper("load_geometry_blueprint")
        self.route_normalizer = route_normalizer or self._required_helper("normalize_plan_route")
        self.cell_normalizer = self._required_helper("normalize_grid_cell")
        self.xy_to_cell = self._required_helper("xy_to_grid_cell")
        self.max_waypoints = int(
            getattr(arena_module, "PLAN_ROUTE_MAX_WAYPOINTS", DEFAULT_MAX_WAYPOINTS)
        )
        if self.max_waypoints <= 0:
            raise CandidateRouteError("arena route waypoint limit must be positive")
        self._graph_cache: dict[str, GridGraph] = {}
        self._clearance_cache: dict[tuple[str, str], bool] = {}

        if clearance_checker is not None:
            self.clearance_checker = clearance_checker
        else:
            near_walls = self._required_helper("wall_clearance_cells_near_segment")

            def arena_clearance(start: str, end: str, clearance: int) -> bool:
                if clearance != WALL_CLEARANCE_UNITS:
                    raise CandidateRouteError("route clearance must remain pinned to 24 units")
                return not bool(near_walls(start, end))

            self.clearance_checker = arena_clearance

    def _required_helper(self, name: str) -> Callable[..., Any]:
        helper = getattr(self.arena, name, None)
        if not callable(helper):
            raise CandidateRouteError(f"arena module is missing required helper: {name}")
        return helper

    def _normalize_cell(self, value: Any) -> str:
        if value is None or value == "":
            return ""
        try:
            return str(self.cell_normalizer(value))
        except (TypeError, ValueError, RuntimeError):
            return ""

    def _observation_cell(self, block: Mapping[str, Any]) -> str:
        cell = self._normalize_cell(block.get("cell"))
        if cell:
            return cell
        if block.get("x") is None or block.get("y") is None:
            return ""
        try:
            return self._normalize_cell(self.xy_to_cell(block.get("x"), block.get("y")))
        except (TypeError, ValueError, RuntimeError):
            return ""

    def _segment_has_clearance(self, start_cell: str, end_cell: str) -> bool:
        if start_cell == end_cell:
            return True
        edge = tuple(sorted((start_cell, end_cell)))
        if edge not in self._clearance_cache:
            self._clearance_cache[edge] = bool(
                self.clearance_checker(start_cell, end_cell, WALL_CLEARANCE_UNITS)
            )
        return self._clearance_cache[edge]

    def build_graph(self, scenario_id: str) -> GridGraph:
        """Build a deterministic, wall-cleared four-neighbour graph."""

        requested_scenario = str(scenario_id)
        cached = self._graph_cache.get(requested_scenario)
        if cached is not None:
            return cached

        blueprint = self.blueprint_loader(requested_scenario)
        if not isinstance(blueprint, Mapping):
            raise CandidateRouteError("map blueprint must be an object")
        raw_ascii = str(blueprint.get("ascii_map", ""))
        source_rows = [line.rstrip("\r") for line in raw_ascii.splitlines() if line.strip()]
        if not source_rows:
            raise CandidateRouteError("map blueprint has no ASCII geometry")
        if len(source_rows) > 26:
            raise CandidateRouteError("ASCII maps with more than 26 rows are unsupported")

        width = max(len(row) for row in source_rows)
        rows = tuple(row.ljust(width, "#") for row in source_rows)
        walkable = {
            _cell_label(row_index, col_index)
            for row_index, row in enumerate(rows)
            for col_index, marker in enumerate(row)
            if marker != "#"
        }

        edge_clearance: dict[tuple[str, str], bool] = {}
        neighbors: dict[str, tuple[str, ...]] = {}
        for cell in sorted(walkable):
            row, col = _row_col(cell)
            adjacent: list[str] = []
            for delta_row, delta_col in ((-1, 0), (0, -1), (0, 1), (1, 0)):
                candidate_row = row + delta_row
                candidate_col = col + delta_col
                if not (0 <= candidate_row < len(rows) and 0 <= candidate_col < width):
                    continue
                candidate = _cell_label(candidate_row, candidate_col)
                if candidate not in walkable:
                    continue
                edge = tuple(sorted((cell, candidate)))
                if edge not in edge_clearance:
                    edge_clearance[edge] = self._segment_has_clearance(*edge)
                if edge_clearance[edge]:
                    adjacent.append(candidate)
            neighbors[cell] = tuple(sorted(adjacent))

        raw_bounds = blueprint.get("bounds", {})
        bounds = {
            str(key): int(value)
            for key, value in raw_bounds.items()
            if str(key) in {"x_min", "x_max", "y_min", "y_max"}
        } if isinstance(raw_bounds, Mapping) else {}
        graph = GridGraph(
            scenario_id=str(blueprint.get("scenario_id") or scenario_id),
            rows=rows,
            walkable_cells=tuple(sorted(walkable)),
            neighbors=neighbors,
            cell_size=int(blueprint.get("cell_size", 64)),
            bounds=bounds,
        )
        self._graph_cache[requested_scenario] = graph
        return graph

    def _segments_have_clearance(self, start_cell: str, route: Sequence[str]) -> bool:
        previous = start_cell
        for cell in route:
            if not self._segment_has_clearance(previous, cell):
                return False
            previous = cell
        return True

    def _arena_validated_route(
        self,
        graph: GridGraph,
        start_cell: str,
        route: Sequence[str],
    ) -> list[str] | None:
        cells = list(route)
        if not cells or len(cells) > self.max_waypoints:
            return None
        if any(cell not in graph.neighbors for cell in cells):
            return None
        if not self._segments_have_clearance(start_cell, cells):
            return None
        try:
            normalized = self.route_normalizer(cells, start_cell=start_cell)
        except (TypeError, ValueError, RuntimeError):
            return None
        if not isinstance(normalized, tuple) or len(normalized) < 2:
            raise CandidateRouteError("arena normalize_plan_route returned an unexpected value")
        normalized_cells = [str(cell) for cell in normalized[1]]
        if not normalized_cells or len(normalized_cells) > self.max_waypoints:
            return None
        if any(cell not in graph.neighbors for cell in normalized_cells):
            return None
        if not self._segments_have_clearance(start_cell, normalized_cells):
            return None
        return normalized_cells

    def route_to(
        self,
        graph: GridGraph,
        start_cell: Any,
        target_cell: Any,
    ) -> list[str] | None:
        """Find, compress, clearance-check, and arena-validate one route."""

        start = self._normalize_cell(start_cell)
        target = self._normalize_cell(target_cell)
        path = shortest_path(graph, start, target)
        if path is None:
            return None
        route = compress_collinear_path(path)
        return self._arena_validated_route(graph, start, route)

    def _walkable_target(self, graph: GridGraph, target_cell: Any) -> str:
        target = self._normalize_cell(target_cell)
        if target in graph.neighbors:
            return target
        if not target:
            return ""
        try:
            target_row, target_col = _row_col(target)
        except (TypeError, ValueError, IndexError):
            return ""
        return min(
            graph.walkable_cells,
            key=lambda cell: (
                abs(_row_col(cell)[0] - target_row) + abs(_row_col(cell)[1] - target_col),
                cell,
            ),
            default="",
        )

    def _current_plan_goal(
        self,
        observation: Mapping[str, Any],
        current_plan: Mapping[str, Any] | None,
    ) -> tuple[str, str]:
        plan = current_plan
        if not isinstance(plan, Mapping):
            for key in ("active_plan", "last_plan"):
                candidate = observation.get(key)
                if isinstance(candidate, Mapping):
                    plan = candidate
                    break
        if not isinstance(plan, Mapping):
            return "", "engage_if_visible"

        raw_route = plan.get("route_cells") or plan.get("route") or []
        cells: list[str] = []
        if isinstance(raw_route, Sequence) and not isinstance(raw_route, (str, bytes)):
            for item in raw_route:
                if isinstance(item, str):
                    cell = self._normalize_cell(item)
                    if cell:
                        cells.append(cell)
                elif isinstance(item, Mapping) and item.get("cell"):
                    cell = self._normalize_cell(item.get("cell"))
                    if cell:
                        cells.append(cell)
        engagement = str(plan.get("engagement_policy") or "engage_if_visible")
        allowed = set(getattr(self.arena, "PLAN_ENGAGEMENT_POLICIES", ()))
        if allowed and engagement not in allowed:
            engagement = "engage_if_visible"
        return (cells[-1] if cells else ""), engagement

    def _flank_target(self, graph: GridGraph, threat_cell: str, side: str) -> str:
        if threat_cell not in graph.neighbors:
            return ""
        threat_row, threat_col = _row_col(threat_cell)
        sign = -1 if side == "left" else 1
        options: list[tuple[int, int, str]] = []
        for cell in graph.walkable_cells:
            row, col = _row_col(cell)
            horizontal_delta = col - threat_col
            if horizontal_delta == 0 or (horizontal_delta < 0) != (sign < 0):
                continue
            distance = abs(row - threat_row) + abs(horizontal_delta)
            if distance > 3:
                continue
            options.append((distance, abs(row - threat_row), cell))
        return min(options, default=(0, 0, ""))[2]

    def _pickup_target(
        self,
        graph: GridGraph,
        start_cell: str,
        pickups: Any,
        kind: str,
    ) -> str:
        if not isinstance(pickups, list):
            return ""
        options: list[tuple[int, str, str]] = []
        for pickup in pickups:
            if not isinstance(pickup, Mapping) or pickup.get("available") is False:
                continue
            pickup_type = str(pickup.get("type", "")).lower()
            descriptor = " ".join(
                str(pickup.get(key, "")).lower() for key in ("id", "name", "type")
            )
            if kind == "health" and pickup_type != "health":
                continue
            if kind == "shotgun" and "shotgun" not in descriptor:
                continue
            target = self._walkable_target(graph, pickup.get("cell"))
            path = shortest_path(graph, start_cell, target)
            if path is None:
                continue
            if self.route_to(graph, start_cell, target) is None:
                continue
            options.append((len(path), target, str(pickup.get("id", ""))))
        return min(options, default=(0, "", ""))[1]

    def _disengage_target(
        self,
        graph: GridGraph,
        start_cell: str,
        threat_cell: str,
    ) -> str:
        if threat_cell not in graph.neighbors:
            return ""
        threat_row, threat_col = _row_col(threat_cell)
        _previous, path_distances = _shortest_path_tree(graph, start_cell)
        options: list[tuple[int, int, str]] = []
        for cell in graph.walkable_cells:
            if cell == start_cell:
                continue
            if cell not in path_distances:
                continue
            row, col = _row_col(cell)
            threat_distance = abs(row - threat_row) + abs(col - threat_col)
            options.append((-threat_distance, path_distances[cell], cell))
        for _negative_distance, _path_length, cell in sorted(options):
            if self.route_to(graph, start_cell, cell) is not None:
                return cell
        return ""

    def _actionable_candidate(
        self,
        *,
        candidate_id: str,
        objective: str,
        route: Sequence[str],
        engagement_policy: str,
        reasoning: str,
        summary: str,
        plan_note: str,
        target_cell: str,
    ) -> dict[str, Any]:
        note = " ".join(plan_note.split())[:80].rstrip()
        if not note:
            raise CandidateRouteError("actionable candidate plan_note cannot be empty")
        return {
            "id": candidate_id,
            "kind": "plan",
            "actionable": True,
            "objective": " ".join(objective.split())[:64].rstrip(),
            "route": list(route),
            "engagement_policy": engagement_policy,
            "reasoning": " ".join(reasoning.split())[:160].rstrip(),
            "summary": " ".join(summary.split())[:180].rstrip(),
            "plan_note": note,
            "target_cell": target_cell,
        }

    @staticmethod
    def _handoff_candidate(reason: str) -> dict[str, Any]:
        return {
            "id": "handoff_to_opus",
            "kind": "handoff",
            "actionable": False,
            "objective": "Request strategic handoff",
            "reasoning": reason,
            "summary": "Escalate this decision to the frontier model.",
        }

    def generate_candidates(
        self,
        observation: Mapping[str, Any],
        *,
        scenario_id: str = "duel_e1m8",
        current_plan: Mapping[str, Any] | None = None,
        last_seen_cell: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return deterministic candidates in ``CANDIDATE_ORDER`` order."""

        graph = self.build_graph(scenario_id)
        self_block = observation.get("self", {})
        opponent = observation.get("opponent", {})
        map_block = observation.get("map", {})
        if not isinstance(self_block, Mapping):
            self_block = {}
        if not isinstance(opponent, Mapping):
            opponent = {}
        if not isinstance(map_block, Mapping):
            map_block = {}

        start_cell = self._observation_cell(self_block)
        if start_cell not in graph.neighbors:
            return [self._handoff_candidate("No legal current map cell is available.")]

        candidates: list[dict[str, Any]] = []

        def add_target(
            candidate_id: str,
            target_cell: str,
            objective: str,
            engagement_policy: str,
            reasoning: str,
            summary: str,
            plan_note: str,
        ) -> None:
            target = self._walkable_target(graph, target_cell)
            route = self.route_to(graph, start_cell, target)
            if not target or route is None:
                return
            candidates.append(
                self._actionable_candidate(
                    candidate_id=candidate_id,
                    objective=objective,
                    route=route,
                    engagement_policy=engagement_policy,
                    reasoning=reasoning,
                    summary=summary,
                    plan_note=plan_note,
                    target_cell=target,
                )
            )

        current_goal, current_engagement = self._current_plan_goal(observation, current_plan)
        if current_goal:
            add_target(
                "continue_current",
                current_goal,
                "Continue current plan",
                current_engagement,
                "The accepted objective remains reachable.",
                "Continue the current route without changing tactics.",
                "I am staying on this route.",
            )

        visible_cell = ""
        if bool(opponent.get("visible")):
            visible_cell = self._walkable_target(graph, opponent.get("cell"))
            if visible_cell:
                add_target(
                    "pursue_visible",
                    visible_cell,
                    "Pursue visible opponent",
                    "force_fight",
                    "The opponent is currently visible and reachable.",
                    "Close on the visible opponent.",
                    "I see them, and I am pushing now.",
                )

        remembered_cell = self._walkable_target(
            graph,
            last_seen_cell or opponent.get("last_seen_cell"),
        )
        if remembered_cell and remembered_cell != visible_cell:
            add_target(
                "pursue_last_seen",
                remembered_cell,
                "Pursue last seen opponent",
                "engage_if_visible",
                "The last confirmed opponent cell is reachable.",
                "Search through the last confirmed contact cell.",
                "I am checking where I last saw them.",
            )

        threat_cell = visible_cell or remembered_cell
        if threat_cell:
            left_target = self._flank_target(graph, threat_cell, "left")
            right_target = self._flank_target(graph, threat_cell, "right")
            if left_target:
                add_target(
                    "flank_left",
                    left_target,
                    "Flank left of opponent",
                    "engage_if_visible",
                    "A reachable cell approaches from the left side.",
                    "Take the stable left-side approach.",
                    "I am wrapping around the left side.",
                )
            if right_target:
                add_target(
                    "flank_right",
                    right_target,
                    "Flank right of opponent",
                    "engage_if_visible",
                    "A reachable cell approaches from the right side.",
                    "Take the stable right-side approach.",
                    "I am wrapping around the right side.",
                )

        pickups = map_block.get("pickups")
        health_target = self._pickup_target(graph, start_cell, pickups, "health")
        if health_target:
            add_target(
                "seek_health",
                health_target,
                "Seek available health",
                "avoid_until_target",
                "An available health pickup has a legal route.",
                "Reposition to the nearest reachable health pickup.",
                "I need that health before the next fight.",
            )

        shotgun_target = self._pickup_target(graph, start_cell, pickups, "shotgun")
        if shotgun_target:
            add_target(
                "seek_shotgun",
                shotgun_target,
                "Seek available shotgun",
                "avoid_until_target",
                "An available weapon pickup has a legal route.",
                "Reposition to the nearest reachable shotgun.",
                "I am grabbing the shotgun first.",
            )

        if threat_cell:
            disengage_target = self._disengage_target(graph, start_cell, threat_cell)
            if disengage_target:
                add_target(
                    "disengage",
                    disengage_target,
                    "Disengage from opponent",
                    "hold_fire",
                    "This route increases distance from the known threat.",
                    "Break contact along a legal route.",
                    "I am backing out to reset this fight.",
                )

        hold_route = self.route_to(graph, start_cell, start_cell)
        if hold_route is not None:
            candidates.append(
                self._actionable_candidate(
                    candidate_id="hold_position",
                    objective="Hold current position",
                    route=hold_route,
                    engagement_policy="hold_fire",
                    reasoning="No movement is required for this safe fallback.",
                    summary="Hold the current legal cell.",
                    plan_note="I am holding here for a moment.",
                    target_cell=start_cell,
                )
            )

        candidates.append(
            self._handoff_candidate(
                "Use a strategic handoff when deterministic choices are insufficient."
            )
        )
        order = {candidate_id: index for index, candidate_id in enumerate(CANDIDATE_ORDER)}
        return sorted(candidates, key=lambda candidate: order[candidate["id"]])

    def safe_fallback(
        self,
        observation: Mapping[str, Any],
        *,
        scenario_id: str = "duel_e1m8",
        current_plan: Mapping[str, Any] | None = None,
        last_seen_cell: str | None = None,
        candidates: Sequence[Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Prefer a validated continuation, otherwise return a validated hold."""

        choices = list(candidates) if candidates is not None else self.generate_candidates(
            observation,
            scenario_id=scenario_id,
            current_plan=current_plan,
            last_seen_cell=last_seen_cell,
        )
        for preferred_id in ("continue_current", "hold_position"):
            for candidate in choices:
                if candidate.get("id") == preferred_id and candidate.get("actionable") is True:
                    return dict(candidate)
        raise CandidateRouteError("no deterministic safe fallback is available")


def build_graph(
    arena_module: Any,
    scenario_id: str,
    **engine_kwargs: Any,
) -> GridGraph:
    """Convenience wrapper for callers that do not retain an engine instance."""

    return CandidateRouteEngine(arena_module, **engine_kwargs).build_graph(scenario_id)


def generate_candidates(
    arena_module: Any,
    observation: Mapping[str, Any],
    *,
    scenario_id: str = "duel_e1m8",
    current_plan: Mapping[str, Any] | None = None,
    last_seen_cell: str | None = None,
    **engine_kwargs: Any,
) -> list[dict[str, Any]]:
    """Convenience wrapper returning deterministic JSON-ready candidates."""

    return CandidateRouteEngine(arena_module, **engine_kwargs).generate_candidates(
        observation,
        scenario_id=scenario_id,
        current_plan=current_plan,
        last_seen_cell=last_seen_cell,
    )


def safe_fallback(
    arena_module: Any,
    observation: Mapping[str, Any],
    *,
    scenario_id: str = "duel_e1m8",
    current_plan: Mapping[str, Any] | None = None,
    last_seen_cell: str | None = None,
    candidates: Sequence[Mapping[str, Any]] | None = None,
    **engine_kwargs: Any,
) -> dict[str, Any]:
    """Convenience wrapper exposing the deterministic safe plan."""

    return CandidateRouteEngine(arena_module, **engine_kwargs).safe_fallback(
        observation,
        scenario_id=scenario_id,
        current_plan=current_plan,
        last_seen_cell=last_seen_cell,
        candidates=candidates,
    )
