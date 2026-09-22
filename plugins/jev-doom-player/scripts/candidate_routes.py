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
DEFAULT_HEALTH_SEEK_THRESHOLD = 125
DEFAULT_PATROL_AFTER_SECONDS = 18.0
DEFAULT_ENDGAME_SECONDS = 20.0
DEFAULT_BADLY_HURT_HEALTH = 60
DEFAULT_CRITICAL_HEALTH = 35
DEFAULT_FINISH_OPPONENT_HEALTH = 35
DEFAULT_FINISH_MIN_HEALTH = 75
DEFAULT_FINISH_MIN_AMMO = 8

CANDIDATE_ORDER = (
    "continue_current",
    "emergency_retreat",
    "take_cover",
    "protect_lead",
    "finish_opponent",
    "force_fight",
    "deny_pickup",
    "pursue_visible",
    "pursue_last_seen",
    "flank_left",
    "flank_right",
    "seek_health",
    "seek_shotgun",
    "hold_chokepoint",
    "patrol_center",
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
        health_seek_threshold: int = DEFAULT_HEALTH_SEEK_THRESHOLD,
        patrol_after_seconds: float = DEFAULT_PATROL_AFTER_SECONDS,
        endgame_seconds: float = DEFAULT_ENDGAME_SECONDS,
        badly_hurt_health: int = DEFAULT_BADLY_HURT_HEALTH,
        critical_health: int = DEFAULT_CRITICAL_HEALTH,
        finish_opponent_health: int = DEFAULT_FINISH_OPPONENT_HEALTH,
        finish_min_health: int = DEFAULT_FINISH_MIN_HEALTH,
        finish_min_ammo: int = DEFAULT_FINISH_MIN_AMMO,
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
        self.health_seek_threshold = int(health_seek_threshold)
        self.patrol_after_seconds = max(0.0, float(patrol_after_seconds))
        self.endgame_seconds = max(0.0, float(endgame_seconds))
        self.badly_hurt_health = int(badly_hurt_health)
        self.critical_health = int(critical_health)
        self.finish_opponent_health = int(finish_opponent_health)
        self.finish_min_health = int(finish_min_health)
        self.finish_min_ammo = int(finish_min_ammo)
        thresholds = (
            self.health_seek_threshold,
            self.badly_hurt_health,
            self.critical_health,
            self.finish_opponent_health,
            self.finish_min_health,
            self.finish_min_ammo,
        )
        if any(value < 0 for value in thresholds):
            raise CandidateRouteError("health and ammo thresholds cannot be negative")
        if self.critical_health > self.badly_hurt_health:
            raise CandidateRouteError("critical_health cannot exceed badly_hurt_health")
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
    ) -> tuple[str, str, bool]:
        plan = current_plan
        if not isinstance(plan, Mapping):
            for key in ("active_plan", "last_plan"):
                candidate = observation.get(key)
                if isinstance(candidate, Mapping):
                    plan = candidate
                    break
        if not isinstance(plan, Mapping):
            return "", "engage_if_visible", False

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

        result = observation.get("last_plan_result")
        result_status = result.get("status") if isinstance(result, Mapping) else ""
        status = str(plan.get("status") or result_status or "").strip().lower()
        route_complete = status in {"complete", "completed", "route_complete"}
        return (cells[-1] if cells else ""), engagement, route_complete

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

    def _center_patrol_target(self, graph: GridGraph, start_cell: str) -> str:
        """Choose a reachable central cell that produces an actual sweep."""

        if start_cell not in graph.neighbors:
            return ""
        center_row = (len(graph.rows) - 1) / 2.0
        center_col = (max((len(row) for row in graph.rows), default=1) - 1) / 2.0
        _previous, path_distances = _shortest_path_tree(graph, start_cell)
        options: list[tuple[float, int, str]] = []
        for cell in graph.walkable_cells:
            if cell == start_cell or cell not in path_distances:
                continue
            row, col = _row_col(cell)
            center_distance = abs(row - center_row) + abs(col - center_col)
            # Prefer the center first, then the farther reachable option among
            # equally central cells so a completed patrol does not become a hold.
            options.append((center_distance, -path_distances[cell], cell))
        for _center_distance, _negative_path_distance, cell in sorted(options):
            if self.route_to(graph, start_cell, cell) is not None:
                return cell
        return ""

    @staticmethod
    def _integer(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _combat_ammo(self, self_block: Mapping[str, Any]) -> int | None:
        ready_weapon = str(self_block.get("ready_weapon") or "").lower()
        numeric_weapon_ammo = {
            "0": None,  # fist
            "1": "ammo_bullets",
            "2": "ammo_shells",
            "3": "ammo_bullets",
            "4": "ammo_rockets",
            "5": "ammo_cells",
            "6": "ammo_cells",
            "7": None,  # chainsaw
            "8": "ammo_shells",
        }
        if ready_weapon in numeric_weapon_ammo:
            field = numeric_weapon_ammo[ready_weapon]
            if field is None:
                return self.finish_min_ammo
            ammo = self._integer(self_block.get(field))
            if ammo is not None:
                return ammo
        weapon_ammo_fields = (
            (("shotgun",), "ammo_shells"),
            (("rocket",), "ammo_rockets"),
            (("plasma", "bfg"), "ammo_cells"),
            (("pistol", "chaingun"), "ammo_bullets"),
        )
        for weapon_names, field in weapon_ammo_fields:
            if any(name in ready_weapon for name in weapon_names):
                ammo = self._integer(self_block.get(field))
                if ammo is not None:
                    return ammo
        known_ammo = [
            ammo
            for field in ("ammo_bullets", "ammo_shells", "ammo_cells", "ammo_rockets")
            if (ammo := self._integer(self_block.get(field))) is not None
        ]
        return max(known_ammo) if known_ammo else None

    @staticmethod
    def _is_reloading(
        self_block: Mapping[str, Any],
        tactical: Mapping[str, Any],
    ) -> bool:
        status = " ".join(
            str(block.get(key) or "")
            for block, key in (
                (self_block, "command_status"),
                (self_block, "last_action"),
                (tactical, "requested_fire_policy"),
                (tactical, "executed_fire_action"),
            )
        ).lower()
        return "reload" in status

    @staticmethod
    def _line_crosses_wall(graph: GridGraph, start_cell: str, end_cell: str) -> bool:
        """Approximate map occlusion with a deterministic Bresenham grid ray."""

        start_row, start_col = _row_col(start_cell)
        end_row, end_col = _row_col(end_cell)
        col = start_col
        row = start_row
        delta_col = abs(end_col - start_col)
        step_col = 1 if start_col < end_col else -1
        delta_row = -abs(end_row - start_row)
        step_row = 1 if start_row < end_row else -1
        error = delta_col + delta_row
        while (row, col) != (end_row, end_col):
            doubled = 2 * error
            if doubled >= delta_row:
                error += delta_row
                col += step_col
            if doubled <= delta_col:
                error += delta_col
                row += step_row
            if (row, col) == (end_row, end_col):
                break
            if _cell_label(row, col) not in graph.neighbors:
                return True
        return False

    def _cover_target(
        self,
        graph: GridGraph,
        start_cell: str,
        threat_cell: str,
    ) -> str:
        if threat_cell not in graph.neighbors:
            return ""
        threat_row, threat_col = _row_col(threat_cell)
        start_row, start_col = _row_col(start_cell)
        start_threat_distance = abs(start_row - threat_row) + abs(start_col - threat_col)
        _previous, path_distances = _shortest_path_tree(graph, start_cell)
        options: list[tuple[int, int, str]] = []
        for cell, path_distance in path_distances.items():
            if cell == start_cell or not self._line_crosses_wall(graph, cell, threat_cell):
                continue
            row, col = _row_col(cell)
            threat_distance = abs(row - threat_row) + abs(col - threat_col)
            if threat_distance < start_threat_distance:
                continue
            options.append((path_distance, -threat_distance, cell))
        for _path_distance, _negative_threat_distance, cell in sorted(options):
            if self.route_to(graph, start_cell, cell) is not None:
                return cell
        return ""

    def _chokepoint_target(self, graph: GridGraph, start_cell: str) -> str:
        """Prefer a reachable central corridor cell with constrained approaches."""

        center_row = (len(graph.rows) - 1) / 2.0
        center_col = (max((len(row) for row in graph.rows), default=1) - 1) / 2.0
        max_row = len(graph.rows) - 1
        max_col = max((len(row) for row in graph.rows), default=1) - 1
        _previous, path_distances = _shortest_path_tree(graph, start_cell)
        options: list[tuple[int, float, int, str]] = []
        for cell, path_distance in path_distances.items():
            row, col = _row_col(cell)
            if row in {0, max_row} or col in {0, max_col}:
                continue
            neighbors = graph.neighbors[cell]
            neighbor_positions = {_row_col(neighbor) for neighbor in neighbors}
            vertical = {(row - 1, col), (row + 1, col)}
            horizontal = {(row, col - 1), (row, col + 1)}
            if len(neighbors) == 2 and (
                neighbor_positions == vertical or neighbor_positions == horizontal
            ):
                tier = 0
            elif len(neighbors) == 3:
                tier = 1
            else:
                continue
            center_distance = abs(row - center_row) + abs(col - center_col)
            options.append((tier, center_distance, path_distance, cell))
        for _tier, _center_distance, _path_distance, cell in sorted(options):
            if self.route_to(graph, start_cell, cell) is not None:
                return cell
        return ""

    def _deny_pickup_target(
        self,
        graph: GridGraph,
        start_cell: str,
        opponent_cell: str,
        opponent_health: int | None,
        pickups: Any,
    ) -> str:
        if not isinstance(pickups, list) or opponent_cell not in graph.neighbors:
            return ""
        _self_previous, self_distances = _shortest_path_tree(graph, start_cell)
        _opponent_previous, opponent_distances = _shortest_path_tree(graph, opponent_cell)
        options: list[tuple[int, int, int, str]] = []
        for pickup in pickups:
            if not isinstance(pickup, Mapping) or pickup.get("available") is False:
                continue
            pickup_type = str(pickup.get("type") or "").lower()
            descriptor = " ".join(
                str(pickup.get(key) or "").lower() for key in ("id", "name", "type")
            )
            is_health = pickup_type == "health"
            is_weapon = pickup_type == "weapon" or "shotgun" in descriptor
            if not is_weapon and not (
                is_health
                and opponent_health is not None
                and opponent_health <= self.health_seek_threshold
            ):
                continue
            target = self._walkable_target(graph, pickup.get("cell"))
            self_distance = self_distances.get(target)
            opponent_distance = opponent_distances.get(target)
            if (
                self_distance is None
                or opponent_distance is None
                or self_distance > opponent_distance
                or self.route_to(graph, start_cell, target) is None
            ):
                continue
            priority = 0 if is_health and opponent_health <= self.badly_hurt_health else 1
            options.append((priority, self_distance - opponent_distance, self_distance, target))
        return min(options, default=(0, 0, 0, ""))[3]

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
        seconds_since_contact: float = 0.0,
        center_patrol_target: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return deterministic candidates in ``CANDIDATE_ORDER`` order."""

        graph = self.build_graph(scenario_id)
        self_block = observation.get("self", {})
        opponent = observation.get("opponent", {})
        map_block = observation.get("map", {})
        tactical = observation.get("tactical_context", {})
        match = observation.get("match", {})
        if not isinstance(self_block, Mapping):
            self_block = {}
        if not isinstance(opponent, Mapping):
            opponent = {}
        if not isinstance(map_block, Mapping):
            map_block = {}
        if not isinstance(tactical, Mapping):
            tactical = {}
        if not isinstance(match, Mapping):
            match = {}

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

        current_goal, current_engagement, current_route_complete = self._current_plan_goal(
            observation,
            current_plan,
        )
        if current_goal and not current_route_complete and current_goal != start_cell:
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

        pickups = map_block.get("pickups")
        current_health = self._integer(self_block.get("health"))
        opponent_health = self._integer(opponent.get("health"))
        combat_ammo = self._combat_ammo(self_block)
        is_reloading = self._is_reloading(self_block, tactical)
        health_target = self._pickup_target(graph, start_cell, pickups, "health")

        try:
            elapsed_seconds = float(match.get("elapsed_time_seconds"))
            timeout_seconds = float(match.get("timeout_seconds"))
            remaining_seconds = max(0.0, timeout_seconds - elapsed_seconds)
        except (TypeError, ValueError):
            remaining_seconds = None
        try:
            health_delta = float(tactical.get("health_delta"))
        except (TypeError, ValueError):
            health_delta = None
        in_endgame = (
            remaining_seconds is not None
            and remaining_seconds <= self.endgame_seconds
        )

        persisted_center_target = self._walkable_target(graph, center_patrol_target)
        center_target = (
            persisted_center_target
            if persisted_center_target and persisted_center_target != start_cell
            else self._center_patrol_target(graph, start_cell)
        )
        if (
            current_health is not None
            and current_health <= self.critical_health
            and not health_target
            and threat_cell
        ):
            emergency_target = (
                self._cover_target(graph, start_cell, visible_cell)
                if visible_cell
                else ""
            ) or self._disengage_target(graph, start_cell, threat_cell)
            if emergency_target:
                add_target(
                    "emergency_retreat",
                    emergency_target,
                    "Emergency retreat without available health",
                    "hold_fire",
                    "Health is critical and no reachable health pickup is available.",
                    "Break contact along the safest legal route instead of accepting a fatal fight.",
                    "I am critically hurt and getting out now.",
                )

        if visible_cell and (
            is_reloading
            or (current_health is not None and current_health <= self.badly_hurt_health)
        ):
            cover_target = self._cover_target(graph, start_cell, visible_cell)
            if cover_target:
                add_target(
                    "take_cover",
                    cover_target,
                    "Break line of sight behind cover",
                    "hold_fire",
                    "The opponent is visible while health is low or the weapon is reloading.",
                    "Reach the nearest legal cell occluded by map geometry.",
                    "I am breaking sight and taking cover.",
                )

        if in_endgame and health_delta is not None and health_delta > 0:
            protect_target = (
                self._disengage_target(graph, start_cell, threat_cell)
                if threat_cell
                else ""
            ) or health_target or start_cell
            add_target(
                "protect_lead",
                protect_target,
                "Protect the endgame health lead",
                "hold_fire",
                "The final seconds favor preserving the current health advantage.",
                "Deny a late equalizer while the health lead is decisive.",
                "I am protecting this lead until time expires.",
            )
        elif in_endgame:
            force_target = threat_cell or center_target
            if force_target:
                add_target(
                    "force_fight",
                    force_target,
                    "Force a final engagement",
                    "force_fight",
                    "Time is nearly over and the current health state does not secure a win.",
                    "Push the best known contact route before the timeout.",
                    "I need a fight before the clock runs out.",
                )

        if (
            visible_cell
            and current_health is not None
            and current_health >= self.finish_min_health
            and opponent_health is not None
            and opponent_health <= self.finish_opponent_health
            and combat_ammo is not None
            and combat_ammo >= self.finish_min_ammo
        ):
            add_target(
                "finish_opponent",
                visible_cell,
                "Finish the weakened opponent",
                "force_fight",
                "The visible opponent is low while current health and equipped ammunition are sufficient.",
                "Commit to the reachable opponent before they can recover.",
                "They are weak, and I have enough to finish this.",
            )

        if visible_cell:
            deny_target = self._deny_pickup_target(
                graph,
                start_cell,
                visible_cell,
                opponent_health,
                pickups,
            )
            if deny_target:
                add_target(
                    "deny_pickup",
                    deny_target,
                    "Deny a valuable pickup",
                    "engage_if_visible",
                    "A valuable health or weapon pickup is reachable no later than the opponent can reach it.",
                    "Contest the pickup to deny the opponent a recovery or weapon upgrade.",
                    "I am cutting them off from that pickup.",
                )

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

        if not visible_cell and not in_endgame:
            chokepoint_target = self._chokepoint_target(graph, start_cell)
            if chokepoint_target:
                add_target(
                    "hold_chokepoint",
                    chokepoint_target,
                    "Hold a central chokepoint",
                    "engage_if_visible",
                    "A reachable central corridor constrains the opponent's approach.",
                    "Defend a strong doorway instead of waiting in an arbitrary cell.",
                    "I am locking down this central doorway.",
                )

        try:
            contact_gap_seconds = max(0.0, float(seconds_since_contact))
        except (TypeError, ValueError):
            contact_gap_seconds = 0.0
        if (
            not in_endgame
            and not visible_cell
            and contact_gap_seconds >= self.patrol_after_seconds
            and center_target
        ):
            add_target(
                "patrol_center",
                center_target,
                "Patrol the center after lost contact",
                "engage_if_visible",
                "No opponent contact has occurred recently, so sweep the central lanes.",
                "Move through center to restore contact and prevent a passive timeout.",
                "I am sweeping center to find this opponent.",
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
    seconds_since_contact: float = 0.0,
    **engine_kwargs: Any,
) -> list[dict[str, Any]]:
    """Convenience wrapper returning deterministic JSON-ready candidates."""

    return CandidateRouteEngine(arena_module, **engine_kwargs).generate_candidates(
        observation,
        scenario_id=scenario_id,
        current_plan=current_plan,
        last_seen_cell=last_seen_cell,
        seconds_since_contact=seconds_since_contact,
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
