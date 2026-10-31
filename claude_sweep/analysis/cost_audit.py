"""Audit only this tournament's local Claude Code logs; export aggregates, never prompts.

Run from any directory: python claude_sweep/analysis/cost_audit.py
Requires the original private Claude project logs; the resulting JSON is portable.
No network calls, dependencies, credentials, or raw transcript exports are used.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
SWEEP = HERE.parent
REPO = SWEEP.parent
DEFAULT_LOGS = Path.home() / ".claude/projects/C--Users-muhha-OneDrive-Desktop-rootly-doom-agent-arena"
TOKEN_FIELDS = ("input_tokens", "output_tokens", "cache_creation_input_tokens",
                "cache_read_input_tokens", "cache_write_5m_tokens", "cache_write_1h_tokens",
                "thinking_tokens_in_output")
# The six primary ALL-MEDIUM sessions are fixed independently of generated metrics.
# The extra same-orientation 5-5 series and all earlier Fable-high series are excluded.
PINNED_PARTICIPANTS = {
    "session_5188b2ed236f": (("Sleepy Intern", "claude-sonnet-5-5"), ("Clingy Burrito", "claude-opus-5-5")),
    "session_572d2d193f0a": (("Stapler Tyrant", "claude-opus-5-5"), ("Divorced Lasagna", "claude-fable-5-1")),
    "session_60e8ac8a1dda": (("Overconfident Intern", "claude-sonnet-5-5"), ("Nervous Burrito", "claude-fable-5-1")),
    "session_8fdec3c440b4": (("Stapler Tyrant", "claude-opus-5-5"), ("Soggy Nachos", "claude-sonnet-5-5")),
    "session_acd0e0242118": (("Stapler Tyrant", "claude-fable-5-1"), ("Nervous Meatball", "claude-opus-5-5")),
    "session_da8fd5b5d730": (("Stapler Tyrant", "claude-fable-5-1"), ("Soggy Burrito", "claude-sonnet-5-5")),
}
PINNED_LOG_IDS = {
    ("session_5188b2ed236f", "player_1"): "d1c74f23-9971-4ddd-9ee3-86105e59438f",
    ("session_5188b2ed236f", "player_2"): "51fc4a65-d0e0-4a40-a99c-0b1a9eafaa50",
    ("session_572d2d193f0a", "player_1"): "fe2f8510-c736-481e-a736-1a339d5239b4",
    ("session_572d2d193f0a", "player_2"): "4aaab9a4-5ffa-4e20-a3d4-436044a0924a",
    ("session_60e8ac8a1dda", "player_1"): "6b72f6ac-c3ce-4271-b61a-6464da4125b3",
    ("session_60e8ac8a1dda", "player_2"): "012f0335-ec16-468b-93be-81474dcd1f53",
    ("session_8fdec3c440b4", "player_1"): "e5f004d5-7432-4b3f-ba2c-5a54ae0532ef",
    ("session_8fdec3c440b4", "player_2"): "8057de5a-f7f5-4aa9-b239-d8e126934c2c",
    ("session_acd0e0242118", "player_1"): "eef1d822-c9f7-4d03-9c45-007595079b86",
    ("session_acd0e0242118", "player_2"): "fb2cff05-d24e-466a-b526-7a76d3354a00",
    ("session_da8fd5b5d730", "player_1"): "39376c4e-d271-4ba2-a442-040044dc5c24",
    ("session_da8fd5b5d730", "player_2"): "d1bb5072-fec5-4702-af9b-d00f58b9ff50",
}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def manifests():
    result = {}
    seen_runs = set()
    for sid, expected_players in sorted(PINNED_PARTICIPANTS.items()):
        folders = [path for path in (SWEEP / "med_reruns").rglob(sid) if path.is_dir()]
        if len(folders) != 1:
            raise ValueError(f"Expected one folder for pinned all-medium session {sid}, found {len(folders)}")
        folder = folders[0]
        verification_path = folder.parent / "effort_verification.json"
        verification = read_json(verification_path)
        if verification.get("session_id") != sid:
            raise ValueError(f"Effort sidecar session mismatch for {sid}")
        summary_paths = sorted(folder.glob("round_*/summary.json"))
        summaries = [read_json(p) for p in summary_paths]
        if len(summaries) != 10 or sorted(s.get("round") for s in summaries) != list(range(1, 11)):
            raise ValueError(f"All-medium session {sid} must contain exactly completed rounds 1-10")
        for path, summary in zip(summary_paths, summaries):
            run_id = summary.get("run_id")
            expected_folder = f"round_{summary['round']:02d}_{run_id}"
            if not isinstance(run_id, str) or not re.fullmatch(r"run_[0-9a-f]{12}", run_id) or path.parent.name != expected_folder:
                raise ValueError(f"Round/run identity mismatch in {sid}: {path.parent.name}")
            if run_id in seen_runs:
                raise ValueError(f"Duplicate run identity in pinned cohort: {run_id}")
            seen_runs.add(run_id)
            expected_winner = {"player_1_dead": "player_2", "player_2_dead": "player_1"}.get(summary.get("terminal_reason"))
            if expected_winner is None or summary.get("winner") != expected_winner:
                raise ValueError(f"Missing or inconsistent completed outcome in {sid} {run_id}")
        players = {}
        for side in (1, 2):
            labels = {s[f"coding_assistant_{side}"] for s in summaries}
            if len(labels) != 1:
                raise ValueError(f"Changing participant identity in {folder.name}")
            label = labels.pop()
            alias, harness, model = (part.strip() for part in label.split(",", 2))
            expected_alias, expected_model = expected_players[side - 1]
            if (alias, harness, model) != (expected_alias, "Claude Code", expected_model):
                raise ValueError(f"All-medium cohort identity changed in {sid} player_{side}: {label}")
            sidecar_player = verification[f"player_{side}"]
            if (sidecar_player.get("model"), sidecar_player.get("effort"), sidecar_player.get("source_log_id")) != (model, "medium", PINNED_LOG_IDS[(sid, f"player_{side}")]):
                raise ValueError(f"Effort sidecar does not match pinned source/model/effort for {sid} player_{side}")
            players[f"player_{side}"] = {"agent_name": alias, "harness": harness, "model_id": model}
        result[folder.name] = {
            "path": str(folder.relative_to(REPO)).replace("\\", "/"),
            "runs": {s["run_id"] for s in summaries},
            "players": players,
            "effort_verification": verification,
            "effort_verification_path": str(verification_path.relative_to(REPO)).replace("\\", "/"),
        }
    if len(result) != 6 or len(seen_runs) != 60:
        raise ValueError("All-medium cohort must contain exactly six sessions and sixty unique completed rounds")
    return result


def usage_tokens(usage):
    ttl = usage.get("cache_creation", {})
    result = {k: int(usage.get(k, 0)) for k in TOKEN_FIELDS[:4]}
    result["cache_write_5m_tokens"] = int(ttl.get("ephemeral_5m_input_tokens", 0))
    result["cache_write_1h_tokens"] = int(ttl.get("ephemeral_1h_input_tokens", 0))
    result["thinking_tokens_in_output"] = int(usage.get("output_tokens_details", {}).get("thinking_tokens", 0))
    if result["cache_creation_input_tokens"] != result["cache_write_5m_tokens"] + result["cache_write_1h_tokens"]:
        raise ValueError("Cache-write TTL coverage is incomplete")
    return result


def estimate(tokens, price):
    mapping = {
        "input": ("input_tokens", "input_usd_per_million"),
        "output": ("output_tokens", "output_usd_per_million"),
        "cache_write_5m": ("cache_write_5m_tokens", "cache_write_5m_usd_per_million"),
        "cache_write_1h": ("cache_write_1h_tokens", "cache_write_1h_usd_per_million"),
        "cache_read": ("cache_read_input_tokens", "cache_read_usd_per_million"),
    }
    components = {name: round(tokens[t] * price[p] / 1_000_000, 10) for name, (t, p) in mapping.items()}
    return {"components_usd": components, "total_usd": round(sum(components.values()), 10)}


def audit(log_root):
    archive = manifests()
    pricing = read_json(HERE / "pricing.json")
    all_runs = set().union(*(m["runs"] for m in archive.values()))
    participant_logs = []
    excluded = []
    unrelated_file_count = sum(p.stem not in set(PINNED_LOG_IDS.values()) for p in log_root.glob("*.jsonl"))
    for log_id in sorted(PINNED_LOG_IDS.values()):
        path = log_root / f"{log_id}.jsonl"
        raw_bytes = path.read_bytes()
        raw = raw_bytes.decode("utf-8")
        all_log_run_refs = set(re.findall(r"\brun_[0-9a-f]{12}\b", raw))
        run_hits = all_log_run_refs & all_runs
        session_hits = [sid for sid, m in archive.items() if sid in raw or run_hits & m["runs"]]
        if not session_hits:
            raise ValueError(f"Pinned log {log_id} does not reference its cohort")
        rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
        assistant_rows = [r for r in rows if r.get("type") == "assistant"]
        ready = set()
        tool_names = Counter()
        tool_ids = {}
        arena_participant_arguments = set()
        for row in assistant_rows:
            for block in row.get("message", {}).get("content", []):
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    name = block.get("name", "")
                    tool_names[name] += 1
                    tool_ids[block.get("id")] = name
                    if name.startswith("mcp__doom-arena__") and block.get("input", {}).get("participant_id"):
                        arena_participant_arguments.add(block["input"]["participant_id"])
                    if block.get("name", "").endswith("set_participant_ready"):
                        inp = block.get("input", {})
                        ready.add((inp.get("participant_id"), inp.get("agent_name")))
        candidates = []
        for sid in session_hits:
            manifest = archive[sid]
            if not manifest["runs"].issubset(run_hits):
                continue
            for side, player in manifest["players"].items():
                if (side, player["agent_name"]) in ready:
                    candidates.append((sid, side, player))
        if len(candidates) != 1:
            excluded.append({
                "source_log_id": path.stem,
                "matched_archived_run_count": len(run_hits),
                "reason": "No unique complete ten-round session plus matching side and arena alias; excluded stale/aborted conversation.",
            })
            continue
        sid, side, player = candidates[0]
        if PINNED_LOG_IDS.get((sid, side)) != path.stem:
            raise ValueError(f"Pinned source log does not match participant identity in {path.stem}")
        model = player["model_id"]
        sidecar_player = archive[sid]["effort_verification"][side]
        # Guard the entire transcript scope: exactly one gameplay instruction and
        # only local UI command messages besides tool results. Any later human
        # request needs a new explicit boundary rather than silently adding costs.
        substantive_users = []
        local_command_markers = ("<command-name>", "<local-command-stdout>", "<local-command-caveat>")
        for row in rows:
            content = row.get("message", {}).get("content")
            if row.get("type") == "user" and isinstance(content, str) and not any(marker in content for marker in local_command_markers):
                substantive_users.append(row)
        if len(substantive_users) != 1:
            raise ValueError(f"Unbounded extra user work in pinned log {path.stem}")
        game_prompt = substantive_users[0]["message"]["content"]
        if not all(marker in game_prompt for marker in ("set_participant_ready", "controller_token", side)) or "doom" not in game_prompt.lower():
            raise ValueError(f"Pinned log lacks a sole recognizable gameplay instruction: {path.stem}")
        if ready != {(side, player["agent_name"])} or arena_participant_arguments != {side}:
            raise ValueError(f"Mixed participant/alias control in {path.stem}")
        if all_log_run_refs != archive[sid]["runs"]:
            raise ValueError(f"Extra or missing gameplay run references outside pinned session {sid} in {path.stem}")
        arena_result_runs = set()
        arena_result_sessions = set()
        for row in rows:
            content = row.get("message", {}).get("content", [])
            if not isinstance(content, list):
                continue
            for block in content:
                if (isinstance(block, dict) and block.get("type") == "tool_result"
                        and tool_ids.get(block.get("tool_use_id"), "").startswith("mcp__doom-arena__")):
                    result_text = json.dumps(block.get("content"))
                    arena_result_runs.update(re.findall(r"\brun_[0-9a-f]{12}\b", result_text))
                    arena_result_sessions.update(re.findall(r"\bsession_[0-9a-f]{12}\b", result_text))
        if arena_result_runs != archive[sid]["runs"] or arena_result_sessions != {sid}:
            raise ValueError(f"Arena tool results do not exclusively cover pinned session {sid} in {path.stem}")
        static_session_refs = set(re.findall(r"\bsession_[0-9a-f]{12}\b", raw)) - arena_result_sessions
        # Entire selected main-thread transcript is gameplay, tool discovery, and final summaries.
        # Reject unrelated tools or models rather than silently including coding activity.
        unrelated_tools = [name for name in tool_names if name != "ToolSearch" and not name.startswith("mcp__doom-arena__")]
        if unrelated_tools:
            raise ValueError(f"Unrelated tools in candidate {path.stem}: {unrelated_tools}")
        actual_models = {r["message"].get("model") for r in assistant_rows}
        if actual_models != {model}:
            raise ValueError(f"Actual API model mismatch in {path.stem}: {actual_models}")
        if any(r.get("isSidechain") for r in assistant_rows):
            raise ValueError(f"Sidechain responses are outside primary-thread scope in {path.stem}")
        # Repeated content blocks carry the SAME usage; summing them would overcharge.
        messages = {}
        for row in assistant_rows:
            msg = row["message"]
            if not msg.get("id") or not isinstance(msg.get("usage"), dict):
                raise ValueError(f"Missing message identity or usage in {path.stem}")
            mid = msg["id"]
            if mid in messages and messages[mid]["message"]["usage"] != msg["usage"]:
                raise ValueError(f"Inconsistent repeated message usage in {path.stem}")
            messages[mid] = row
        totals = Counter({key: 0 for key in TOKEN_FIELDS})
        efforts = Counter()
        per_turn_efforts = Counter()
        usage_meta = Counter()
        max_context = 0
        for row in messages.values():
            usage = row["message"]["usage"]
            tokens = usage_tokens(usage)
            totals.update(tokens)
            efforts[str(row.get("effort"))] += 1
            per_turn_efforts[str(row.get("perTurnEffort"))] += 1
            if row.get("effort") != "medium" or row.get("perTurnEffort") != "medium":
                raise ValueError(f"Non-medium response effort in pinned log {path.stem}")
            meta = (usage.get("service_tier"), usage.get("speed"), usage.get("inference_geo"))
            usage_meta[meta] += 1
            if meta != ("standard", "standard", "global"):
                raise ValueError(f"Nonstandard pricing modifier in {path.stem}: {meta}")
            if any(usage.get("server_tool_use", {}).values()) or usage.get("fallback_credit"):
                raise ValueError(f"Additional tool charges or fallback credit in {path.stem}")
            max_context = max(max_context, tokens["input_tokens"] + tokens["cache_creation_input_tokens"] + tokens["cache_read_input_tokens"])
        requests = [r for r in rows if r.get("type") == "api-request"]
        request_models = {r.get("params", {}).get("model") for r in requests}
        if request_models != {model}:
            raise ValueError(f"Requested API model mismatch in {path.stem}: {request_models}")
        request_efforts = Counter(str(r.get("params", {}).get("output_config", {}).get("effort")) for r in requests)
        if set(request_efforts) != {"medium"}:
            raise ValueError(f"Non-medium API request effort in pinned log {path.stem}: {request_efforts}")
        request_ids = {r["id"] for r in requests}
        used_refs = {r.get("requestRef") for r in messages.values()}
        first_request_time = min(r["timestamp"] for r in requests)
        last_request_time = max(r["timestamp"] for r in requests)
        if substantive_users[0]["timestamp"] > first_request_time:
            raise ValueError(f"API work predates the gameplay instruction in {path.stem}")
        transcript_times = [r["timestamp"] for r in assistant_rows]
        last_assistant_time = max(transcript_times)
        post_game_model_command_times = [
            r["timestamp"] for r in rows
            if r.get("type") == "user" and r.get("timestamp", "") > last_assistant_time
            and isinstance(r.get("message", {}).get("content"), str)
            and "<command-name>" in r["message"]["content"] and "/model" in r["message"]["content"]
        ]
        states = [r for r in rows if r.get("type") == "cost-state"]
        last_state = states[-1] if states else None
        state_export = None
        if last_state:
            # Cost-state is a cumulative snapshot. Select the last; never sum snapshots.
            repriced = {}
            for state_model, mu in last_state.get("modelUsage", {}).items():
                price = pricing["models"].get(state_model) or pricing.get("auxiliary_models", {}).get(state_model)
                if price is None:
                    raise ValueError(f"Unpriced cumulative model {state_model}")
                tt = {
                    "input_tokens": mu.get("inputTokens", 0), "output_tokens": mu.get("outputTokens", 0),
                    "cache_read_input_tokens": mu.get("cacheReadInputTokens", 0),
                    "cache_write_5m_tokens": mu.get("cacheCreationEphemeral5mInputTokens", 0),
                    "cache_write_1h_tokens": mu.get("cacheCreationEphemeral1hInputTokens", 0),
                }
                if state_model == "claude-haiku-5-5" and tt["input_tokens"] + tt["cache_read_input_tokens"] + tt["cache_write_5m_tokens"] + tt["cache_write_1h_tokens"] > 100_000:
                    raise ValueError("Cannot verify auxiliary Haiku tier from session aggregate")
                repriced[state_model] = estimate(tt, price)["total_usd"]
                if abs(repriced[state_model] - mu.get("costUSD", 0)) > 1e-8:
                    raise ValueError(f"Cumulative cost does not reconcile to published rates: {path.stem}/{state_model}")
            state_export = {
                "total_api_equivalent_usd": last_state.get("totalCostUSD"),
                "has_unknown_model_cost": last_state.get("hasUnknownModelCost"),
                "model_usage": last_state.get("modelUsage", {}),
                "scope": "Whole Claude Code session cumulative snapshot; may include background requests absent from assistant transcript.",
                "snapshot_count": len(states),
                "primary_model_usd": last_state.get("modelUsage", {}).get(model, {}).get("costUSD"),
                "auxiliary_model_usd": sum(v.get("costUSD", 0) for k, v in last_state.get("modelUsage", {}).items() if k != model),
                "repriced_model_costs_usd": repriced,
                "repricing_matches_recorded_costs": True,
                "post_game_model_command_at_utc": post_game_model_command_times,
                "nonparticipant_nonhaiku_model_costs_usd": {k: v.get("costUSD", 0) for k, v in last_state.get("modelUsage", {}).items() if k not in {model, "claude-haiku-5-5"}},
                "bounded_tournament_scope_certified": False,
            }
        participant_logs.append({
            "arena_session_id": sid,
            "participant_id": side,
            **player,
            "source_log_id": path.stem,
            "source_sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "source_bytes": len(raw_bytes),
            "effort_verification_path": archive[sid]["effort_verification_path"],
            "original_verification_source_sha256": sidecar_player.get("source_sha256"),
            "source_hash_matches_original_verification": hashlib.sha256(raw_bytes).hexdigest() == sidecar_player.get("source_sha256"),
            "request_response_counts_match_original_verification": (len(requests), len(messages)) == (sidecar_player.get("api_requests"), sidecar_player.get("unique_api_responses")),
            "sole_substantive_user_instruction_at_utc": substantive_users[0]["timestamp"],
            "substantive_user_instruction_count": len(substantive_users),
            "archive_path": archive[sid]["path"],
            "matched_rounds": len(archive[sid]["runs"]),
            "matched_run_ids": sorted(run_hits),
            "verified_arena_tool_result_session_ids": sorted(arena_result_sessions),
            "non_gameplay_session_id_references": sorted(static_session_refs),
            "non_gameplay_reference_note": "References outside arena tool results are retained as context metadata; gameplay tool results must exclusively identify the pinned session.",
            "first_request_at_utc": first_request_time,
            "last_request_at_utc": last_request_time,
            "first_assistant_at_utc": min(transcript_times),
            "last_assistant_at_utc": max(transcript_times),
            "observed_assistant_rows": len(assistant_rows),
            "unique_api_messages": len(messages),
            "duplicate_content_rows_removed": len(assistant_rows) - len(messages),
            "api_request_rows": len(requests),
            "request_refs_without_response_usage": len(request_ids - used_refs),
            "effort_by_message_count": dict(efforts),
            "per_turn_effort_by_message_count": dict(per_turn_efforts),
            "effort_by_api_request_count": dict(request_efforts),
            "standard_global_messages": sum(usage_meta.values()),
            "max_input_context_tokens": max_context,
            "tokens": dict(totals),
            "main_thread_api_equivalent": estimate(totals, pricing["models"][model]),
            "recorded_cost_state": state_export,
        })
    keys = [(p["arena_session_id"], p["participant_id"]) for p in participant_logs]
    expected_keys = {(sid, side) for sid in archive for side in ("player_1", "player_2")}
    if len(keys) != len(set(keys)) or set(keys) != expected_keys:
        raise ValueError("Participant log coverage is not exactly one unique log for every archived participant")
    by_model = {}
    for model in pricing["models"]:
        logs = [p for p in participant_logs if p["model_id"] == model]
        tokens = Counter({key: 0 for key in TOKEN_FIELDS})
        for p in logs:
            tokens.update(p["tokens"])
        cost = estimate(tokens, pricing["models"][model])
        by_model[model] = {
            "display_name": pricing["models"][model]["display_name"],
            "participant_sessions": len(logs),
            "round_appearances": sum(p["matched_rounds"] for p in logs),
            "unique_api_messages": sum(p["unique_api_messages"] for p in logs),
            "tokens": dict(tokens),
            "main_thread_api_equivalent": cost,
            "mean_main_thread_usd_per_round_appearance": cost["total_usd"] / sum(p["matched_rounds"] for p in logs),
            "cost_state_sessions_available": sum(p["recorded_cost_state"] is not None for p in logs),
            "all_conversation_cost_snapshots_available": all(p["recorded_cost_state"] is not None for p in logs),
            "full_session_cost_available_for_all": False,
            "recorded_conversation_total_usd": sum(p["recorded_cost_state"]["total_api_equivalent_usd"] for p in logs if p["recorded_cost_state"]),
            "recorded_primary_model_total_usd": sum(p["recorded_cost_state"]["primary_model_usd"] for p in logs if p["recorded_cost_state"]),
            "recorded_other_model_total_usd": sum(p["recorded_cost_state"]["auxiliary_model_usd"] for p in logs if p["recorded_cost_state"]),
        }
    available_states = [p["recorded_cost_state"] for p in participant_logs if p["recorded_cost_state"]]
    additional_primary_count = sum(abs(p["recorded_cost_state"]["primary_model_usd"] - p["main_thread_api_equivalent"]["total_usd"]) > 1e-8 for p in participant_logs if p["recorded_cost_state"])
    missing_states_count = len(participant_logs) - len(available_states)
    model_switch_states = [p for p in participant_logs if p["recorded_cost_state"] and p["recorded_cost_state"]["post_game_model_command_at_utc"]]
    unreturned_requests = sum(p["request_refs_without_response_usage"] for p in participant_logs)
    state_totals = {
        "covered_logs": len(available_states),
        "total_logs": len(participant_logs),
        "total_usd": sum(s["total_api_equivalent_usd"] for s in available_states),
        "auxiliary_model_usd": sum(s["auxiliary_model_usd"] for s in available_states),
        "all_snapshot_model_costs_reconcile_to_published_rates": all(s["repricing_matches_recorded_costs"] for s in available_states),
        "bounded_tournament_scope_certified": False,
        "warning": "Whole-conversation cumulative totals may include background or post-game activity absent from the gameplay transcript. They are not certified bounded tournament costs and must not be used as a wins-per-dollar denominator.",
    }
    return {
        "schema_version": 1,
        "cohort": "all_medium_60_round_sweep",
        "required_effort": "medium",
        "excluded_arena_session_ids": ["session_fcc7bb2f60a8", "session_0126b7e77ed7", "session_12edeaaa9be8", "session_234aaaa29bc0", "session_d553d09a35fc"],
        "pinned_arena_session_ids": sorted(PINNED_PARTICIPANTS),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "pricing_checked_date": pricing["retrieved_date_local"],
        "currency": "USD",
        "actual_invoice_cost_available": False,
        "full_session_cost_available_for_all": False,
        "all_conversation_cost_snapshots_available": missing_states_count == 0,
        "bounded_tournament_total_available": False,
        "uniform_main_thread_usage_available_for_all": True,
        "scope": "Observed primary-model main-thread API messages in twelve gameplay conversations, including tool discovery, between-round waits, and final summaries; excludes other conversations and unrecorded background usage.",
        "method": [
            "Match each private log to all ten archived run IDs plus the participant side and arena alias; verify actual response model equals the archive label.",
            "Pin the six primary all-medium session IDs, twelve source log IDs, and participant identities independently of generated metrics; require rounds 1-10, completed outcomes, and sixty globally unique run IDs.",
            "Require medium effort in every API request, response effort field, and per-turn effort field; exclude the extra same-orientation 5-5 series and all older Fable-high series.",
            "Require every arena tool result to identify only its pinned session and ten runs; reject extra gameplay runs or mixed participant control. Separately flag other session IDs in static context.",
            "Verify all tools in included conversations are Doom Arena or ToolSearch; reject unrelated coding activity or model switches.",
            "Require exactly one substantive user instruction, identifying Doom gameplay, before the first API request; exclude local UI commands and reject later unrelated user work rather than silently expanding scope.",
            "Deduplicate assistant content blocks by message.id; repeated usage must match exactly; each response is counted once.",
            "Sum input, output, cache-read, and cache-write tokens separately; cache writes use observed one-hour TTL. Thinking tokens are a subset of output.",
            "Verify every included response is standard service/speed and global inference, with no web-tool charges or fallback credits.",
            "Price response aggregates with verified current standard global API list rates. These estimates are not a subscription invoice or all-inclusive cost.",
            f"Cumulative cost-state snapshots exist for {len(available_states)} of {len(participant_logs)} conversations. Export the final snapshot per conversation separately; never add snapshots to response totals. Snapshot presence does not certify tournament-only scope.",
        ],
        "coverage": {
            "archived_sessions": len(archive),
            "archived_rounds": sum(len(m["runs"]) for m in archive.values()),
            "expected_participant_logs": len(expected_keys),
            "matched_participant_logs": len(participant_logs),
            "cumulative_cost_state_logs": len(available_states),
            "excluded_candidate_logs": excluded,
            "unrelated_project_logs_not_read": unrelated_file_count,
            "unique_api_messages": sum(p["unique_api_messages"] for p in participant_logs),
            "duplicate_assistant_content_rows_removed": sum(p["duplicate_content_rows_removed"] for p in participant_logs),
            "api_requests_without_response_usage": sum(p["request_refs_without_response_usage"] for p in participant_logs),
        },
        "total_main_thread_api_equivalent_usd": round(sum(p["main_thread_api_equivalent"]["total_usd"] for p in participant_logs), 10),
        "recorded_cost_state_totals": state_totals,
        "partial_recorded_cost_state_totals": {**state_totals, "legacy_key_note": "Retained for compatibility; inspect covered_logs and bounded_tournament_scope_certified, not this legacy key's name."},
        "limitations": [
            f"API request records without corresponding assistant response usage: {unreturned_requests}. No charge or token count is invented for them.",
            f"{additional_primary_count} available cost-state snapshots contain additional primary-model usage beyond the deduplicated assistant transcript; background work is not fully visible there.",
            f"{len(available_states)}/{len(participant_logs)} whole-conversation cost snapshots are present ({missing_states_count} missing). Their scope extends beyond the last gameplay response, so all-in bounded tournament costs cannot be certified.",
            f"{len(model_switch_states)} conversations have a /model command after their final gameplay response. Any cumulative background or post-game charges remain outside the observed primary-thread tournament estimate.",
            "Per-model prices use one checked date, not historical invoices. Subscription allocations, credits, taxes, negotiated prices, and unseen work are excluded.",
            "These are session-scoped estimates, not per-round or per-intent token allocations. Per-round figures are session totals divided by appearances.",
        ],
        "by_model": by_model,
        "participants": sorted(participant_logs, key=lambda p: (p["arena_session_id"], p["participant_id"])),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-root", type=Path, default=DEFAULT_LOGS)
    args = parser.parse_args()
    if not args.log_root.is_dir():
        raise SystemExit("Private project logs unavailable; use the existing aggregate cost_audit.json or pass --log-root.")
    result = audit(args.log_root)
    (HERE / "cost_audit.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"coverage": result["coverage"], "total_main_thread_api_equivalent_usd": result["total_main_thread_api_equivalent_usd"], "by_model": result["by_model"]}, indent=2))


if __name__ == "__main__":
    main()
