from test_latest_planner import harness
from test_controller_jev_only_selection import actionable_candidates
import test_controller as fixtures


def test_decision_id_links_observation_goal_plan_and_outcome():
    h = harness(['seek_health'])
    h.controller._evaluate(fixtures.observation(), actionable_candidates())
    h.controller._submit_candidate(actionable_candidates()[1], source='jev')
    old_id = h.controller._decision_id
    h.controller._decision_id = 'next-decision'
    h.controller._record_outcome('completed', {'opponent': {'visible': False}})
    h.controller._record_outcome('completed')
    events = [(e, p) for e, p in h.telemetry.records if e in {
        'decision_observation', 'jev_goal_decision', 'jev_decision', 'plan_submission', 'plan_outcome'}]
    assert len(events) == 4
    assert {p['decision_id'] for _, p in events} == {old_id}


def test_search_failure_records_history_without_suppressing_destination():
    h = harness(['hold_position'])
    plan = {**actionable_candidates()[1], 'id': 'explore_unvisited:A02',
            'target_cell': 'A02', 'sequence_number': 10}
    h.controller._current_plan = plan
    h.routes.generate_candidates = lambda *a, **kw: [plan, actionable_candidates()[0]]
    h.controller._record_outcome('stalled')
    assert h.controller._recent_plan_outcomes[-1]['outcome'] == 'stalled'
    assert any(c['id'] == plan['id'] for c in h.controller._generate_candidates(fixtures.observation()))


def test_active_destination_persists_without_more_model_calls():
    h = harness(['seek_health'])
    obs = fixtures.lifecycle_observation()
    h.client._observations = [obs] * 7 + [fixtures.lifecycle_observation(phase='finished')]
    original_read = h.client._read_participant_observation_and_plan
    def read(participant):
        observation, _ = original_read(participant)
        return observation, ({'status': 'active', 'sequence_number': 7} if h.client.plan_calls else {})
    h.client._read_participant_observation_and_plan = read
    def candidates(*args, **kwargs):
        values = actionable_candidates()
        if h.client.plan_calls:
            values.append({**values[1], 'id': 'continue_current'})
        return values
    h.routes.generate_candidates = candidates
    try:
        result = h.controller.run(max_run_ms=1000)
        assert result['status'] == 'finished'
        assert len(h.adapter.states) == 1
        assert len(h.client.plan_calls) == 1
        assert any(e == 'plan_outcome' and p['outcome'] == 'match_finished' for e, p in h.telemetry.records)
    finally:
        h.controller.close()
