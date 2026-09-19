from __future__ import annotations

from collections.abc import Mapping
import io
import json
from pathlib import Path
import socket
import sys
from typing import Any
from urllib.error import HTTPError, URLError

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from jev_adapter import (  # noqa: E402
    DEFAULT_ENDPOINT,
    DEFAULT_MODEL,
    HANDOFF_CHOICE_ID,
    FakeJevAdapter,
    JevAdapter,
    JevCandidateError,
    JevConfigurationError,
    JevDecision,
    JevHTTPError,
    JevModelMismatchError,
    JevRequestError,
    JevResponseError,
    JevTimeoutError,
    JevUnknownChoiceError,
    filter_outbound_state,
)
from contracts import build_outbound_state  # noqa: E402


API_KEY = "unit-test-key-not-from-env"


def candidates() -> list[dict[str, Any]]:
    return [
        {
            "id": "seek_health",
            "objective": "Reach the nearest available health pickup",
            "engagement_policy": "disengage",
            "reasoning": "Health is critical",
            "plan_note": "I need that medkit more than another duel.",
            "route": [{"x": 1, "y": 2}],
            "controller_token": "must-not-leak",
        },
        {
            "id": "hold_position",
            "objective": "Hold a defensible cell",
            "engagement_policy": "engage_if_visible",
            "reasoning": "The current angle is safe",
            "plan_note": "I own this corner for now.",
        },
    ]


def state() -> dict[str, Any]:
    return {
        "participant_id": "player_1",
        "state_mode": "fog_of_war",
        "self": {
            "health": 28,
            "cell": "C04",
            "ammo_bullets": 12,
            "los_status": "lost",
            "controller_token": "must-not-leak",
        },
        "opponent": {
            "participant_id": "player_2",
            "visible": False,
            "cell": None,
            "hidden_x": 900,
        },
        "tactical_context": {
            "replan_recommended": True,
            "replan_reasons": ["health_threshold"],
        },
        "map": {
            "rows": 8,
            "cols": 8,
            "pickups": [{"type": "health", "cell": "B03"}],
            "blocked_cells": ["A01"],
        },
        "match": {"phase": "combat", "elapsed_time_seconds": 12},
        "objective": "reduce_opponent_health_to_zero",
        "raw_state": {"opponent_x": 900},
        "local_path": "C:/secret",
    }


