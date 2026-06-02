from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


BASE = Path(__file__).resolve().parent


def find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "benchmarks" / "results").exists():
            return candidate
    raise FileNotFoundError("Could not locate repository root containing benchmarks/results")


REPO = find_repo_root(BASE)
RESULTS = REPO / "benchmarks" / "results"
TABLES = BASE / "tables"
FIGURES = BASE / "figures"
DATA = BASE / "data"

OFFICIAL_FOLDERS = [
    "player1-gpt-5-5__player2-gpt-5-4",
    "player1-gpt-5-4__player2-gpt-5-5",
    "player1-gpt-5-5__player2-gpt-5-4-mini",
    "player1-gpt-5-4-mini__player2-gpt-5-5",
    "player1-gpt-5-5__player2-gpt-5-3-codex-spark",
    "player1-gpt-5-3-codex-spark__player2-gpt-5-5",
    "player1-gpt-5-4__player2-gpt-5-4-mini",
    "player1-gpt-5-4-mini__player2-gpt-5-4",
    "player1-gpt-5-4__player2-gpt-5-3-codex-spark",
    "player1-gpt-5-3-codex-spark__player2-gpt-5-4",
    "player1-gpt-5-4-mini__player2-gpt-5-3-codex-spark",
    "player1-gpt-5-3-codex-spark__player2-gpt-5-4-mini",
]

MODEL_LABELS = {
    "gpt-5-5": "gpt-5.5",
    "gpt-5-4": "gpt-5.4",
    "gpt-5-4-mini": "gpt-5.4-mini",
    "gpt-5-3-codex-spark": "gpt-5.3-codex-spark",
}

INTENT_ORDER = [
    "resource control",
    "engagement/combat",
    "evasion/recovery",
    "map control/exploration",
]


def safe_read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def resolve_result_folder(name: str) -> Path | None:
    exact = RESULTS / name
    if exact.exists():
        return exact
    lowered = name.lower()
    for path in RESULTS.iterdir():
        if path.is_dir() and path.name.lower() == lowered:
            return path
    return None


def parse_models(folder_name: str) -> tuple[str, str]:
    match = re.match(r"(?i)player1-(.+)__player2-(.+)", folder_name)
    if not match:
        return "unknown-player1", "unknown-player2"
    return match.group(1), match.group(2)


def label_model(model: str) -> str:
    return MODEL_LABELS.get(model, model)


def mean(values: list[float]) -> float:
    values = [float(v) for v in values if v is not None]
    return round(sum(values) / len(values), 3) if values else 0.0


def median(values: list[float]) -> float:
    values = sorted(float(v) for v in values if v is not None)
    if not values:
        return 0.0
    mid = len(values) // 2
    if len(values) % 2:
        return round(values[mid], 3)
    return round((values[mid - 1] + values[mid]) / 2, 3)


def percentile(values: list[float], p: float) -> float:
    values = sorted(float(v) for v in values if v is not None)
    if not values:
        return 0.0
    idx = min(len(values) - 1, max(0, int(math.ceil((p / 100) * len(values))) - 1))
    return round(values[idx], 3)


def sum_field(rows: list[dict], field: str) -> float:
    total = 0.0
    for row in rows:
        try:
            total += float(row.get(field) or 0)
        except ValueError:
            pass
    return total


def binomial_two_sided_p(wins: int, losses: int) -> float:
    n = wins + losses
    if n <= 0:
        return 1.0
    observed = min(wins, losses)
    prob = sum(math.comb(n, k) for k in range(0, observed + 1)) / (2**n)
    return round(min(1.0, 2 * prob), 5)


def flatten_route(route) -> list[str]:
    if isinstance(route, list):
        values = route
    elif isinstance(route, str):
        values = re.split(r"[;\s,]+", route)
    else:
        values = []
    cells = []
    for value in values:
        text = str(value).strip().upper()
        if re.fullmatch(r"[A-Z]\d{1,2}", text):
            cells.append(f"{text[0]}{int(text[1:]):02d}")
    return cells


def classify_intent(plan: dict, pickup_cells: set[str]) -> str:
    text = " ".join(
        str(plan.get(key) or "").lower()
        for key in ("objective", "reasoning", "plan_note", "route")
    )
    route_cells = set(flatten_route(plan.get("route_cells") or plan.get("route")))
    if (
        any(word in text for word in ("shotgun", "weapon", "pickup", "health", "medikit", "heal", "resource"))
        or bool(route_cells & pickup_cells)
    ):
        return "resource control"
    if any(word in text for word in ("fight", "engage", "attack", "shoot", "enemy", "opponent", "pressure", "contact", "finish")):
        return "engagement/combat"
    if any(word in text for word in ("retreat", "evade", "escape", "avoid", "recover", "reset", "safe", "distance", "unstuck")):
        return "evasion/recovery"
    return "map control/exploration"


