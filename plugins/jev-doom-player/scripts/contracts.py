"""Safety and data contracts for the Jev Doom player sidecar."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any


CONTRACT_VERSION = "1"
CONTROLLER_MODES = frozenset(
    {
        "idle",
        "prepared",
        "running",
        "awaiting_opus",
        "stopping",
        "finished",
        "failed",
    }
)
MAX_OUTBOUND_BYTES = 16_000
MAX_DIRECTIVE_CHARS = 320
MAX_CANDIDATES = 20
MAX_ROUTE_WAYPOINTS = 8

_SENSITIVE_KEYS = {
    "authorization",
    "api_key",
    "apikey",
    "controller_token",
    "controller_tokens",
    "openrouter_api_key",
    "secret",
    "token",
}
_SECRET_VALUE_PATTERN = re.compile(r"(?:sk-or-v1-|sk-ant-|sk-proj-)[A-Za-z0-9_-]{8,}")
_ABSOLUTE_PATH_PATTERN = re.compile(r"^(?:[A-Za-z]:[\\/]|/(?:home|Users|root|tmp)/)")


class ContractError(ValueError):
    """Raised when data crosses a sidecar safety boundary incorrectly."""


def _clean_text(value: Any, limit: int) -> str:
    return " ".join(str(value or "").replace("\t", " ").split())[:limit]


def _optional_float(value: Any) -> float | None:
    try:
        return float(value) if value not in {None, ""} else None
    except (TypeError, ValueError):
        return None


def _copy_present(source: Mapping[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: source[key] for key in keys if key in source and source[key] is not None}


def _route_cells(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    result: list[str] = []
    for item in value[:MAX_ROUTE_WAYPOINTS]:
        cell = _clean_text(item, 3).upper()
        if re.fullmatch(r"[A-W](?:0[1-9]|[12][0-9]|3[0-3])", cell):
            result.append(cell)
    return result


def build_outbound_state(
    observation: Mapping[str, Any],
    *,
    current_plan: Mapping[str, Any] | None = None,
    strategic_directive: str = "",
) -> dict[str, Any]:
    """Reduce a fog-filtered arena observation to the only fields Jev may see."""

    self_state = observation.get("self") if isinstance(observation.get("self"), Mapping) else {}
    opponent = observation.get("opponent") if isinstance(observation.get("opponent"), Mapping) else {}
    tactical = observation.get("tactical_context") if isinstance(observation.get("tactical_context"), Mapping) else {}
    match = observation.get("match") if isinstance(observation.get("match"), Mapping) else {}
    map_state = observation.get("map") if isinstance(observation.get("map"), Mapping) else {}

    visible = bool(opponent.get("visible"))
    opponent_state: dict[str, Any] = {
        "participant_id": _clean_text(opponent.get("participant_id"), 16),
        "alive": bool(opponent.get("alive")),
        "visible": visible,
    }
    if visible:
        opponent_state.update(
            _copy_present(
                opponent,
                (
                    "health",
                    "cell",
                    "distance",
                    "relative_angle",
                    "distance_bucket",
                    "los_status",
                    "in_view_cone",
                    "revealed_by_hit",
                ),
            )
        )

    pickups: list[dict[str, Any]] = []
    raw_pickups = map_state.get("pickups")
    if isinstance(raw_pickups, list):
        for raw in raw_pickups[:8]:
            if not isinstance(raw, Mapping):
                continue
            pickup = _copy_present(raw, ("id", "type", "name", "cell", "purpose", "available", "distance"))
            pickups.append({key: _clean_text(value, 64) if isinstance(value, str) else value for key, value in pickup.items()})

    replan_reasons = tactical.get("replan_reasons")
    if not isinstance(replan_reasons, list):
        replan_reasons = []

    outbound: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "participant_id": _clean_text(observation.get("participant_id"), 16),
        "opponent_id": _clean_text(observation.get("opponent_id"), 16),
        "state_mode": _clean_text(observation.get("state_mode"), 24),
        "self": _copy_present(
            self_state,
            (
                "health",
                "alive",
                "cell",
                "angle",
                "ready_weapon",
                "ammo_bullets",
                "ammo_shells",
                "ammo_cells",
                "ammo_rockets",
                "command_status",
                "last_action",
                "damage_dealt",
                "shots_fired",
                "shots_hit",
                "invalid_actions",
                "los_status",
            ),
        ),
        "opponent": opponent_state,
        "tactical": {
            **_copy_present(
                tactical,
                (
                    "health_delta",
                    "distance_bucket",
                    "los_status",
                    "pressure_state",
                    "replan_recommended",
                    "policy_compliance_reason",
                ),
            ),
            "replan_reasons": [_clean_text(reason, 48) for reason in replan_reasons[:8]],
        },
        "pickups": pickups,
        "match": _copy_present(
            match,
            ("phase", "winner", "terminal_reason", "elapsed_time_seconds", "timeout_seconds"),
        ),
        "strategic_directive": _clean_text(strategic_directive, MAX_DIRECTIVE_CHARS),
    }

    if current_plan:
        route = current_plan.get("route_cells", current_plan.get("route", []))
        outbound["current_plan"] = {
            **_copy_present(
                current_plan,
                (
                    "candidate_id",
                    "sequence_number",
                    "objective",
                    "engagement_policy",
                    "status",
                    "current_waypoint_cell",
                    "waypoints_remaining",
                ),
            ),
            "route": _route_cells(route),
        }

    assert_outbound_safe(outbound)
    return outbound


def assert_outbound_safe(payload: Any) -> None:
    """Reject secrets, local paths, oversized payloads, and unbounded structures."""

    def visit(value: Any, path: str = "$") -> None:
        if isinstance(value, Mapping):
            for raw_key, child in value.items():
                key = str(raw_key).strip().lower()
                if key in _SENSITIVE_KEYS or key.endswith("_api_key") or key.endswith("_token"):
                    raise ContractError(f"sensitive field is forbidden at {path}.{raw_key}")
                visit(child, f"{path}.{raw_key}")
            return
        if isinstance(value, (list, tuple)):
            if len(value) > 255:
                raise ContractError(f"list is too large at {path}")
            for index, child in enumerate(value):
                visit(child, f"{path}[{index}]")
            return
        if isinstance(value, str):
            if _SECRET_VALUE_PATTERN.search(value):
                raise ContractError(f"secret-like value is forbidden at {path}")
            if _ABSOLUTE_PATH_PATTERN.match(value):
                raise ContractError(f"absolute local path is forbidden at {path}")

    visit(payload)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_OUTBOUND_BYTES:
        raise ContractError(f"outbound payload exceeds {MAX_OUTBOUND_BYTES} bytes")


def make_handoff_packet(
    *,
    reason: str,
    state: Mapping[str, Any],
    current_plan: Mapping[str, Any] | None,
    candidates: list[Mapping[str, Any]],
    probabilities: Mapping[str, Any] | None = None,
    confidence: float | None = None,
) -> dict[str, Any]:
    """Build the compact model-visible packet returned for strategic escalation."""

    summaries: list[dict[str, Any]] = []
    for candidate in candidates[:MAX_CANDIDATES]:
        summaries.append(
            {
                "id": _clean_text(candidate.get("id"), 48),
                "objective": _clean_text(candidate.get("objective"), 64),
                "summary": _clean_text(candidate.get("summary", candidate.get("reasoning", "")), 160),
                "route": _route_cells(candidate.get("route", [])),
                "engagement_policy": _clean_text(candidate.get("engagement_policy"), 32),
            }
        )
    packet: dict[str, Any] = {
        "reason": _clean_text(reason, 96),
        "state": dict(state),
        "current_plan": dict(current_plan or {}),
        "candidates": summaries,
        "probabilities": {
            _clean_text(key, 48): parsed
            for key, value in (probabilities or {}).items()
            if (parsed := _optional_float(value)) is not None
        },
        "confidence": _optional_float(confidence),
    }
    assert_outbound_safe(packet)
    return packet