def response_payload(
    *,
    choice: str = "seek_health",
    probabilities: Mapping[str, float] | None = None,
    confidence: float | None = 0.81,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    answer: dict[str, Any] = {"type": "choice", "choice": choice}
    if probabilities is not None:
        answer["probabilities"] = dict(probabilities)
    if confidence is not None:
        answer["confidence"] = confidence
    return {
        "id": "gen-test-1",
        "model": model,
        "provider": "TypeSafe",
        "answers": {"plan": answer},
        "usage": {"input_tokens": 42, "output_tokens": 8, "cost": 0.0000021},
    }


class FakeResponse:
    def __init__(self, payload: bytes | Mapping[str, Any], status: int = 200) -> None:
        if isinstance(payload, Mapping):
            payload = json.dumps(payload).encode("utf-8")
        self._payload = payload
        self.status = status
        self.closed = False

    def read(self, limit: int = -1) -> bytes:
        return self._payload if limit < 0 else self._payload[:limit]

    def close(self) -> None:
        self.closed = True


class RecordingOpener:
    def __init__(self, *results: Any) -> None:
        self.results = list(results)
        self.calls: list[tuple[Any, float]] = []

    def __call__(self, request: Any, *, timeout: float) -> FakeResponse:
        self.calls.append((request, timeout))
        result = self.results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


def http_error(status: int, message: str = "upstream failed") -> HTTPError:
    body = json.dumps({"error": {"code": status, "message": message}}).encode()
    return HTTPError(DEFAULT_ENDPOINT, status, message, {}, io.BytesIO(body))


def complete_probabilities() -> dict[str, float]:
    return {"seek_health": 0.8, "hold_position": 0.2}


def test_builds_exact_decisions_request_and_filters_state_and_candidates() -> None:
    opener = RecordingOpener(
        FakeResponse(response_payload(probabilities=complete_probabilities()))
    )
    times = iter([10.0, 10.125])
    adapter = JevAdapter(
        API_KEY,
        opener=opener,
        timeout_seconds=7,
        clock=lambda: next(times),
    )

    result = adapter.choose(state(), reversed(candidates()))

    request, timeout = opener.calls[0]
    sent = json.loads(request.data)
    assert request.full_url == "https://openrouter.ai/api/alpha/decisions"
    assert request.method == "POST"
    assert timeout == 7
    assert request.get_header("Authorization") == f"Bearer {API_KEY}"
    assert request.get_header("Content-type") == "application/json"
    assert set(sent) == {"model", "state", "questions"}
    assert sent["model"] == "typesafe/jev-1.13"
    assert list(sent["questions"]["plan"]["criteria"]) == [
        "hold_position",
        "seek_health",
    ]
    assert HANDOFF_CHOICE_ID not in sent["questions"]["plan"]["instructions"]
    serialized = request.data.decode("utf-8")
    for forbidden in (
        "must-not-leak",
        "controller_token",
        "raw_state",
        "local_path",
        "hidden_x",
        "blocked_cells",
        '"route"',
        API_KEY,
    ):
        assert forbidden not in serialized
    assert result.selected_id == "seek_health"
    assert result.choice == "seek_health"
    assert result.confidence == pytest.approx(0.81)
    assert result.probabilities == complete_probabilities()
    assert result.model == DEFAULT_MODEL
    assert result.provider == "TypeSafe"
    assert result.usage == {"input_tokens": 42, "output_tokens": 8, "cost": 0.0000021}
    assert result.request_id == "gen-test-1"
    assert result.latency_ms == pytest.approx(125.0)


def test_accepts_optional_probabilities_and_confidence() -> None:
    opener = RecordingOpener(FakeResponse(response_payload(confidence=None)))
    decision = JevAdapter(API_KEY, opener=opener).choose(state(), candidates())
    assert decision.probabilities == {}
    assert decision.confidence is None


def test_rejects_choice_that_is_not_the_highest_reported_probability() -> None:
    payload = response_payload(
        choice="hold_position",
        probabilities={"seek_health": 0.8, "hold_position": 0.2},
    )

    with pytest.raises(JevResponseError, match="highest-probability"):
        JevAdapter(API_KEY, opener=RecordingOpener(FakeResponse(payload))).choose(
            state(), candidates()
        )


def test_accepts_direct_stable_id_to_criteria_mapping() -> None:
    probabilities = {"hold_position": 1.0}
    payload = response_payload(
        choice="hold_position",
        probabilities=probabilities,
    )
    opener = RecordingOpener(FakeResponse(payload))

    decision = JevAdapter(API_KEY, opener=opener).choose(
        state(), {"hold_position": "Hold a defensible cell and watch the corridor"}
    )

    assert decision.choice == "hold_position"
    sent = json.loads(opener.calls[0][0].data)
    assert sent["questions"]["plan"]["criteria"]["hold_position"] == (
        "criteria: Hold a defensible cell and watch the corridor"
    )


def test_includes_handoff_only_when_caller_offers_it() -> None:
    offered = [
        *candidates(),
        {
            "id": HANDOFF_CHOICE_ID,
            "summary": "Escalate when no tactical plan safely fits.",
        },
    ]
    probabilities = {
        "seek_health": 0.7,
        "hold_position": 0.2,
        HANDOFF_CHOICE_ID: 0.1,
    }
    opener = RecordingOpener(
        FakeResponse(response_payload(probabilities=probabilities))
    )

    JevAdapter(API_KEY, opener=opener).choose(state(), offered)

    sent = json.loads(opener.calls[0][0].data)
    assert HANDOFF_CHOICE_ID in sent["questions"]["plan"]["criteria"]
    assert HANDOFF_CHOICE_ID in sent["questions"]["plan"]["instructions"]


@pytest.mark.parametrize("status", [429, 502, 503, 524, 529])
def test_retries_only_documented_retryable_statuses(status: int) -> None:
    sleeps: list[float] = []
    opener = RecordingOpener(
        http_error(status),
        http_error(status),
        FakeResponse(response_payload(probabilities=complete_probabilities())),
    )
    adapter = JevAdapter(
        API_KEY,
        opener=opener,
        max_retries=2,
        backoff_seconds=0.1,
        sleep=sleeps.append,
    )
    assert adapter.choose(state(), candidates()).choice == "seek_health"
    assert len(opener.calls) == 3
    assert sleeps == pytest.approx([0.1, 0.2])


def test_does_not_retry_non_retryable_http_error() -> None:
    opener = RecordingOpener(http_error(401, "invalid key"))
    with pytest.raises(JevHTTPError) as raised:
        JevAdapter(API_KEY, opener=opener).choose(state(), candidates())
    assert raised.value.status_code == 401
    assert raised.value.retryable is False
    assert len(opener.calls) == 1
    assert API_KEY not in str(raised.value)


def test_retry_budget_is_bounded() -> None:
    opener = RecordingOpener(http_error(503), http_error(503))
    with pytest.raises(JevHTTPError) as raised:
        JevAdapter(API_KEY, opener=opener, max_retries=1, sleep=lambda _: None).choose(
            state(), candidates()
        )
    assert raised.value.status_code == 503
    assert len(opener.calls) == 2


def test_timeout_is_bounded_and_explicit() -> None:
    opener = RecordingOpener(URLError(socket.timeout("timed out")))
    with pytest.raises(JevTimeoutError, match="3s client timeout"):
        JevAdapter(API_KEY, opener=opener, timeout_seconds=3).choose(state(), candidates())
    assert len(opener.calls) == 1


def test_transport_error_is_explicit() -> None:
    opener = RecordingOpener(URLError("dns unavailable"))
    with pytest.raises(JevRequestError, match="dns unavailable"):
        JevAdapter(API_KEY, opener=opener).choose(state(), candidates())


@pytest.mark.parametrize(
    ("payload", "exception"),
    [
        (b"not json", JevResponseError),
        (response_payload(choice="invented"), JevUnknownChoiceError),
        (
            response_payload(
                probabilities={"seek_health": 0.6, "hold_position": 0.2}
            ),
            JevResponseError,
        ),
        (response_payload(confidence=1.2), JevResponseError),
        (response_payload(model="typesafe/jev-2"), JevModelMismatchError),
    ],
)
def test_rejects_malformed_or_incompatible_responses(
    payload: bytes | Mapping[str, Any], exception: type[Exception]
) -> None:
    with pytest.raises(exception):
        JevAdapter(API_KEY, opener=RecordingOpener(FakeResponse(payload))).choose(
            state(), candidates()
        )


def test_accepts_canonical_model_suffix_for_pinned_family() -> None:
    payload = response_payload(
        model="typesafe/jev-1.13-20260917",
        probabilities=complete_probabilities(),
    )
    decision = JevAdapter(API_KEY, opener=RecordingOpener(FakeResponse(payload))).choose(
        state(), candidates()
    )
    assert decision.model == "typesafe/jev-1.13-20260917"


def test_filter_outbound_state_requires_approved_fields() -> None:
    assert filter_outbound_state({"health": 90, "secret": "no"}) == {"health": 90}
    with pytest.raises(JevConfigurationError, match="no approved"):
        filter_outbound_state({"controller_token": "no"})


def test_accepts_the_scaffolds_contract_shaped_state_without_losing_tactics() -> None:
    observation = {
        "participant_id": "player_1",
        "opponent_id": "player_2",
        "state_mode": "fog_of_war",
        "self": {"health": 75, "alive": True, "cell": "M06", "ammo_bullets": 40},
        "opponent": {"participant_id": "player_2", "alive": True, "visible": False},
        "tactical_context": {
            "los_status": "blocked",
            "replan_recommended": True,
            "replan_reasons": ["lost_los"],
        },
        "map": {"pickups": [{"id": "health_a", "type": "health", "cell": "D04"}]},
        "match": {"phase": "combat", "elapsed_time_seconds": 3},
    }
    outbound = build_outbound_state(
        observation,
        current_plan={"candidate_id": "hold", "route": ["M06"]},
        strategic_directive="Stay safe",
    )

    filtered = filter_outbound_state(outbound)

    assert filtered["contract_version"] == "1"
    assert filtered["opponent_id"] == "player_2"
    assert filtered["tactical"]["replan_reasons"] == ["lost_los"]
    assert filtered["pickups"] == [{"cell": "D04", "id": "health_a", "type": "health"}]
    assert filtered["current_plan"]["route"] == ["M06"]


def test_rejects_duplicate_or_unstable_candidate_ids_before_network() -> None:
    opener = RecordingOpener(FakeResponse(response_payload()))
    adapter = JevAdapter(API_KEY, opener=opener)
    duplicate = [candidates()[0], dict(candidates()[0])]
    with pytest.raises(JevCandidateError, match="duplicate"):
        adapter.choose(state(), duplicate)
    invalid = [dict(candidates()[0], id="bad id")]
    with pytest.raises(JevCandidateError, match="stable ASCII"):
        adapter.choose(state(), invalid)
    assert opener.calls == []


def test_configuration_does_not_load_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(JevConfigurationError, match="OPENROUTER_API_KEY"):
        JevAdapter()
    with pytest.raises(JevConfigurationError, match="at most 30"):
        JevAdapter(API_KEY, timeout_seconds=31)
    with pytest.raises(JevConfigurationError, match="between 0 and 3"):
        JevAdapter(API_KEY, max_retries=4)


def test_fake_adapter_records_filtered_calls_and_repeats_last_decision() -> None:
    expected = JevDecision(
        selected_id="hold_position",
        probabilities={"hold_position": 0.8, "seek_health": 0.2},
        confidence=0.7,
        provider="fake",
        usage={"input_tokens": 0, "output_tokens": 0},
    )
    adapter = FakeJevAdapter([expected])
    assert adapter.model == DEFAULT_MODEL
    assert adapter.endpoint == "fake://jev-decisions"
    assert adapter.choose(state(), candidates()) is expected
    assert adapter.choose(state(), candidates()) is expected
    assert len(adapter.calls) == 2
    assert adapter.calls[0]["state"]["self"]["health"] == 28
    assert "controller_token" not in adapter.calls[0]["state"]["self"]


def test_fake_adapter_can_raise_scripted_failure_and_reject_unknown_choice() -> None:
    scripted = FakeJevAdapter([JevTimeoutError("test timeout")], repeat_last=False)
    with pytest.raises(JevTimeoutError, match="test timeout"):
        scripted.choose(state(), candidates())

    unknown = FakeJevAdapter(selected_id="not_offered")
    with pytest.raises(JevUnknownChoiceError):
        unknown.choose(state(), candidates())
