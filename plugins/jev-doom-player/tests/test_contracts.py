from __future__ import annotations

import pytest

from contracts import CONTROLLER_MODES, ContractError, assert_outbound_safe, build_outbound_state, make_handoff_packet


def sample_observation(*, visible: bool = False):
    return {
        "participant_id": "player_1",
        "opponent_id": "player_2",
        "state_mode": "fog_of_war",
        "self": {"health": 75, "alive": True, "cell": "M06", "x": -700, "y": 20, "ammo_bullets": 40},
        "opponent": {
            "participant_id": "player_2",
            "alive": True,
            "visible": visible,
            "health": 80,
            "cell": "M20",
            "x": 999,
            "y": 888,
        },
        "tactical_context": {"los_status": "blocked", "replan_recommended": True, "replan_reasons": ["lost_los"]},
        "map": {"pickups": [{"id": "health_a", "type": "health", "cell": "D04", "x": 1, "y": 2}]},
        "match": {"phase": "combat", "elapsed_time_seconds": 3},
        "controller_token": "never-send-me",
    }


def test_controller_modes_are_frozen():
    assert CONTROLLER_MODES == {
        "idle", "prepared", "running", "awaiting_opus", "stopping", "finished", "failed"
    }


def test_outbound_state_hides_coordinates_and_hidden_opponent_details():
    outbound = build_outbound_state(sample_observation(visible=False), strategic_directive="Stay safe")

    assert outbound["self"]["cell"] == "M06"
    assert "x" not in outbound["self"]
    assert outbound["opponent"] == {"participant_id": "player_2", "alive": True, "visible": False}
    assert "controller_token" not in outbound
    assert outbound["pickups"] == [{"id": "health_a", "type": "health", "cell": "D04"}]


def test_visible_opponent_cell_is_allowed_but_coordinates_are_not():
    outbound = build_outbound_state(sample_observation(visible=True))
    assert outbound["opponent"]["cell"] == "M20"
    assert "x" not in outbound["opponent"]
    assert "y" not in outbound["opponent"]


@pytest.mark.parametrize(
    "payload",
    [
        {"controller_token": "abc"},
        {"nested": {"openrouter_api_key": "abc"}},
        {"note": "sk-or-v1-abcdefghijk"},
        {"path": r"C:\\Users\\someone\\secret.txt"},
    ],
)
def test_outbound_guard_rejects_secrets_and_local_paths(payload):
    with pytest.raises(ContractError):
        assert_outbound_safe(payload)


def test_handoff_packet_is_compact_and_sanitized():
    state = build_outbound_state(sample_observation())
    packet = make_handoff_packet(
        reason="low_confidence",
        state=state,
        current_plan={"candidate_id": "hold", "route": ["M06"]},
        candidates=[{"id": "hold", "objective": "hold", "route": ["M06"], "reasoning": "Safe"}],
        probabilities={"hold": 0.6},
        confidence=0.2,
    )
    assert packet["reason"] == "low_confidence"
    assert packet["candidates"][0]["id"] == "hold"
    assert packet["confidence"] == 0.2

