import copy
import pytest
import test_controller as fixtures
from test_controller_jev_only_selection import actionable_candidates
from controller import ControllerError
from jev_adapter import JevDecision


def harness(choices):
    h = fixtures.make_lifecycle_harness(decisions=[
        JevDecision(selected_id=c, confidence=0.01, latency_ms=2) for c in choices])
    h.routes.generate_candidates = lambda *a, **kw: copy.deepcopy(actionable_candidates())
    h.controller.prepare('player_1', control_mode='jev_only')
    return h


@pytest.mark.parametrize('version', ['flat_v1', 'flat_v2', 'hierarchical_v1'])
def test_removed_versions_rejected_before_preparing(version):
    h = fixtures.make_lifecycle_harness()
    with pytest.raises(ControllerError, match='Only flat_v3'):
        h.controller.prepare('player_1', control_mode='jev_only', planner_version=version)
    assert h.controller._mode == 'idle'


def test_one_call_and_no_goal_selection():
    h = harness(['seek_health'])
    h.controller._evaluate(fixtures.observation(), actionable_candidates())
    assert len(h.adapter.states) == 1
    assert not any(event == 'jev_goal_decision' for event, _ in h.telemetry.records)


def test_rejected_directive_does_not_require_repreparing():
    h = harness(['hold_position'])
    with pytest.raises(TypeError):
        h.controller.run(strategic_directive='old prompt')
    assert h.controller._mode == 'prepared'
    assert h.controller._planner_version == 'flat_v3'