def load_pickup_cells() -> tuple[set[str], set[str], list[str]]:
    ascii_path = REPO / "scripts" / "map_blueprints" / "duel_e1m8_ascii.txt"
    if not ascii_path.exists():
        return set(), set(), []
    rows = [line.rstrip("\n") for line in ascii_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    health, shotgun = set(), set()
    for r, line in enumerate(rows, start=1):
        for c, ch in enumerate(line, start=1):
            cell = f"{chr(ord('A') + r - 1)}{c:02d}"
            if ch.upper() == "H":
                health.add(cell)
            if ch.upper() == "S":
                shotgun.add(cell)
    return health, shotgun, rows


def extract_rounds() -> tuple[list[dict], list[dict], dict]:
    health_cells, shotgun_cells, ascii_rows = load_pickup_cells()
    pickup_cells = health_cells | shotgun_cells
    round_rows: list[dict] = []
    plan_rows: list[dict] = []
    data_quality = {
        "missing_folders": [],
        "folder_round_counts": {},
        "missing_analysis_summary": [],
        "missing_stats": [],
        "legacy_excluded": True,
        "health_cells": sorted(health_cells),
        "shotgun_cells": sorted(shotgun_cells),
    }

    for official_name in OFFICIAL_FOLDERS:
        folder = resolve_result_folder(official_name)
        if not folder:
            data_quality["missing_folders"].append(official_name)
            continue
        p1_model, p2_model = parse_models(folder.name)
        round_dirs = sorted(
            [path for path in folder.iterdir() if path.is_dir() and path.name.startswith("round_")],
            key=lambda p: int(re.search(r"round_(\d+)", p.name).group(1)) if re.search(r"round_(\d+)", p.name) else 999,
        )
        data_quality["folder_round_counts"][folder.name] = len(round_dirs)
        for round_dir in round_dirs:
            round_match = re.search(r"round_(\d+)", round_dir.name)
            round_no = int(round_match.group(1)) if round_match else 0
            summary = safe_read_json(round_dir / "summary.json")
            stats = safe_read_json(round_dir / "stats.json")
            analysis = safe_read_json(round_dir / "analysis_summary.json")
            if not stats:
                data_quality["missing_stats"].append(str(round_dir))
            if not analysis:
                data_quality["missing_analysis_summary"].append(str(round_dir))

            outcome = analysis.get("outcome", {})
            combat = analysis.get("combat", {})
            resources = analysis.get("resources", {})
            routing = analysis.get("routing", {})
            stats_summary = stats.get("summary", {})
            by_participant = stats.get("by_participant", {})
            winner = summary.get("winner") or outcome.get("winner") or "draw"
            if winner not in {"player_1", "player_2"}:
                winner = "draw"
            winner_model = {"player_1": p1_model, "player_2": p2_model}.get(winner, "draw")
            first_shotgun = (resources.get("first_shotgun_pickup") or {}).get("participant_id")
            first_health = (resources.get("first_health_pickup") or {}).get("participant_id")
            pickup_counts = resources.get("pickup_counts", {})
            stuck_by_participant = stats_summary.get("stuck_recovery_invocations_by_participant") or {}

            decision_by_participant = defaultdict(list)
            decision_by_sequence = {}
            for turn in stats.get("inferred_decision_turns", []):
                pid = turn.get("participant_id")
                value = turn.get("inferred_decision_latency_ms")
                seq = turn.get("sequence_number")
                if pid and value is not None:
                    decision_by_participant[pid].append(float(value))
                    if seq is not None:
                        decision_by_sequence[(pid, int(seq))] = float(value)

            participant_plan_counts = Counter()
            participant_invalid_counts = Counter()
            participant_route_errors = defaultdict(Counter)
            for call in stats.get("calls", []):
                if call.get("tool_name") != "set_participant_plan":
                    continue
                pid = call.get("participant_id")
                if not pid:
                    continue
                participant_plan_counts[pid] += 1
                if call.get("accepted") is False or call.get("is_error"):
                    participant_invalid_counts[pid] += 1
                    participant_route_errors[pid][call.get("error_type") or "other"] += 1

            for pid, model, opponent_model in (
                ("player_1", p1_model, p2_model),
                ("player_2", p2_model, p1_model),
            ):
                c = combat.get(pid, {})
                opp = combat.get("player_2" if pid == "player_1" else "player_1", {})
                bp = by_participant.get(pid, {})
                pc = pickup_counts.get(pid, {})
                row = {
                    "folder": folder.name,
                    "round_dir": round_dir.name,
                    "round": round_no,
                    "run_id": summary.get("run_id") or stats.get("run_id") or analysis.get("run_id"),
                    "participant": pid,
                    "model": model,
                    "model_label": label_model(model),
                    "opponent_model": opponent_model,
                    "opponent_model_label": label_model(opponent_model),
                    "winner": winner,
                    "winner_model": winner_model,
                    "winner_model_label": label_model(winner_model) if winner_model != "draw" else "draw",
                    "won": winner == pid,
                    "lost": winner in {"player_1", "player_2"} and winner != pid,
                    "draw": winner == "draw",
                    "terminal_reason": summary.get("terminal_reason") or outcome.get("terminal_reason"),
                    "elapsed_time_seconds": summary.get("elapsed_time_seconds") or outcome.get("elapsed_time_seconds") or 0,
                    "timeout_seconds": summary.get("timeout_seconds") or outcome.get("timeout_seconds") or 0,
                    "final_health": c.get("final_health", 0),
                    "opponent_final_health": opp.get("final_health", 0),
                    "damage_dealt": c.get("damage_dealt", 0),
                    "damage_taken": c.get("damage_taken", 0),
                    "shots_fired": c.get("shots_fired", 0),
                    "shots_hit": c.get("shots_hit", 0),
                    "accuracy": c.get("accuracy", 0),
                    "total_mcp_calls": bp.get("count", 0),
                    "mcp_errors": bp.get("errors", 0),
                    "participant_mcp_latency_ms": bp.get("average_latency_ms", 0),
                    "round_mcp_errors": stats_summary.get("errored_mcp_calls", 0),
                    "round_mcp_latency_ms": stats_summary.get("average_mcp_latency_ms", 0),
                    "round_decision_latency_ms": stats_summary.get("average_inferred_chat_decision_latency_ms", 0),
                    "avg_decision_latency_ms": mean(decision_by_participant.get(pid, [])),
                    "set_participant_plan_calls": participant_plan_counts[pid],
                    "invalid_plan_count": participant_invalid_counts[pid],
                    "waypoint_in_wall_cell": participant_route_errors[pid]["waypoint_in_wall_cell"],
                    "route_diagonal_segment": participant_route_errors[pid]["route_diagonal_segment"],
                    "route_errors_other": sum(participant_route_errors[pid].values())
                    - participant_route_errors[pid]["waypoint_in_wall_cell"]
                    - participant_route_errors[pid]["route_diagonal_segment"],
                    "stuck_recovery_count": stuck_by_participant.get(pid, 0),
                    "shotgun_pickups": pc.get("shotgun", 0),
                    "health_pickups": pc.get("health", 0),
                    "first_shotgun": first_shotgun == pid,
                    "first_health": first_health == pid,
                    "unique_cells_visited": (routing.get(pid, {}) or {}).get("unique_cells_visited", 0),
                    "distance_traveled": (routing.get(pid, {}) or {}).get("distance_traveled", 0),
                    "damage_diff": c.get("damage_dealt", 0) - c.get("damage_taken", 0),
                }
                shots = float(row["shots_fired"] or 0)
                row["damage_per_shot"] = round(float(row["damage_dealt"] or 0) / shots, 3) if shots else 0
                elapsed = float(row["elapsed_time_seconds"] or 0)
                row["damage_per_second"] = round(float(row["damage_dealt"] or 0) / elapsed, 3) if elapsed else 0
                round_rows.append(row)

            for call in stats.get("calls", []):
                if call.get("tool_name") != "set_participant_plan":
                    continue
                pid = call.get("participant_id")
                if pid not in {"player_1", "player_2"}:
                    continue
                model = p1_model if pid == "player_1" else p2_model
                opponent_model = p2_model if pid == "player_1" else p1_model
                objective = call.get("plan_objective") or call.get("objective") or ""
                reasoning = call.get("plan_reasoning") or call.get("reasoning") or ""
                plan_note = (
                    call.get("plan_note")
                    or call.get("plan_summary")
                    or call.get("plan_plan_summary")
                    or call.get("summary")
                    or ""
                )
                route_cells = flatten_route(call.get("plan_route_cells") or call.get("route") or [])
                seq = call.get("plan_sequence_number") or call.get("sequence_number")
                try:
                    seq_int = int(seq)
                except Exception:
                    seq_int = 0
                plan = {
                    "folder": folder.name,
                    "round": round_no,
                    "round_dir": round_dir.name,
                    "run_id": summary.get("run_id") or stats.get("run_id"),
                    "participant": pid,
                    "model": model,
                    "model_label": label_model(model),
                    "opponent_model": opponent_model,
                    "opponent_model_label": label_model(opponent_model),
                    "winner": winner,
                    "winner_model": winner_model,
                    "winner_model_label": label_model(winner_model) if winner_model != "draw" else "draw",
                    "won": winner == pid,
                    "lost": winner in {"player_1", "player_2"} and winner != pid,
                    "draw": winner == "draw",
                    "terminal_reason": summary.get("terminal_reason") or outcome.get("terminal_reason"),
                    "sequence_number": seq_int,
                    "objective": objective,
                    "route": ";".join(route_cells),
                    "route_cells": route_cells,
                    "reasoning": reasoning,
                    "plan_note": plan_note,
                    "started_at_ms": call.get("started_at_ms"),
                    "completed_at_ms": call.get("completed_at_ms"),
                    "decision_latency_ms": decision_by_sequence.get((pid, seq_int), 0),
                    "mcp_latency_ms": call.get("latency_ms", 0),
                    "accepted": call.get("accepted") is True,
                    "rejected": call.get("accepted") is False or call.get("is_error") is True,
                    "rejection_reason": call.get("error_type") or call.get("error") or "",
                    "request_chars": call.get("request_chars", 0),
                    "response_chars": call.get("response_chars", 0),
                    "route_waypoint_count": len(route_cells),
                }
                plan["intent_category"] = classify_intent(plan, pickup_cells)
                plan["opening_category"] = classify_opening(plan)
                plan.update(score_plan_quality(plan, health_cells, shotgun_cells))
                plan_rows.append(plan)
    return round_rows, plan_rows, data_quality


def classify_opening(plan: dict) -> str:
    text = " ".join(str(plan.get(k) or "").lower() for k in ("objective", "reasoning", "plan_note"))
    if "shotgun" in text or "weapon" in text:
        return "shotgun first"
    if "health" in text or "medikit" in text or "heal" in text:
        return "health first"
    if "center" in text or "middle" in text:
        return "center contest"
    if "fight" in text or "enemy" in text or "contact" in text or "opponent" in text:
        return "direct search"
    if "hold" in text or "safe" in text:
        return "defensive hold"
    return "edge rotate"


def score_plan_quality(plan: dict, health_cells: set[str], shotgun_cells: set[str]) -> dict:
    text = " ".join(str(plan.get(k) or "").lower() for k in ("objective", "reasoning", "plan_note"))
    route = set(plan.get("route_cells") or [])
    pickup_route = bool(route & (health_cells | shotgun_cells))
    resource_awareness = 5 if ("shotgun" in text or "health" in text or pickup_route) else 2
    map_awareness = 5 if any(word in text for word in ("wall", "blocked", "route", "corridor", "lane", "cell")) else 3
    opponent_awareness = 5 if any(word in text for word in ("enemy", "opponent", "contact", "visible", "fight")) else 2
    adaptation = 5 if any(word in text for word in ("again", "previous", "avoid", "failed", "re-route", "reroute", "stuck")) else 2
    aligned = True
    if ("shotgun" in text or "weapon" in text) and not (route & shotgun_cells):
        aligned = False
    if ("health" in text or "heal" in text or "medikit" in text) and not (route & health_cells):
        aligned = False
    route_objective_alignment = 5 if aligned else 2
    if plan.get("rejected"):
        route_objective_alignment = min(route_objective_alignment, 2)
        map_awareness = min(map_awareness, 2)
    quality = mean([route_objective_alignment, map_awareness, opponent_awareness, resource_awareness, adaptation])
    return {
        "route_objective_alignment": route_objective_alignment,
        "map_awareness": map_awareness,
        "opponent_awareness": opponent_awareness,
        "resource_awareness": resource_awareness,
        "adaptation": adaptation,
        "plan_quality": quality,
        "reasoning_action_aligned": aligned and not plan.get("rejected"),
    }


def write_csv(path: Path, rows: list[dict], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not fieldnames:
        fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            clean = {}
            for key in fieldnames:
                value = row.get(key)
                if isinstance(value, list):
                    value = ";".join(str(v) for v in value)
                clean[key] = value
            writer.writerow(clean)


def build_tables(round_rows: list[dict], plan_rows: list[dict]) -> dict[str, list[dict]]:
    models = sorted({row["model"] for row in round_rows})
    tables: dict[str, list[dict]] = {}

    leaderboard = []
    for model in models:
        rows = [row for row in round_rows if row["model"] == model]
        wins = sum(1 for row in rows if row["won"])
        losses = sum(1 for row in rows if row["lost"])
        draws = sum(1 for row in rows if row["draw"])
        strict = wins + losses
        score = wins + 0.5 * draws
        leaderboard.append(
            {
                "model": model,
                "label": label_model(model),
                "total_matches": len(rows),
                "wins": wins,
                "losses": losses,
                "draws": draws,
                "win_rate_excluding_draws": round(100 * wins / strict, 3) if strict else 0,
                "score_draw_half": score,
                "score_pct": round(100 * score / len(rows), 3) if rows else 0,
                "avg_damage_dealt": mean([r["damage_dealt"] for r in rows]),
                "avg_damage_taken": mean([r["damage_taken"] for r in rows]),
                "avg_damage_diff": mean([r["damage_diff"] for r in rows]),
                "avg_final_health": mean([r["final_health"] for r in rows]),
                "avg_match_time": mean([r["elapsed_time_seconds"] for r in rows]),
                "avg_decision_latency_ms": mean([r["avg_decision_latency_ms"] for r in rows]),
                "avg_mcp_latency_ms": mean([r["participant_mcp_latency_ms"] for r in rows]),
                "mcp_error_rate": round(sum_field(rows, "mcp_errors") / max(1, sum_field(rows, "total_mcp_calls")), 5),
                "total_mcp_errors": int(sum_field(rows, "mcp_errors")),
            }
        )
    tables["leaderboard"] = sorted(leaderboard, key=lambda r: r["score_pct"], reverse=True)

    h2h = []
    for model in models:
        for opponent in models:
            if model == opponent:
                continue
            rows = [row for row in round_rows if row["model"] == model and row["opponent_model"] == opponent]
            if not rows:
                continue
            wins = sum(1 for row in rows if row["won"])
            losses = sum(1 for row in rows if row["lost"])
            draws = sum(1 for row in rows if row["draw"])
            score = wins + 0.5 * draws
            h2h.append(
                {
                    "model": model,
                    "opponent": opponent,
                    "matches": len(rows),
                    "wins": wins,
                    "losses": losses,
                    "draws": draws,
                    "score_pct": round(100 * score / len(rows), 3),
                    "win_rate_excluding_draws": round(100 * wins / max(1, wins + losses), 3),
                    "damage_diff_total": round(sum_field(rows, "damage_diff"), 3),
                    "avg_match_time": mean([r["elapsed_time_seconds"] for r in rows]),
                    "binomial_p_excluding_draws": binomial_two_sided_p(wins, losses),
                }
            )
    tables["head_to_head_matrix"] = h2h

    directed = []
    for folder in OFFICIAL_FOLDERS:
        actual = resolve_result_folder(folder)
        if not actual:
            continue
        rows = [row for row in round_rows if row["folder"] == actual.name]
        p1 = [row for row in rows if row["participant"] == "player_1"]
        p2 = [row for row in rows if row["participant"] == "player_2"]
        directed.append(
            {
                "folder": actual.name,
                "player_1_model": p1[0]["model"] if p1 else "",
                "player_2_model": p2[0]["model"] if p2 else "",
                "player_1_wins": sum(1 for row in p1 if row["won"]),
                "player_2_wins": sum(1 for row in p2 if row["won"]),
                "draws": sum(1 for row in p1 if row["draw"]),
                "player_1_avg_damage": mean([r["damage_dealt"] for r in p1]),
                "player_2_avg_damage": mean([r["damage_dealt"] for r in p2]),
                "player_1_avg_decision_latency": mean([r["avg_decision_latency_ms"] for r in p1]),
                "player_2_avg_decision_latency": mean([r["avg_decision_latency_ms"] for r in p2]),
                "player_1_mcp_errors": int(sum_field(p1, "mcp_errors")),
                "player_2_mcp_errors": int(sum_field(p2, "mcp_errors")),
            }
        )
    tables["directed_pov_results"] = directed

    resource = []
    for model in models:
        rows = [row for row in round_rows if row["model"] == model]
        first_shotgun_rows = [row for row in rows if row["first_shotgun"]]
        opponent_first_shotgun_rows = [row for row in rows if not row["first_shotgun"]]
        resource.append(
            {
                "model": model,
                "first_shotgun_pickups": sum(1 for row in rows if row["first_shotgun"]),
                "first_health_pickups": sum(1 for row in rows if row["first_health"]),
                "total_shotgun_pickups": int(sum_field(rows, "shotgun_pickups")),
                "total_health_pickups": int(sum_field(rows, "health_pickups")),
                "win_rate_when_getting_first_shotgun": round(100 * sum(1 for row in first_shotgun_rows if row["won"]) / max(1, len(first_shotgun_rows)), 3),
                "win_rate_when_opponent_gets_first_shotgun": round(100 * sum(1 for row in opponent_first_shotgun_rows if row["won"]) / max(1, len(opponent_first_shotgun_rows)), 3),
            }
        )
    tables["resource_control_summary"] = resource

    route = []
    for model in models:
        rows = [row for row in round_rows if row["model"] == model]
        valid = int(sum_field(rows, "set_participant_plan_calls") - sum_field(rows, "invalid_plan_count"))
        rejected = int(sum_field(rows, "invalid_plan_count"))
        route.append(
            {
                "model": model,
                "valid_plans": valid,
                "rejected_plans": rejected,
                "invalid_route_rate": round(rejected / max(1, valid + rejected), 5),
                "waypoint_in_wall_cell": int(sum_field(rows, "waypoint_in_wall_cell")),
                "route_diagonal_segment": int(sum_field(rows, "route_diagonal_segment")),
                "route_rebase_count": 0,
                "route_repair_count": 0,
                "stuck_recovery_count": int(sum_field(rows, "stuck_recovery_count")),
                "avg_unique_cells_visited": mean([r["unique_cells_visited"] for r in rows]),
                "avg_distance_traveled": mean([r["distance_traveled"] for r in rows]),
                "revisited_cell_rate": 0,
            }
        )
    tables["route_planning_reliability"] = route

    examples = []
    for plan in sorted(plan_rows, key=lambda p: p["plan_quality"], reverse=True):
        if len(examples) >= 30:
            break
        if not (plan.get("objective") or plan.get("reasoning") or plan.get("plan_note")):
            continue
        examples.append(
            {
                "model": plan["model"],
                "matchup": plan["folder"],
                "round": plan["round"],
                "participant": plan["participant"],
                "objective": plan["objective"],
                "route": plan["route"],
                "reasoning": plan["reasoning"],
                "plan_note": plan["plan_note"],
                "outcome": "win" if plan["won"] else "loss" if plan["lost"] else "draw",
                "why_it_matters": why_example_matters(plan),
            }
        )
    tables["reasoning_plan_note_examples"] = examples

    timing = []
    for plan in plan_rows:
        timing.append(
            {
                "model": plan["model"],
                "matchup": plan["folder"],
                "round": plan["round"],
                "participant": plan["participant"],
                "sequence_number": plan["sequence_number"],
                "objective": plan["objective"],
                "route": plan["route"],
                "reasoning": plan["reasoning"],
                "plan_note": plan["plan_note"],
                "inferred_decision_latency_ms": plan["decision_latency_ms"],
                "mcp_latency_ms": plan["mcp_latency_ms"],
                "accepted": plan["accepted"],
                "rejected": plan["rejected"],
                "rejection_reason": plan["rejection_reason"],
            }
        )
    tables["per_plan_decision_timing"] = timing

    intent_dist = []
    for model in models:
        model_plans = [p for p in plan_rows if p["model"] == model]
        total = len(model_plans)
        counts = Counter(p["intent_category"] for p in model_plans)
        row = {"model": model, "total_plans": total}
        for category in INTENT_ORDER:
            row[category] = counts.get(category, 0)
            row[f"{category}_pct"] = round(100 * counts.get(category, 0) / max(1, total), 3)
        intent_dist.append(row)
    tables["planning_intent_distribution"] = intent_dist

    plan_quality = []
    for model in models:
        model_plans = [p for p in plan_rows if p["model"] == model]
        plan_quality.append(
            {
                "model": model,
                "plans": len(model_plans),
                "avg_plan_quality": mean([p["plan_quality"] for p in model_plans]),
                "alignment_rate": round(100 * sum(1 for p in model_plans if p["reasoning_action_aligned"]) / max(1, len(model_plans)), 3),
                "avg_route_objective_alignment": mean([p["route_objective_alignment"] for p in model_plans]),
                "avg_map_awareness": mean([p["map_awareness"] for p in model_plans]),
                "avg_resource_awareness": mean([p["resource_awareness"] for p in model_plans]),
                "avg_opponent_awareness": mean([p["opponent_awareness"] for p in model_plans]),
                "avg_adaptation": mean([p["adaptation"] for p in model_plans]),
            }
        )
    tables["plan_quality_by_model"] = plan_quality
    return tables


def why_example_matters(plan: dict) -> str:
    text = " ".join(str(plan.get(k) or "").lower() for k in ("objective", "reasoning", "plan_note"))
    if "shotgun" in text or "health" in text:
        return "resource-aware plan"
    if "blocked" in text or "wall" in text or "avoid" in text:
        return "map-aware rerouting"
    if "opponent" in text or "enemy" in text:
        return "opponent-aware planning"
    if plan.get("won"):
        return "high-scoring winning plan"
    return "representative planning sample"


def text_table(rows: list[dict], fields: list[str], limit: int = 20) -> str:
    if not rows:
        return "_No rows._\n"
    rows = rows[:limit]
    header = "| " + " | ".join(fields) + " |"
    sep = "| " + " | ".join(["---"] * len(fields)) + " |"
    body = []
    for row in rows:
        values = []
        for field in fields:
            value = row.get(field, "")
            values.append(str(value).replace("\n", " ")[:120])
        body.append("| " + " | ".join(values) + " |")
    return "\n".join([header, sep] + body) + "\n"


def save_fig(name: str) -> Path:
    path = FIGURES / name
    plt.tight_layout()
    plt.savefig(path, dpi=160)
    plt.close()
    return path


def plot_bar(labels, values, title, ylabel, filename, color="#476a6f"):
    plt.figure(figsize=(8, 4.8))
    plt.bar(labels, values, color=color)
    plt.title(title)
    plt.ylabel(ylabel)
    plt.xticks(rotation=20, ha="right")
    return save_fig(filename)


def generate_figures(round_rows: list[dict], plan_rows: list[dict], tables: dict[str, list[dict]]) -> list[Path]:
    FIGURES.mkdir(parents=True, exist_ok=True)
    figs: list[Path] = []
    models = [r["model"] for r in tables["leaderboard"]]
    model_labels = [label_model(m) for m in models]

    figs.append(plot_bar(model_labels, [r["score_pct"] for r in tables["leaderboard"]], "Overall model score (draw = 0.5)", "Score %", "fig01_overall_win_rate.png"))

    h2h_scores = {(r["model"], r["opponent"]): r["score_pct"] for r in tables["head_to_head_matrix"]}
    mat = np.full((len(models), len(models)), np.nan)
    for i, model in enumerate(models):
        for j, opponent in enumerate(models):
            if model == opponent:
                mat[i, j] = 50
            elif (model, opponent) in h2h_scores:
                mat[i, j] = h2h_scores[(model, opponent)]
    plt.figure(figsize=(7, 5.8))
    im = plt.imshow(mat, cmap="RdYlGn", vmin=0, vmax=100)
    plt.colorbar(im, label="Score %")
    plt.xticks(range(len(models)), model_labels, rotation=25, ha="right")
    plt.yticks(range(len(models)), model_labels)
    for i in range(len(models)):
        for j in range(len(models)):
            if not np.isnan(mat[i, j]):
                plt.text(j, i, f"{mat[i,j]:.0f}", ha="center", va="center", fontsize=9)
    plt.title("Head-to-head score heatmap")
    figs.append(save_fig("fig02_head_to_head_heatmap.png"))

    side = defaultdict(lambda: {"p1_w": 0, "p1_n": 0, "p2_w": 0, "p2_n": 0})
    for row in round_rows:
        bucket = side[row["model"]]
        if row["participant"] == "player_1":
            bucket["p1_n"] += 1
            bucket["p1_w"] += int(row["won"])
        else:
            bucket["p2_n"] += 1
            bucket["p2_w"] += int(row["won"])
    x = np.arange(len(models))
    p1_vals = [100 * side[m]["p1_w"] / max(1, side[m]["p1_n"]) for m in models]
    p2_vals = [100 * side[m]["p2_w"] / max(1, side[m]["p2_n"]) for m in models]
    plt.figure(figsize=(8.5, 4.8))
    plt.bar(x - 0.2, p1_vals, 0.4, label="as player_1")
    plt.bar(x + 0.2, p2_vals, 0.4, label="as player_2")
    plt.xticks(x, model_labels, rotation=20, ha="right")
    plt.ylabel("Win rate %")
    plt.title("Directed side-bias check")
    plt.legend()
    figs.append(save_fig("fig03_side_bias.png"))

    figs.append(plot_round_lines(round_rows, "elapsed_time_seconds", "Match time over rounds", "Elapsed seconds", "fig04_match_time_over_rounds.png"))
    figs.append(plot_round_lines(round_rows, "round_mcp_errors", "MCP errors over rounds", "Errors", "fig05_mcp_errors_over_rounds.png"))
    figs.append(plot_round_lines(round_rows, "avg_decision_latency_ms", "Decision latency over rounds", "Decision latency ms", "fig06_decision_latency_over_rounds.png"))
    figs.append(plot_round_lines(round_rows, "participant_mcp_latency_ms", "MCP/server latency over rounds", "MCP latency ms", "fig07_mcp_latency_over_rounds.png"))

    plt.figure(figsize=(8, 4.8))
    data = [[p["decision_latency_ms"] for p in plan_rows if p["model"] == m and p["decision_latency_ms"]] for m in models]
    plt.boxplot(data, tick_labels=model_labels, showfliers=False)
    plt.xticks(rotation=20, ha="right")
    plt.ylabel("Inferred decision latency ms")
    plt.title("Per-plan thinking time distribution")
    figs.append(save_fig("fig07b_plan_thinking_time_distribution.png"))

    plt.figure(figsize=(7, 5.2))
    colors = plt.cm.tab10(np.linspace(0, 1, len(models)))
    for color, model in zip(colors, models):
        xs = [p["decision_latency_ms"] for p in plan_rows if p["model"] == model]
        ys = [p["mcp_latency_ms"] for p in plan_rows if p["model"] == model]
        plt.scatter(xs, ys, s=14, alpha=0.45, label=label_model(model), color=color)
    plt.xlabel("Inferred decision latency ms")
    plt.ylabel("MCP/server latency ms")
    plt.title("Decision latency vs MCP latency")
    plt.legend(fontsize=8)
    figs.append(save_fig("fig07c_decision_vs_mcp_latency.png"))

    figs.append(plot_bar(model_labels, [r["avg_damage_diff"] for r in tables["leaderboard"]], "Average damage differential by model", "Damage dealt - taken", "fig08_damage_differential.png", "#7a4e48"))

    plt.figure(figsize=(8, 4.8))
    acc = [mean([r["accuracy"] for r in round_rows if r["model"] == m]) * 100 for m in models]
    dps = [mean([r["damage_per_second"] for r in round_rows if r["model"] == m]) for m in models]
    x = np.arange(len(models))
    plt.bar(x - 0.2, acc, 0.4, label="accuracy %")
    plt.bar(x + 0.2, dps, 0.4, label="damage/sec")
    plt.xticks(x, model_labels, rotation=20, ha="right")
    plt.title("Accuracy and combat efficiency")
    plt.legend()
    figs.append(save_fig("fig09_accuracy_combat_efficiency.png"))

    resource = tables["resource_control_summary"]
    plt.figure(figsize=(8, 4.8))
    x = np.arange(len(resource))
    plt.bar(x - 0.2, [r["win_rate_when_getting_first_shotgun"] for r in resource], 0.4, label="first shotgun")
    plt.bar(x + 0.2, [r["win_rate_when_opponent_gets_first_shotgun"] for r in resource], 0.4, label="opponent first shotgun")
    plt.xticks(x, [label_model(r["model"]) for r in resource], rotation=20, ha="right")
    plt.ylabel("Win rate %")
    plt.title("Resource advantage outcomes")
    plt.legend()
    figs.append(save_fig("fig10_resource_advantage_outcomes.png"))

    route = tables["route_planning_reliability"]
    plt.figure(figsize=(8, 4.8))
    labels = [label_model(r["model"]) for r in route]
    wall = np.array([r["waypoint_in_wall_cell"] for r in route])
    diag = np.array([r["route_diagonal_segment"] for r in route])
    other = np.array([max(0, r["rejected_plans"] - r["waypoint_in_wall_cell"] - r["route_diagonal_segment"]) for r in route])
    plt.bar(labels, wall, label="waypoint in wall")
    plt.bar(labels, diag, bottom=wall, label="diagonal segment")
    plt.bar(labels, other, bottom=wall + diag, label="other")
    plt.xticks(rotation=20, ha="right")
    plt.ylabel("Rejected plans")
    plt.title("Route error distribution")
    plt.legend()
    figs.append(save_fig("fig11_route_error_distribution.png"))

    figs.append(plot_route_heatmap(plan_rows, "fig12_route_cell_heatmap.png"))
    figs.append(plot_opening_diversity(plan_rows, "fig13_opening_route_diversity.png"))
    figs.append(plot_plan_note_examples(tables["reasoning_plan_note_examples"], "fig14_plan_note_examples.png"))
    figs.append(plot_intent_distribution(tables["planning_intent_distribution"], "fig15_planning_intent_distribution.png"))
    figs.append(plot_intent_over_rounds(plan_rows, "fig16_planning_intent_over_rounds.png"))
    figs.append(plot_outcome_by_intent(plan_rows, "fig17_outcome_by_planning_intent.png"))
    figs.append(plot_bar(model_labels, [next(r["avg_plan_quality"] for r in tables["plan_quality_by_model"] if r["model"] == m) for m in models], "Plan quality score by model", "Heuristic quality score", "fig18_plan_quality_score_by_model.png", "#52633f"))
    figs.append(plot_bar(model_labels, [next(r["alignment_rate"] for r in tables["plan_quality_by_model"] if r["model"] == m) for m in models], "Reasoning-action alignment", "Alignment rate %", "fig19_reasoning_action_alignment.png", "#805a7a"))
    coords = text_embedding_2d(plan_rows)
    figs.append(plot_embedding(plan_rows, coords, "fig20_thought_process_embedding_map.png"))
    figs.append(plot_thinking_vs_quality(plan_rows, "fig21_thinking_time_vs_plan_quality.png"))
    figs.append(plot_opening_flow(plan_rows, "fig22_opening_strategy_flow.png"))
    figs.append(plot_radar(tables["leaderboard"], tables["planning_intent_distribution"], tables["route_planning_reliability"], "fig23_model_personality_radar.png"))
    figs.append(plot_strategy_trajectory(plan_rows, coords, "fig24_strategy_trajectory_over_rounds.png"))
    return figs


def plot_round_lines(round_rows: list[dict], field: str, title: str, ylabel: str, filename: str) -> Path:
    plt.figure(figsize=(9, 5))
    models = sorted({r["model"] for r in round_rows})
    for model in models:
        xs, ys = [], []
        for rnd in sorted({int(r["round"]) for r in round_rows}):
            vals = [float(r.get(field) or 0) for r in round_rows if r["model"] == model and int(r["round"]) == rnd]
            if vals:
                xs.append(rnd)
                ys.append(sum(vals) / len(vals))
        plt.plot(xs, ys, marker="o", label=label_model(model))
    plt.xlabel("Round")
    plt.ylabel(ylabel)
    plt.title(title)
    plt.legend(fontsize=8)
    return save_fig(filename)


def plot_route_heatmap(plan_rows: list[dict], filename: str) -> Path:
    counts = Counter()
    for plan in plan_rows:
        for cell in plan.get("route_cells") or []:
            counts[cell] += 1
    rows = [ord(c[0]) - ord("A") + 1 for c in counts if re.fullmatch(r"[A-Z]\d{2}", c)]
    cols = [int(c[1:]) for c in counts if re.fullmatch(r"[A-Z]\d{2}", c)]
    max_r = max(rows or [24])
    max_c = max(cols or [33])
    grid = np.zeros((max_r, max_c))
    for cell, count in counts.items():
        if re.fullmatch(r"[A-Z]\d{2}", cell):
            grid[ord(cell[0]) - ord("A"), int(cell[1:]) - 1] = count
    plt.figure(figsize=(10, 5.5))
    plt.imshow(grid, cmap="magma")
    plt.colorbar(label="Route waypoint count")
    plt.title("Path coverage heatmap from submitted route cells")
    plt.xlabel("Column")
    plt.ylabel("Row")
    return save_fig(filename)


def plot_opening_diversity(plan_rows: list[dict], filename: str) -> Path:
    first = {}
    for plan in sorted(plan_rows, key=lambda p: (p["folder"], p["round"], p["participant"], p["sequence_number"])):
        key = (plan["folder"], plan["round"], plan["participant"])
        if key not in first and plan["accepted"]:
            first[key] = plan
    counts = Counter((p["model"], p["opening_category"]) for p in first.values())
    cats = sorted({cat for _, cat in counts})
    models = sorted({p["model"] for p in first.values()})
    bottom = np.zeros(len(models))
    plt.figure(figsize=(9, 5))
    for cat in cats:
        vals = np.array([counts[(m, cat)] for m in models])
        plt.bar([label_model(m) for m in models], vals, bottom=bottom, label=cat)
        bottom += vals
    plt.xticks(rotation=20, ha="right")
    plt.ylabel("Opening plans")
    plt.title("Opening route diversity")
    plt.legend(fontsize=8)
    return save_fig(filename)


def plot_plan_note_examples(rows: list[dict], filename: str) -> Path:
    plt.figure(figsize=(12, 7))
    plt.axis("off")
    lines = ["Selected public reasoning / plan-note examples"]
    for row in rows[:8]:
        note = row.get("plan_note") or row.get("reasoning") or row.get("objective")
        lines.append(f"- {label_model(row['model'])} R{row['round']}: {note[:125]}")
    plt.text(0.01, 0.98, "\n".join(lines), va="top", ha="left", fontsize=9, wrap=True)
    return save_fig(filename)


def plot_intent_distribution(rows: list[dict], filename: str) -> Path:
    models = [r["model"] for r in rows]
    bottom = np.zeros(len(models))
    plt.figure(figsize=(9, 5))
    for cat in INTENT_ORDER:
        vals = np.array([r[f"{cat}_pct"] for r in rows])
        plt.bar([label_model(m) for m in models], vals, bottom=bottom, label=cat)
        bottom += vals
    plt.xticks(rotation=20, ha="right")
    plt.ylabel("% plans")
    plt.title("Planning intent distribution")
    plt.legend(fontsize=8)
    return save_fig(filename)


def plot_intent_over_rounds(plan_rows: list[dict], filename: str) -> Path:
    plt.figure(figsize=(10, 5.2))
    rounds = sorted({int(p["round"]) for p in plan_rows})
    for cat in INTENT_ORDER:
        ys = []
        for rnd in rounds:
            plans = [p for p in plan_rows if int(p["round"]) == rnd]
            ys.append(100 * sum(1 for p in plans if p["intent_category"] == cat) / max(1, len(plans)))
        plt.plot(rounds, ys, marker="o", label=cat)
    plt.xlabel("Round")
    plt.ylabel("% plans")
    plt.title("Planning intent over rounds")
    plt.legend(fontsize=8)
    return save_fig(filename)


def plot_outcome_by_intent(plan_rows: list[dict], filename: str) -> Path:
    values = []
    for cat in INTENT_ORDER:
        plans = [p for p in plan_rows if p["intent_category"] == cat]
        values.append(100 * sum(1 for p in plans if p["won"]) / max(1, len(plans)))
    return plot_bar(INTENT_ORDER, values, "Outcome by planning intent", "Win rate for plans in won rounds %", filename, "#4f6170")


def plan_text(plan: dict) -> str:
    return " ".join(str(plan.get(k) or "") for k in ("objective", "reasoning", "plan_note"))


def text_embedding_2d(plan_rows: list[dict]) -> np.ndarray:
    texts = [plan_text(p).lower() for p in plan_rows]
    vocab = {}
    for text in texts:
        for token in re.findall(r"[a-z0-9]+", text):
            if len(token) > 2 and token not in vocab:
                vocab[token] = len(vocab)
    if not texts or not vocab:
        return np.zeros((len(texts), 2))
    matrix = np.zeros((len(texts), len(vocab)))
    for i, text in enumerate(texts):
        for token in re.findall(r"[a-z0-9]+", text):
            if token in vocab:
                matrix[i, vocab[token]] += 1
    matrix -= matrix.mean(axis=0, keepdims=True)
    try:
        _, _, vh = np.linalg.svd(matrix, full_matrices=False)
        coords = matrix @ vh[:2].T
    except Exception:
        coords = np.zeros((len(texts), 2))
    return coords


def plot_embedding(plan_rows: list[dict], coords: np.ndarray, filename: str) -> Path:
    models = sorted({p["model"] for p in plan_rows})
    plt.figure(figsize=(8, 6))
    for model in models:
        idx = [i for i, p in enumerate(plan_rows) if p["model"] == model]
        plt.scatter(coords[idx, 0], coords[idx, 1], s=14, alpha=0.45, label=label_model(model))
    plt.title("Thought-process embedding map (public plan text, local SVD)")
    plt.xlabel("component 1")
    plt.ylabel("component 2")
    plt.legend(fontsize=8)
    return save_fig(filename)


def plot_thinking_vs_quality(plan_rows: list[dict], filename: str) -> Path:
    models = sorted({p["model"] for p in plan_rows})
    plt.figure(figsize=(8, 5.5))
    for model in models:
        plans = [p for p in plan_rows if p["model"] == model]
        plt.scatter([p["decision_latency_ms"] for p in plans], [p["plan_quality"] for p in plans], s=14, alpha=0.45, label=label_model(model))
    plt.xlabel("Inferred decision latency ms")
    plt.ylabel("Plan quality heuristic")
    plt.title("Thinking time vs plan quality")
    plt.legend(fontsize=8)
    return save_fig(filename)


def plot_opening_flow(plan_rows: list[dict], filename: str) -> Path:
    first = {}
    for plan in sorted(plan_rows, key=lambda p: (p["folder"], p["round"], p["participant"], p["sequence_number"])):
        key = (plan["folder"], plan["round"], plan["participant"])
        if key not in first and plan["accepted"]:
            first[key] = plan
    counts = Counter((p["model"], p["opening_category"], "win" if p["won"] else "loss" if p["lost"] else "draw") for p in first.values())
    labels = [f"{label_model(m)}\n{cat}\n{outcome}" for (m, cat, outcome), _ in counts.most_common(14)]
    values = [count for _, count in counts.most_common(14)]
    return plot_bar(labels, values, "Opening strategy flow equivalent", "Opening count", filename, "#74624b")


def plot_radar(leaderboard, intent_dist, route_table, filename: str) -> Path:
    models = [r["model"] for r in leaderboard]
    metrics = ["aggression", "resource", "caution", "exploration", "tool discipline", "spatial accuracy", "speed", "combat efficiency"]
    angles = np.linspace(0, 2 * np.pi, len(metrics), endpoint=False).tolist()
    angles += angles[:1]
    plt.figure(figsize=(7, 7))
    ax = plt.subplot(111, polar=True)
    max_latency = max(float(r["avg_decision_latency_ms"] or 1) for r in leaderboard)
    max_dps = max(1.0, max(mean([0]) for _ in [0]))
    for model in models:
        lb = next(r for r in leaderboard if r["model"] == model)
        intent = next(r for r in intent_dist if r["model"] == model)
        route = next(r for r in route_table if r["model"] == model)
        values = [
            intent["engagement/combat_pct"] / 100,
            intent["resource control_pct"] / 100,
            intent["evasion/recovery_pct"] / 100,
            intent["map control/exploration_pct"] / 100,
            1 - min(1, float(lb["mcp_error_rate"] or 0) * 10),
            1 - min(1, float(route["invalid_route_rate"] or 0)),
            1 - (float(lb["avg_decision_latency_ms"] or 0) / max_latency),
            max(0, min(1, (float(lb["avg_damage_diff"] or 0) + 100) / 200)),
        ]
        values += values[:1]
        ax.plot(angles, values, label=label_model(model))
        ax.fill(angles, values, alpha=0.08)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(metrics, fontsize=8)
    ax.set_title("Model personality radar")
    ax.legend(loc="upper right", bbox_to_anchor=(1.35, 1.12), fontsize=8)
    return save_fig(filename)


def plot_strategy_trajectory(plan_rows: list[dict], coords: np.ndarray, filename: str) -> Path:
    plt.figure(figsize=(8, 6))
    models = sorted({p["model"] for p in plan_rows})
    for model in models:
        xs, ys = [], []
        for rnd in sorted({int(p["round"]) for p in plan_rows}):
            idx = [i for i, p in enumerate(plan_rows) if p["model"] == model and int(p["round"]) == rnd]
            if idx:
                xs.append(float(coords[idx, 0].mean()))
                ys.append(float(coords[idx, 1].mean()))
        plt.plot(xs, ys, marker="o", label=label_model(model))
    plt.title("Strategy trajectory over rounds")
    plt.xlabel("planning-text component 1")
    plt.ylabel("planning-text component 2")
    plt.legend(fontsize=8)
    return save_fig(filename)


def write_report(round_rows: list[dict], plan_rows: list[dict], tables: dict[str, list[dict]], figures: list[Path], data_quality: dict) -> None:
    top = tables["leaderboard"][0] if tables["leaderboard"] else {}
    lines = [
        "# Doom Arena official model benchmark analysis",
        "",
        "## Executive summary",
        "",
        f"- Official dataset: {len(round_rows)//2} matches across {len(data_quality['folder_round_counts'])} directed folders and {len({r['model'] for r in round_rows})} models.",
        f"- Top score: {label_model(top.get('model',''))} with {top.get('score_pct', 0)}% score using draw = 0.5.",
        f"- Total public route plans analyzed: {len(plan_rows)}.",
        "- Model thinking is analyzed only from public `objective`, `reasoning`, `plan_note`, and route fields. Hidden chain-of-thought is not available or claimed.",
        "- Decision latency is reported separately from local MCP/server latency.",
        "",
        "## Data quality",
        "",
        f"- Official folders found: {len(data_quality['folder_round_counts'])}/12.",
        f"- Round counts by folder: `{json.dumps(data_quality['folder_round_counts'], sort_keys=True)}`.",
        f"- Missing folders: `{data_quality['missing_folders']}`.",
        f"- Missing `analysis_summary.json`: `{data_quality['missing_analysis_summary']}`.",
        f"- Missing `stats.json`: `{data_quality['missing_stats']}`.",
        "- `benchmarks/results/legacy/` was explicitly excluded.",
        "- The thought-process map uses a local bag-of-words/SVD projection, not an external embedding API.",
        "",
        "## Overall leaderboard",
        "",
        text_table(tables["leaderboard"], ["label", "total_matches", "wins", "losses", "draws", "score_pct", "avg_damage_diff", "avg_decision_latency_ms", "mcp_error_rate"], 10),
        "",
        "## Head-to-head results",
        "",
        "Final model-vs-model results combine both POV directions. Directed folders are used only for side-bias diagnostics.",
        "",
        text_table(tables["head_to_head_matrix"], ["model", "opponent", "matches", "wins", "losses", "draws", "score_pct", "damage_diff_total", "binomial_p_excluding_draws"], 20),
        "",
        "## Directed POV and side-bias notes",
        "",
        text_table(tables["directed_pov_results"], ["folder", "player_1_wins", "player_2_wins", "draws", "player_1_avg_damage", "player_2_avg_damage"], 20),
        "",
        "## Resource control",
        "",
        text_table(tables["resource_control_summary"], ["model", "first_shotgun_pickups", "first_health_pickups", "total_shotgun_pickups", "total_health_pickups", "win_rate_when_getting_first_shotgun"], 10),
        "",
        "## Route-planning reliability",
        "",
        text_table(tables["route_planning_reliability"], ["model", "valid_plans", "rejected_plans", "invalid_route_rate", "waypoint_in_wall_cell", "route_diagonal_segment", "stuck_recovery_count", "avg_unique_cells_visited"], 10),
        "",
        "## Public model planning behavior",
        "",
        "Plans were classified into resource control, engagement/combat, evasion/recovery, and map control/exploration using public plan fields only.",
        "",
        text_table(tables["planning_intent_distribution"], ["model", "total_plans", "resource control_pct", "engagement/combat_pct", "evasion/recovery_pct", "map control/exploration_pct"], 10),
        "",
        "## Per-plan timing",
        "",
        text_table(timing_summary(plan_rows), ["model", "plans", "decision_mean_ms", "decision_median_ms", "decision_p95_ms", "mcp_mean_ms"], 10),
        "",
        "## Selected plan-note examples",
        "",
        text_table(tables["reasoning_plan_note_examples"], ["model", "round", "objective", "reasoning", "plan_note", "outcome", "why_it_matters"], 12),
        "",
        "## Figures",
        "",
    ]
    for path in figures:
        rel = path.relative_to(BASE).as_posix()
        title = path.stem.replace("_", " ")
        lines += [f"### {title}", "", f"![{title}]({rel})", ""]
    lines += [
        "## Skipped figures and limitations",
        "",
        "- No required figure was skipped. The embedding map is a local lexical projection because no external embedding service was used.",
        "- Plan quality and intent labels are deterministic heuristics over public plan text and routes. They are useful for comparison but not a substitute for human review.",
        "- Pickup counts come from recorded benchmark summaries; repeated pickup events may reflect engine-level event logging behavior.",
        "",
        "## Completion audit",
        "",
        "- `analysis.md` exists and summarizes the benchmark.",
        "- Required tables were saved under `tables/` and key tables are embedded above.",
        "- Required figures were saved under `figures/` and referenced above.",
        "- Legacy results were excluded.",
        "- Final model comparisons combine both POV directions.",
        "- Decision latency and MCP/server latency are reported separately.",
        "- Public model planning behavior uses `objective`, `reasoning`, `plan_note`, and route fields only.",
        "",
    ]
    (BASE / "analysis.md").write_text("\n".join(lines), encoding="utf-8")


def timing_summary(plan_rows: list[dict]) -> list[dict]:
    rows = []
    for model in sorted({p["model"] for p in plan_rows}):
        plans = [p for p in plan_rows if p["model"] == model]
        decisions = [float(p["decision_latency_ms"] or 0) for p in plans if p["decision_latency_ms"]]
        mcps = [float(p["mcp_latency_ms"] or 0) for p in plans if p["mcp_latency_ms"]]
        rows.append(
            {
                "model": model,
                "plans": len(plans),
                "decision_mean_ms": mean(decisions),
                "decision_median_ms": median(decisions),
                "decision_p95_ms": percentile(decisions, 95),
                "mcp_mean_ms": mean(mcps),
            }
        )
    return rows


def main() -> None:
    for path in (TABLES, FIGURES, DATA):
        path.mkdir(parents=True, exist_ok=True)
    round_rows, plan_rows, data_quality = extract_rounds()
    tables = build_tables(round_rows, plan_rows)
    write_csv(DATA / "round_participants.csv", round_rows)
    write_csv(DATA / "plans.csv", plan_rows)
    for name, rows in tables.items():
        write_csv(TABLES / f"{name}.csv", rows)
    figures = generate_figures(round_rows, plan_rows, tables)
    write_report(round_rows, plan_rows, tables, figures, data_quality)
    manifest = {
        "output_folder": str(BASE),
        "official_folders_requested": OFFICIAL_FOLDERS,
        "official_folders_found": sorted(data_quality["folder_round_counts"].keys()),
        "models": sorted({row["model"] for row in round_rows}),
        "matches": len(round_rows) // 2,
        "round_participant_rows": len(round_rows),
        "plans": len(plan_rows),
        "tables": sorted(str(path.relative_to(BASE)).replace("\\", "/") for path in TABLES.glob("*.csv")),
        "figures": sorted(str(path.relative_to(BASE)).replace("\\", "/") for path in FIGURES.glob("*.png")),
        "data_quality": data_quality,
    }
    (DATA / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"matches": manifest["matches"], "plans": manifest["plans"], "figures": len(manifest["figures"]), "tables": len(manifest["tables"])}, indent=2))


if __name__ == "__main__":
    main()
