"""Frozen neutral_v1 route menu. Geometry assistance, never a utility ranking."""
from collections import defaultdict
from dataclasses import replace
from functools import lru_cache
from hashlib import sha256
from pathlib import Path

from candidate_routes import shortest_path, compress_collinear_path, _row_col, _shortest_path_tree

VERSION = 'neutral_v1'
BUDGET = 20
FAMILIES = (
    'continue_current', 'pursue_visible', 'investigate_last_seen', 'seek_shotgun',
    'seek_health', 'pickup_then_move', 'sweep_region', 'explore_unvisited',
    'recheck_region', 'alternate_approach', 'move_to_cover', 'increase_distance',
    'move_to_position', 'hold_position',
)


@lru_cache(maxsize=1)
def generator_hash():
    return sha256(Path(__file__).read_bytes()).hexdigest()


def generate(engine, observation, *, scenario_id, current_plan=None,
             last_seen_cell='', visited_cells=None, now=0):
    graph = engine.build_graph(scenario_id)
    start = engine._observation_cell(observation.get('self', {}))
    visited = visited_cells or {}
    pool, omitted = [], []
    if start not in graph.neighbors:
        return [], {'version': VERSION, 'offered': [], 'omitted': [], 'error': 'invalid_start'}

    def offer(family, target, via=(), path=None, policy='engage_if_visible', label=''):
        cid = family if family in {'continue_current', 'hold_position'} else f'{family}:{label or target}'
        if path is None:
            path = [start]
            for destination in (*via, target):
                segment = shortest_path(graph, path[-1], destination)
                if segment is None:
                    omitted.append({'id': cid, 'target_cell': target, 'reason': 'unreachable'})
                    return
                path.extend(segment[1:])
        route = engine._arena_validated_route(graph, start, compress_collinear_path(path))
        if not route or (target == start and len(path) == 1 and family != 'hold_position'):
            omitted.append({'id': cid, 'target_cell': target, 'route': compress_collinear_path(path),
                            'reason': 'invalid_route_or_no_movement'})
            return
        candidate = engine._actionable_candidate(
            candidate_id=cid, objective=('Hold current position' if family == 'hold_position'
                else f'{family.replace("_", " ")} at {target}'), route=route,
            engagement_policy=policy, reasoning='Public geometry and supplied observation.',
            summary=f'Route to {target}.', plan_note=f'I am selecting {family.replace("_", " ")}.',
            target_cell=target)
        candidate.update(action_family=family, path_length_cells=len(path)-1,
                         via_cells=list(via), last_visited_age_seconds=(max(0, now-visited[target])
                         if target in visited else None))
        pool.append(candidate)

    # Preserve the actual remaining route, not a newly chosen shortcut to its end.
    plan = current_plan or {}
    raw_route = plan.get('route_cells', plan.get('route', []))
    if raw_route and plan.get('status') not in {'complete', 'completed', 'route_complete', 'stalled', 'rejected'}:
        route = list(raw_route)
        waypoint = plan.get('current_waypoint_cell')
        if waypoint in route:
            route = route[route.index(waypoint):]
        elif start in route:
            route = route[route.index(start)+1:]
        if route:
            offer('continue_current', route[-1], via=route[:-1],
                  policy=plan.get('engagement_policy') or 'engage_if_visible')

    opponent = observation.get('opponent', {})
    visible = opponent.get('cell') if opponent.get('visible') else ''
    if visible in graph.neighbors:
        offer('pursue_visible', visible)
    if last_seen_cell in graph.neighbors:
        offer('investigate_last_seen', last_seen_cell)
    threat = visible if visible in graph.neighbors else last_seen_cell

    # Five public geometric regions, anchored at normalized grid coordinates.
    height, width = len(graph.rows), max(map(len, graph.rows))
    _, reachable = _shortest_path_tree(graph, start)
    anchors = {}
    for name, ry, rx in [('center', .5, .5), ('northwest', .25, .25),
                         ('northeast', .25, .75), ('southwest', .75, .25),
                         ('southeast', .75, .75)]:
        anchors[name] = min(reachable, key=lambda c:
            (abs(_row_col(c)[0]-ry*(height-1))+abs(_row_col(c)[1]-rx*(width-1)), c))
    for region, target in anchors.items():
        offer('move_to_position', target, label=region)
        # A two-anchor sweep expresses coverage instead of a one-cell exploration hop.
        other = anchors['center'] if region != 'center' else anchors['northwest']
        offer('sweep_region', target, via=(other,), label=region)
        if target not in visited:
            offer('explore_unvisited', target, label=region)
        else:
            offer('recheck_region', target, label=region)

    pickups = observation.get('map', {}).get('pickups', [])
    for pickup in sorted(pickups, key=lambda p: (str(p.get('cell')), str(p.get('id')))):
        descriptor = ' '.join(str(pickup.get(k, '')).lower() for k in ('type', 'name', 'id'))
        family = 'seek_health' if pickup.get('type') == 'health' else 'seek_shotgun' if 'shotgun' in descriptor else ''
        if not family:
            continue
        target = pickup.get('cell', '')
        if pickup.get('available') is not True:
            omitted.append({'id': f'{family}:{target}', 'reason': 'unavailable_or_unknown'})
            continue
        offer(family, target)
        for region, onward in anchors.items():
            if onward != target:
                offer('pickup_then_move', onward, via=(target,), label=f'{target}_{region}')
        # Nearby public junctions allow a pickup-plus-movement plan even when a
        # full cross-region route would exceed the shared eight-waypoint limit.
        _, from_pickup = _shortest_path_tree(graph, target)
        junctions = sorted((c for c, d in from_pickup.items() if d >= 3 and len(graph.neighbors[c]) >= 3),
                           key=lambda c: (from_pickup[c], c))[:2]
        for onward in junctions:
            offer('pickup_then_move', onward, via=(target,), label=f'{target}_{onward}')

    if threat in graph.neighbors:
        sr, sc = _row_col(start)
        tr, tc = _row_col(threat)
        initial_distance = abs(sr-tr)+abs(sc-tc)
        # No health, score, ammo, clock or contact-age eligibility gates.
        for region, target in anchors.items():
            row, col = _row_col(target)
            if abs(row-tr)+abs(col-tc) > initial_distance:
                offer('increase_distance', target, label=region)
        cover = [c for c in graph.walkable_cells if c != start and engine._line_crosses_wall(graph, c, threat)]
        # Fixed geometric order; no threat-distance or tactical score ranking.
        for target in sorted(cover, key=lambda c: (abs(_row_col(c)[0]-sr)+abs(_row_col(c)[1]-sc), c))[:4]:
            offer('move_to_cover', target)

    # Alternate paths exclude a middle edge of the baseline path. This guarantees
    # a different traversed path, not merely an east/west endpoint label.
    for target in sorted({p['target_cell'] for p in pool if p['action_family'] in
                         {'pursue_visible', 'investigate_last_seen', 'seek_health', 'seek_shotgun'}}):
        baseline = shortest_path(graph, start, target)
        if not baseline or len(baseline) < 3:
            continue
        index = (len(baseline)-1)//2
        a, b = baseline[index:index+2]
        neighbors = dict(graph.neighbors)
        neighbors[a] = tuple(c for c in neighbors[a] if c != b)
        neighbors[b] = tuple(c for c in neighbors[b] if c != a)
        alternate = shortest_path(replace(graph, neighbors=neighbors), start, target)
        if alternate:
            offer('alternate_approach', target, path=alternate)
        else:
            omitted.append({'id': f'alternate_approach:{target}', 'reason': 'no_alternate_path'})
    offer('hold_position', start, policy='hold_fire')

    # Fixed family round-robin: a family cannot monopolize the budget by producing
    # many destinations. Policy variants follow default routes and use spare slots.
    queues = defaultdict(list)
    for candidate in pool:
        queues[candidate['action_family']].append(candidate)
    ordered = []
    for depth in range(max(map(len, queues.values()), default=0)):
        for family in FAMILIES:
            if depth < len(queues[family]):
                ordered.append(queues[family][depth])
    defaults = list(ordered)
    for candidate in defaults:
        if candidate['action_family'] in {'hold_position', 'continue_current'}:
            continue
        for policy in ('avoid_until_target', 'hold_fire', 'force_fight'):
            ordered.append({**candidate, 'id': candidate['id']+':'+policy, 'engagement_policy': policy})
    offered, seen = [], set()
    for candidate in ordered:
        signature = (tuple(candidate['route']), candidate['engagement_policy'])
        reason = 'duplicate_route_policy' if signature in seen else 'candidate_budget' if len(offered) >= BUDGET else ''
        if reason:
            omitted.append({**candidate, 'omission_reason': reason})
        else:
            offered.append(candidate)
        seen.add(signature)
    return offered, {'version': VERSION, 'generator_sha256': generator_hash(), 'budget': BUDGET, 'selection_rule':
        'family_round_robin_then_policy_variants; deduplicate route+policy; first 20',
        'offered': offered, 'omitted': omitted}
