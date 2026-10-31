"""Reproduce the pinned all-medium, six-series Claude sweep from arena artifacts.

Run from any directory: python claude_sweep/analysis/analyze_claude.py
Only metrics.json beside this script is written. No APIs or extra packages are
used. Unknown plan failures and ambiguous pinned archives fail for review.
All rates are fractions; all exported decision samples are in seconds.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODELS = {
    "opus": ("Claude Opus 5.5", "claude-opus-5-5"),
    "fable": ("Claude Fable 5.1", "claude-fable-5-1"),
    "sonnet": ("Claude Sonnet 5.5", "claude-sonnet-5-5"),
}
SERIES = [
    ("med_reruns/opus v sonnet/med_opus v sonnet/session_8fdec3c440b4", "opus", "sonnet"),
    ("med_reruns/opus v sonnet/med_sonnet v opus/session_5188b2ed236f", "sonnet", "opus"),
    ("med_reruns/opus v fable/med_opus v fable/session_572d2d193f0a", "opus", "fable"),
    ("med_reruns/opus v fable/med_fable v opus/session_acd0e0242118", "fable", "opus"),
    ("med_reruns/sonnet v fable/med_sonnet v fable/session_60e8ac8a1dda", "sonnet", "fable"),
    ("med_reruns/sonnet v fable/med_fable v sonnet/session_da8fd5b5d730", "fable", "sonnet"),
]
COHORT = "all_medium_60_round_sweep"
EXCLUDED_SESSIONS = [
    {"session_id": sid, "reason": "Excluded original Fable-high series; raw archives removed after medium replacement."}
    for sid in ("session_d553d09a35fc", "session_12edeaaa9be8", "session_234aaaa29bc0", "session_0126b7e77ed7")
] + [{"session_id": "session_fcc7bb2f60a8", "reason": "Additional 5-5 Sonnet-versus-Fable series, outside the pinned six-series cohort; not counted twice."}]
ROUTE_ERRORS = ("diagonal", "blocked", "waypoint_limit", "stationary")
OPERATIONAL_ERRORS = ("post_finish", "run_mismatch")
OUTCOMES = ("accepted", *ROUTE_ERRORS, *OPERATIONAL_ERRORS)
PARTICIPANTS = ("player_1", "player_2")
CONFIG_FIELDS = (
    "runner", "total_rounds", "scenario_id", "arena_mode", "seed",
    "timeout_seconds", "decision_cadence_ms", "intent_duration_ms",
    "control_path", "control_mode", "hide_enemy_position",
    "enable_weapon_pickups", "randomize_spawns", "scenario_pool",
    "enforce_controller_tokens",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def utc(milliseconds: int) -> str:
    return datetime.fromtimestamp(milliseconds / 1000, timezone.utc).isoformat()


def ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def percentile(values: list[float], quantile: float) -> float | None:
    """Linearly interpolate ordered samples at index (n - 1) * quantile."""
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * quantile
    lower = math.floor(index)
    upper = math.ceil(index)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def classify_plan(call: dict) -> str:
    """Route validation returns accepted:false even when is_error is false."""
    error = str(call.get("error", "")).lower()
    if call.get("accepted") is True and not call.get("is_error"):
        return "accepted"
    if "already finished" in error:
        return "post_finish"
    if "controller token file" in error and "run_id" in error:
        return "run_mismatch"
    if call.get("accepted") is False:
        if "diagonal" in error:
            return "diagonal"
        if "blocked cell" in error or "blocked wall cell" in error:
            return "blocked"
        if "at most 8 waypoints" in error:
            return "waypoint_limit"
        if "does not move" in error:
            return "stationary"
    raise ValueError(
        f"Manual review required: unclassified plan outcome {call.get('call_id')}: "
        f"accepted={call.get('accepted')}, is_error={call.get('is_error')}, error={error}"
    )


def score() -> dict:
    return dict(matches=0, wins=0, losses=0, draws=0)


def add_score(target: dict, won: bool, drawn: bool = False) -> None:
    target["matches"] += 1
    target["wins"] += int(won)
    target["draws"] += int(drawn)
    target["losses"] += int(not won and not drawn)


def finish_score(target: dict) -> None:
    target["win_rate"] = ratio(target["wins"], target["matches"])


def empty_model(key: str) -> dict:
    label, model_id = MODELS[key]
    return {
        "label": label, "model_id": model_id, "effort": "medium", **score(),
        "shots": 0, "hits": 0, "damage": 0, "damage_taken": 0,
        "side_counts": {pid: score() for pid in PARTICIPANTS},
        "mcp_calls": 0, "mcp_flagged_errors": 0,
        "plan_calls": 0, "plan_outcomes": {outcome: 0 for outcome in OUTCOMES},
        "decision_seconds": [],
        "decision_outcome_counts": {outcome: 0 for outcome in OUTCOMES},
        "plan_calls_without_decision_interval": 0,
    }


def analyze() -> dict:
    # Historical and additional sessions coexist with the selected six-series
    # cohort. Reject missing, relocated, or duplicated copies of pinned IDs.
    expected_sessions = {Path(path).name: path for path, _, _ in SERIES}
    actual_sessions = defaultdict(list)
    for path in ROOT.rglob("session_*"):
        if path.is_dir() and path.name in expected_sessions:
            actual_sessions[path.name].append(relative(path))
    for session_id, expected_path in expected_sessions.items():
        require(actual_sessions[session_id] == [expected_path],
                f"Expected one pinned archive at {expected_path}; found {actual_sessions[session_id]}")
    models = {key: empty_model(key) for key in MODELS}
    head = {key: {other: score() for other in MODELS if other != key} for key in MODELS}
    manifest = []
    config_counts = {field: Counter() for field in CONFIG_FIELDS}
    config_missing = []
    prompt_missing = []
    series_records = []
    round_records = []
    run_ids = set()
    overall_tools = Counter()
    sources = Counter()
    audit_mismatches = []
    lifecycle_differences = []
    latency_mismatches = []
    call_run_mismatches = []
    summary_totals = Counter()
    unassigned_calls = Counter()
    prompt_hashes = {pid: [] for pid in PARTICIPANTS}
    game_instruction_hashes = {pid: Counter() for pid in PARTICIPANTS}
    filtered_turns = Counter()
    token_usage_coverage = 0
    raw_model_labels_empty = 0
    decision_details = {key: [] for key in MODELS}
    non_plan_errors = defaultdict(Counter)
    effort_records = []

    def record_file(path: Path, kind: str) -> dict:
        entry = {"path": relative(path), "kind": kind, "exists": path.is_file()}
        if entry["exists"]:
            content = path.read_bytes()
            entry.update(sha256=hashlib.sha256(content).hexdigest(), bytes=len(content))
        manifest.append(entry)
        return entry

    def audit(path: Path, metric: str, reported: int | float, observed: int | float) -> None:
        if not math.isclose(reported, observed, rel_tol=0, abs_tol=0.001):
            audit_mismatches.append({"path": relative(path), "metric": metric,
                                     "reported": reported, "from_calls": observed})

    for setup, (folder, p1_model, p2_model) in enumerate(SERIES, 1):
        session = ROOT / folder
        assignment = dict(zip(PARTICIPANTS, (p1_model, p2_model)))
        effort_path = session.parent / "effort_verification.json"
        effort = read_json(effort_path)
        record_file(effort_path, "effort_verification")
        require(effort.get("session_id") == session.name and effort.get("rounds") == 10,
                f"Effort verification session mismatch in {effort_path}")
        for pid, key in assignment.items():
            evidence = effort[pid]
            require(evidence.get("model") == MODELS[key][1] and evidence.get("effort") == "medium",
                    f"Non-medium or wrong-model effort evidence for {session.name}/{pid}")
            require(bool(re.fullmatch(r"[0-9a-f]{64}", evidence.get("source_sha256", ""))),
                    f"Missing source-log hash for {session.name}/{pid}")
            require(evidence.get("api_requests", 0) > 0 and evidence.get("unique_api_responses", 0) > 0,
                    f"Missing API metadata coverage for {session.name}/{pid}")
        effort_records.append({"session_id": session.name, "path": relative(effort_path),
                               "basis": effort["basis"], "verified_at_utc": effort["verified_at_utc"],
                               **{pid: effort[pid] for pid in PARTICIPANTS}})
        paths = sorted(session.glob("round_*/summary.json"))
        require(len(paths) == 10, f"Expected 10 summaries in {folder}")
        round_numbers = []
        series_score = Counter()
        series_start = []
        series_end = []
        series_configs = 0

        for summary_path in paths:
            directory = summary_path.parent
            stats_path = directory / "stats.json"
            config_path = directory / "config.json"
            summary = read_json(summary_path)
            stats = read_json(stats_path)
            run_id = summary["run_id"]
            require(run_id not in run_ids, f"Duplicate run ID {run_id}")
            run_ids.add(run_id)
            require(stats["run_id"] == run_id, f"Stats run mismatch {directory}")
            require(summary["winner"] in PARTICIPANTS, f"Unfinished/drawn round {run_id}")
            require(summary["terminal_reason"] in ("player_1_dead", "player_2_dead"),
                    f"Non-elimination ending in {run_id}")
            expected_dead = "player_2_dead" if summary["winner"] == "player_1" else "player_1_dead"
            require(summary["terminal_reason"] == expected_dead, f"Winner mismatch {run_id}")
            round_numbers.append(summary["round"])
            series_score[summary["winner"]] += 1
            series_start.append(stats["started_at_ms"])
            series_end.append(stats["generated_at_ms"])
            for path, kind in ((summary_path, "summary"), (stats_path, "stats"), (config_path, "config")):
                record_file(path, kind)
            if config_path.is_file():
                config = read_json(config_path)
                require(config["run_id"] == run_id, f"Config run mismatch {run_id}")
                require(config["duel_session_id"] == session.name, f"Config session mismatch {run_id}")
                require(config["round"] == summary["round"], f"Config round mismatch {run_id}")
                for field in CONFIG_FIELDS:
                    config_counts[field][json.dumps(config.get(field), sort_keys=True)] += 1
                series_configs += 1
            else:
                config_missing.append(relative(config_path))
            for pid in PARTICIPANTS:
                prompt_entry = record_file(directory / f"{pid}_mcp_instructions.md", "prompt")
                if prompt_entry["exists"]:
                    prompt_hashes[pid].append(prompt_entry["sha256"])
                    text = (directory / f"{pid}_mcp_instructions.md").read_text(encoding="utf-8-sig")
                    require("BENCHMARK ISOLATION" in text, f"Unrecognized prompt body in {prompt_entry['path']}")
                    body = text[text.index("BENCHMARK ISOLATION"):]
                    body = re.sub(r'(controller_token["`\s]*[:=][\s"`]*)([^"`,}\s]+)',
                                  r'\1<CONTROLLER_TOKEN>', body)
                    game_instruction_hashes[pid][hashlib.sha256(body.encode("utf-8")).hexdigest()] += 1
                else:
                    prompt_missing.append(prompt_entry["path"])

            record = {
                "setup": setup, "session_id": session.name, "run_id": run_id,
                "round": summary["round"], "path": relative(directory),
                "player_1": p1_model, "player_2": p2_model,
                "winner": assignment[summary["winner"]], "winner_participant": summary["winner"],
                "terminal_reason": summary["terminal_reason"],
                "elapsed_time_seconds": summary["elapsed_time_seconds"],
                "seed": summary["seed"], "timeout_seconds": summary["timeout_seconds"],
                "started_at_ms": stats["started_at_ms"], "started_at_utc": utc(stats["started_at_ms"]),
                "stats_generated_at_ms": stats["generated_at_ms"],
                "stats_generated_at_utc": utc(stats["generated_at_ms"]),
                "players": {},
            }
            for number, pid in enumerate(PARTICIPANTS, 1):
                key = assignment[pid]
                opponent = assignment[PARTICIPANTS[2 - number]]
                identity = summary[f"coding_assistant_{number}"]
                require(identity.endswith(", Claude Code, " + MODELS[key][1]),
                        f"Unexpected identity for {pid} in {run_id}: {identity}")
                if effort[pid].get("alias"):
                    require(identity.startswith(effort[pid]["alias"] + ", "),
                            f"Effort evidence alias mismatch for {run_id}/{pid}")
                if not summary.get(f"{pid}_model"):
                    raw_model_labels_empty += 1
                t = models[key]
                won = summary["winner"] == pid
                for target in (t, t["side_counts"][pid], head[key][opponent]):
                    add_score(target, won)
                t["shots"] += summary[f"{pid}_shots_fired"]
                t["hits"] += summary[f"{pid}_shots_hit"]
                t["damage"] += summary[f"{pid}_damage_dealt"]
                t["damage_taken"] += summary[f"{PARTICIPANTS[2 - number]}_damage_dealt"]
                record["players"][pid] = {
                    "model": key, "identity": identity, "won": won,
                    "shots": summary[f"{pid}_shots_fired"], "hits": summary[f"{pid}_shots_hit"],
                    "damage": summary[f"{pid}_damage_dealt"],
                    "damage_taken": summary[f"{PARTICIPANTS[2 - number]}_damage_dealt"],
                    "health_end": summary[f"{pid}_health_end"],
                    "plan_calls": 0, "plan_outcomes": {o: 0 for o in OUTCOMES},
                    "decision_seconds": [],
                }

            calls = stats["calls"]
            call_ids = [call["call_id"] for call in calls]
            require(len(call_ids) == len(set(call_ids)), f"Duplicate call IDs within {run_id}")
            by_id = {call["call_id"]: call for call in calls}
            require(not stats.get("active_calls"), f"Unfinished telemetry calls in {run_id}")
            reported = stats["summary"]
            checks = {
                "total_mcp_calls": len(calls),
                "completed_mcp_calls": sum(c.get("status") == "completed" for c in calls),
                "errored_mcp_calls": sum(bool(c.get("is_error")) for c in calls),
                "in_flight_mcp_calls": 0,
            }
            for metric, value in checks.items():
                audit(stats_path, "summary." + metric, reported[metric], value)
                summary_totals[metric] += reported[metric]
            summary_totals["intents_sent"] += reported["intents_sent"]
            summary_totals["intent_lifecycles"] += len(stats["intent_lifecycles"])
            summary_totals["rationales_logged"] += reported["rationales_logged"]
            token_usage_coverage += bool(stats.get("token_usage_by_participant"))
            for group_name, discriminator in (("by_tool", "tool_name"), ("by_participant", "participant_id")):
                for group, values in stats[group_name].items():
                    members = [c for c in calls if c.get(discriminator) == group]
                    audit(stats_path, f"{group_name}.{group}.count", values["count"], len(members))
                    audit(stats_path, f"{group_name}.{group}.errors", values["errors"],
                          sum(bool(c.get("is_error")) for c in members))

            accepted_calls = 0
            for call in calls:
                tool = call["tool_name"]
                pid = call.get("participant_id")
                overall_tools[tool] += 1
                sources[call.get("source", "unavailable")] += 1
                if call.get("run_id") != run_id:
                    call_run_mismatches.append({"run_id": run_id, "call_id": call["call_id"],
                                                "call_run_id": call.get("run_id")})
                if all(call.get(k) is not None for k in ("started_at_ms", "completed_at_ms", "latency_ms")):
                    measured = call["completed_at_ms"] - call["started_at_ms"]
                    if not math.isclose(measured, call["latency_ms"], abs_tol=0.001):
                        latency_mismatches.append({"run_id": run_id, "call_id": call["call_id"],
                                                   "latency_ms": call["latency_ms"], "timestamp_delta_ms": measured})
                if pid in assignment:
                    models[assignment[pid]]["mcp_calls"] += 1
                    models[assignment[pid]]["mcp_flagged_errors"] += bool(call.get("is_error"))
                else:
                    unassigned_calls[tool] += 1
                if tool != "set_participant_plan":
                    if call.get("is_error") or call.get("accepted") is False:
                        non_plan_errors[tool][classify_plan(call)] += 1
                    continue
                require(pid in assignment, f"Plan without participant in {run_id}/{call['call_id']}")
                outcome = classify_plan(call)
                accepted_calls += outcome == "accepted"
                for target in (models[assignment[pid]], record["players"][pid]):
                    target["plan_calls"] += 1
                    target["plan_outcomes"][outcome] += 1
            if accepted_calls != reported["intents_sent"]:
                lifecycle_differences.append({
                    "run_id": run_id, "path": relative(stats_path),
                    "accepted_plan_calls": accepted_calls,
                    "reported_intents_sent": reported["intents_sent"],
                    "intent_lifecycles": len(stats["intent_lifecycles"]),
                })

            timed_plan_ids = set()
            observation_uses = Counter()
            raw_latencies = []
            for turn in stats["inferred_decision_turns"]:
                pid = turn.get("participant_id")
                value = turn.get("inferred_decision_latency_ms")
                call = by_id.get(turn.get("intent_call_id"))
                if value is not None:
                    raw_latencies.append(value)
                if pid not in assignment or value is None or not call or call.get("tool_name") != "set_participant_plan":
                    filtered_turns["excluded"] += 1
                    continue
                require(call.get("participant_id") == pid, f"Decision participant mismatch {run_id}")
                observation = by_id.get(turn.get("observation_call_id"))
                require(observation is not None and observation.get("tool_name") == "get_participant_observation",
                        f"Decision missing observation {run_id}/{turn.get('intent_call_id')}")
                require(value >= 0 and math.isfinite(value), f"Invalid decision latency in {run_id}")
                require(value == turn["intent_started_at_ms"] - turn["observation_completed_at_ms"],
                        f"Decision timestamp delta mismatch {run_id}")
                require(turn["intent_call_id"] not in timed_plan_ids, f"Duplicated decision turn {run_id}")
                timed_plan_ids.add(turn["intent_call_id"])
                observation_uses[(pid, turn["observation_call_id"])] += 1
                filtered_turns["included"] += 1
                seconds = value / 1000
                models[assignment[pid]]["decision_seconds"].append(seconds)
                models[assignment[pid]]["decision_outcome_counts"][classify_plan(call)] += 1
                record["players"][pid]["decision_seconds"].append(seconds)
                previous_accepted = any(
                    c["tool_name"] == "set_participant_plan"
                    and c.get("participant_id") == pid
                    and c.get("accepted") is True and not c.get("is_error")
                    and c["completed_at_ms"] <= call["started_at_ms"]
                    for c in calls
                )
                decision_details[assignment[pid]].append({
                    "run_id": run_id, "path": relative(stats_path), "participant_id": pid,
                    "observation_call_id": turn["observation_call_id"], "intent_call_id": turn["intent_call_id"],
                    "seconds": seconds, "plan_outcome": classify_plan(call),
                    "sequence_number": call.get("sequence_number"),
                    "before_first_accepted_plan_completion": not previous_accepted,
                })
            filtered_turns["additional_intervals_reusing_observation"] += sum(v - 1 for v in observation_uses.values())
            if raw_latencies:
                audit(stats_path, "summary.average_inferred_chat_decision_latency_ms",
                      reported["average_inferred_chat_decision_latency_ms"], statistics.mean(raw_latencies))
            for call in calls:
                if call["tool_name"] == "set_participant_plan" and call["call_id"] not in timed_plan_ids:
                    models[assignment[call["participant_id"]]]["plan_calls_without_decision_interval"] += 1
            round_records.append(record)

        require(sorted(round_numbers) == list(range(1, 11)), f"Round sequence mismatch in {folder}")
        series_records.append({
            "setup": setup, "session_id": session.name, "path": folder,
            "player_1": p1_model, "player_2": p2_model, "matches": len(paths),
            "effort": "medium", "effort_verification": relative(effort_path),
            "p1_wins": series_score["player_1"], "p2_wins": series_score["player_2"], "draws": 0,
            "available_configs": series_configs,
            "started_at_utc": utc(min(series_start)), "last_stats_generated_at_utc": utc(max(series_end)),
        })

    require(len(run_ids) == 60, "Expected exactly 60 unique completed matches")
    for key, t in models.items():
        require(t["matches"] == 40, f"Expected 40 appearances for {key}")
        require(t["hits"] <= t["shots"], f"Invalid shot totals for {key}")
        finish_score(t)
        for side in t["side_counts"].values():
            require(side["matches"] == 20, f"Expected 20 appearances on each side for {key}")
            finish_score(side)
        for h in head[key].values():
            require(h["matches"] == 20, f"Expected 20 appearances per matchup for {key}")
            finish_score(h)
        t["accuracy"] = ratio(t["hits"], t["shots"])
        t["damage_differential_per_match"] = (t["damage"] - t["damage_taken"]) / t["matches"]
        samples = t["decision_seconds"]
        t["decision_count"] = len(samples)
        t["mean_decision_seconds"] = statistics.mean(samples) if samples else None
        t["median_decision_seconds"] = statistics.median(samples) if samples else None
        t["p95_decision_seconds"] = percentile(samples, 0.95)
        t["route_rejections"] = sum(t["plan_outcomes"][outcome] for outcome in ROUTE_ERRORS)
        t["route_validation_attempts"] = t["plan_outcomes"]["accepted"] + t["route_rejections"]
        t["route_rejection_rate"] = ratio(t["route_rejections"], t["route_validation_attempts"])
        t["operational_plan_errors"] = sum(t["plan_outcomes"][outcome] for outcome in OPERATIONAL_ERRORS)
        t["rejected_plans"] = t["route_rejections"] + t["operational_plan_errors"]
        t["all_plan_error_rate"] = ratio(t["rejected_plans"], t["plan_calls"])
        t["mcp_flagged_error_rate"] = ratio(t["mcp_flagged_errors"], t["mcp_calls"])
        require(sum(t["plan_outcomes"].values()) == t["plan_calls"], f"Plan outcomes fail reconciliation for {key}")
    require(sum(t["wins"] for t in models.values()) == 60, "Wins do not reconcile")
    require(sum(t["losses"] for t in models.values()) == 60, "Losses do not reconcile")
    require(sum(t["damage"] for t in models.values()) == sum(t["damage_taken"] for t in models.values()),
            "Damage does not reconcile")

    return {
        "schema_version": 1, "cohort": COHORT, "effort": "medium",
        "matches": len(run_ids), "sessions": len(series_records),
        "pinned_session_ids": [Path(path).name for path, _, _ in SERIES],
        "excluded_sessions": EXCLUDED_SESSIONS, "effort_verification": effort_records,
        "model_order": list(MODELS), "models": models, "head_to_head": head,
        "series": series_records, "per_round": round_records,
        "validation": {
            "unique_run_ids": len(run_ids), "duplicate_run_ids": 0,
            "completed_rounds": len(round_records), "eliminations": len(round_records), "draws": 0,
            "rounds_per_session": 10, "appearances_per_model": 40, "appearances_per_model_per_side": 20,
            "summaries": len(round_records), "stats_files": len(round_records),
            "config_files": len(round_records) - len(config_missing),
            "prompt_files": sum(len(hashes) for hashes in prompt_hashes.values()),
            "mcp_calls": sum(overall_tools.values()), "plan_calls": sum(t["plan_calls"] for t in models.values()),
            "accepted_plan_calls": sum(t["plan_outcomes"]["accepted"] for t in models.values()),
            "route_rejections": sum(t["route_rejections"] for t in models.values()),
            "operational_plan_errors": sum(t["operational_plan_errors"] for t in models.values()),
            "unclassified_plan_outcomes": 0, "decision_intervals": filtered_turns["included"],
            "archive_membership_verified": True, "participant_identities_verified": True,
            "effort_verification_files": len(effort_records), "effort_verified_participants": 2 * len(effort_records),
            "all_participants_medium_verified": True,
        },
        "methodology": {
            "scope": "Only the six explicitly pinned all-medium sessions: retained twenty Opus/Sonnet rounds plus forty selected medium Fable reruns. Original Fable-high series, additional session_fcc7bb2f60a8, and partial/restarted sessions are excluded.",
            "effort": "All twelve participant model/effort identities are checked against archived verification sidecars citing actual Claude API request/response metadata and source-log hashes. This public analyzer validates the sidecar evidence; the separate cost audit reopens the private logs.",
            "identity": "Exact Claude model IDs and Claude Code harness parsed from summary.coding_assistant_1/2, not blank player_N_model fields.",
            "accuracy": "Pooled shots hit / pooled shots fired; not an average of per-round percentages.",
            "damage_differential": "(Total damage dealt - opponent damage dealt) / appearances.",
            "decision_time": "Pooled inferred_decision_turns whose intent_call_id resolves to set_participant_plan: observation completion to plan call start, seconds. Includes retries, rejected plans, orchestration, and post-finish attempts; not pure model inference latency or time to a valid plan.",
            "p95": "Linear interpolation between sorted samples at index (n - 1) * 0.95 (Hyndman-Fan type 7).",
            "route_rejection_rate": "Invalid routes / (accepted plans + invalid routes). Every recorded attempted call including retries is counted. Post-finish and run mismatch failures are excluded from both numerator and denominator.",
            "failure_classification": "accepted:false is a rejection even if is_error:false. Unknown failures stop analysis for manual review.",
            "mcp_flagged_errors": "Calls with is_error:true, including operational tool failures. This excludes accepted:false route validation responses and is not a route-rejection metric. Participant counts exclude get_match_result calls with no participant_id.",
            "timestamps": "Stats started_at_ms is run initialization, not necessarily combat start. generated_at_ms is the last telemetry snapshot, not necessarily combat end. Exported ISO timestamps are UTC.",
            "prompt_hashes": "Raw prompt file SHA256 hashes. Prompts contain dynamic controller tokens, participant assignments, aliases, and round context, so different hashes alone do not demonstrate different instruction templates. Raw prompt contents/tokens are not copied into this analysis.",
            "normalized_game_instruction_hashes": "Separately hash each saved prompt from BENCHMARK ISOLATION to EOF after replacing controller_token argument values with a fixed placeholder. This checks the game-instruction body, not the preceding identity/alias/round header. No source prompt is modified.",
            "costs": "No token or cost estimates are produced by this script.",
        },
        "configuration": {
            "available": len(round_records) - len(config_missing), "missing": config_missing,
            "fields": {field: [{"value": json.loads(value), "rounds": count} for value, count in values.items()]
                       for field, values in config_counts.items()},
            "summary_seeds": dict(Counter(str(r["seed"]) for r in round_records)),
            "summary_timeouts_seconds": dict(Counter(str(r["timeout_seconds"]) for r in round_records)),
            "first_run_initialized_at_utc": min(r["started_at_utc"] for r in round_records),
            "last_stats_generated_at_utc": max(r["stats_generated_at_utc"] for r in round_records),
            "run_initialization_dates_utc": dict(Counter(r["started_at_utc"][:10] for r in round_records)),
            "unique_raw_prompt_hashes": {pid: len(set(hashes)) for pid, hashes in prompt_hashes.items()},
            "normalized_game_instruction_bodies": {
                pid: [{"sha256": digest, "files": count} for digest, count in counts.items()]
                for pid, counts in game_instruction_hashes.items()
            },
            "missing_prompts": prompt_missing,
        },
        "telemetry_audit": {
            "summary_totals": dict(summary_totals), "tools": dict(overall_tools), "sources": dict(sources),
            "aggregate_reconciliation_mismatches": audit_mismatches,
            "accepted_plan_vs_lifecycle_differences": lifecycle_differences,
            "call_latency_timestamp_mismatches": latency_mismatches,
            "call_run_id_mismatches": call_run_mismatches,
            "decision_interval_filter": dict(filtered_turns),
            "largest_decision_intervals": {key: sorted(rows, key=lambda row: row["seconds"], reverse=True)[:5]
                                            for key, rows in decision_details.items()},
            "non_plan_error_outcomes": {tool: dict(counts) for tool, counts in non_plan_errors.items()},
            "unassigned_mcp_calls_by_tool": dict(unassigned_calls),
            "stats_files_with_token_usage": token_usage_coverage,
            "empty_player_model_fields": raw_model_labels_empty,
            "caveats": [
                "The first Opus-versus-Sonnet round has no config.json or saved participant prompts. Its summary still supplies model identities, seed, timeout, and result, but full settings and prompt wording for that round cannot be independently verified from those artifacts.",
                f"{sum(t['plan_outcomes']['accepted'] for t in models.values())} accepted plan-call records coexist with {summary_totals['intent_lifecycles']} intent lifecycle records; {len(lifecycle_differences)} rounds differ. Accepted-call counts do not prove that each call produced a distinct executed lifecycle. This report uses per-call outcomes for plan/error rates and preserves the discrepancy.",
                "Stats rationales_logged is zero throughout. This field is not evidence that the models performed no reasoning, and no tactical causal claims are derived from it.",
                "analysis_summary pickup counts are not used: its text-matching parser can match words such as shotgun in plan text rather than actual pickup events.",
                "No token usage is recorded in any stats.json. Arena call counts alone cannot determine model token consumption or cost.",
                "Decision intervals include opening-plan preparation and post-finish attempts. The largest intervals and whether they precede the first accepted plan are exported for inspection. Reused observations make retry intervals dependent; samples are retained rather than trimmed.",
                "The model IDs are reported benchmark identities; arena artifacts do not attest provider-side serving configuration, reasoning effort, or model weights.",
                "This is a descriptive agent-system benchmark with shared route execution, fixed seed/spawn setting, and continuing sessions; rounds are not independent randomized model trials.",
            ],
        },
        "input_manifest": sorted(manifest, key=lambda entry: entry["path"]),
    }


def main() -> None:
    report = analyze()
    output = Path(__file__).with_name("metrics.json")
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"output": str(output), "validation": report["validation"],
                      "models": {key: {field: value for field, value in model.items()
                                       if field not in ("decision_seconds",)}
                                 for key, model in report["models"].items()}}, indent=2))


if __name__ == "__main__":
    main()
