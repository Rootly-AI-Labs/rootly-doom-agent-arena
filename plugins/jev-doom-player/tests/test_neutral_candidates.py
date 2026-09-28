from copy import deepcopy
import sys

import pytest

from candidate_routes import CandidateRouteEngine
from neutral_candidates import generate, FAMILIES, BUDGET
from test_candidate_routes import FakeArena
from arena_bridge import resolve_repo_root, load_arena_module
from contracts import build_outbound_state, assert_outbound_safe
from candidate_facts import candidate_facts


def obs():
    return {'self': {'cell': 'A01', 'health': 150},
            'opponent': {'visible': True, 'cell': 'I09', 'health': 150},
            'match': {'elapsed_time_seconds': 0, 'timeout_seconds': 180},
            'map': {'pickups': [{'id': 'shotgun', 'name': 'shotgun', 'type': 'weapon',
                                 'cell': 'C03', 'available': True},
                                {'id': 'health', 'type': 'health', 'cell': 'G07', 'available': True}]}}


def menu(observation=None, **kwargs):
    engine = CandidateRouteEngine(FakeArena('\n'.join(['.........']*9)))
    return generate(engine, observation or obs(), scenario_id='test', **kwargs)


def test_menu_has_neutral_families_unique_routes_fixed_budget_and_audit():
    offered, audit = menu()
    assert len(offered) <= BUDGET
    assert len({(tuple(c['route']), c['engagement_policy']) for c in offered}) == len(offered)
    assert all(c['action_family'] in FAMILIES for c in offered)
    assert all(len(c['route']) <= 8 for c in offered)
    assert audit['offered'] == offered
    assert audit['omitted']
    assert any(c.get('omission_reason') == 'candidate_budget' for c in audit['omitted'])
    assert {c['action_family'] for c in offered} >= {
        'pursue_visible', 'seek_shotgun', 'seek_health', 'pickup_then_move',
        'sweep_region', 'explore_unvisited', 'hold_position'}
    assert all(c['engagement_policy'] == 'engage_if_visible' for c in offered
               if c['action_family'] not in {'hold_position', 'continue_current'})


def test_health_time_and_score_do_not_gate_menu():
    before = obs()
    after = deepcopy(before)
    after['self']['health'] = 1
    after['opponent']['health'] = 1
    after['match']['elapsed_time_seconds'] = 179
    after['tactical_context'] = {'health_delta': -149}
    assert menu(before) == menu(after)


def test_visible_enemy_does_not_remove_search_and_no_cooldown_on_rechecks():
    offered, _ = menu(visited_cells={'C03': 99, 'E05': 99}, now=100)
    assert any(c['action_family'] == 'sweep_region' for c in offered)
    assert any(c['action_family'] == 'recheck_region' for c in offered)


def test_hidden_enemy_coordinates_never_change_menu():
    first = obs()
    first['opponent'] = {'visible': False, 'cell': 'I09', 'health': 1}
    second = deepcopy(first)
    second['opponent'] = {'visible': False, 'cell': 'B02', 'health': 150}
    assert menu(first) == menu(second)


def test_consumed_pickup_not_offered_and_missing_contact_not_invented():
    state = obs()
    state['map']['pickups'][0]['available'] = False
    state['opponent'] = {'visible': False}
    offered, audit = menu(state)
    assert not any(c['action_family'] in {'pursue_visible', 'investigate_last_seen', 'seek_shotgun'} for c in offered)
    assert any(c.get('reason') == 'unavailable_or_unknown' for c in audit['omitted'])


def test_cover_offered_at_full_health_and_alternate_is_distinct():
    engine = CandidateRouteEngine(FakeArena('.........\n....#....\n....#....\n....#....\n.........\n.........\n.........\n.........\n.........'))
    offered, audit = generate(engine, obs(), scenario_id='test')
    all_rows = offered + audit['omitted']
    assert any(c.get('action_family') == 'move_to_cover' for c in all_rows)
    baseline = next(c for c in all_rows if c.get('action_family') == 'seek_shotgun')
    alternate = next(c for c in all_rows if c.get('action_family') == 'alternate_approach' and c['target_cell'] == 'C03')
    assert baseline['route'] != alternate['route']


def test_real_map_menu_passes_arena_validation_and_outbound_size():
    arena = load_arena_module(resolve_repo_root())
    engine = CandidateRouteEngine(arena)
    state = obs()
    state['self']['cell'] = 'B02'
    state['opponent'] = {'visible': False}
    state['map']['pickups'] = [
        {'id': 'shotgun_f17', 'type': 'weapon', 'name': 'shotgun', 'cell': 'F17', 'available': True},
        {'id': 'shotgun_r17', 'type': 'weapon', 'name': 'shotgun', 'cell': 'R17', 'available': True}]
    offered, audit = generate(engine, state, scenario_id='duel_e1m8_blind_spawn')
    assert any(c['action_family'] == 'pickup_then_move' for c in offered)
    for c in offered:
        assert engine._arena_validated_route(engine.build_graph('duel_e1m8_blind_spawn'), 'B02', c['route'])
    outbound = build_outbound_state(state)
    outbound['candidates'] = candidate_facts(offered)
    assert_outbound_safe(outbound)


def test_v3_rejects_host_advice_and_uses_one_choice():
    from test_latest_planner import harness
    from controller import ControllerError
    h = harness(['hold_position'])
    h.controller._planner_version = 'flat_v3'
    with pytest.raises(TypeError):
        h.controller.run(strategic_directive='Get the shotgun')
    offered, audit = menu()
    h.controller._candidate_audit = audit
    h.controller._evaluate(obs(), offered)
    assert len(h.adapter.states) == 1
    assert any(event == 'candidate_menu' for event, _ in h.telemetry.records)
    assert not any(event == 'jev_goal_decision' for event, _ in h.telemetry.records)
