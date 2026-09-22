from __future__ import annotations

import copy
from typing import Any

import pytest

from controller import ControllerError, JevPlayerController
from jev_adapter import DEFAULT_ENDPOINT, DEFAULT_MODEL, JevDecision


def _observation() -> dict[str, Any]:
    return {
        "participant_id": "player_1",
        "opponent_id": "player_2",
        "state_mode": "fog_of_war",
        "self": {
            "health": 80,
            "alive": True,
            "cell": "A01",
            "ammo_bullets": 20,
            "los_status": "blocked",
        },
        "opponent": {
            "participant_id": "player_2",
            "alive": True,
            "visible": False,
        },
        "tactical_context": {
            "los_status": "blocked",
            "replan_recommended": False,
            "replan_reasons": [],
        },
        "map": {"pickups": []},
        "match": {"phase": "combat", "elapsed_time_seconds": 2},
    }


def _candidates() -> list[dict[str, Any]]:
    return [
        {
            "id": "hold_position",
            "kind": "plan",
            "actionable": True,
            "objective": "Hold current position",
            "route": ["A01"],
            "engagement_policy": "hold_fire",
            "reasoning": "The current cell is a legal safe fallback.",
            "summary": "Hold the current legal cell.",
            "plan_note": "I am holding here for a moment.",
        },
        {
            "id": "handoff_to_opus",
            "kind": "handoff",
            "actionable": False,
            "objective": "Request strategic handoff",
            "reasoning": "Escalate when the deterministic choices are insufficient.",
            "summary": "Escalate this decision to the frontier model.",
        },
    ]


def _decision(confidence: float) -> JevDecision:
    return JevDecision(
        selected_id="hold_position",
        probabilities={"hold_position": 0.7, "handoff_to_opus": 0.3},
        confidence=confidence,
        model=DEFAULT_MODEL,
        provider="fake",
        usage={"input_tokens": 8, "output_tokens": 2},
        latency_ms=1.0,
        request_id=f"request-{confidence}",
    )


class NormalizingArena:
    def __init__(self) -> None:
        self.normalized_routes: list[tuple[Any, str]] = []

    def normalize_plan_route(self, route: Any, *, start_cell: str):
        self.normalized_routes.append((copy.deepcopy(route), start_cell))
        if route != [" a02 "]:
            raise ValueError("route must contain the approved A02 waypoint")
        return "A02", ["A02"]

    @staticmethod
    def normalize_plan_engagement_policy(value: Any) -> str:
        if value != "avoid_until_target":
            raise ValueError("invalid engagement policy")
        return "avoid_until_target"

    @staticmethod
    def normalize_plan_objective(value: Any) -> str:
        return " ".join(str(value).split())

    @staticmethod
    def normalize_plan_reasoning(value: Any) -> str:
        return " ".join(str(value).split())

    @staticmethod
    def normalize_plan_summary(value: Any) -> str:
        return " ".join(str(value).split())


class ResumeClient:
    def __init__(self) -> None:
        self.run_id = "run_resume"
        self.scenario_id = "duel_e1m8"
        self.plan_calls: list[tuple[Any, ...]] = []
        self.stop_calls = 0

    def _read_participant_observation_and_plan(self, _participant_id: str):
        return copy.deepcopy(_observation()), {}

    def _sync_run_metadata(self) -> None:
        return None

    @staticmethod
    def set_participant_ready(*_args: Any) -> dict[str, Any]:
        return {"accepted": True}

    def set_participant_plan(self, *args: Any) -> dict[str, Any]:
        self.plan_calls.append(args)
        return {"accepted": True, "intent_id": f"intent_{len(self.plan_calls)}"}

    def stop_participant_intent(self, *_args: Any) -> dict[str, Any]:
        self.stop_calls += 1
        return {"accepted": True}


