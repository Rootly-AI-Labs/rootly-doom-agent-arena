"""Supervised Jev controller for one Doom Arena participant."""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from arena_bridge import (
    ArenaBridgeError,
    load_arena_module,
    load_controller_token,
    load_repo_env,
    read_filtered_observation,
    recover_next_sequence,
    resolve_repo_root,
    verify_active_sequence,
)
from candidate_routes import CandidateRouteEngine, CandidateRouteError
from contracts import CONTROLLER_MODES, build_outbound_state, make_handoff_packet, assert_outbound_safe
from jev_adapter import (
    DEFAULT_ENDPOINT,
    DEFAULT_MODEL,
    HANDOFF_CHOICE_ID,
    JevAdapter,
    JevDecision,
    JevError,
)
from telemetry import JsonlTelemetry, filtered_state_hash
from candidate_facts import candidate_facts


PARTICIPANTS = frozenset({"player_1", "player_2"})
CONTROL_MODES = frozenset({"jev_only", "jev_hybrid"})
DEFAULT_RUN_MS = 45_000
MAX_RUN_MS = 55_000
MIN_RUN_MS = 100
DEFAULT_POLL_SECONDS = 0.25
DEFAULT_EVALUATION_SECONDS = 2.0
MIN_EVALUATION_SECONDS = 0.5
DEFAULT_SAFE_REFRESH_SECONDS = 12.0
DEFAULT_HANDOFF_COOLDOWN_SECONDS = 15.0
DEFAULT_HANDOFF_DEDUPE_SECONDS = 30.0
DEFAULT_HANDOFF_REARM_THRESHOLD = 0.45
_SECRET_VALUE_PATTERN = re.compile(r"(?:sk-or-v1-|sk-ant-|sk-proj-)[A-Za-z0-9_-]{8,}")


class ControllerError(RuntimeError):
    """Raised for invalid lifecycle transitions or local integration failures."""


