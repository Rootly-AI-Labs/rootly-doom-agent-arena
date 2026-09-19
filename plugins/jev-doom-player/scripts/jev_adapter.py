"""Narrow OpenRouter Jev Decisions transport for the Doom player.

This module intentionally has no dotenv or third-party dependency.  The caller
must pass an API key or place ``OPENROUTER_API_KEY`` in the process environment.
Only an explicitly whitelisted view of arena state and candidate summaries can
cross this boundary.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
import json
import math
import os
import re
import socket
import time
from types import MappingProxyType
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
DEFAULT_MODEL = "typesafe/jev-1.13"
HANDOFF_CHOICE_ID = "handoff_to_opus"
QUESTION_ID = "plan"
RETRYABLE_STATUS_CODES = frozenset({429, 502, 503, 524, 529})

_MAX_TIMEOUT_SECONDS = 30.0
_MAX_RETRIES = 3
_MAX_REQUEST_BYTES = 256 * 1024
_MAX_RESPONSE_BYTES = 1024 * 1024
_MAX_STRING_LENGTH = 2_000
_CANDIDATE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")

# The state reaching this adapter should already have passed the arena's
# fog-of-war filter.  This second, explicit whitelist prevents later callers
# from accidentally adding raw rows, controller tokens, or environment data.
_STATE_SCHEMA: Mapping[str, Any] = MappingProxyType(
    {
        "contract_version": None,
        "participant_id": None,
        "opponent_id": None,
        "state_mode": None,
        "objective": None,
        "strategic_directive": None,
        "health": None,
        "ammo": None,
        "cell": None,
        "opponent_visible": None,
        "opponent_cell": None,
        "last_seen_opponent_cell": None,
        "available_pickups": "json",
        "pickups": "json",
        "current_objective": None,
        "route_status": None,
        "trigger": "json",
        "self": frozenset(
            {
                "health",
                "alive",
                "cell",
                "angle",
                "ammo_bullets",
                "ammo_shells",
                "ready_weapon",
                "command_status",
                "last_action",
                "damage_dealt",
                "shots_fired",
                "shots_hit",
                "invalid_actions",
                "health_delta",
                "distance_bucket",
                "los_status",
                "pressure_state",
                "last_damage_taken_ms",
                "last_damage_dealt_ms",
                "executed_fire_action",
                "executed_movement_action",
                "policy_compliance_reason",
            }
        ),
        "opponent": frozenset(
            {
                "participant_id",
                "health",
                "alive",
                "visible",
                "cell",
                "angle",
                "distance",
                "relative_angle",
                "distance_bucket",
                "los_status",
                "in_view_cone",
                "revealed_by_hit",
            }
        ),
        "tactical_context": frozenset(
            {
                "health_delta",
                "distance_bucket",
                "los_status",
                "pressure_state",
                "last_damage_taken_ms",
                "last_damage_dealt_ms",
                "replan_recommended",
                "replan_reasons",
                "executed_fire_action",
                "executed_movement_action",
                "policy_compliance_reason",
            }
        ),
        # ``contracts.build_outbound_state`` uses this shorter key.
        "tactical": frozenset(
            {
                "health_delta",
                "distance_bucket",
                "los_status",
                "pressure_state",
                "replan_recommended",
                "replan_reasons",
                "policy_compliance_reason",
            }
        ),
        "map": frozenset(
            {
                "cell_size",
                "rows",
                "cols",
                "row_labels",
                "col_labels",
                "weapon_pickups_enabled",
                "pickups",
            }
        ),
        "match": frozenset(
            {
                "phase",
                "winner",
                "terminal_reason",
                "elapsed_time_seconds",
                "timeout_seconds",
            }
        ),
        "current_plan": frozenset(
            {
                "id",
                "candidate_id",
                "sequence_number",
                "objective",
                "engagement_policy",
                "reasoning",
                "plan_note",
                "status",
                "route_progress",
                "current_waypoint_cell",
                "waypoints_remaining",
                "route",
            }
        ),
    }
)

_CANDIDATE_SUMMARY_FIELDS = (
    "objective",
    "engagement_policy",
    "criteria",
    "summary",
    "reasoning",
    "plan_note",
)


class JevError(RuntimeError):
    """Base class for all adapter failures."""


class JevConfigurationError(JevError):
    """The adapter cannot run because its local configuration is invalid."""


class JevCandidateError(JevError):
    """Candidate IDs or summaries are invalid."""


class JevRequestError(JevError):
    """The request could not reach OpenRouter."""


class JevTimeoutError(JevRequestError):
    """The bounded OpenRouter request timed out."""


class JevHTTPError(JevRequestError):
    """OpenRouter returned a non-success status."""

    def __init__(self, status_code: int, message: str, *, retryable: bool) -> None:
        super().__init__(f"OpenRouter returned HTTP {status_code}: {message}")
        self.status_code = status_code
        self.retryable = retryable


class JevResponseError(JevError):
    """OpenRouter returned malformed or contract-incompatible JSON."""


class JevUnknownChoiceError(JevResponseError):
    """Jev selected an ID that was not offered in the request."""


class JevModelMismatchError(JevResponseError):
    """The response reports a model outside the configured pinned family."""


@dataclass(frozen=True, slots=True)
class JevDecision:
    """A parsed Jev Choice decision.

    OpenRouter declares ``probabilities`` and ``confidence`` as optional on the
    Decisions route, even though TypeSafe normally returns both. Callers must
    preserve that optionality and apply the policy for their configured control
    mode rather than manufacturing certainty.
    """

    selected_id: str
    probabilities: Mapping[str, float] = field(default_factory=dict)
    confidence: float | None = None
    model: str = DEFAULT_MODEL
    provider: str | None = None
    usage: Mapping[str, int | float] = field(default_factory=dict)
    latency_ms: float = 0.0
    request_id: str | None = None

    @property
    def choice(self) -> str:
        """Alias matching the upstream Choice response field."""

        return self.selected_id


def _bounded_string(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise JevCandidateError(f"{field_name} must be a string")
    value = value.strip()
    if not value:
        raise JevCandidateError(f"{field_name} must not be empty")
    if len(value) > _MAX_STRING_LENGTH:
        raise JevCandidateError(
            f"{field_name} exceeds the {_MAX_STRING_LENGTH}-character limit"
        )
    return value


def _copy_json_value(value: Any, *, depth: int = 0) -> Any:
    """Copy a bounded JSON value without falling back to ``repr``."""

    if depth > 6:
        raise JevConfigurationError("outbound state nesting is too deep")
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise JevConfigurationError("outbound state contains a non-finite number")
        return value
    if isinstance(value, str):
        return value[:_MAX_STRING_LENGTH]
    if isinstance(value, Mapping):
        copied: dict[str, Any] = {}
        keys = list(value)
        if not all(isinstance(key, str) for key in keys):
            raise JevConfigurationError("outbound state object keys must be strings")
        for key in sorted(keys):
            copied[key] = _copy_json_value(value[key], depth=depth + 1)
        return copied
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if len(value) > 256:
            raise JevConfigurationError("outbound state array exceeds 256 items")
        return [_copy_json_value(item, depth=depth + 1) for item in value]
    raise JevConfigurationError(
        f"outbound state contains unsupported value type {type(value).__name__}"
    )


def filter_outbound_state(state: Mapping[str, Any]) -> dict[str, Any]:
    """Return the deterministic, explicitly whitelisted Jev state."""

    if not isinstance(state, Mapping):
        raise JevConfigurationError("state must be a mapping")

    filtered: dict[str, Any] = {}
    for key in sorted(_STATE_SCHEMA):
        if key not in state:
            continue
        rule = _STATE_SCHEMA[key]
        value = state[key]
        if rule is None or rule == "json":
            filtered[key] = _copy_json_value(value)
            continue
        if not isinstance(value, Mapping):
            raise JevConfigurationError(f"state.{key} must be an object")
        filtered[key] = {
            child_key: _copy_json_value(value[child_key])
            for child_key in sorted(rule)
            if child_key in value
        }

    if not filtered:
        raise JevConfigurationError("state contains no approved outbound fields")
    return filtered


def _candidate_mapping(candidate: Any) -> Mapping[str, Any]:
    if isinstance(candidate, Mapping):
        return candidate
    fields: dict[str, Any] = {}
    for name in ("id", "candidate_id", *_CANDIDATE_SUMMARY_FIELDS):
        if hasattr(candidate, name):
            fields[name] = getattr(candidate, name)
    if not fields:
        raise JevCandidateError("each candidate must be a mapping or candidate object")
    return fields


def _candidate_criteria(candidates: Iterable[Any]) -> tuple[dict[str, str], tuple[str, ...]]:
    by_id: dict[str, str] = {}
    if isinstance(candidates, Mapping):
        candidate_rows: Iterable[Any] = (
            {"id": candidate_id, "criteria": criterion}
            for candidate_id, criterion in candidates.items()
        )
    else:
        candidate_rows = candidates
    for candidate in candidate_rows:
        row = _candidate_mapping(candidate)
        raw_id = row.get("id", row.get("candidate_id"))
        candidate_id = _bounded_string(raw_id, field_name="candidate id")
        if not _CANDIDATE_ID_RE.fullmatch(candidate_id):
            raise JevCandidateError(
                "candidate id must be 1-64 stable ASCII letters, digits, '.', '_', ':', or '-'"
            )
        if candidate_id in by_id:
            raise JevCandidateError(f"duplicate candidate id: {candidate_id}")

        summary_parts: list[str] = []
        for field_name in _CANDIDATE_SUMMARY_FIELDS:
            value = row.get(field_name)
            if value is None:
                continue
            text = _bounded_string(value, field_name=f"candidate {candidate_id}.{field_name}")
            summary_parts.append(f"{field_name.replace('_', ' ')}: {text}")
        if not summary_parts:
            raise JevCandidateError(f"candidate {candidate_id} has no approved summary fields")
        by_id[candidate_id] = "; ".join(summary_parts)

    if not by_id:
        raise JevCandidateError("at least one candidate is required")
    ordered = dict(sorted(by_id.items()))
    return ordered, tuple(ordered)


def _safe_error_message(raw: bytes) -> str:
    text = raw[:8_192].decode("utf-8", errors="replace")
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return text.strip()[:300] or "request failed"
    if isinstance(parsed, Mapping):
        error = parsed.get("error")
        if isinstance(error, Mapping) and isinstance(error.get("message"), str):
            return error["message"][:300]
    return "request failed"


def _read_limited(response: Any) -> bytes:
    raw = response.read(_MAX_RESPONSE_BYTES + 1)
    if len(raw) > _MAX_RESPONSE_BYTES:
        raise JevResponseError("OpenRouter response exceeded the 1 MiB limit")
    return raw


class JevAdapter:
    """Synchronous, bounded transport for one Jev Choice evaluation."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str = DEFAULT_MODEL,
        endpoint: str = DEFAULT_ENDPOINT,
        timeout_seconds: float = 10.0,
        max_retries: int = 2,
        backoff_seconds: float = 0.25,
        opener: Callable[..., Any] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        resolved_key = api_key if api_key is not None else os.environ.get("OPENROUTER_API_KEY")
        if not isinstance(resolved_key, str) or not resolved_key.strip():
            raise JevConfigurationError("OPENROUTER_API_KEY is required")
        if not isinstance(model, str) or not model.strip():
            raise JevConfigurationError("model must be a non-empty string")
        if not isinstance(endpoint, str) or not endpoint.startswith("https://"):
            raise JevConfigurationError("endpoint must be an https URL")
        if not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool):
            raise JevConfigurationError("timeout_seconds must be numeric")
        if not 0 < float(timeout_seconds) <= _MAX_TIMEOUT_SECONDS:
            raise JevConfigurationError(
                f"timeout_seconds must be greater than 0 and at most {_MAX_TIMEOUT_SECONDS:g}"
            )
        if not isinstance(max_retries, int) or isinstance(max_retries, bool):
            raise JevConfigurationError("max_retries must be an integer")
        if not 0 <= max_retries <= _MAX_RETRIES:
            raise JevConfigurationError(f"max_retries must be between 0 and {_MAX_RETRIES}")
        if not isinstance(backoff_seconds, (int, float)) or isinstance(backoff_seconds, bool):
            raise JevConfigurationError("backoff_seconds must be numeric")
        if not 0 <= float(backoff_seconds) <= 5.0:
            raise JevConfigurationError("backoff_seconds must be between 0 and 5")

        self._api_key = resolved_key.strip()
        self.model = model.strip()
        self.endpoint = endpoint
        self.timeout_seconds = float(timeout_seconds)
        self.max_retries = max_retries
        self.backoff_seconds = float(backoff_seconds)
        self._opener = opener or urlopen
        self._sleep = sleep
        self._clock = clock

    def choose(self, state: Mapping[str, Any], candidates: Iterable[Any]) -> JevDecision:
        """Choose exactly one of the caller-provided candidate IDs using Jev Choice."""

        filtered_state = filter_outbound_state(state)
        criteria, offered_ids = _candidate_criteria(candidates)
        instructions = (
            "Select the single safest and most useful tactical plan for the current "
            "arena state. Return only the typed Choice."
        )
        if HANDOFF_CHOICE_ID in offered_ids:
            instructions = (
                "Select the single safest and most useful tactical plan for the current "
                "arena state. Choose handoff_to_opus if no offered plan safely fits or "
                "the available state is insufficient. Return only the typed Choice."
            )
        payload = {
            "model": self.model,
            "state": filtered_state,
            "questions": {
                QUESTION_ID: {
                    "type": "choice",
                    "instructions": instructions,
                    "criteria": criteria,
                }
            },
        }
        body = json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        ).encode("utf-8")
        if len(body) > _MAX_REQUEST_BYTES:
            raise JevConfigurationError("Jev request exceeded the 256 KiB limit")

        request = Request(
            self.endpoint,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        started = self._clock()
        raw = self._send(request)
        latency_ms = max(0.0, (self._clock() - started) * 1_000.0)
        return self._parse_response(raw, offered_ids=offered_ids, latency_ms=latency_ms)

    def _send(self, request: Request) -> bytes:
        for attempt in range(self.max_retries + 1):
            response: Any | None = None
            try:
                response = self._opener(request, timeout=self.timeout_seconds)
                status = getattr(response, "status", None)
                if status is None and hasattr(response, "getcode"):
                    status = response.getcode()
                raw = _read_limited(response)
                if status is not None and not 200 <= int(status) < 300:
                    raise JevHTTPError(
                        int(status),
                        _safe_error_message(raw),
                        retryable=int(status) in RETRYABLE_STATUS_CODES,
                    )
                return raw
            except HTTPError as exc:
                raw = exc.read(8_192)
                error = JevHTTPError(
                    int(exc.code),
                    _safe_error_message(raw),
                    retryable=int(exc.code) in RETRYABLE_STATUS_CODES,
                )
                if error.retryable and attempt < self.max_retries:
                    self._sleep(self.backoff_seconds * (2**attempt))
                    continue
                raise error from exc
            except JevHTTPError as exc:
                if exc.retryable and attempt < self.max_retries:
                    self._sleep(self.backoff_seconds * (2**attempt))
                    continue
                raise
            except (socket.timeout, TimeoutError) as exc:
                raise JevTimeoutError(
                    f"OpenRouter request exceeded the {self.timeout_seconds:g}s client timeout"
                ) from exc
            except URLError as exc:
                if isinstance(exc.reason, (socket.timeout, TimeoutError)):
                    raise JevTimeoutError(
                        f"OpenRouter request exceeded the {self.timeout_seconds:g}s client timeout"
                    ) from exc
                reason = str(exc.reason)[:300] or "network error"
                raise JevRequestError(f"OpenRouter request failed: {reason}") from exc
            finally:
                if response is not None:
                    close = getattr(response, "close", None)
                    if callable(close):
                        close()
        raise AssertionError("retry loop exhausted without returning or raising")

    def _parse_response(
        self,
        raw: bytes,
        *,
        offered_ids: tuple[str, ...],
        latency_ms: float,
    ) -> JevDecision:
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise JevResponseError("OpenRouter returned malformed JSON") from exc
        if not isinstance(payload, Mapping):
            raise JevResponseError("OpenRouter response must be a JSON object")

        response_model = payload.get("model")
        if not isinstance(response_model, str) or not response_model:
            raise JevResponseError("OpenRouter response is missing model")
        if response_model != self.model and not response_model.startswith(f"{self.model}-"):
            raise JevModelMismatchError(
                f"expected model {self.model!r}, received {response_model!r}"
            )

        answers = payload.get("answers")
        if not isinstance(answers, Mapping):
            raise JevResponseError("OpenRouter response is missing answers")
        answer = answers.get(QUESTION_ID)
        if not isinstance(answer, Mapping) or answer.get("type") != "choice":
            raise JevResponseError("OpenRouter response is missing the plan Choice answer")
        selected_id = answer.get("choice")
        if not isinstance(selected_id, str) or not selected_id:
            raise JevResponseError("Jev Choice answer is missing choice")
        if selected_id not in offered_ids:
            raise JevUnknownChoiceError(f"Jev selected unknown candidate id {selected_id!r}")

        probabilities = self._parse_probabilities(answer.get("probabilities"), offered_ids)
        if probabilities:
            selected_probability = probabilities.get(selected_id)
            if selected_probability is None:
                raise JevResponseError(
                    "probabilities must include the selected candidate id"
                )
            highest_probability = max(probabilities.values())
            if selected_probability < highest_probability and not math.isclose(
                selected_probability,
                highest_probability,
                abs_tol=1e-9,
            ):
                raise JevResponseError(
                    "Jev choice does not match the highest-probability candidate"
                )
        confidence = self._parse_optional_probability(answer.get("confidence"), "confidence")
        usage = self._parse_usage(payload.get("usage"))

        provider = payload.get("provider")
        if provider is not None and not isinstance(provider, str):
            raise JevResponseError("provider must be a string when present")
        request_id = payload.get("id")
        if request_id is not None and not isinstance(request_id, str):
            raise JevResponseError("id must be a string when present")

        return JevDecision(
            selected_id=selected_id,
            probabilities=MappingProxyType(probabilities),
            confidence=confidence,
            model=response_model,
            provider=provider,
            usage=MappingProxyType(usage),
            latency_ms=latency_ms,
            request_id=request_id,
        )

    @staticmethod
    def _parse_optional_probability(value: Any, field_name: str) -> float | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise JevResponseError(f"{field_name} must be numeric when present")
        parsed = float(value)
        if not math.isfinite(parsed) or not 0.0 <= parsed <= 1.0:
            raise JevResponseError(f"{field_name} must be finite and between 0 and 1")
        return parsed

    @classmethod
    def _parse_probabilities(
        cls, value: Any, offered_ids: tuple[str, ...]
    ) -> dict[str, float]:
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            raise JevResponseError("probabilities must be an object when present")
        unknown = set(value).difference(offered_ids)
        if unknown:
            raise JevResponseError(
                f"probabilities contain unknown candidate ids: {sorted(unknown)!r}"
            )
        parsed: dict[str, float] = {}
        for candidate_id in sorted(value):
            probability = cls._parse_optional_probability(
                value[candidate_id], f"probabilities.{candidate_id}"
            )
            if probability is None:
                raise JevResponseError("probability values must not be null")
            parsed[candidate_id] = probability
        if parsed and not math.isclose(sum(parsed.values()), 1.0, abs_tol=1e-3):
            raise JevResponseError("probabilities must sum to 1")
        return parsed

    @staticmethod
    def _parse_usage(value: Any) -> dict[str, int | float]:
        if not isinstance(value, Mapping):
            raise JevResponseError("OpenRouter response is missing usage")
        parsed: dict[str, int | float] = {}
        for name in ("input_tokens", "output_tokens"):
            token_count = value.get(name)
            if isinstance(token_count, bool) or not isinstance(token_count, int) or token_count < 0:
                raise JevResponseError(f"usage.{name} must be a non-negative integer")
            parsed[name] = token_count
        if "cost" in value:
            cost = value["cost"]
            if isinstance(cost, bool) or not isinstance(cost, (int, float)):
                raise JevResponseError("usage.cost must be numeric")
            cost = float(cost)
            if not math.isfinite(cost) or cost < 0:
                raise JevResponseError("usage.cost must be finite and non-negative")
            parsed["cost"] = cost
        return parsed


class FakeJevAdapter:
    """Deterministic in-memory adapter for controller and unit tests."""

    def __init__(
        self,
        decisions: Iterable[JevDecision | BaseException] | None = None,
        *,
        selected_id: str = HANDOFF_CHOICE_ID,
        confidence: float | None = None,
        model: str = DEFAULT_MODEL,
        endpoint: str = "fake://jev-decisions",
        repeat_last: bool = True,
    ) -> None:
        if decisions is None:
            decisions = [
                JevDecision(
                    selected_id=selected_id,
                    confidence=confidence,
                    model=model,
                    provider="fake",
                    usage={"input_tokens": 0, "output_tokens": 0},
                )
            ]
        self.model = model
        self.endpoint = endpoint
        self.repeat_last = repeat_last
        self._decisions = list(decisions)
        if not self._decisions:
            raise JevConfigurationError("FakeJevAdapter requires at least one decision")
        self._index = 0
        self.calls: list[dict[str, Any]] = []

    def choose(self, state: Mapping[str, Any], candidates: Iterable[Any]) -> JevDecision:
        materialized_candidates: Iterable[Any]
        if isinstance(candidates, Mapping):
            materialized_candidates = dict(candidates)
        else:
            materialized_candidates = list(candidates)
        criteria, offered_ids = _candidate_criteria(materialized_candidates)
        self.calls.append(
            {
                "state": filter_outbound_state(state),
                "candidate_ids": tuple(criteria),
            }
        )
        if self._index >= len(self._decisions):
            if not self.repeat_last:
                raise JevRequestError("FakeJevAdapter decision queue is exhausted")
            item = self._decisions[-1]
        else:
            item = self._decisions[self._index]
            self._index += 1
        if isinstance(item, BaseException):
            raise item
        if item.selected_id not in offered_ids:
            raise JevUnknownChoiceError(
                f"fake selected unknown candidate id {item.selected_id!r}"
            )
        return item


__all__ = [
    "DEFAULT_ENDPOINT",
    "DEFAULT_MODEL",
    "HANDOFF_CHOICE_ID",
    "FakeJevAdapter",
    "JevAdapter",
    "JevCandidateError",
    "JevConfigurationError",
    "JevDecision",
    "JevError",
    "JevHTTPError",
    "JevModelMismatchError",
    "JevRequestError",
    "JevResponseError",
    "JevTimeoutError",
    "JevUnknownChoiceError",
    "filter_outbound_state",
]
