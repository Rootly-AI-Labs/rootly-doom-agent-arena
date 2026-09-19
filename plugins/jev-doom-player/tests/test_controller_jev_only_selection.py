from __future__ import annotations

import copy
from typing import Any

import pytest
import test_controller as fixtures
from jev_adapter import DEFAULT_MODEL, JevDecision


def actionable_candidates() -> list[dict[str, Any]]:
    hold, handoff = fixtures.candidates()
    return [
        hold,
        {
            "id": "seek_health",
            "kind": "plan",
            "actionable": True,
            "objective": "Reach the nearby health",
            "route": ["A01", "A02"],
            "engagement_policy": "engage_if_visible",
            "reasoning": "The health route is legal and immediately useful.",
            "summary": "Move one cell toward health.",
            "plan_note": "I am making the healthy choice for once.",
        },
        handoff,
    ]


def jev_choice(selected_id: str, *, confidence: float | None) -> JevDecision:
    return JevDecision(
        selected_id=selected_id,
        probabilities={
            "hold_position": 0.2,
            "seek_health": 0.6,
            "handoff_to_opus": 0.2,
        },
        confidence=confidence,
        model=DEFAULT_MODEL,
        provider="fake",
        usage={"input_tokens": 10, "output_tokens": 2},
        latency_ms=1.0,
        request_id=f"jev-only-{selected_id}",
    )


def jev_only_harness(decision: JevDecision):
    harness = fixtures.make_lifecycle_harness(
        decisions=[decision],
        observations=[
            fixtures.lifecycle_observation(),
            fixtures.lifecycle_observation(),
            fixtures.lifecycle_observation(),
            fixtures.lifecycle_observation(phase="finished"),
        ],
    )
    candidate_set = actionable_candidates()

    def generate_candidates(*_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        harness.routes.generate_count += 1
        return copy.deepcopy(candidate_set)

    harness.routes.generate_candidates = generate_candidates
    return harness


def plan_submissions(harness: Any) -> list[dict[str, Any]]:
    return [
        payload
        for event, payload in harness.telemetry.records
        if event == "plan_submission"
    ]


@pytest.mark.parametrize("confidence", [None, 0.0, 0.2])
def test_jev_only_submits_actionable_choice_regardless_of_confidence(
    confidence: float | None,
) -> None:
    harness = jev_only_harness(jev_choice("seek_health", confidence=confidence))
    try:
        harness.controller.prepare("player_1", control_mode="jev_only")

        result = harness.controller.run(max_run_ms=1_000)

        assert result["status"] == "finished"
        assert result["handoff"] is None
        assert result["last_plan"]["id"] == "seek_health"
        assert harness.client.plan_calls[0][1] == ["A01", "A02"]
        assert harness.routes.fallback_count == 0
        assert plan_submissions(harness) == [
            {
                "run_id": "run_test",
                "participant_id": "player_1",
                "sequence_number": 7,
                "candidate_id": "seek_health",
                "source": "jev",
                "accepted": True,
            }
        ]
    finally:
        harness.controller.close()


def test_jev_only_does_not_offer_handoff_candidate_to_adapter() -> None:
    harness = jev_only_harness(jev_choice("seek_health", confidence=0.9))
    try:
        harness.controller.prepare("player_1", control_mode="jev_only")

        result = harness.controller.run(max_run_ms=1_000)

        assert result["status"] == "finished"
        assert len(harness.adapter.candidate_sets) == 1
        offered = harness.adapter.candidate_sets[0]
        assert [candidate["id"] for candidate in offered] == [
            "hold_position",
            "seek_health",
        ]
        assert all(candidate["actionable"] is True for candidate in offered)
        decision_event = next(
            payload
            for event, payload in harness.telemetry.records
            if event == "jev_decision"
        )
        assert decision_event["candidate_ids"] == ["hold_position", "seek_health"]
    finally:
        harness.controller.close()


@pytest.mark.parametrize("selected_id", ["unknown_choice", "handoff_to_opus"])
def test_jev_only_unknown_or_non_actionable_choice_falls_back_safely(
    selected_id: str,
) -> None:
    harness = jev_only_harness(jev_choice(selected_id, confidence=0.9))
    try:
        harness.controller.prepare("player_1", control_mode="jev_only")

        result = harness.controller.run(max_run_ms=1_000)

        assert result["status"] == "finished"
        assert result["handoff"] is None
        assert result["last_plan"]["id"] == "hold_position"
        assert harness.client.plan_calls[0][1] == ["A01"]
        assert harness.routes.fallback_count == 1
        assert [submission["source"] for submission in plan_submissions(harness)] == [
            "deterministic_fallback"
        ]
    finally:
        harness.controller.close()
