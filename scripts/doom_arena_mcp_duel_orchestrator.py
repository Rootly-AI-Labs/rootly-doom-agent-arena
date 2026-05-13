#!/usr/bin/env python3
"""Prepare and monitor an MCP-controlled Doom Arena duel."""

from __future__ import annotations

import argparse
import json
import secrets
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from doom_arena_mcp import DoomArenaClient, DoomArenaError, parse_state


REPO_ROOT = Path(__file__).resolve().parents[1]
RESULTS_ROOT = REPO_ROOT / "benchmarks" / "results"
CONTROLLER_TOKENS_PATH = REPO_ROOT / "src" / "arena_controller_tokens.local.json"
DEFAULT_SERVER_URL = "http://127.0.0.1:8001"
PARTICIPANTS = ("player_1", "player_2")
VALID_PARTICIPANT_INTENTS = ("hold", "engage_opponent", "strafe_attack", "search")
VALID_PARTICIPANT_INTENT_STYLES = ("balanced", "aggressive", "evasive", "cautious")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare and monitor an MCP-controlled Doom Arena duel.")
    parser.add_argument("--server-url", default=DEFAULT_SERVER_URL)
    parser.add_argument("--player-1-model", default="codex")
    parser.add_argument("--player-2-model", default="claude")
    parser.add_argument("--round", type=int, default=1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--decision-interval-ms", type=int, default=750)
    parser.add_argument(
        "--decision-cadence-ms",
        type=int,
        default=750,
        help="Suggested fast MCP tactical decision cadence for generated agent instructions.",
    )
    parser.add_argument(
        "--intent-duration-ms",
        type=int,
        default=2500,
        help="Suggested normal tactical intent duration for generated agent instructions.",
    )
    parser.add_argument("--max-in-flight-decisions", type=int, default=1)
    parser.add_argument("--fallback-intent", choices=VALID_PARTICIPANT_INTENTS, default="search")
    parser.add_argument("--fallback-style", choices=VALID_PARTICIPANT_INTENT_STYLES, default="balanced")
    parser.add_argument(
        "--rolling-control",
        action="store_true",
        help="Opt in to local scripted rolling tactical intents. Without this, only external MCP/LLM agents control the duel.",
    )
    parser.add_argument(
        "--monitor-only",
        action="store_true",
        help="Deprecated alias for the default behavior: reset/generate instructions/monitor only.",
    )
    parser.add_argument("--max-steps", type=int, default=100)
    parser.add_argument("--state-wait-timeout-seconds", type=int, default=45)
    parser.add_argument("--enforce-controller-tokens", action="store_true", default=True)
    parser.add_argument("--no-controller-tokens", action="store_true")
    return parser.parse_args()


class ResultWriter:
    def __init__(self, run_dir: Path):
        self.run_dir = run_dir
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.events_file = (self.run_dir / "events.jsonl").open("w", encoding="utf-8")
        self._lock = threading.Lock()

    def write_json(self, name: str, payload: dict[str, Any]) -> None:
        (self.run_dir / name).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def write_text(self, name: str, text: str) -> None:
        (self.run_dir / name).write_text(text, encoding="utf-8")

    def write_event(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self.events_file.write(json.dumps(payload, separators=(",", ":")) + "\n")
            self.events_file.flush()

    def close(self) -> None:
        with self._lock:
            self.events_file.close()


def load_json(text: str) -> dict[str, Any]:
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise RuntimeError("Expected JSON object")
    return parsed


def run_metadata_status(client: DoomArenaClient) -> dict[str, Any]:
    try:
        text = client._request("GET", "/api/arena/run-metadata")
        rows = parse_state(text)
        return {"reachable": True, "row": rows[0] if rows else {}, "raw": text[:1000]}
    except DoomArenaError as exc:
        return {"reachable": False, "error": str(exc)}


def state_status(client: DoomArenaClient, run_id: str) -> dict[str, Any]:
    try:
        state = load_json(client.get_arena_state(run_id))
        return {"available": True, "run_id": state.get("run_id", ""), "tick": state.get("tick", 0), "phase": state.get("phase", "")}
    except DoomArenaError as exc:
        error = str(exc)
        return {
            "available": False,
            "is_404": "HTTP 404" in error,
            "error": error,
        }


def wait_for_duel_state(client: DoomArenaClient, run_id: str, timeout_seconds: int) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_error = ""
    latest_metadata: dict[str, Any] = {}
    latest_state: dict[str, Any] = {}
    while time.time() < deadline:
        latest_metadata = run_metadata_status(client)
        try:
            state = load_json(client.get_arena_state(run_id))
            latest_state = {"available": True, "run_id": state.get("run_id", ""), "tick": state.get("tick", 0), "phase": state.get("phase", "")}
            if state.get("run_id") == run_id and state.get("player_1") and state.get("player_2"):
                return state
        except (DoomArenaError, RuntimeError, json.JSONDecodeError) as exc:
            last_error = str(exc)
            latest_state = state_status(client, run_id)
        time.sleep(0.25)
    raise RuntimeError(
        "Timed out waiting for MCP duel state.\n"
        f"  server_url: {client.server_url}\n"
        f"  expected run_id: {run_id}\n"
        f"  latest run metadata: {json.dumps(latest_metadata, indent=2)}\n"
        f"  latest state status: {json.dumps(latest_state, indent=2)}\n"
        "Open the Doom page in the browser, click Start Duel or let orchestrator reset duel, "
        "and keep the tab open so arena_game_state.local.tsv is exported.\n"
        f"  last_error: {last_error}"
    )


def build_controller_tokens(run_id: str, player_1_model: str, player_2_model: str, enforce: bool) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "player_1": {
            "model": player_1_model,
            "controller_token": secrets.token_urlsafe(24),
        },
        "player_2": {
            "model": player_2_model,
            "controller_token": secrets.token_urlsafe(24),
        },
        "enforce_controller_tokens": enforce,
    }


def write_controller_tokens(run_dir: Path, tokens: dict[str, Any]) -> None:
    text = json.dumps(tokens, indent=2) + "\n"
    (run_dir / "controller_tokens.json").write_text(text, encoding="utf-8")
    CONTROLLER_TOKENS_PATH.write_text(text, encoding="utf-8")


def now_ms() -> int:
    return int(time.time() * 1000)


def opponent_id(participant_id: str) -> str:
    return "player_2" if participant_id == "player_1" else "player_1"


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def choose_tactical_intent(participant_id: str, state: dict[str, Any], request_id: int) -> dict[str, Any]:
    player = state.get(participant_id, {})
    visible = bool(player.get("opponent_visible", False))
    distance = safe_int(player.get("opponent_distance"), 9999)
    aim_error = abs(safe_int(player.get("opponent_relative_angle"), 180))
    health = safe_int(player.get("health"), 100)
    ammo = safe_int(player.get("ammo"), 0)

    if state.get("phase") == "finished":
        return {
            "intent": "hold",
            "style": "cautious",
            "movement_bias": "cautious",
            "fire_policy": "hold_fire",
            "distance_policy": "maintain",
        }

    if health <= 35 or distance <= 320:
        return {
            "intent": "strafe_attack",
            "style": "evasive",
            "strafe_direction": "alternate",
            "movement_bias": "evasive",
            "fire_policy": "only_when_aligned" if ammo > 0 else "hold_fire",
            "distance_policy": "kite",
            "aggression": 0.55,
        }

    if visible and distance > 850:
        return {
            "intent": "engage_opponent",
            "style": "balanced",
            "strafe_direction": "auto",
            "movement_bias": "direct",
            "fire_policy": "suppressive" if aim_error <= 18 and ammo > 0 else "only_when_aligned",
            "distance_policy": "close",
            "aggression": 0.65,
        }

    if visible:
        return {
            "intent": "strafe_attack",
            "style": "aggressive",
            "strafe_direction": "alternate" if request_id % 2 == 0 else "auto",
            "movement_bias": "circle",
            "fire_policy": "suppressive" if aim_error <= 18 and ammo > 0 else "only_when_aligned",
            "distance_policy": "maintain",
            "aggression": 0.75,
        }

    return {
        "intent": "search",
        "style": "balanced",
        "strafe_direction": "auto",
        "movement_bias": "direct",
        "fire_policy": "hold_fire",
        "distance_policy": "maintain",
        "aggression": 0.4,
    }


class RollingTacticalController:
    """Non-blocking tactical intent scheduler.

    The decision provider can be backed by a real model wrapper later. For now the
    orchestrator uses a deterministic local provider and the smoke test injects
    artificial latency to validate rolling behavior.
    """

    def __init__(
        self,
        client: DoomArenaClient,
        controller_tokens: dict[str, Any],
        *,
        decision_cadence_ms: int,
        intent_duration_ms: int,
        max_in_flight_decisions: int,
        fallback_intent: str,
        fallback_style: str,
        event_sink: Callable[[dict[str, Any]], None] | None = None,
        decision_provider: Callable[[str, dict[str, Any], int], dict[str, Any]] = choose_tactical_intent,
    ):
        self.client = client
        self.controller_tokens = controller_tokens
        self.decision_cadence_ms = max(50, int(decision_cadence_ms))
        self.intent_duration_ms = max(100, int(intent_duration_ms))
        self.max_in_flight_decisions = max(1, int(max_in_flight_decisions))
        self.fallback_intent = fallback_intent
        self.fallback_style = fallback_style
        self.event_sink = event_sink
        self.decision_provider = decision_provider
        self._executor = ThreadPoolExecutor(max_workers=self.max_in_flight_decisions * len(PARTICIPANTS))
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._latest_state: dict[str, Any] = {}
        self._futures: dict[Future[dict[str, Any]], dict[str, Any]] = {}
        self._request_counter = 0
        self._sequence_numbers = {participant_id: 0 for participant_id in PARTICIPANTS}
        self._latest_started_request = {participant_id: 0 for participant_id in PARTICIPANTS}
        self._latest_applied_request = {participant_id: 0 for participant_id in PARTICIPANTS}
        self._last_request_started_at_ms = {participant_id: 0 for participant_id in PARTICIPANTS}
        self._active_until_ms = {participant_id: 0 for participant_id in PARTICIPANTS}
        self._last_intent_sent_at_ms = {participant_id: 0 for participant_id in PARTICIPANTS}
        self._decision_latencies_ms: list[int] = []
        self._intents_sent = 0
        self._stale_responses_discarded = 0
        self._fallbacks = 0
        self._coverage_started_at_ms = 0
        self._last_coverage_sample_ms = 0
        self._active_weighted_ms = 0.0
        self._waiting_weighted_ms = 0.0

    def start(self, initial_state: dict[str, Any]) -> None:
        with self._lock:
            self._latest_state = dict(initial_state)
            self._coverage_started_at_ms = now_ms()
            self._last_coverage_sample_ms = self._coverage_started_at_ms
        for participant_id in PARTICIPANTS:
            self._send_intent(
                participant_id,
                self._fallback_payload(participant_id),
                source="initial",
                request_id=0,
            )
        self._thread = threading.Thread(target=self._run, name="doom-arena-rolling-tactical-controller", daemon=True)
        self._thread.start()

    def update_state(self, state: dict[str, Any]) -> None:
        with self._lock:
            self._latest_state = dict(state)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
        self._executor.shutdown(wait=False, cancel_futures=True)

    def metrics(self) -> dict[str, Any]:
        with self._lock:
            self._sample_coverage_locked(now_ms())
            total_weighted_ms = self._active_weighted_ms + self._waiting_weighted_ms
            active_percent = 0.0 if total_weighted_ms <= 0 else (self._active_weighted_ms / total_weighted_ms) * 100.0
            waiting_percent = 0.0 if total_weighted_ms <= 0 else (self._waiting_weighted_ms / total_weighted_ms) * 100.0
            avg_latency = (
                sum(self._decision_latencies_ms) / len(self._decision_latencies_ms)
                if self._decision_latencies_ms
                else 0.0
            )
            return {
                "average_decision_latency_ms": round(avg_latency, 3),
                "max_decision_latency_ms": max(self._decision_latencies_ms) if self._decision_latencies_ms else 0,
                "number_of_intents_sent": self._intents_sent,
                "number_of_stale_responses_discarded": self._stale_responses_discarded,
                "number_of_fallbacks": self._fallbacks,
                "percent_time_with_active_intent": round(active_percent, 3),
                "percent_time_waiting_without_valid_intent": round(waiting_percent, 3),
                "active_sequence_number": dict(self._sequence_numbers),
            }

    def _run(self) -> None:
        while not self._stop.is_set():
            now = now_ms()
            with self._lock:
                self._sample_coverage_locked(now)
                phase = self._latest_state.get("phase", "")
            if phase == "finished":
                return
            self._handle_completed_futures()
            for participant_id in PARTICIPANTS:
                self._maybe_send_fallback(participant_id)
                self._maybe_start_decision(participant_id)
            time.sleep(0.025)

    def _sample_coverage_locked(self, current_ms: int) -> None:
        if self._last_coverage_sample_ms <= 0:
            self._last_coverage_sample_ms = current_ms
            return
        elapsed = max(0, current_ms - self._last_coverage_sample_ms)
        if elapsed <= 0:
            return
        active_count = sum(1 for participant_id in PARTICIPANTS if self._active_until_ms[participant_id] > current_ms)
        participant_count = max(1, len(PARTICIPANTS))
        self._active_weighted_ms += elapsed * (active_count / participant_count)
        self._waiting_weighted_ms += elapsed * ((participant_count - active_count) / participant_count)
        self._last_coverage_sample_ms = current_ms

    def _emit(self, event: dict[str, Any]) -> None:
        if self.event_sink is None:
            return
        payload = {"timestamp": utc_now(), "event": event.get("event", "rolling_control"), **event}
        self.event_sink(payload)

    def _token(self, participant_id: str) -> str | None:
        participant = self.controller_tokens.get(participant_id, {})
        token = participant.get("controller_token")
        return str(token) if token else None

    def _fallback_payload(self, participant_id: str) -> dict[str, Any]:
        return {
            "intent": self.fallback_intent,
            "style": self.fallback_style,
            "target_id": opponent_id(participant_id),
            "preferred_distance": 600,
            "aggression": 0.35 if self.fallback_intent == "search" else 0.2,
            "strafe_direction": "auto",
            "movement_bias": "direct" if self.fallback_intent == "search" else "cautious",
            "fire_policy": "hold_fire" if self.fallback_intent in {"search", "hold"} else "only_when_aligned",
            "distance_policy": "maintain",
            "replan_if": ["lost_los", "stuck"],
        }

    def _normalize_payload(self, participant_id: str, raw_payload: dict[str, Any]) -> dict[str, Any]:
        payload = self._fallback_payload(participant_id)
        payload.update({key: value for key, value in raw_payload.items() if value is not None})
        payload["target_id"] = opponent_id(participant_id)
        payload["duration_ms"] = self.intent_duration_ms
        payload["decision_cadence_ms"] = self.decision_cadence_ms
        return payload

    def _send_intent(
        self,
        participant_id: str,
        raw_payload: dict[str, Any],
        *,
        source: str,
        request_id: int,
    ) -> None:
        payload = self._normalize_payload(participant_id, raw_payload)
        with self._lock:
            self._sequence_numbers[participant_id] += 1
            sequence_number = self._sequence_numbers[participant_id]
        sent_at_ms = now_ms()
        self.client.set_participant_intent(
            participant_id,
            str(payload["intent"]),
            style=str(payload["style"]),
            target_id=str(payload["target_id"]),
            preferred_distance=safe_int(payload.get("preferred_distance"), 600),
            aggression=safe_float(payload.get("aggression"), 0.5),
            duration_ms=safe_int(payload.get("duration_ms"), self.intent_duration_ms),
            controller_token=self._token(participant_id),
            strafe_direction=str(payload.get("strafe_direction", "auto")),
            movement_bias=str(payload.get("movement_bias", "direct")),
            fire_policy=str(payload.get("fire_policy", "only_when_aligned")),
            distance_policy=str(payload.get("distance_policy", "maintain")),
            replan_if=payload.get("replan_if", []),
            sequence_number=sequence_number,
            decision_cadence_ms=self.decision_cadence_ms,
        )
        with self._lock:
            self._intents_sent += 1
            self._active_until_ms[participant_id] = sent_at_ms + self.intent_duration_ms
            self._last_intent_sent_at_ms[participant_id] = sent_at_ms
            if request_id:
                self._latest_applied_request[participant_id] = max(
                    self._latest_applied_request[participant_id],
                    request_id,
                )
        self._emit(
            {
                "event": "mcp_intent_sent",
                "participant_id": participant_id,
                "source": source,
                "request_id": request_id,
                "sequence_number": sequence_number,
                "intent": payload["intent"],
                "style": payload["style"],
                "duration_ms": self.intent_duration_ms,
                "decision_cadence_ms": self.decision_cadence_ms,
                "active_sequence_number": sequence_number,
            }
        )

    def _maybe_send_fallback(self, participant_id: str) -> None:
        current_ms = now_ms()
        with self._lock:
            active_until = self._active_until_ms[participant_id]
            has_pending = any(meta["participant_id"] == participant_id for meta in self._futures.values())
        if active_until > current_ms:
            return
        if not has_pending:
            return
        with self._lock:
            self._fallbacks += 1
        self._emit(
            {
                "event": "fallback_intent_sent",
                "participant_id": participant_id,
                "active_sequence_number": self._sequence_numbers.get(participant_id, 0),
            }
        )
        self._send_intent(
            participant_id,
            self._fallback_payload(participant_id),
            source="fallback",
            request_id=0,
        )

    def _maybe_start_decision(self, participant_id: str) -> None:
        current_ms = now_ms()
        with self._lock:
            in_flight = sum(1 for meta in self._futures.values() if meta["participant_id"] == participant_id)
            if in_flight >= self.max_in_flight_decisions:
                return
            last_started = self._last_request_started_at_ms[participant_id]
            if current_ms - last_started < self.decision_cadence_ms:
                return
            self._request_counter += 1
            request_id = self._request_counter
            self._latest_started_request[participant_id] = request_id
            self._last_request_started_at_ms[participant_id] = current_ms
            state_snapshot = dict(self._latest_state)
        future = self._executor.submit(self.decision_provider, participant_id, state_snapshot, request_id)
        with self._lock:
            self._futures[future] = {
                "participant_id": participant_id,
                "request_id": request_id,
                "started_at_ms": current_ms,
            }
        self._emit(
            {
                "event": "llm_request_started",
                "participant_id": participant_id,
                "request_id": request_id,
                "active_sequence_number": self._sequence_numbers.get(participant_id, 0),
            }
        )

    def _handle_completed_futures(self) -> None:
        with self._lock:
            completed = [(future, meta) for future, meta in self._futures.items() if future.done()]
            for future, _ in completed:
                self._futures.pop(future, None)
        for future, meta in completed:
            participant_id = str(meta["participant_id"])
            request_id = int(meta["request_id"])
            started_at_ms = int(meta["started_at_ms"])
            latency_ms = max(0, now_ms() - started_at_ms)
            try:
                payload = future.result()
            except Exception as exc:
                self._emit(
                    {
                        "event": "llm_response_received",
                        "participant_id": participant_id,
                        "request_id": request_id,
                        "decision_latency_ms": latency_ms,
                        "error": str(exc),
                    }
                )
                continue

            with self._lock:
                self._decision_latencies_ms.append(latency_ms)
                newest_started = self._latest_started_request[participant_id]
                latest_applied = self._latest_applied_request[participant_id]
                is_stale = (
                    request_id < latest_applied
                    or (self.max_in_flight_decisions > 1 and request_id < newest_started)
                )

            self._emit(
                {
                    "event": "llm_response_received",
                    "participant_id": participant_id,
                    "request_id": request_id,
                    "decision_latency_ms": latency_ms,
                    "stale": is_stale,
                }
            )

            if is_stale:
                with self._lock:
                    self._stale_responses_discarded += 1
                self._emit(
                    {
                        "event": "stale_llm_response_discarded",
                        "participant_id": participant_id,
                        "request_id": request_id,
                        "active_sequence_number": self._sequence_numbers.get(participant_id, 0),
                    }
                )
                continue

            self._send_intent(participant_id, payload, source="llm_response", request_id=request_id)


def instructions(
    participant_id: str,
    model: str,
    opponent_id: str,
    controller_token: str,
    enforce_tokens: bool,
    decision_cadence_ms: int = 750,
    intent_duration_ms: int = 2000,
) -> str:
    token_line = (
        f"Your controller_token is: `{controller_token}`\n\n"
        "Always include `controller_token` when calling `get_participant_observation`, "
        "`set_participant_intent`, and `stop_participant_intent`.\n"
        if enforce_tokens
        else "Controller token enforcement is disabled for this local trusted smoke run.\n"
    )
    return f"""# Doom Arena MCP Instructions: {participant_id}

You are one of two separate MCP agents in Doom Arena Duel.
You are `{model}`.
You control only `{participant_id}`.

{token_line}
Core rule:
- You do not control frame-level movement.
- You are sending short-lived tactical policies.
- Doom continues executing the latest valid policy until a newer one arrives or it expires.
- Choose one high-level tactical intent every 500-1000ms in fast tactical mode.
- Use MCP tool `set_participant_intent` for normal play.
- Do not use frame-level `forward`, `strafe`, `turn`, or `attack` controls.

Loop template:
1. Call MCP tool `get_participant_observation` with `participant_id="{participant_id}"` and your controller token.
2. Read the shared state and choose one high-level intent.
3. Increment `sequence_number`.
4. Call MCP tool `set_participant_intent` once for this decision with `participant_id="{participant_id}"`, your controller token, the incremented `sequence_number`, and one normalized intent.
5. Wait about {decision_cadence_ms}ms in fast tactical mode.
6. Repeat until `get_match_result` shows `phase="finished"`.

Allowed MCP tools:
- `get_participant_observation`
- `set_participant_intent`
- `stop_participant_intent`
- `get_match_result`
- `get_duel_events` if useful

Available intents:
- `engage_opponent`
- `strafe_attack`
- `hold`
- `search`

Available styles:
- `balanced`
- `aggressive`
- `evasive`
- `cautious`

Intent schema example:

```json
{{
  "participant_id": "{participant_id}",
  "controller_token": "{controller_token if enforce_tokens else '<disabled>'}",
  "intent": "strafe_attack",
  "style": "aggressive",
  "target_id": "{opponent_id}",
  "preferred_distance": 600,
  "aggression": 0.7,
  "duration_ms": {intent_duration_ms},
  "sequence_number": 1,
  "decision_cadence_ms": {decision_cadence_ms},
  "strafe_direction": "auto",
  "movement_bias": "circle",
  "fire_policy": "only_when_aligned",
  "distance_policy": "maintain",
  "replan_if": ["lost_los", "stuck", "low_health"]
}}
```

Fast tactical mode:
- Choose a new high-level tactical intent every 500-1000ms.
- Use `duration_ms` between 1500 and 2500 for normal combat.
- Default recommendation: `decision_cadence_ms={decision_cadence_ms}` and `duration_ms={intent_duration_ms}`.
- Include `sequence_number` and increment it on every decision.
- Newer intents with higher `sequence_number` override older intents immediately.

Stable mode:
- Choose every 1-3 seconds.
- Use `duration_ms` between 2500 and 7000.
- Use this when you need slower, more stable tactical planning.

Intent policy:

| Situation | Intent |
| --- | --- |
| Match `phase` is `finished` | Call `stop_participant_intent`, then stop the loop. |
| Opponent visible and aligned or close combat | `strafe_attack` with style `aggressive`. |
| Opponent visible and far away | `engage_opponent` with style `balanced`. |
| Opponent hidden or not visible | `search` with style `balanced`. |
| Very close or under pressure | `strafe_attack` with style `evasive`. |
| Winning on health near timeout | `hold` with style `cautious`, or `strafe_attack` with style `evasive`. |
| Unsure what to do | `engage_opponent` with style `balanced`. |

State fields to watch:
- `phase`
- `winner`
- `controller_mode`
- `intent`
- `intent_status`
- `autopilot_action`
- `autopilot_reason`
- `aim_error`
- `stuck_recovery`
- `replan_recommended`
- `replan_reasons`
- `sequence_number`
- `decision_cadence_ms`
- `health`
- `ammo`
- `opponent_distance` or distance if available
- `opponent_visible` or line of sight if available

Loop behavior:
- Observe state before every intent decision.
- Pick one high-level intent.
- Use `set_participant_intent`, not frame-level movement, for normal play.
- Wait about {decision_cadence_ms}ms between fast tactical decisions.
- Reassess and refresh the intent before it expires if the same plan still makes sense.
- Use `duration_ms={intent_duration_ms}` for fast tactical combat intents.
- Keep incrementing `sequence_number`; do not reuse an older number.
- Stop when `get_match_result` returns `phase="finished"`.
- During benchmark loops, avoid prose if tool-only behavior is expected.

Rules:
- Control only `{participant_id}`.
- Do not control `{opponent_id}`.
- Never call `set_participant_intent` for `{opponent_id}`.
- Use `get_participant_observation` before each high-level intent decision.
- Use `set_participant_intent` once per decision during normal play.
- If phase is finished, stop sending intents and controls.
- Do not call or request tools that directly mutate health, position, ammo, or winner.
- Both players receive the same full shared state for this MVP.
- Keep choosing high-level intents until the match is finished.

Deprecated frame-level control guidance:
- Do not call low-level participant input tools or follow old instructions that tell you to continuously choose `forward`, `strafe`, `turn`, or `attack`.
- The Doom-side autopilot converts your high-level intent into normal gameplay controls.
"""


def event_record(step: int, state: dict[str, Any], duel_events: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "timestamp": utc_now(),
        "step": step,
        "run_id": state.get("run_id", ""),
        "scenario_id": state.get("scenario_id", ""),
        "state_tick": state.get("tick", 0),
        "phase": state.get("phase", ""),
        "winner": state.get("winner", ""),
        "terminal_reason": state.get("terminal_reason", ""),
        "health": {
            "player_1": state.get("player_1", {}).get("health", 0),
            "player_2": state.get("player_2", {}).get("health", 0),
        },
        "actions": {
            "player_1": state.get("player_1", {}).get("last_action", ""),
            "player_2": state.get("player_2", {}).get("last_action", ""),
        },
        "duel_events": duel_events,
    }


def summary_from_state(
    state: dict[str, Any],
    config: dict[str, Any],
    steps: int,
    terminal_reason: str | None = None,
    rolling_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    player_1 = state.get("player_1", {})
    player_2 = state.get("player_2", {})
    summary = {
        "run_id": state.get("run_id", config.get("run_id", "")),
        "mode": "duel",
        "player_1_model": config["player_1_model"],
        "player_2_model": config["player_2_model"],
        "winner": state.get("winner", "") or ("running" if terminal_reason else ""),
        "terminal_reason": state.get("terminal_reason", "") or terminal_reason or "",
        "elapsed_time_seconds": state.get("elapsed_time_seconds", 0),
        "timeout_seconds": config["timeout_seconds"],
        "steps": steps,
        "player_1_health_end": player_1.get("health", 0),
        "player_2_health_end": player_2.get("health", 0),
        "player_1_damage_dealt": player_1.get("damage_dealt", 0),
        "player_2_damage_dealt": player_2.get("damage_dealt", 0),
        "player_1_shots_fired": player_1.get("shots_fired", 0),
        "player_2_shots_fired": player_2.get("shots_fired", 0),
        "player_1_shots_hit": player_1.get("shots_hit", 0),
        "player_2_shots_hit": player_2.get("shots_hit", 0),
        "player_1_invalid_actions": player_1.get("invalid_actions", 0),
        "player_2_invalid_actions": player_2.get("invalid_actions", 0),
    }
    if rolling_metrics is not None:
        summary["rolling_control"] = rolling_metrics
    return summary


def main() -> int:
    args = parse_args()
    enforce_tokens = bool(args.enforce_controller_tokens and not args.no_controller_tokens)
    rolling_control_enabled = bool(args.rolling_control and not args.monitor_only)
    client = DoomArenaClient(args.server_url)
    reset = load_json(
        client.reset_duel(
            args.player_1_model,
            args.player_2_model,
            args.round,
            args.seed,
            args.timeout_seconds,
        )
    )
    run_id = str(reset["run_id"])
    run_dir = RESULTS_ROOT / run_id
    writer = ResultWriter(run_dir)
    controller_tokens = build_controller_tokens(run_id, args.player_1_model, args.player_2_model, enforce_tokens)
    write_controller_tokens(run_dir, controller_tokens)
    config = {
        "runner": "doom_arena_mcp_duel_orchestrator",
        "server_url": args.server_url,
        "run_id": run_id,
        "scenario_id": reset.get("scenario_id", ""),
        "arena_mode": "duel",
        "player_1_model": args.player_1_model,
        "player_2_model": args.player_2_model,
        "round": args.round,
        "seed": args.seed,
        "timeout_seconds": args.timeout_seconds,
        "decision_interval_ms": args.decision_interval_ms,
        "decision_cadence_ms": args.decision_cadence_ms,
        "intent_duration_ms": args.intent_duration_ms,
        "max_in_flight_decisions": args.max_in_flight_decisions,
        "fallback_intent": args.fallback_intent,
        "fallback_style": args.fallback_style,
        "rolling_control_enabled": rolling_control_enabled,
        "max_steps": args.max_steps,
        "state_mode": "shared_full",
        "control_path": (
            "rolling orchestrator tactical intents"
            if rolling_control_enabled
            else "external MCP clients call doom_arena_mcp.py tools"
        ),
        "enforce_controller_tokens": enforce_tokens,
        "controller_tokens_file": str(CONTROLLER_TOKENS_PATH),
    }
    writer.write_json("config.json", config)
    writer.write_text(
        "player_1_mcp_instructions.md",
        instructions(
            "player_1",
            args.player_1_model,
            "player_2",
            controller_tokens["player_1"]["controller_token"],
            enforce_tokens,
            args.decision_cadence_ms,
            args.intent_duration_ms,
        ),
    )
    writer.write_text(
        "player_2_mcp_instructions.md",
        instructions(
            "player_2",
            args.player_2_model,
            "player_1",
            controller_tokens["player_2"]["controller_token"],
            enforce_tokens,
            args.decision_cadence_ms,
            args.intent_duration_ms,
        ),
    )
    print(
        json.dumps(
            {
                "run_id": run_id,
                "results_dir": str(run_dir),
                "player_1_instructions": str(run_dir / "player_1_mcp_instructions.md"),
                "player_2_instructions": str(run_dir / "player_2_mcp_instructions.md"),
                "controller_tokens": str(run_dir / "controller_tokens.json"),
            },
            indent=2,
        ),
        flush=True,
    )

    state: dict[str, Any] = {"run_id": run_id}
    steps = 0
    rolling_controller: RollingTacticalController | None = None
    try:
        state = wait_for_duel_state(client, run_id, args.state_wait_timeout_seconds)
        if rolling_control_enabled:
            rolling_controller = RollingTacticalController(
                client,
                controller_tokens,
                decision_cadence_ms=args.decision_cadence_ms,
                intent_duration_ms=args.intent_duration_ms,
                max_in_flight_decisions=args.max_in_flight_decisions,
                fallback_intent=args.fallback_intent,
                fallback_style=args.fallback_style,
                event_sink=writer.write_event,
            )
            rolling_controller.start(state)
        max_steps = max(1, args.max_steps)
        while steps < max_steps:
            if rolling_controller is not None:
                rolling_controller.update_state(state)
            steps += 1
            events = load_json(client.get_duel_events(run_id, 25)).get("events", [])
            writer.write_event(event_record(steps, state, events))
            if state.get("phase") == "finished":
                break
            time.sleep(max(0.05, args.decision_interval_ms / 1000.0))
            state = wait_for_duel_state(client, run_id, args.state_wait_timeout_seconds)
        terminal = None if state.get("phase") == "finished" else "max_steps"
        rolling_metrics = rolling_controller.metrics() if rolling_controller is not None else None
        writer.write_json("summary.json", summary_from_state(state, config, steps, terminal, rolling_metrics))
    except Exception as exc:
        rolling_metrics = rolling_controller.metrics() if rolling_controller is not None else None
        writer.write_event(
            {
                "timestamp": utc_now(),
                "step": steps,
                "run_id": run_id,
                "phase": "error",
                "error": str(exc),
            }
        )
        writer.write_json("summary.json", summary_from_state(state, config, steps, "orchestrator_error", rolling_metrics))
        if rolling_controller is not None:
            rolling_controller.stop()
        writer.close()
        raise

    if rolling_controller is not None:
        rolling_controller.stop()
    writer.close()
    rolling_metrics = rolling_controller.metrics() if rolling_controller is not None else None
    print(json.dumps({"run_id": run_id, "results_dir": str(run_dir), "summary": summary_from_state(state, config, steps, terminal, rolling_metrics)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