def _clamp_run_ms(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ControllerError("max_run_ms must be an integer") from exc
    if not MIN_RUN_MS <= parsed <= MAX_RUN_MS:
        raise ControllerError(f"max_run_ms must be between {MIN_RUN_MS} and {MAX_RUN_MS}")
    return parsed


def _safe_error_text(error: BaseException, *secrets: str | None) -> str:
    message = " ".join(str(error).split()) or type(error).__name__
    for secret in (*secrets, os.environ.get("OPENROUTER_API_KEY")):
        if secret:
            message = message.replace(secret, "[REDACTED]")
    return _SECRET_VALUE_PATTERN.sub("[REDACTED]", message)[:1_000]


def _candidate_summary(candidate: Mapping[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key in ("id", "kind", "objective", "route", "engagement_policy", "summary", "plan_note"):
        value = candidate.get(key)
        if value is not None and value != "":
            summary[key] = value
    return summary


class JevPlayerController:
    """Own one participant's plan stream inside the MCP server process."""

    def __init__(
        self,
        *,
        arena_module: Any | None = None,
        client: Any | None = None,
        adapter: Any | None = None,
        route_engine: Any | None = None,
        telemetry: JsonlTelemetry | None = None,
        repo_root: str | Path | None = None,
        token_loader: Callable[[Any, Any, str], str] = load_controller_token,
        observation_reader: Callable[[Any, Any, str], dict[str, Any]] = read_filtered_observation,
        sequence_loader: Callable[[Any, str], int] = recover_next_sequence,
        sequence_verifier: Callable[[Any, str, int], bool] = verify_active_sequence,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        poll_seconds: float = DEFAULT_POLL_SECONDS,
        evaluation_seconds: float = DEFAULT_EVALUATION_SECONDS,
        safe_refresh_seconds: float = DEFAULT_SAFE_REFRESH_SECONDS,
        handoff_cooldown_seconds: float = DEFAULT_HANDOFF_COOLDOWN_SECONDS,
        handoff_dedupe_seconds: float = DEFAULT_HANDOFF_DEDUPE_SECONDS,
        handoff_rearm_threshold: float = DEFAULT_HANDOFF_REARM_THRESHOLD,
    ) -> None:
        self._arena = arena_module
        self._client = client
        self._adapter = adapter
        self._route_engine = route_engine
        self._telemetry = telemetry or JsonlTelemetry()
        self._repo_root_hint = repo_root
        self._repo_root: Path | None = None
        self._token_loader = token_loader
        self._observation_reader = observation_reader
        self._sequence_loader = sequence_loader
        self._sequence_verifier = sequence_verifier
        self._clock = clock
        self._sleep = sleep
        self._poll_seconds = max(0.05, float(poll_seconds))
        self._evaluation_seconds = max(MIN_EVALUATION_SECONDS, float(evaluation_seconds))
        self._safe_refresh_seconds = max(1.0, float(safe_refresh_seconds))
        self._handoff_cooldown_seconds = max(0.0, float(handoff_cooldown_seconds))
        self._handoff_dedupe_seconds = max(
            self._handoff_cooldown_seconds,
            float(handoff_dedupe_seconds),
        )
        self._handoff_rearm_threshold = float(handoff_rearm_threshold)
        if not 0.0 <= self._handoff_rearm_threshold <= 1.0:
            raise ControllerError("handoff_rearm_threshold must be between 0 and 1")

        self._condition = threading.Condition(threading.RLock())
        self._submission_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._mode = "idle"
        self._control_mode = "jev_hybrid"
        self._planner_version = "flat_v3"
        self._decision_id = None
        self._search_cooldowns = {}
        self._outcome_sequences = set()
        self._plan_fingerprint = None
        self._hierarchy_goal = ""
        self._goal_fingerprint = None
        self._last_seen_at = None
        self._visited_cells: dict[str, float] = {}
        self._selected_target = None
        self._planning_started_at = None
        self._observation_received_at = None
        self._participant_id = ""
        self._agent_name = ""
        self._controller_token: str | None = None
        self._run_id = ""
        self._scenario_id = ""
        self._sequence_number = 1
        self._last_seen_cell = ""
        self._last_contact_at = 0.0
        self._last_health: int | None = None
        self._last_damage_dealt: int | None = None
        self._last_observation: dict[str, Any] = {}
        self._last_outbound_state: dict[str, Any] = {}
        self._current_plan: dict[str, Any] = {}
        self._last_decision: dict[str, Any] = {}
        self._handoff: dict[str, Any] = {}
        self._last_error = ""
        self._stop_reason = ""
        self._stop_cleanup: dict[str, Any] = {}
        self._prepared_candidates: list[dict[str, Any]] = []
        self._prepared_decision: JevDecision | None = None
        self._prepared_handoff_reason = ""
        self._last_fingerprint: tuple[Any, ...] | None = None
        self._last_evaluation_at = 0.0
        self._last_submission_at = 0.0
        self._failure_count = 0
        self._retry_after = 0.0
        self._last_handoff_signature: tuple[Any, ...] | None = None
        self._last_handoff_at = 0.0
        self._handoff_cooldown_until = 0.0
        self._handoff_rearmed = True

    # Dependencies remain lazy so installing/enabling the plugin is dormant.
    def _record(self, event, payload):
        if self._planner_version in {'flat_v3'}:
            payload = {'decision_id': self._decision_id, **payload}
        self._telemetry.record(event, payload)

    def _record_outcome(self, status, observation=None):
        plan = self._current_plan
        seq = plan.get('sequence_number')
        if self._planner_version not in {'flat_v3'} or seq is None or seq in self._outcome_sequences:
            return
        self._outcome_sequences.add(seq)
        if self._planner_version == 'flat_v3':
            self._recent_plan_outcomes = (getattr(self, '_recent_plan_outcomes', []) + [{
                'candidate_id': plan.get('id'), 'target_cell': plan.get('target_cell'),
                'outcome': status}])[-8:]
        self._record('plan_outcome', {'run_id': self._run_id, 'participant_id': self._participant_id,
            'decision_id': plan.get('decision_id'), 'sequence_number': seq,
            'candidate_id': plan.get('id'), 'outcome': status})

    def _ensure_dependencies(self) -> None:
        if self._arena is None:
            self._repo_root = resolve_repo_root(self._repo_root_hint)
            load_repo_env(self._repo_root)
            self._arena = load_arena_module(self._repo_root)
        if self._client is None:
            server_url = os.environ.get("DOOM_ARENA_BASE_URL", "http://127.0.0.1:8001")
            self._client = self._arena.DoomArenaClient(server_url)
        if self._route_engine is None:
            self._route_engine = CandidateRouteEngine(self._arena)
        if self._adapter is None:
            configured_endpoint = os.environ.get("OPENROUTER_DECISIONS_URL", "").strip()
            if configured_endpoint and configured_endpoint != DEFAULT_ENDPOINT:
                raise ControllerError(
                    f"OPENROUTER_DECISIONS_URL must be exactly {DEFAULT_ENDPOINT}"
                )
            configured_model = os.environ.get("OPENROUTER_MODEL", "").strip()
            if configured_model and configured_model != DEFAULT_MODEL:
                raise ControllerError(f"OPENROUTER_MODEL must be exactly {DEFAULT_MODEL}")
            self._adapter = JevAdapter(model=DEFAULT_MODEL, endpoint=DEFAULT_ENDPOINT)

    def _confidence_threshold(self) -> float:
        raw = os.environ.get("JEV_DOOM_CONFIDENCE_THRESHOLD", "0.65")
        try:
            parsed = float(raw)
        except ValueError as exc:
            raise ControllerError("JEV_DOOM_CONFIDENCE_THRESHOLD must be numeric") from exc
        if not 0.0 <= parsed <= 1.0:
            raise ControllerError("JEV_DOOM_CONFIDENCE_THRESHOLD must be between 0 and 1")
        return parsed

    def _read_observation_and_plan(self) -> tuple[dict[str, Any], dict[str, Any]]:
        reader = getattr(self._client, "_read_participant_observation_and_plan", None)
        if callable(reader):
            observation, active_plan = reader(self._participant_id)
            self._observation_received_at = self._clock()
            if not isinstance(observation, dict):
                raise ControllerError("Arena returned an invalid participant observation")
            return observation, dict(active_plan or {})
        observation = self._observation_reader(self._arena, self._client, self._participant_id)
        self._observation_received_at = self._clock()
        return observation, {}

    def _with_spawn_fallback(self, observation: dict[str, Any]) -> dict[str, Any]:
        self_block = observation.setdefault("self", {})
        if isinstance(self_block, dict) and not self_block.get("cell"):
            spawn_cell_fn = getattr(self._client, "participant_spawn_cell", None)
            spawn_cell = str(spawn_cell_fn(self._participant_id) if callable(spawn_cell_fn) else "")
            if spawn_cell:
                self_block["cell"] = spawn_cell
                self_block.setdefault("alive", True)
        return observation

    def _update_last_seen(self, observation: Mapping[str, Any]) -> None:
        now = self._clock()
        cell = observation.get('self', {}).get('cell')
        if isinstance(cell, str) and re.fullmatch(r'[A-W](?:0[1-9]|[12][0-9]|3[0-3])', cell):
            self._visited_cells[cell] = now
        opponent = observation.get("opponent") if isinstance(observation.get("opponent"), Mapping) else {}
        if opponent.get("visible") and opponent.get("cell"):
            self._last_seen_cell = str(opponent["cell"])
            self._last_seen_at = now
            self._last_contact_at = now
        self_state = observation.get("self") if isinstance(observation.get("self"), Mapping) else {}
        try:
            health = int(self_state.get("health"))
        except (TypeError, ValueError):
            health = None
        try:
            damage_dealt = int(self_state.get("damage_dealt"))
        except (TypeError, ValueError):
            damage_dealt = None
        if self._last_health is not None and health is not None and health < self._last_health:
            self._last_contact_at = now
        if (
            self._last_damage_dealt is not None
            and damage_dealt is not None
            and damage_dealt > self._last_damage_dealt
        ):
            self._last_contact_at = now
        self._last_health = health
        self._last_damage_dealt = damage_dealt

    def _generate_candidates(
        self,
        observation: Mapping[str, Any],
        current_plan: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        candidates, self._candidate_audit = self._route_engine.generate_neutral_candidates(
            observation, scenario_id=self._scenario_id,
            current_plan={**self._current_plan, **(current_plan or {})},
            last_seen_cell=self._last_seen_cell or '',
            visited_cells=self._visited_cells, now=self._clock())
        if self._control_mode == 'jev_hybrid':
            handoff = CandidateRouteEngine._handoff_candidate('Request guidance from the configured LLM.')
            if len(candidates) >= 20:
                removed = candidates[-1]
                self._candidate_audit['omitted'].append({**removed, 'omission_reason': 'hybrid_handoff_slot'})
                candidates = candidates[:-1]
            candidates = [*candidates, handoff]
            self._candidate_audit['offered'] = candidates
        return candidates

    def _safe_fallback(
        self,
        observation: Mapping[str, Any],
        candidates: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        return dict(
            self._route_engine.safe_fallback(
                observation,
                scenario_id=self._scenario_id,
                current_plan=self._current_plan or None,
                last_seen_cell=self._last_seen_cell or None,
                candidates=candidates,
            )
        )

    def _evaluate(
        self,
        observation: Mapping[str, Any],
        candidates: Sequence[Mapping[str, Any]],
    ) -> JevDecision:
        started = self._clock()
        self._decision_id = uuid.uuid4().hex
        self._planning_started_at = self._observation_received_at if self._observation_received_at is not None else started
        if self._planner_version == 'flat_v3':
            self._record('candidate_menu', {'run_id': self._run_id,
                **getattr(self, '_candidate_audit', {})})
        outbound = build_outbound_state(
            observation,
            repo_root=self._repo_root,
            current_plan=self._current_plan or None,
        )
        if self._planner_version in {"flat_v3"}:
            self._record('decision_observation', {'run_id': self._run_id,
                'participant_id': self._participant_id, 'state': outbound,
                'state_hash': filtered_state_hash(outbound)})
            outbound['memory'] = {'last_seen_opponent_cell': self._last_seen_cell or None,
                'visited_cell_count': len(self._visited_cells),
                'search_memory_basis': 'Recorded player cells only; not a visibility or cleared-area map.',
                'last_seen_age_seconds': max(0.0, self._clock() - self._last_seen_at)
                if self._last_seen_at is not None else None}
            if self._planner_version == 'flat_v3':
                outbound['memory']['recent_plan_outcomes'] = getattr(self, '_recent_plan_outcomes', [])
                outbound['memory']['last_plan_feedback'] = {
                    key: self._last_active_plan[key] for key in
                    ('status', 'sequence_number', 'current_waypoint_cell')
                    if key in self._last_active_plan}
            outbound['planning'] = {'stage': 'plan', 'selection_mode': 'all_legal_plans'}
            outbound['candidates'] = candidate_facts(candidates)
        assert_outbound_safe(outbound)
        decision = self._adapter.choose(outbound, candidates)
        if self._planner_version in {'flat_v3'} and decision.selected_id not in {c['id'] for c in candidates}:
            raise ControllerError('Jev selected an option outside the offered menu')
        if self._planner_version in {'flat_v3'}:
            chosen = next(c for c in candidates if c['id'] == decision.selected_id)
            self._hierarchy_goal = chosen.get('action_family', '')  # Descriptive label only.
            self._selected_target = chosen.get('target_cell') or (chosen.get('route') or [None])[-1]
        self._last_outbound_state = outbound
        self._last_decision = {
            "selected_id": decision.selected_id,
            "probabilities": dict(decision.probabilities),
            "confidence": decision.confidence,
            "model": decision.model,
            "provider": decision.provider,
            "usage": dict(decision.usage),
            "latency_ms": round(decision.latency_ms, 3),
            "request_id": decision.request_id,
        }
        self._record(
            "jev_decision",
            {
                "run_id": self._run_id,
                "participant_id": self._participant_id,
                "control_mode": self._control_mode,
                "jev_model": decision.model,
                "filtered_state_hash": filtered_state_hash(outbound),
                "candidate_ids": [candidate.get("id") for candidate in candidates],
                "planner_version": self._planner_version,
                "goal": self._hierarchy_goal or None,
                "candidates": candidate_facts(candidates),
                "planning_elapsed_ms": round((self._clock() - started) * 1000, 3),
                **self._last_decision,
            },
        )
        return decision

    def _find_candidate(self, candidates: Sequence[Mapping[str, Any]], candidate_id: str) -> dict[str, Any] | None:
        for candidate in candidates:
            if candidate.get("id") == candidate_id and candidate.get("actionable") is True:
                if self._planner_version in {'flat_v3'}:
                    target = candidate.get('target_cell') or (candidate.get('route') or [None])[-1]
                    if target != self._selected_target:
                        return None
                return dict(candidate)
        return None

    def _decision_handoff_reason(self, decision: JevDecision) -> str:
        if self._control_mode == "jev_only":
            return ""
        if decision.selected_id == HANDOFF_CHOICE_ID:
            return "jev_requested_handoff"
        if decision.confidence is None:
            return "jev_confidence_missing"
        threshold = self._confidence_threshold()
        if not self._handoff_rearmed:
            threshold = min(threshold, self._handoff_rearm_threshold)
        if decision.confidence < threshold:
            return "jev_low_confidence"
        return ""

    def _note_actionable_decision(self, decision: JevDecision) -> None:
        if (
            decision.confidence is not None
            and decision.confidence >= self._confidence_threshold()
        ):
            self._handoff_rearmed = True

    def _handoff_signature(
        self,
        reason: str,
        observation: Mapping[str, Any],
        candidates: Sequence[Mapping[str, Any]],
        decision: JevDecision | None,
    ) -> tuple[Any, ...]:
        self_state = observation.get("self") if isinstance(observation.get("self"), Mapping) else {}
        opponent = observation.get("opponent") if isinstance(observation.get("opponent"), Mapping) else {}
        try:
            health_bucket = int(self_state.get("health")) // 25
        except (TypeError, ValueError):
            health_bucket = None
        return (
            reason,
            decision.selected_id if decision else None,
            self_state.get("cell"),
            health_bucket,
            bool(opponent.get("visible")),
            opponent.get("cell") if opponent.get("visible") else self._last_seen_cell,
            tuple(candidate.get("id") for candidate in candidates),
        )

    def _handoff_suppression(
        self,
        reason: str,
        observation: Mapping[str, Any],
        candidates: Sequence[Mapping[str, Any]],
        decision: JevDecision | None,
    ) -> tuple[str, tuple[Any, ...]]:
        signature = self._handoff_signature(reason, observation, candidates, decision)
        now = self._clock()
        if now < self._handoff_cooldown_until:
            return "cooldown", signature
        if (
            signature == self._last_handoff_signature
            and now - self._last_handoff_at < self._handoff_dedupe_seconds
        ):
            return "duplicate", signature
        return "", signature

    def _build_handoff(
        self,
        reason: str,
        observation: Mapping[str, Any],
        candidates: Sequence[Mapping[str, Any]],
        decision: JevDecision | None = None,
    ) -> dict[str, Any]:
        state = build_outbound_state(
            observation,
            repo_root=self._repo_root,
            current_plan=self._current_plan or None,
        )
        return make_handoff_packet(
            reason=reason,
            state=state,
            current_plan=_candidate_summary(self._current_plan) if self._current_plan else None,
            candidates=[dict(candidate) for candidate in candidates],
            probabilities=dict(decision.probabilities) if decision else {},
            confidence=decision.confidence if decision else None,
        )

    def prepare(
        self,
        participant_id: str,
        agent_name: str | None = None,
        control_mode: str | None = None,
        planner_version: str | None = None,
    ) -> dict[str, Any]:
        participant_id = str(participant_id).strip().lower()
        if participant_id not in PARTICIPANTS:
            raise ControllerError("participant_id must be player_1 or player_2")
        selected_mode = str(control_mode or os.environ.get("JEV_DOOM_CONTROL_MODE", "jev_hybrid")).strip().lower()
        if selected_mode not in CONTROL_MODES:
            raise ControllerError("control_mode must be jev_only or jev_hybrid")
        planner = planner_version or os.environ.get('JEV_DOOM_PLANNER') or 'flat_v3'
        if planner != 'flat_v3':
            raise ControllerError('Only flat_v3 is supported. Remove the obsolete planner setting; do not downgrade.')
        selected_name = " ".join(str(agent_name or "").split())
        if not selected_name:
            selected_name = "Jev Jockey" if participant_id == "player_1" else "Jev Wrangler"

        with self._condition:
            if self._thread is not None and self._thread.is_alive():
                raise ControllerError("Stop the active Jev player before preparing another participant")
            self._reset_runtime_locked()
            self._participant_id = participant_id
            self._control_mode = selected_mode
            self._planner_version = planner
            self._agent_name = selected_name

        try:
            self._ensure_dependencies()
            self._controller_token = self._token_loader(self._arena, self._client, participant_id)
            self._run_id = str(self._client.run_id)
            self._scenario_id = str(self._client.scenario_id)
            observation, active_plan = self._read_observation_and_plan()
            observation = self._with_spawn_fallback(observation)
            self._update_last_seen(observation)
            self._sequence_number = self._sequence_loader(self._client, participant_id)
            candidates = self._generate_candidates(observation, active_plan)
            if not any(candidate.get("actionable") for candidate in candidates):
                raise ControllerError("No legal opening plan candidate is available")

            self._prepared_candidates = [dict(candidate) for candidate in candidates]
            self._last_observation = dict(observation)

            if self._repo_root is not None and getattr(self._telemetry, "path", None) is None:
                safe_run = "".join(ch for ch in self._run_id if ch.isalnum() or ch in "_-")[:80]
                self._telemetry = JsonlTelemetry(
                    self._repo_root / "benchmarks" / "results" / safe_run / f"jev_{participant_id}.jsonl"
                )

            ready_text = self._client.set_participant_ready(
                participant_id,
                self._controller_token,
                selected_name,
            )
            ready = json.loads(ready_text) if isinstance(ready_text, str) else ready_text
            if not isinstance(ready, Mapping) or not ready.get("accepted", True):
                raise ControllerError("Arena rejected participant readiness")

            with self._condition:
                self._mode = "prepared"
                self._condition.notify_all()
            return {
                **self.status(),
                "ready": True,
                "agent_name": selected_name,
                "opening_observation": build_outbound_state(observation),
                "candidate_ids": [candidate.get("id") for candidate in candidates],
                "opening_handoff_reason": None,
            }
        except Exception as exc:
            safe_error = _safe_error_text(exc, self._controller_token)
            with self._condition:
                self._mode = "failed"
                self._last_error = safe_error
                self._controller_token = None
                self._condition.notify_all()
            if isinstance(exc, (ControllerError, ArenaBridgeError, CandidateRouteError, JevError)):
                raise ControllerError(safe_error) from exc
            raise

    def _reset_runtime_locked(self) -> None:
        self._decision_id = None
        self._search_cooldowns = {}
        self._recent_plan_outcomes = []
        self._outcome_sequences = set()
        self._plan_fingerprint = None
        self._visited_cells = {}
        self._hierarchy_goal = ''
        self._goal_fingerprint = None
        self._last_seen_at = None
        self._selected_target = None
        self._planning_started_at = None
        self._observation_received_at = None
        self._stop_event = threading.Event()
        self._thread = None
        self._mode = "idle"
        self._controller_token = None
        self._run_id = ""
        self._scenario_id = ""
        self._sequence_number = 1
        self._last_seen_cell = ""
        self._last_contact_at = self._clock()
        self._last_health = None
        self._last_damage_dealt = None
        self._last_observation = {}
        self._last_active_plan = {}
        self._last_outbound_state = {}
        self._current_plan = {}
        self._center_patrol_target = ""
        self._last_decision = {}
        self._handoff = {}
        self._last_error = ""
        self._stop_reason = ""
        self._stop_cleanup = {}
        self._prepared_candidates = []
        self._prepared_decision = None
        self._prepared_handoff_reason = ""
        self._last_fingerprint = None
        self._last_evaluation_at = 0.0
        self._last_submission_at = 0.0
        self._failure_count = 0
        self._retry_after = 0.0
        self._last_handoff_signature = None
        self._last_handoff_at = 0.0
        self._handoff_cooldown_until = 0.0
        self._handoff_rearmed = True

    def _submit_candidate(self, candidate: Mapping[str, Any], *, source: str) -> dict[str, Any]:
        with self._submission_lock:
            if self._stop_event.is_set() or self._mode == "stopping":
                raise ControllerError("Jev controller is stopping")
            if candidate.get("actionable") is not True:
                raise ControllerError("Cannot submit a non-actionable candidate")
            if (
                self._current_plan
                and str(self._last_active_plan.get("status") or "")
                not in {"complete", "completed", "route_complete", "stalled", "rejected"}
                and self._plan_signature(candidate) == self._plan_signature(self._current_plan)
            ):
                self._record(
                    "plan_deduplicated",
                    {
                        "run_id": self._run_id,
                        "participant_id": self._participant_id,
                        "candidate_id": candidate.get("id"),
                        "active_sequence_number": self._current_plan.get("sequence_number"),
                        "source": source,
                        "reason": "exact_active_plan",
                    },
                )
                return {
                    "accepted": True,
                    "deduplicated": True,
                    "intent_id": self._current_plan.get("intent_id"),
                    "sequence_number": self._current_plan.get("sequence_number"),
                }
            sequence = self._sequence_number
            text = self._client.set_participant_plan(
                self._participant_id,
                list(candidate.get("route") or []),
                str(candidate.get("objective") or ""),
                str(candidate.get("engagement_policy") or "engage_if_visible"),
                str(candidate.get("reasoning") or ""),
                str(candidate.get("plan_note") or "I am taking the safe route."),
                self._controller_token,
                sequence,
            )
            if self._stop_event.is_set() or self._mode == "stopping":
                raise ControllerError("Jev controller stopped during plan submission")
            result = json.loads(text) if isinstance(text, str) else text
            if not isinstance(result, Mapping) or not bool(result.get("accepted")):
                message = result.get("error") if isinstance(result, Mapping) else "invalid response"
                raise ControllerError(f"Arena rejected plan: {message}")
            if not self._sequence_verifier(self._client, self._participant_id, sequence):
                try:
                    recovered = self._sequence_loader(self._client, self._participant_id)
                except Exception:
                    recovered = sequence + 1
                self._sequence_number = max(sequence + 1, int(recovered))
                raise ControllerError("Arena did not acknowledge the submitted plan sequence")

            self._sequence_number += 1
            self._record_outcome('replaced', self._last_observation)
            self._last_submission_at = self._clock()
            self._current_plan = {
                **dict(candidate),
                "candidate_id": candidate.get("id"),
                "sequence_number": sequence,
                "intent_id": result.get("intent_id"),
                "submission_source": source,
                "decision_id": self._decision_id,
                "goal": self._hierarchy_goal if source == 'jev' else None,
            }
            self._plan_fingerprint = self._fingerprint(self._last_observation, {'status': 'active'})
            if candidate.get("id") == "patrol_center":
                route = list(candidate.get("route") or [])
                self._center_patrol_target = str(
                    candidate.get("target_cell") or (route[-1] if route else "")
                )
            else:
                self._center_patrol_target = ""
            self._record(
                "plan_submission",
                {
                    "run_id": self._run_id,
                    "participant_id": self._participant_id,
                    "sequence_number": sequence,
                    "candidate_id": candidate.get("id"),
                    "source": source,
                    "accepted": True,
                    "planner_version": self._planner_version,
                    "goal": (self._hierarchy_goal or None) if source == 'jev' else None,
                    **({'observation_to_accepted_plan_ms': round((self._clock() - self._planning_started_at) * 1000, 3)}
                       if source == 'jev' and self._planner_version in {'flat_v3'} and self._planning_started_at is not None else {}),
                },
            )
            return dict(result)

    @staticmethod
    def _plan_signature(candidate: Mapping[str, Any]) -> tuple[Any, ...]:
        return (
            str(candidate.get("id") or candidate.get("candidate_id") or ""),
            str(candidate.get("objective") or ""),
            tuple(str(cell) for cell in (candidate.get("route") or [])),
            str(candidate.get("target_cell") or ""),
            str(candidate.get("engagement_policy") or ""),
        )

    def _set_handoff(
        self,
        reason: str,
        observation: Mapping[str, Any],
        candidates: Sequence[Mapping[str, Any]],
        decision: JevDecision | None = None,
        signature: tuple[Any, ...] | None = None,
    ) -> None:
        if self._stop_event.is_set():
            return
        handoff = self._build_handoff(reason, observation, candidates, decision)
        handoff_signature = signature or self._handoff_signature(
            reason,
            observation,
            candidates,
            decision,
        )
        with self._condition:
            if self._stop_event.is_set() or self._mode == "stopping":
                return
            self._handoff = handoff
            self._last_handoff_signature = handoff_signature
            self._last_handoff_at = self._clock()
            self._mode = "awaiting_opus"
            self._record(
                "handoff",
                {
                    "run_id": self._run_id,
                    "participant_id": self._participant_id,
                    "reason": reason,
                    "candidate_ids": [candidate.get("id") for candidate in candidates],
                },
            )
            self._condition.notify_all()

    def _apply_opening(self) -> None:
        candidates = self._prepared_candidates
        if not candidates:
            raise ControllerError("Opening candidates were not prepared")
        try:
            decision = self._evaluate(self._last_observation, candidates)
        except (JevError, CandidateRouteError, ControllerError) as exc:
            self._last_error = _safe_error_text(exc, self._controller_token)
            self._recover_with_fresh_fallback("opening_jev_failure")
        else:
            refreshed = self._refresh_candidates_after_delay()
            if refreshed is None:
                return
            observation, candidates = refreshed
            reason = self._decision_handoff_reason(decision)
            selected = self._find_candidate(candidates, decision.selected_id)
            if selected is None and not reason:
                reason = "jev_selected_non_actionable_candidate"
            if reason:
                self._handle_evaluation_failure(
                    reason,
                    observation,
                    candidates,
                    decision,
                )
            else:
                try:
                    self._submit_candidate(selected, source="jev")
                except ControllerError as exc:
                    self._last_error = _safe_error_text(exc, self._controller_token)
                    self._recover_with_fresh_fallback(
                        "opening_plan_rejection",
                        decision,
                    )
                else:
                    self._note_actionable_decision(decision)
        finally:
            self._prepared_candidates = []
            self._prepared_decision = None
            self._last_evaluation_at = self._clock()
            self._last_fingerprint = None

    def _fingerprint(self, observation: Mapping[str, Any], active_plan: Mapping[str, Any]) -> tuple[Any, ...]:
        self_state = observation.get("self") if isinstance(observation.get("self"), Mapping) else {}
        opponent = observation.get("opponent") if isinstance(observation.get("opponent"), Mapping) else {}
        tactical = observation.get("tactical_context") if isinstance(observation.get("tactical_context"), Mapping) else {}
        pickups = observation.get("map", {}).get("pickups", []) if isinstance(observation.get("map"), Mapping) else []
        available_pickups = tuple(
            sorted(
                str(item.get("id"))
                for item in pickups
                if isinstance(item, Mapping) and item.get("available") is not False
            )
        )
        health = self_state.get("health")
        try:
            health_bucket = int(health) // 25
        except (TypeError, ValueError):
            health_bucket = None
        match = observation.get("match") if isinstance(observation.get("match"), Mapping) else {}
        try:
            endgame = (
                float(match.get("timeout_seconds"))
                - float(match.get("elapsed_time_seconds"))
                <= 20.0
            )
        except (TypeError, ValueError):
            endgame = False
        active_status = str(active_plan.get("status") or "")
        route_terminal = active_status in {
            "complete",
            "completed",
            "route_complete",
            "stalled",
            "rejected",
        }
        # Normal cell and waypoint progress is execution, not a new tactical
        # event. Position becomes material again when no plan is active or the
        # plan reaches a terminal state.
        position_event = self_state.get("cell") if not active_plan or route_terminal else None
        ammo_buckets = tuple(
            (key, int(self_state.get(key)) // 5)
            for key in ("ammo_bullets", "ammo_shells", "ammo_cells", "ammo_rockets")
            if str(self_state.get(key, "")).lstrip("-").isdigit()
        )
        return (
            position_event,
            health_bucket,
            self_state.get("damage_dealt"),
            self_state.get("ready_weapon"),
            ammo_buckets,
            bool(opponent.get("visible")),
            opponent.get("cell") if opponent.get("visible") else self._last_seen_cell,
            opponent.get("health") if opponent.get("visible") else None,
            bool(tactical.get("replan_recommended")),
            tuple(tactical.get("replan_reasons") or []),
            available_pickups,
            active_status if route_terminal else "active",
            endgame,
        )

    def _match_finished(self, observation: Mapping[str, Any]) -> bool:
        match = observation.get("match") if isinstance(observation.get("match"), Mapping) else {}
        self_state = observation.get("self") if isinstance(observation.get("self"), Mapping) else {}
        return str(match.get("phase", "")) == "finished" or self_state.get("alive") is False

    def _mark_match_finished(self) -> None:
        with self._condition:
            self._mode = "finished"
            self._stop_reason = "match_finished"
            self._condition.notify_all()

    def _refresh_control_state(self) -> tuple[dict[str, Any], dict[str, Any], bool]:
        self._client._sync_run_metadata()
        if str(self._client.run_id) != self._run_id:
            raise ControllerError("Arena run changed; prepare the Jev player for the new run")
        observation, active_plan = self._read_observation_and_plan()
        observation = self._with_spawn_fallback(observation)
        self._update_last_seen(observation)
        self._last_observation = dict(observation)
        self._last_active_plan = dict(active_plan or {})
        if self._planner_version in {'flat_v3'} and self._current_plan:
            status = active_plan.get('status')
            same_sequence = active_plan.get('sequence_number') in (None, self._current_plan.get('sequence_number'))
            if same_sequence and status in {'complete', 'completed', 'route_complete', 'stalled', 'rejected'}:
                self._record_outcome(status, observation)
            target = self._current_plan.get('target_cell') or (self._current_plan.get('route') or [None])[-1]
            if target and observation.get('self', {}).get('cell') == target:
                self._record_outcome('destination_reached', observation)
        if self._center_patrol_target:
            self_block = observation.get("self") if isinstance(observation.get("self"), Mapping) else {}
            active_status = str(active_plan.get("status") or "")
            if (
                str(self_block.get("cell") or "") == self._center_patrol_target
                or active_status
                in {"complete", "completed", "route_complete", "stalled", "rejected"}
            ):
                self._center_patrol_target = ""
        finished = self._match_finished(observation)
        if finished:
            self._record_outcome('match_finished', observation)
            self._mark_match_finished()
        return observation, active_plan, finished

    def _refresh_candidates_after_delay(
        self,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
        observation, active_plan, finished = self._refresh_control_state()
        if finished:
            return None
        candidates = self._generate_candidates(observation, active_plan)
        return observation, candidates

    def _recover_with_fresh_fallback(
        self,
        reason: str,
        decision: JevDecision | None = None,
    ) -> bool:
        refreshed = self._refresh_candidates_after_delay()
        if refreshed is None:
            return False
        observation, candidates = refreshed
        self._handle_evaluation_failure(reason, observation, candidates, decision)
        return True

    def _handle_evaluation_failure(
        self,
        reason: str,
        observation: Mapping[str, Any],
        candidates: Sequence[Mapping[str, Any]],
        decision: JevDecision | None = None,
    ) -> None:
        if self._stop_event.is_set():
            return
        if self._planner_version in {'flat_v3'}:
            self._goal_fingerprint = None  # Reconsider after invalid/stale decisions or API failures.
        try:
            fallback = self._safe_fallback(observation, candidates)
        except CandidateRouteError:
            if self._control_mode == "jev_hybrid":
                self._set_handoff(reason, observation, candidates, decision)
                return
            raise
        suppression = ""
        signature: tuple[Any, ...] | None = None
        if self._control_mode == "jev_hybrid":
            suppression, signature = self._handoff_suppression(
                reason,
                observation,
                candidates,
                decision,
            )
        if suppression:
            selected = self._find_candidate(candidates, decision.selected_id) if decision else None
            recovery = selected or fallback
            if self._current_plan.get("id") != recovery.get("id") or (
                self._clock() - self._last_submission_at >= self._safe_refresh_seconds
            ):
                self._submit_candidate(recovery, source="jev_handoff_suppressed")
            if decision is not None:
                self._note_actionable_decision(decision)
            self._record(
                "handoff_suppressed",
                {
                    "run_id": self._run_id,
                    "participant_id": self._participant_id,
                    "reason": reason,
                    "suppression": suppression,
                    "selected_id": decision.selected_id if decision else None,
                },
            )
            return
        if self._current_plan.get("id") != fallback.get("id") or (
            self._clock() - self._last_submission_at >= self._safe_refresh_seconds
        ):
            self._submit_candidate(fallback, source="deterministic_fallback")
        if self._control_mode == "jev_hybrid":
            self._set_handoff(
                reason,
                observation,
                candidates,
                decision,
                signature=signature,
            )
        else:
            self._failure_count += 1
            self._retry_after = self._clock() + min(30.0, float(2 ** min(self._failure_count, 5)))

    def _supervisor_loop(self) -> None:
        try:
            if self._prepared_candidates:
                observation, active_plan, finished = self._refresh_control_state()
                if finished:
                    return
                self._prepared_candidates = self._generate_candidates(observation, active_plan)
                if not any(candidate.get("actionable") for candidate in self._prepared_candidates):
                    raise ControllerError("No legal opening plan candidate is available")
                self._apply_opening()
                with self._condition:
                    self._condition.notify_all()

            while not self._stop_event.is_set():
                observation, active_plan, finished = self._refresh_control_state()
                if finished:
                    return

                now = self._clock()
                with self._condition:
                    awaiting = self._mode == "awaiting_opus"
                if awaiting:
                    if self._current_plan and now - self._last_submission_at >= self._safe_refresh_seconds:
                        candidates = self._generate_candidates(observation, active_plan)
                        fallback = self._safe_fallback(observation, candidates)
                        try:
                            self._submit_candidate(fallback, source="handoff_safe_refresh")
                        except ControllerError as exc:
                            self._last_error = _safe_error_text(exc, self._controller_token)
                            self._last_submission_at = now
                    self._sleep(self._poll_seconds)
                    continue

                fingerprint = self._fingerprint(observation, active_plan)
                if self._last_fingerprint is None:
                    self._last_fingerprint = fingerprint
                    material_change = False
                else:
                    material_change = fingerprint != self._last_fingerprint
                heartbeat = now - self._last_evaluation_at >= self._evaluation_seconds
                if self._planner_version in {'flat_v3'} and active_plan and not material_change:
                    heartbeat = now - self._last_evaluation_at >= self._safe_refresh_seconds
                retry_ready = now >= self._retry_after
                if (self._planner_version in {'flat_v3'}
                        and self._current_plan.get('submission_source') == 'jev'
                        and self._current_plan.get('sequence_number') not in self._outcome_sequences
                        and fingerprint == self._plan_fingerprint):
                    candidates = self._generate_candidates(observation, active_plan)
                    target = self._current_plan.get('target_cell') or (self._current_plan.get('route') or [None])[-1]
                    retained = next((c for c in candidates if c['id'] == 'continue_current'
                        and (c.get('target_cell') or (c.get('route') or [None])[-1]) == target), None)
                    if retained:
                        self._last_evaluation_at = now
                        self._last_fingerprint = fingerprint
                        self._sleep(self._poll_seconds)
                        continue
                if retry_ready and (material_change or heartbeat):
                    if now - self._last_evaluation_at < MIN_EVALUATION_SECONDS:
                        self._sleep(self._poll_seconds)
                        continue
                    self._last_fingerprint = fingerprint
                    self._last_evaluation_at = now
                    candidates = self._generate_candidates(observation, active_plan)
                    if not any(candidate.get("actionable") for candidate in candidates):
                        self._handle_evaluation_failure("no_legal_candidates", observation, candidates)
                        continue
                    try:
                        decision = self._evaluate(observation, candidates)
                        if self._stop_event.is_set():
                            break
                        refreshed = self._refresh_candidates_after_delay()
                        if refreshed is None:
                            return
                        observation, candidates = refreshed
                        reason = self._decision_handoff_reason(decision)
                        selected = self._find_candidate(candidates, decision.selected_id)
                        if selected is None and not reason:
                            reason = "jev_selected_non_actionable_candidate"
                        if reason:
                            self._handle_evaluation_failure(reason, observation, candidates, decision)
                        else:
                            try:
                                self._submit_candidate(selected, source="jev")
                            except ControllerError as exc:
                                self._last_error = _safe_error_text(exc, self._controller_token)
                                if not self._recover_with_fresh_fallback(
                                    "plan_rejection",
                                    decision,
                                ):
                                    return
                            else:
                                self._note_actionable_decision(decision)
                                self._failure_count = 0
                                self._retry_after = 0.0
                    except (JevError, CandidateRouteError, ControllerError) as exc:
                        if self._stop_event.is_set():
                            break
                        self._last_error = _safe_error_text(exc, self._controller_token)
                        if not self._recover_with_fresh_fallback("jev_or_plan_failure"):
                            return
                self._sleep(self._poll_seconds)
        except Exception as exc:
            with self._condition:
                if not self._stop_event.is_set() and self._mode != "stopping":
                    self._mode = "failed"
                    self._last_error = _safe_error_text(exc, self._controller_token)
                self._condition.notify_all()
        finally:
            with self._condition:
                # An explicit stop owns arena cleanup and the final lifecycle
                # transition.  In particular, it still needs the controller
                # token after an in-flight plan submission releases its lock.
                self._condition.notify_all()

    def _start_thread_locked(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._supervisor_loop,
            name=f"jev-doom-{self._participant_id or 'idle'}",
            daemon=True,
        )
        self._thread.start()

    def _wait_for_return(self, max_run_ms: int) -> dict[str, Any]:
        deadline = self._clock() + max_run_ms / 1000.0
        with self._condition:
            while self._mode not in {"awaiting_opus", "finished", "failed", "idle"}:
                remaining = deadline - self._clock()
                if remaining <= 0:
                    break
                self._condition.wait(timeout=min(remaining, 0.25))
        return self.status()

    def run(self, max_run_ms: int = DEFAULT_RUN_MS) -> dict[str, Any]:
        max_run_ms = _clamp_run_ms(max_run_ms)
        with self._condition:
            if self._mode not in {"prepared", "running", "awaiting_opus"}:
                raise ControllerError("Prepare the Jev player before running it")
            if self._mode == "awaiting_opus":
                return self.status()
            self._mode = "running"
            self._start_thread_locked()
        return self._wait_for_return(max_run_ms)

    def _normalize_override(self, override_plan: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(override_plan, Mapping):
            raise ControllerError("override_plan must be an object")
        observation = self._last_observation
        self_block = observation.get("self") if isinstance(observation.get("self"), Mapping) else {}
        start_cell = str(self_block.get("cell") or "")
        route = override_plan.get("route")
        try:
            _route_text, route_cells = self._arena.normalize_plan_route(route, start_cell=start_cell)
            engagement = self._arena.normalize_plan_engagement_policy(
                override_plan.get("engagement_policy", "engage_if_visible")
            )
            objective = self._arena.normalize_plan_objective(override_plan.get("objective", "Strategic override"))
            reasoning = self._arena.normalize_plan_reasoning(override_plan.get("reasoning", "Host strategic override"))
            note = self._arena.normalize_plan_summary(
                override_plan.get("plan_note", "I am switching to the strategic route.")
            )[:80]
        except Exception as exc:
            raise ControllerError(f"Invalid override_plan: {exc}") from exc
        if not note:
            raise ControllerError("override_plan.plan_note is required")
        return {
            "id": "opus_override",
            "kind": "plan",
            "actionable": True,
            "objective": objective,
            "route": route_cells,
            "engagement_policy": engagement,
            "reasoning": reasoning,
            "summary": reasoning,
            "plan_note": note,
        }

    def resume(
        self,
        override_plan: Mapping[str, Any] | None = None,
        max_run_ms: int = DEFAULT_RUN_MS,
    ) -> dict[str, Any]:
        max_run_ms = _clamp_run_ms(max_run_ms)
        with self._condition:
            if self._mode != "awaiting_opus":
                raise ControllerError("resume_jev_player requires an active strategic handoff")
            if override_plan is not None:
                candidate = self._normalize_override(override_plan)
                self._submit_candidate(candidate, source="opus_override")
            self._handoff = {}
            self._prepared_handoff_reason = ""
            self._last_fingerprint = None
            self._retry_after = 0.0
            self._failure_count = 0
            self._handoff_cooldown_until = self._clock() + self._handoff_cooldown_seconds
            self._handoff_rearmed = False
            self._mode = "running"
            self._start_thread_locked()
            self._condition.notify_all()
        return self._wait_for_return(max_run_ms)

    def status(self) -> dict[str, Any]:
        with self._condition:
            if self._mode not in CONTROLLER_MODES:
                raise AssertionError(f"unknown controller mode {self._mode}")
            match = self._last_observation.get("match", {}) if isinstance(self._last_observation, Mapping) else {}
            return {
                "status": self._mode,
                "control_mode": self._control_mode,
                "planner_version": self._planner_version,
                "current_goal": self._hierarchy_goal or None,
                "run_id": self._run_id or None,
                "scenario_id": self._scenario_id or None,
                "participant_id": self._participant_id or None,
                "agent_name": self._agent_name or None,
                "next_sequence_number": self._sequence_number if self._participant_id else None,
                "last_plan": _candidate_summary(self._current_plan) if self._current_plan else None,
                "last_decision": dict(self._last_decision) if self._last_decision else None,
                "jev_model": str(getattr(self._adapter, "model", DEFAULT_MODEL)),
                "jev_endpoint": str(getattr(self._adapter, "endpoint", DEFAULT_ENDPOINT)),
                "handoff": dict(self._handoff) if self._handoff else None,
                "match": {
                    key: match.get(key)
                    for key in ("phase", "winner", "terminal_reason", "elapsed_time_seconds")
                    if isinstance(match, Mapping) and match.get(key) not in {None, ""}
                },
                "last_error": self._last_error or None,
                "stop_reason": self._stop_reason or None,
                "stop_cleanup": dict(self._stop_cleanup) if self._stop_cleanup else None,
                "supervisor_alive": bool(self._thread and self._thread.is_alive()),
            }

    def stop(self) -> dict[str, Any]:
        with self._condition:
            thread = self._thread
            if self._mode == "idle" and not (thread and thread.is_alive()):
                return self.status()
            cleanup_client = self._client
            cleanup_participant = self._participant_id
            cleanup_token = self._controller_token
            self._mode = "stopping"
            self._stop_reason = "stop_requested"
            self._stop_event.set()
            self._condition.notify_all()

        cleanup_ok = True
        with self._submission_lock:
            if cleanup_client is not None and cleanup_participant and cleanup_token:
                try:
                    cleanup_text = cleanup_client.stop_participant_intent(
                        cleanup_participant,
                        cleanup_token,
                        False,
                    )
                    cleanup = json.loads(cleanup_text) if isinstance(cleanup_text, str) else cleanup_text
                    if isinstance(cleanup, Mapping):
                        accepted = bool(cleanup.get("accepted", True))
                        cleared = bool(cleanup.get("cleared", accepted))
                        cleanup_ok = accepted and cleared
                        self._stop_cleanup = {
                            "accepted": accepted,
                            "cleared": cleared,
                            "ignored": bool(cleanup.get("ignored", False)),
                        }
                        if cleanup.get("reason"):
                            self._stop_cleanup["reason"] = str(cleanup["reason"])[:160]
                    else:
                        cleanup_ok = False
                        self._stop_cleanup = {
                            "accepted": False,
                            "cleared": False,
                            "reason": "invalid arena cleanup response",
                        }
                except Exception as exc:
                    cleanup_ok = False
                    self._stop_cleanup = {
                        "accepted": False,
                        "cleared": False,
                        "reason": _safe_error_text(exc, cleanup_token),
                    }
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        with self._condition:
            supervisor_alive = bool(thread and thread.is_alive())
            if not cleanup_ok:
                self._mode = "failed"
                self._stop_reason = "arena_cleanup_failed"
                self._last_error = str(self._stop_cleanup.get("reason") or "Arena cleanup failed")
            elif supervisor_alive:
                self._mode = "stopping"
                self._stop_reason = "waiting_for_supervisor"
            else:
                self._mode = "idle"
                self._stop_reason = "stopped"
            self._controller_token = None
            self._prepared_candidates = []
            self._prepared_decision = None
            self._handoff = {}
            self._condition.notify_all()
            return self.status()

    def close(self) -> None:
        self.stop()


__all__ = [
    "CONTROL_MODES",
    "ControllerError",
    "JevPlayerController",
    "MAX_RUN_MS",
]
