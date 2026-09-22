from __future__ import annotations

import copy
import json
import threading
from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any

import controller as controller_module
import pytest
from controller import ControllerError, JevPlayerController
from jev_adapter import DEFAULT_ENDPOINT, DEFAULT_MODEL, JevDecision, JevRequestError


def observation() -> dict[str, Any]:
    return {
        "participant_id": "player_1",
        "opponent_id": "player_2",
        "state_mode": "fog_of_war",
        "self": {
            "health": 100,
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
        "match": {"phase": "combat", "elapsed_time_seconds": 1},
    }


def candidates() -> list[dict[str, Any]]:
    return [
        {
            "id": "hold_position",
            "kind": "plan",
            "actionable": True,
            "objective": "Hold current position",
            "route": ["A01"],
            "engagement_policy": "hold_fire",
            "reasoning": "The current cell is the safe deterministic fallback.",
            "summary": "Hold the current legal cell.",
            "plan_note": "I am holding here for a moment.",
        },
        {
            "id": "handoff_to_opus",
            "kind": "handoff",
            "actionable": False,
            "objective": "Request strategic handoff",
            "reasoning": "Escalate when deterministic choices are insufficient.",
            "summary": "Escalate this decision to the frontier model.",
        },
    ]


def decision() -> JevDecision:
    return JevDecision(
        selected_id="hold_position",
        probabilities={"hold_position": 0.95, "handoff_to_opus": 0.05},
        confidence=0.9,
        model=DEFAULT_MODEL,
        provider="fake",
        usage={"input_tokens": 10, "output_tokens": 2},
        latency_ms=1.0,
        request_id="test-request",
    )


class FakeArena:
    pass


class FakeClient:
    def __init__(self) -> None:
        self.run_id = "run_test"
        self.scenario_id = "duel_e1m8"
        self.ready_calls: list[tuple[Any, ...]] = []
        self.plan_calls: list[tuple[Any, ...]] = []
        self.stop_calls: list[tuple[Any, ...]] = []
        self.read_count = 0

    def _read_participant_observation_and_plan(self, _participant_id: str):
        self.read_count += 1
        return copy.deepcopy(observation()), {}

    def _sync_run_metadata(self) -> None:
        return None

    def set_participant_ready(self, *args: Any) -> dict[str, Any]:
        self.ready_calls.append(args)
        return {"accepted": True}

    def set_participant_plan(self, *args: Any) -> dict[str, Any]:
        self.plan_calls.append(args)
        return {"accepted": True, "intent_id": f"intent_{len(self.plan_calls)}"}

    def stop_participant_intent(self, *args: Any) -> dict[str, Any]:
        self.stop_calls.append(args)
        return {"accepted": True}


class FakeRouteEngine:
    def __init__(self) -> None:
        self.generate_count = 0

    def generate_candidates(self, *_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        self.generate_count += 1
        return copy.deepcopy(candidates())

    def safe_fallback(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return copy.deepcopy(candidates()[0])


class RecordingAdapter:
    model = DEFAULT_MODEL
    endpoint = DEFAULT_ENDPOINT

    def __init__(self) -> None:
        self.states: list[dict[str, Any]] = []
        self.candidate_sets: list[list[dict[str, Any]]] = []

    def choose(self, state: dict[str, Any], offered: list[dict[str, Any]]) -> JevDecision:
        self.states.append(copy.deepcopy(state))
        self.candidate_sets.append(copy.deepcopy(offered))
        return decision()


class BlockingAdapter(RecordingAdapter):
    def __init__(self) -> None:
        super().__init__()
        self.entered = threading.Event()
        self.release = threading.Event()

    def choose(self, state: dict[str, Any], offered: list[dict[str, Any]]) -> JevDecision:
        self.states.append(copy.deepcopy(state))
        self.candidate_sets.append(copy.deepcopy(offered))
        self.entered.set()
        if not self.release.wait(timeout=5.0):
            raise AssertionError("test did not release the blocking Jev adapter")
        return decision()


class RaisingAdapter(RecordingAdapter):
    def choose(self, state: dict[str, Any], offered: list[dict[str, Any]]) -> JevDecision:
        self.states.append(copy.deepcopy(state))
        self.candidate_sets.append(copy.deepcopy(offered))
        raise JevRequestError("simulated OpenRouter outage")


def make_controller(adapter: Any) -> tuple[JevPlayerController, FakeClient]:
    client = FakeClient()
    controller = JevPlayerController(
        arena_module=FakeArena(),
        client=client,
        adapter=adapter,
        route_engine=FakeRouteEngine(),
        token_loader=lambda _arena, _client, _participant: "controller-test-token",
        sequence_loader=lambda _client, _participant: 1,
        sequence_verifier=lambda _client, _participant, _sequence: True,
        poll_seconds=0.05,
        evaluation_seconds=10.0,
        safe_refresh_seconds=30.0,
    )
    return controller, client


LIFECYCLE_CONTROLLER_TOKEN = "controller-secret-never-returned"
LIFECYCLE_OBSERVATION_TOKEN = "observation-secret-never-returned"


def lifecycle_observation(
    *,
    phase: str = "combat",
    run_id: str = "run_test",
) -> dict[str, Any]:
    value = observation()
    value["match"] = {
        "phase": phase,
        "run_id": run_id,
        "elapsed_time_seconds": 2,
    }
    # The arena boundary should already remove this. Keeping it in the fake
    # proves the controller's outbound whitelist is a second safety boundary.
    value["controller_token"] = LIFECYCLE_OBSERVATION_TOKEN
    return value


def lifecycle_decision(*, confidence: float) -> JevDecision:
    return JevDecision(
        selected_id="hold_position",
        probabilities={"hold_position": 0.95, "handoff_to_opus": 0.05},
        confidence=confidence,
        model=DEFAULT_MODEL,
        provider="fake",
        usage={"input_tokens": 10, "output_tokens": 0},
        latency_ms=1.25,
        request_id="fake-lifecycle-decision",
    )


class FakeClock:
    def __init__(self, value: float = 100.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class LifecycleClient(FakeClient):
    def __init__(
        self,
        observations: list[dict[str, Any]] | None = None,
        *,
        change_run_id_on_sync: bool = False,
    ) -> None:
        super().__init__()
        self._observations = list(observations or [lifecycle_observation()])
        self.change_run_id_on_sync = change_run_id_on_sync
        self.observation_calls: list[str] = []
        self.sync_calls = 0

    def _read_participant_observation_and_plan(self, participant_id: str):
        self.read_count += 1
        self.observation_calls.append(participant_id)
        if len(self._observations) > 1:
            item = self._observations.pop(0)
        else:
            item = self._observations[0]
        return copy.deepcopy(item), {}

    def _sync_run_metadata(self) -> None:
        self.sync_calls += 1
        if self.change_run_id_on_sync:
            self.run_id = "run_changed"


class BlockingPlanClient(LifecycleClient):
    def __init__(self) -> None:
        super().__init__()
        self.plan_entered = threading.Event()
        self.release_plan = threading.Event()
        self.active_intent = False
        self.call_order: list[str] = []

    def set_participant_plan(self, *args: Any) -> dict[str, Any]:
        self.plan_calls.append(args)
        self.plan_entered.set()
        if not self.release_plan.wait(timeout=5.0):
            raise AssertionError("test did not release the blocked arena plan write")
        self.active_intent = True
        self.call_order.append("plan_write")
        return {"accepted": True, "intent_id": "blocked-intent"}

    def stop_participant_intent(
        self,
        participant_id: str,
        controller_token: str,
        preserve_opening_plan: bool = True,
    ) -> dict[str, Any]:
        self.stop_calls.append(
            (participant_id, controller_token, preserve_opening_plan)
        )
        self.active_intent = False
        self.call_order.append("forced_clear")
        return {"accepted": True, "cleared": True, "ignored": False}


class IgnoredCleanupClient(LifecycleClient):
    def stop_participant_intent(
        self,
        participant_id: str,
        controller_token: str,
        preserve_opening_plan: bool = True,
    ) -> dict[str, Any]:
        self.stop_calls.append(
            (participant_id, controller_token, preserve_opening_plan)
        )
        return {
            "accepted": True,
            "cleared": False,
            "ignored": True,
            "reason": "opening plans are preserved while waiting_for_agents",
        }


class QueuedAdapter(RecordingAdapter):
    def __init__(self, decisions: list[JevDecision]) -> None:
        super().__init__()
        self.decisions = list(decisions)

    def choose(self, state: dict[str, Any], offered: list[dict[str, Any]]) -> JevDecision:
        self.states.append(copy.deepcopy(state))
        self.candidate_sets.append(copy.deepcopy(offered))
        if not self.decisions:
            raise AssertionError("unexpected extra Jev decision")
        return self.decisions.pop(0)


class LifecycleRouteEngine(FakeRouteEngine):
    def __init__(self) -> None:
        super().__init__()
        self.fallback_count = 0

    def safe_fallback(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        self.fallback_count += 1
        return copy.deepcopy(candidates()[0])


class RecordingTelemetry:
    path = None

    def __init__(self) -> None:
        self.records: list[tuple[str, dict[str, Any]]] = []

    def record(self, event: str, payload: Mapping[str, Any]) -> None:
        self.records.append((event, copy.deepcopy(dict(payload))))


class RecordingTokenLoader:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, Any, str]] = []

    def __call__(self, arena: Any, client: Any, participant_id: str) -> str:
        self.calls.append((arena, client, participant_id))
        return LIFECYCLE_CONTROLLER_TOKEN


class RecordingSequenceVerifier:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, str, int]] = []

    def __call__(self, client: Any, participant_id: str, sequence_number: int) -> bool:
        self.calls.append((client, participant_id, sequence_number))
        return True


def make_lifecycle_harness(
    *,
    decisions: list[JevDecision] | None = None,
    observations: list[dict[str, Any]] | None = None,
    sequence_number: int = 7,
    change_run_id_on_sync: bool = False,
    adapter: Any | None = None,
    client: LifecycleClient | None = None,
) -> SimpleNamespace:
    arena = FakeArena()
    selected_client = client or LifecycleClient(
        observations,
        change_run_id_on_sync=change_run_id_on_sync,
    )
    selected_adapter = adapter or QueuedAdapter(
        decisions or [lifecycle_decision(confidence=0.95)]
    )
    routes = LifecycleRouteEngine()
    telemetry = RecordingTelemetry()
    token_loader = RecordingTokenLoader()
    verifier = RecordingSequenceVerifier()
    sequence_calls: list[tuple[Any, str]] = []

    def load_sequence(candidate_client: Any, participant_id: str) -> int:
        sequence_calls.append((candidate_client, participant_id))
        return sequence_number

    controller = JevPlayerController(
        arena_module=arena,
        client=selected_client,
        adapter=selected_adapter,
        route_engine=routes,
        telemetry=telemetry,
        token_loader=token_loader,
        sequence_loader=load_sequence,
        sequence_verifier=verifier,
        poll_seconds=0.05,
        evaluation_seconds=60,
        safe_refresh_seconds=60,
    )
    return SimpleNamespace(
        controller=controller,
        arena=arena,
        client=selected_client,
        adapter=selected_adapter,
        routes=routes,
        telemetry=telemetry,
        token_loader=token_loader,
        verifier=verifier,
        sequence_calls=sequence_calls,
    )


def assert_lifecycle_secrets_absent(value: Any) -> None:
    encoded = json.dumps(value, sort_keys=True)
    assert LIFECYCLE_CONTROLLER_TOKEN not in encoded
    assert LIFECYCLE_OBSERVATION_TOKEN not in encoded
    assert "controller_token" not in encoded


def test_fingerprint_ignores_normal_cell_and_waypoint_progress() -> None:
    controller, _client = make_controller(RecordingAdapter())
    first = observation()
    second = copy.deepcopy(first)
    second["self"]["cell"] = "A02"
    active_first = {
        "status": "active",
        "current_waypoint_cell": "A02",
        "waypoints_remaining": 3,
    }
    active_second = {
        "status": "active",
        "current_waypoint_cell": "A03",
        "waypoints_remaining": 2,
    }

    assert controller._fingerprint(first, active_first) == controller._fingerprint(second, active_second)

    second["self"]["health"] = 50
    assert controller._fingerprint(first, active_first) != controller._fingerprint(second, active_second)


def test_exact_active_candidate_is_deduplicated_without_consuming_sequence() -> None:
    harness = make_lifecycle_harness()
    candidate = candidates()[0]
    harness.controller._mode = "running"
    harness.controller._participant_id = "player_1"
    harness.controller._controller_token = LIFECYCLE_CONTROLLER_TOKEN
    harness.controller._sequence_number = 8
    harness.controller._current_plan = {
        **candidate,
        "sequence_number": 7,
        "intent_id": "intent_7",
    }
    harness.controller._last_active_plan = {"status": "active"}

    result = harness.controller._submit_candidate(candidate, source="jev")

    assert result["accepted"] is True
    assert result["deduplicated"] is True
    assert harness.controller._sequence_number == 8
    assert harness.client.plan_calls == []
    assert any(event == "plan_deduplicated" for event, _payload in harness.telemetry.records)


@pytest.mark.parametrize(
    ("name", "value", "expected"),
    [
        ("OPENROUTER_DECISIONS_URL", "https://example.invalid/decisions", DEFAULT_ENDPOINT),
        ("OPENROUTER_MODEL", "~typesafe/jev-latest", DEFAULT_MODEL),
    ],
)
def test_production_setup_rejects_non_exact_openrouter_configuration_before_adapter(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
    expected: str,
) -> None:
    monkeypatch.delenv("OPENROUTER_DECISIONS_URL", raising=False)
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    monkeypatch.setenv(name, value)
    adapter_factory_calls: list[dict[str, Any]] = []

    def adapter_factory(**kwargs: Any) -> Any:
        adapter_factory_calls.append(kwargs)
        raise AssertionError("adapter construction must not occur for unsafe configuration")

    monkeypatch.setattr(controller_module, "JevAdapter", adapter_factory)
    controller = JevPlayerController(
        arena_module=FakeArena(),
        client=FakeClient(),
        route_engine=FakeRouteEngine(),
    )

    with pytest.raises(ControllerError, match=f"must be exactly {expected}"):
        controller._ensure_dependencies()

    assert adapter_factory_calls == []


def test_hybrid_run_directive_is_in_the_first_jev_state() -> None:
    adapter = RecordingAdapter()
    controller, client = make_controller(adapter)
    controller.prepare("player_1", control_mode="jev_hybrid")
    assert adapter.states == []

    controller.run("Guard the center lane", max_run_ms=100)

    assert adapter.states
    assert adapter.states[0]["strategic_directive"] == "Guard the center lane"
    assert len(client.plan_calls) == 1
    controller.stop()


def test_jev_only_run_directive_is_in_the_first_jev_state() -> None:
    adapter = RecordingAdapter()
    controller, client = make_controller(adapter)
    controller.prepare("player_1", control_mode="jev_only")
    directive = (
        "Primary objective: eliminate the opponent. Prioritize establishing contact, "
        "acquiring a viable weapon, pursuing the opponent, and dealing damage. Do not "
        "camp, repeatedly hold the same location, or retreat merely to preserve health. "
        "Use health and cover only when they improve the chance of winning the fight. "
        "If no contact occurs for 15-20 seconds, sweep the center and likely enemy locations. "
        "In the final 20 seconds, force engagement unless protecting a meaningful lead."
    )
    assert len(directive) > 320

    controller.run(directive, max_run_ms=100)

    assert adapter.states
    assert adapter.states[0]["strategic_directive"] == directive
    assert len(client.plan_calls) == 1
    controller.stop()


def test_unchanged_state_does_not_repeat_jev_or_plan_before_evaluation_interval() -> None:
    adapter = RecordingAdapter()
    controller, client = make_controller(adapter)
    controller.prepare("player_1", control_mode="jev_only")

    controller.run(max_run_ms=150)

    assert len(adapter.states) == 1
    assert len(client.plan_calls) == 1
    assert client.read_count >= 2
    controller.stop()


def test_stop_racing_blocking_opening_decision_prevents_post_stop_plan_write() -> None:
    adapter = BlockingAdapter()
    controller, client = make_controller(adapter)
    controller.prepare("player_1", control_mode="jev_only")
    run_errors: list[ControllerError] = []
    stop_results: list[dict[str, Any]] = []

    def run_controller() -> None:
        try:
            controller.run(max_run_ms=500)
        except ControllerError as exc:  # pragma: no cover - asserted below
            run_errors.append(exc)

    run_thread = threading.Thread(target=run_controller, name="test-controller-run")
    run_thread.start()
    assert adapter.entered.wait(timeout=1.0), "supervisor never entered the Jev call"

    stop_thread = threading.Thread(target=lambda: stop_results.append(controller.stop()))
    stop_thread.start()
    assert controller._stop_event.wait(timeout=1.0), "stop did not set the cancellation event"
    adapter.release.set()

    stop_thread.join(timeout=2.0)
    run_thread.join(timeout=2.0)
    assert not stop_thread.is_alive()
    assert not run_thread.is_alive()
    assert run_errors == []
    assert client.plan_calls == []
    assert stop_results and stop_results[0]["status"] == "idle"
    assert controller.status()["status"] == "idle"
    assert controller.status()["supervisor_alive"] is False


def test_controller_is_dormant_until_prepare() -> None:
    harness = make_lifecycle_harness()

    status = harness.controller.status()

    assert status == {
        "status": "idle",
        "control_mode": "jev_hybrid",
        "run_id": None,
        "scenario_id": None,
        "participant_id": None,
        "agent_name": None,
        "next_sequence_number": None,
        "last_plan": None,
        "last_decision": None,
        "jev_model": DEFAULT_MODEL,
        "jev_endpoint": DEFAULT_ENDPOINT,
        "handoff": None,
        "match": {},
        "last_error": None,
        "stop_reason": None,
        "stop_cleanup": None,
        "supervisor_alive": False,
    }
    assert harness.client.observation_calls == []
    assert harness.client.ready_calls == []
    assert harness.client.plan_calls == []
    assert harness.adapter.states == []
    assert harness.routes.generate_count == 0
    assert harness.token_loader.calls == []


def test_prepare_keeps_strict_token_internal_and_defers_jev_call() -> None:
    harness = make_lifecycle_harness()
    try:
        prepared = harness.controller.prepare(
            "player_1",
            agent_name="Doom Roomba",
            control_mode="jev_only",
        )

        assert prepared["status"] == "prepared"
        assert prepared["control_mode"] == "jev_only"
        assert prepared["ready"] is True
        assert prepared["candidate_ids"] == ["hold_position"]
        assert prepared["opening_handoff_reason"] is None
        assert harness.token_loader.calls == [
            (harness.arena, harness.client, "player_1")
        ]
        assert harness.client.ready_calls == [
            ("player_1", LIFECYCLE_CONTROLLER_TOKEN, "Doom Roomba")
        ]
        assert harness.sequence_calls == [(harness.client, "player_1")]
        assert harness.adapter.states == []
        assert_lifecycle_secrets_absent(prepared)
        assert_lifecycle_secrets_absent(harness.controller.status())
    finally:
        harness.controller.close()


def test_high_confidence_opening_submits_route_and_verifies_sequence() -> None:
    harness = make_lifecycle_harness(
        observations=[
            lifecycle_observation(),
            lifecycle_observation(),
            lifecycle_observation(),
            lifecycle_observation(phase="finished"),
        ],
        sequence_number=7,
    )
    try:
        harness.controller.prepare("player_1", control_mode="jev_only")
        result = harness.controller.run(max_run_ms=1_000)

        assert result["status"] == "finished"
        assert result["next_sequence_number"] == 8
        assert result["last_plan"]["id"] == "hold_position"
        assert result["last_plan"]["route"] == ["A01"]
        assert len(harness.adapter.states) == 1
        assert harness.adapter.states[0]["participant_id"] == "player_1"
        assert_lifecycle_secrets_absent(harness.adapter.states[0])
        assert harness.client.plan_calls == [
            (
                "player_1",
                ["A01"],
                "Hold current position",
                "hold_fire",
                "The current cell is the safe deterministic fallback.",
                "I am holding here for a moment.",
                LIFECYCLE_CONTROLLER_TOKEN,
                7,
            )
        ]
        assert harness.verifier.calls == [(harness.client, "player_1", 7)]
        submission = next(
            payload
            for event, payload in harness.telemetry.records
            if event == "plan_submission"
        )
        assert submission["candidate_id"] == "hold_position"
        assert submission["source"] == "jev"
        assert_lifecycle_secrets_absent(result)
    finally:
        harness.controller.close()


def test_hybrid_low_confidence_submits_fallback_and_returns_handoff() -> None:
    harness = make_lifecycle_harness(
        decisions=[lifecycle_decision(confidence=0.2)]
    )
    try:
        prepared = harness.controller.prepare("player_1", control_mode="jev_hybrid")
        result = harness.controller.run(max_run_ms=1_000)

        assert prepared["opening_handoff_reason"] is None
        assert result["status"] == "awaiting_opus"
        assert result["handoff"]["reason"] == "jev_low_confidence"
        assert result["last_plan"]["id"] == "hold_position"
        assert harness.client.plan_calls[0][1] == ["A01"]
        submission = next(
            payload
            for event, payload in harness.telemetry.records
            if event == "plan_submission"
        )
        assert submission["source"] == "deterministic_fallback"
        assert harness.routes.fallback_count == 1
        assert_lifecycle_secrets_absent(result)
    finally:
        harness.controller.close()


def test_handoff_hysteresis_cooldown_and_duplicate_suppression() -> None:
    clock = FakeClock()
    controller = JevPlayerController(
        arena_module=FakeArena(),
        client=FakeClient(),
        adapter=RecordingAdapter(),
        route_engine=FakeRouteEngine(),
        clock=clock,
        handoff_cooldown_seconds=15,
        handoff_dedupe_seconds=30,
        handoff_rearm_threshold=0.45,
    )
    controller._control_mode = "jev_hybrid"
    current_observation = observation()
    offered = candidates()
    moderate = lifecycle_decision(confidence=0.5)
    low = lifecycle_decision(confidence=0.4)

    assert controller._decision_handoff_reason(moderate) == "jev_low_confidence"

    reason = controller._decision_handoff_reason(low)
    signature = controller._handoff_signature(reason, current_observation, offered, low)
    controller._last_handoff_signature = signature
    controller._last_handoff_at = clock()
    controller._handoff_cooldown_until = clock() + 15
    controller._handoff_rearmed = False

    assert controller._decision_handoff_reason(moderate) == ""
    assert controller._decision_handoff_reason(low) == "jev_low_confidence"
    assert controller._handoff_suppression(
        reason,
        current_observation,
        offered,
        low,
    )[0] == "cooldown"

    clock.advance(15)
    assert controller._handoff_suppression(
        reason,
        current_observation,
        offered,
        low,
    )[0] == "duplicate"

    clock.advance(15)
    assert controller._handoff_suppression(
        reason,
        current_observation,
        offered,
        low,
    )[0] == ""

    controller._note_actionable_decision(lifecycle_decision(confidence=0.9))
    assert controller._decision_handoff_reason(moderate) == "jev_low_confidence"


def test_jev_only_low_confidence_uses_jev_choice_without_handoff() -> None:
    harness = make_lifecycle_harness(
        decisions=[lifecycle_decision(confidence=0.2)],
        observations=[
            lifecycle_observation(),
            lifecycle_observation(),
            lifecycle_observation(),
            lifecycle_observation(phase="finished"),
        ],
    )
    try:
        harness.controller.prepare("player_1", control_mode="jev_only")
        result = harness.controller.run(max_run_ms=1_000)

        assert result["status"] == "finished"
        assert result["control_mode"] == "jev_only"
        assert result["handoff"] is None
        assert result["last_plan"]["id"] == "hold_position"
        assert harness.client.plan_calls[0][1] == ["A01"]
        assert harness.routes.fallback_count == 0
        submission = next(
            payload
            for event, payload in harness.telemetry.records
            if event == "plan_submission"
        )
        assert submission["source"] == "jev"
        assert_lifecycle_secrets_absent(result)
    finally:
        harness.controller.close()


def test_opening_jev_error_uses_fallback_and_hands_off_in_hybrid_mode() -> None:
    adapter = RaisingAdapter()
    harness = make_lifecycle_harness(adapter=adapter)
    try:
        harness.controller.prepare("player_1", control_mode="jev_hybrid")

        result = harness.controller.run(max_run_ms=1_000)

        assert result["status"] == "awaiting_opus"
        assert result["handoff"]["reason"] == "opening_jev_failure"
        assert result["last_plan"]["id"] == "hold_position"
        assert "simulated OpenRouter outage" in result["last_error"]
        assert len(adapter.states) == 1
        assert len(harness.client.plan_calls) == 1
        assert harness.routes.fallback_count == 1
    finally:
        harness.controller.close()


def test_opening_jev_error_uses_fallback_without_handoff_in_jev_only_mode() -> None:
    adapter = RaisingAdapter()
    harness = make_lifecycle_harness(adapter=adapter)
    try:
        harness.controller.prepare("player_1", control_mode="jev_only")

        result = harness.controller.run(max_run_ms=100)

        assert result["status"] == "running"
        assert result["handoff"] is None
        assert result["last_plan"]["id"] == "hold_position"
        assert "simulated OpenRouter outage" in result["last_error"]
        assert len(adapter.states) == 1
        assert len(harness.client.plan_calls) == 1
        assert harness.routes.fallback_count == 1
    finally:
        harness.controller.close()


def test_match_finishing_during_blocked_jev_inference_prevents_plan_write() -> None:
    adapter = BlockingAdapter()
    harness = make_lifecycle_harness(
        adapter=adapter,
        observations=[
            lifecycle_observation(),
            lifecycle_observation(),
            lifecycle_observation(phase="finished"),
        ],
    )
    run_results: list[dict[str, Any]] = []
    run_errors: list[BaseException] = []

    def run_controller() -> None:
        try:
            run_results.append(harness.controller.run(max_run_ms=1_000))
        except BaseException as exc:  # pragma: no cover - asserted below
            run_errors.append(exc)

    try:
        harness.controller.prepare("player_1", control_mode="jev_only")
        run_thread = threading.Thread(target=run_controller, name="test-finish-during-jev")
        run_thread.start()
        assert adapter.entered.wait(timeout=1.0), "supervisor never entered Jev inference"

        adapter.release.set()
        run_thread.join(timeout=2.0)

        assert not run_thread.is_alive()
        assert run_errors == []
        assert run_results and run_results[0]["status"] == "finished"
        assert run_results[0]["stop_reason"] == "match_finished"
        assert harness.client.plan_calls == []
    finally:
        adapter.release.set()
        harness.controller.close()


def test_invalid_lifecycle_and_max_run_ms_are_rejected_without_side_effects() -> None:
    harness = make_lifecycle_harness()

    with pytest.raises(ControllerError, match="Prepare the Jev player"):
        harness.controller.run(max_run_ms=100)
    with pytest.raises(ControllerError, match="active strategic handoff"):
        harness.controller.resume(max_run_ms=100)
    for invalid in (99, 55_001, "not-an-integer"):
        with pytest.raises(ControllerError, match="max_run_ms"):
            harness.controller.run(max_run_ms=invalid)
    with pytest.raises(ControllerError, match="participant_id"):
        harness.controller.prepare("spectator")
    with pytest.raises(ControllerError, match="control_mode"):
        harness.controller.prepare("player_1", control_mode="unknown")

    assert harness.token_loader.calls == []
    assert harness.adapter.states == []
    assert harness.client.ready_calls == []
    assert harness.client.plan_calls == []


def test_stop_clears_internal_token_and_stops_arena_intent_once() -> None:
    harness = make_lifecycle_harness()
    harness.controller.prepare("player_1", control_mode="jev_only")

    stopped = harness.controller.stop()
    stopped_again = harness.controller.stop()

    assert stopped["status"] == "idle"
    assert stopped["stop_reason"] == "stopped"
    assert stopped["stop_cleanup"] == {
        "accepted": True,
        "cleared": True,
        "ignored": False,
    }
    assert stopped_again["status"] == "idle"
    assert harness.client.stop_calls == [
        ("player_1", LIFECYCLE_CONTROLLER_TOKEN, False)
    ]
    assert harness.controller._controller_token is None
    assert_lifecycle_secrets_absent(stopped)


def test_stop_surfaces_ignored_arena_cleanup_as_failed() -> None:
    client = IgnoredCleanupClient()
    harness = make_lifecycle_harness(client=client)
    harness.controller.prepare("player_1", control_mode="jev_only")

    stopped = harness.controller.stop()

    assert stopped["status"] == "failed"
    assert stopped["stop_reason"] == "arena_cleanup_failed"
    assert stopped["stop_cleanup"] == {
        "accepted": True,
        "cleared": False,
        "ignored": True,
        "reason": "opening plans are preserved while waiting_for_agents",
    }
    assert stopped["last_error"] == "opening plans are preserved while waiting_for_agents"
    assert client.stop_calls == [
        ("player_1", LIFECYCLE_CONTROLLER_TOKEN, False)
    ]
    assert harness.controller._controller_token is None


def test_stop_serializes_with_inflight_plan_and_force_clears_after_write() -> None:
    client = BlockingPlanClient()
    harness = make_lifecycle_harness(
        client=client,
        adapter=RecordingAdapter(),
    )
    run_results: list[dict[str, Any]] = []
    run_errors: list[BaseException] = []
    stop_results: list[dict[str, Any]] = []

    def run_controller() -> None:
        try:
            run_results.append(harness.controller.run(max_run_ms=1_000))
        except BaseException as exc:  # pragma: no cover - asserted below
            run_errors.append(exc)

    harness.controller.prepare("player_1", control_mode="jev_only")
    run_thread = threading.Thread(target=run_controller, name="test-blocked-plan-run")
    run_thread.start()
    assert client.plan_entered.wait(timeout=1.0), "supervisor never began the plan write"

    stop_thread = threading.Thread(
        target=lambda: stop_results.append(harness.controller.stop()),
        name="test-blocked-plan-stop",
    )
    stop_thread.start()
    assert harness.controller._stop_event.wait(timeout=1.0), "stop did not request cancellation"
    assert stop_thread.is_alive(), "stop returned before the in-flight write was released"

    client.release_plan.set()
    stop_thread.join(timeout=2.0)
    run_thread.join(timeout=2.0)

    assert not stop_thread.is_alive()
    assert not run_thread.is_alive()
    assert run_errors == []
    assert run_results and run_results[0]["status"] in {"idle", "stopping"}
    assert stop_results and stop_results[0]["status"] == "idle"
    assert stop_results[0]["stop_cleanup"]["cleared"] is True
    assert client.call_order == ["plan_write", "forced_clear"]
    assert client.active_intent is False
    assert client.stop_calls == [
        ("player_1", LIFECYCLE_CONTROLLER_TOKEN, False)
    ]
    assert harness.controller.status()["supervisor_alive"] is False


def test_run_id_change_fails_controller_and_requires_reprepare() -> None:
    harness = make_lifecycle_harness(
        observations=[lifecycle_observation(), lifecycle_observation()],
        change_run_id_on_sync=True,
    )
    try:
        harness.controller.prepare("player_1", control_mode="jev_only")
        result = harness.controller.run(max_run_ms=1_000)

        assert result["status"] == "failed"
        assert result["run_id"] == "run_test"
        assert "Arena run changed" in result["last_error"]
        assert harness.client.run_id == "run_changed"
        assert harness.client.sync_calls == 1
        assert_lifecycle_secrets_absent(result)
    finally:
        harness.controller.close()