class ResumeRouteEngine:
    @staticmethod
    def generate_candidates(*_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        return copy.deepcopy(_candidates())

    @staticmethod
    def safe_fallback(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return copy.deepcopy(_candidates()[0])


class ScriptedAdapter:
    model = DEFAULT_MODEL
    endpoint = DEFAULT_ENDPOINT

    def __init__(self, *decisions: JevDecision) -> None:
        self.decisions = list(decisions)
        self.states: list[dict[str, Any]] = []

    def choose(self, state: dict[str, Any], _candidates: list[dict[str, Any]]) -> JevDecision:
        self.states.append(copy.deepcopy(state))
        index = min(len(self.states) - 1, len(self.decisions) - 1)
        return self.decisions[index]


def _controller(
    adapter: ScriptedAdapter,
) -> tuple[JevPlayerController, ResumeClient, NormalizingArena]:
    arena = NormalizingArena()
    client = ResumeClient()
    controller = JevPlayerController(
        arena_module=arena,
        client=client,
        adapter=adapter,
        route_engine=ResumeRouteEngine(),
        token_loader=lambda _arena, _client, _participant: "controller-test-token",
        sequence_loader=lambda _client, _participant: 1,
        sequence_verifier=lambda _client, _participant, _sequence: True,
        poll_seconds=0.05,
        evaluation_seconds=0.5,
        safe_refresh_seconds=30.0,
    )
    return controller, client, arena


def _prepare_hybrid_handoff(
    adapter: ScriptedAdapter,
) -> tuple[JevPlayerController, ResumeClient, NormalizingArena]:
    controller, client, arena = _controller(adapter)
    controller.prepare("player_1", control_mode="jev_hybrid")
    result = controller.run(max_run_ms=500)
    assert result["status"] == "awaiting_opus"
    assert len(client.plan_calls) == 1
    assert controller.status()["next_sequence_number"] == 2
    return controller, client, arena


def test_hybrid_handoff_resumes_with_normalized_override_then_jev_resumes() -> None:
    adapter = ScriptedAdapter(_decision(0.2), _decision(0.95))
    controller, client, arena = _prepare_hybrid_handoff(adapter)
    override = {
        "route": [" a02 "],
        "objective": "  Take   the safe lane  ",
        "engagement_policy": "avoid_until_target",
        "reasoning": "  Opus   chose cover  ",
        "plan_note": "  I am   taking cover.  ",
    }

    result = controller.resume(
        strategic_directive="Protect the health lead",
        override_plan=override,
        max_run_ms=700,
    )

    assert result["status"] == "running"
    assert arena.normalized_routes == [([" a02 "], "A01")]
    override_calls = [call for call in client.plan_calls if call[2] == "Take the safe lane"]
    assert len(override_calls) == 1
    assert override_calls[0][1] == ["A02"]
    assert override_calls[0][3:6] == (
        "avoid_until_target",
        "Opus chose cover",
        "I am taking cover.",
    )
    assert override_calls[0][7] == 2
    assert len(adapter.states) >= 2
    assert adapter.states[1]["strategic_directive"] == "Protect the health lead"
    assert len(client.plan_calls) == 3
    assert controller.status()["next_sequence_number"] == 4
    controller.stop()


def test_invalid_override_preserves_safe_plan_handoff_mode_and_sequence() -> None:
    adapter = ScriptedAdapter(_decision(0.2))
    controller, client, _arena = _prepare_hybrid_handoff(adapter)
    before = controller.status()
    before_plan_calls = list(client.plan_calls)

    with pytest.raises(ControllerError, match="Invalid override_plan"):
        controller.resume(
            override_plan={
                "route": ["INVALID"],
                "objective": "Unsafe override",
                "engagement_policy": "avoid_until_target",
                "reasoning": "Should not be submitted",
                "plan_note": "Do not move.",
            },
            max_run_ms=100,
        )

    after = controller.status()
    assert after["status"] == "awaiting_opus"
    assert after["next_sequence_number"] == before["next_sequence_number"] == 2
    assert after["last_plan"] == before["last_plan"]
    assert after["handoff"] == before["handoff"]
    assert client.plan_calls == before_plan_calls
    controller.stop()


def test_duplicate_resume_is_rejected_without_an_extra_submission() -> None:
    adapter = ScriptedAdapter(_decision(0.2), _decision(0.95))
    controller, client, _arena = _prepare_hybrid_handoff(adapter)

    first = controller.resume(strategic_directive="Continue locally", max_run_ms=100)
    assert first["status"] == "running"
    plan_count = len(client.plan_calls)
    sequence = controller.status()["next_sequence_number"]

    with pytest.raises(ControllerError, match="requires an active strategic handoff"):
        controller.resume(strategic_directive="Duplicate resume", max_run_ms=100)

    assert len(client.plan_calls) == plan_count
    assert controller.status()["next_sequence_number"] == sequence
    assert controller.status()["status"] == "running"
    controller.stop()


def test_resume_arms_cooldown_and_requires_confident_rearm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller, _client, _arena = _controller(ScriptedAdapter(_decision(0.2)))
    controller._mode = "awaiting_opus"
    monkeypatch.setattr(controller, "_start_thread_locked", lambda: None)
    monkeypatch.setattr(controller, "_wait_for_return", lambda _max_run_ms: controller.status())
    before = controller._clock()

    result = controller.resume(strategic_directive="Continue safely", max_run_ms=100)

    assert result["status"] == "running"
    assert controller._handoff_cooldown_until >= before + 15.0
    assert controller._handoff_rearmed is False

