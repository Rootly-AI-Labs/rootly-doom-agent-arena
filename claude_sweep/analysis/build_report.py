"""Generate the active all-medium README and sweep index."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

HERE = Path(__file__).resolve().parent
COHORT = "all_medium_60_round_sweep"
ORDER = ("opus", "fable", "sonnet")
IDS = {"session_8fdec3c440b4", "session_5188b2ed236f", "session_572d2d193f0a",
       "session_acd0e0242118", "session_60e8ac8a1dda", "session_da8fd5b5d730"}
FIGURES = (
    ("claude-output-token-price-vs-win-rate", "All-medium win rate versus output-token list price"),
    ("claude-pairwise-win-rate", "All-medium head-to-head win rates"),
    ("claude-player-side-performance", "All-medium win rates by player position"),
    ("claude-decision-time-and-route-validity", "All-medium decision intervals and route rejection rates"),
    ("claude-wins-per-dollar", "Claude wins per observed API-equivalent dollar: Opus 1.87, Sonnet 0.83, Fable 0.55"),
)


def load(name):
    return json.loads((HERE / name).read_text(encoding="utf-8-sig"))


def table(headers, rows, right_align_from=None):
    return "\n".join(["| " + " | ".join(headers) + " |",
                      "| " + " | ".join("---:" if right_align_from is not None and i >= right_align_from else "---" for i, _ in enumerate(headers)) + " |",
                      *("| " + " | ".join(map(str, row)) + " |" for row in rows)])


def record(wins, losses):
    return f"{wins}–{losses}"


def image(i):
    stem, label = FIGURES[i]
    return f"![{label}](figures/{stem}.png)\n\n[PNG](figures/{stem}.png) · [SVG](figures/{stem}.svg)"


def archive(row, prefix="../"):
    return f"[{row['session_id']}]({quote(prefix + row['path'] + '/', safe='/')})"


def build(m, c, pricing):
    assert m["cohort"] == c["cohort"] == COHORT
    assert set(m["pinned_session_ids"]) == set(c["pinned_arena_session_ids"]) == IDS
    assert m["validation"]["all_participants_medium_verified"]
    assert m["validation"]["effort_verified_participants"] == 12
    assert m["matches"] == 60 and m["validation"]["duplicate_run_ids"] == 0
    models, series, v, audit = m["models"], m["series"], m["validation"], m["telemetry_audit"]
    costs = {k: c["by_model"][models[k]["model_id"]] for k in ORDER}
    participants = {(p["arena_session_id"], p["participant_id"]): p for p in c["participants"]}
    assert len(series) == 6 and len(participants) == 12
    for s in series:
        for pid in ("player_1", "player_2"):
            p = participants[(s["session_id"], pid)]
            assert p["model_id"] == models[s[pid]]["model_id"]
            assert set(p["effort_by_message_count"]) == set(p["effort_by_api_request_count"]) == {"medium"}
    snapshots = [p for p in c["participants"] if p.get("recorded_cost_state") is not None]
    snapshot_total = sum(p["recorded_cost_state"]["total_api_equivalent_usd"] for p in snapshots)
    extra_primary = sum(p["recorded_cost_state"].get("primary_model_usd", 0) >
                        p["main_thread_api_equivalent"]["total_usd"] + 0.000001 for p in snapshots)
    coverage = c["coverage"]
    opus, fable, sonnet = (models[k] for k in ORDER)
    observed_costs = {k: costs[k]["main_thread_api_equivalent"]["total_usd"] for k in ORDER}
    assert all(value > 0 for value in observed_costs.values())
    wins_per_dollar = {k: models[k]["wins"] / observed_costs[k] for k in ORDER}
    best_efficiency = max(wins_per_dollar.values())
    efficiency = {k: wins_per_dollar[k] / best_efficiency for k in ORDER}
    assert all(0 <= value <= 1 for value in efficiency.values())
    leaders = {field: max(models[k][field] for k in ORDER)
               for field in ("win_rate", "accuracy", "damage_differential_per_match")}
    fastest = min(models[k]["mean_decision_seconds"] for k in ORDER)

    def highlight(text, leading, badge=""):
        return "**" + text + badge + "**" if leading else text

    ranked = sorted(ORDER, key=lambda k: models[k]["win_rate"], reverse=True)
    leaderboard = table(["Rank", "Model", "Win rate", "Wins–Losses", "Decision speed", "Accuracy", "Damage diff", "Win rate / cost"], [
        [rank, models[k]["label"],
         highlight(f"{models[k]['win_rate']:.1%}", models[k]["win_rate"] == leaders["win_rate"]),
         record(models[k]["wins"], models[k]["losses"]),
         highlight(f"{models[k]['mean_decision_seconds']:.2f}s", models[k]["mean_decision_seconds"] == fastest, " ⚡"),
         highlight(f"{models[k]['accuracy']:.1%}", models[k]["accuracy"] == leaders["accuracy"]),
         highlight(f"{models[k]['damage_differential_per_match']:+.2f}", models[k]["damage_differential_per_match"] == leaders["damage_differential_per_match"]),
         highlight(f"{efficiency[k]:.2f}×", wins_per_dollar[k] == best_efficiency)]
        for rank, k in enumerate(ranked, 1)], right_align_from=2)
    leaderboard_notes = (
        "Bold marks the category leader; ⚡ marks the fastest decisions. All models used medium effort.\n\n"
        "- **Win rate** = wins ÷ matches played.\n"
        "- **Decision speed** = mean interval from observation completion to a plan submission; lower is faster. It includes host/orchestration time, retries, and rejected attempts, not only model inference.\n"
        "- **Accuracy** = total shots hit ÷ total shots fired.\n"
        "- **Damage diff** = average damage dealt minus opponent damage dealt per match.\n"
        "- **Win rate / cost** = wins per estimated API dollar, normalized so the best model = 1.00×. The denominator uses observed primary-thread usage across winning and losing matches at Standard API rates.\n\n"
        "**Cost scope:** these are API-equivalent estimates from recorded primary-model responses, including input, cache reads/writes, and output. They are not complete full-session costs or actual billed charges: one request lacks response usage, and background usage is incomplete. They are not directly comparable with a leaderboard using full-session costs."
    )
    efficiency_summary = (
        f"Opus delivered the most wins per observed API-equivalent dollar: **{wins_per_dollar['opus']:.2f}**, "
        f"compared with Sonnet's **{wins_per_dollar['sonnet']:.2f}** and Fable's **{wins_per_dollar['fable']:.2f}**. "
        "Opus won the most matches; Sonnet made the fastest decisions."
    )
    tested_models = "Models tested: " + ", ".join(chr(96) + models[k]["model_id"] + chr(96) for k in ranked) + "."
    pair_rows = []
    for focal, opponent in (("opus", "sonnet"), ("opus", "fable"), ("fable", "sonnet")):
        a = next(s for s in series if (s["player_1"], s["player_2"]) == (focal, opponent))
        b = next(s for s in series if (s["player_1"], s["player_2"]) == (opponent, focal))
        h = m["head_to_head"][focal][opponent]
        pair_rows.append([models[focal]["label"], models[opponent]["label"], record(a["p1_wins"], a["p2_wins"]),
                          record(b["p2_wins"], b["p1_wins"]), record(h["wins"], h["losses"]), f"{h['win_rate']:.0%}"])
    side_rows = [[models[k]["label"], *(f"{record(models[k]['side_counts'][p]['wins'], models[k]['side_counts'][p]['losses'])} ({models[k]['side_counts'][p]['win_rate']:.0%})"
                  for p in ("player_1", "player_2"))] for k in ORDER]
    timing_rows = [[models[k]["label"], models[k]["decision_count"], *(f"{models[k][field]:.3f} s"
                    for field in ("mean_decision_seconds", "median_decision_seconds", "p95_decision_seconds"))] for k in ORDER]
    route_rows = [[models[k]["label"], *(models[k]["plan_outcomes"][o] for o in ("accepted", "diagonal", "blocked", "waypoint_limit", "stationary")),
                   f"{models[k]['route_rejections']}/{models[k]['route_validation_attempts']}", f"{models[k]['route_rejection_rate']:.1%}"] for k in ORDER]
    operation_rows = [[models[k]["label"], models[k]["plan_outcomes"]["post_finish"], models[k]["plan_outcomes"]["run_mismatch"],
                       models[k]["plan_calls"], f"{models[k]['rejected_plans']}/{models[k]['plan_calls']} ({models[k]['all_plan_error_rate']:.1%})"] for k in ORDER]
    fields = (("Uncached input", "input_tokens"), ("Cache-read input", "cache_read_input_tokens"),
              ("One-hour cache-write input", "cache_write_1h_tokens"), ("Output", "output_tokens"),
              ("Thinking, included in output", "thinking_tokens_in_output"))
    token_rows = [[label, *(f"{costs[k]['tokens'][field]:,}" for k in ORDER)] for label, field in fields]
    token_rows.append(["Unique API responses", *(f"{costs[k]['unique_api_messages']:,}" for k in ORDER)])
    cost_rows = [[models[k]["label"], f"${costs[k]['main_thread_api_equivalent']['total_usd']:.8f}",
                  f"${costs[k]['mean_main_thread_usd_per_round_appearance']:.4f}",
                  f"{sum(p['model_id'] == models[k]['model_id'] for p in snapshots)}/4"] for k in ORDER]
    price_rows = [[models[k]["label"], *(f"${pricing['models'][models[k]['model_id']][field]:g}" for field in
                   ("input_usd_per_million", "cache_read_usd_per_million", "cache_write_1h_usd_per_million", "output_usd_per_million"))] for k in ORDER]
    series_rows = []
    for s in series:
        common = [models[s["player_1"]]["label"], models[s["player_2"]]["label"], record(s["p1_wins"], s["p2_wins"])]
        amounts = [f"${participants[(s['session_id'], pid)]['main_thread_api_equivalent']['total_usd']:.4f}" for pid in ("player_1", "player_2")]
        series_rows.append([s["setup"], archive(s), *common, *amounts])
    no_intervals = sum(t["plan_calls_without_decision_interval"] for t in models.values())
    reused = audit["decision_interval_filter"]["additional_intervals_reusing_observation"]
    tails = ", ".join(f"{r['seconds']:.3f} s" for r in audit["largest_decision_intervals"]["fable"][:3])
    non_plan_errors = sum(sum(x.values()) for x in audit["non_plan_error_outcomes"].values())
    inputs = sum(e["exists"] for e in m["input_manifest"])
    missing = len(m["input_manifest"]) - inputs
    title = f"# Claude Opus 5.5 in Doom: {opus['wins']} wins in {opus['matches']} matches"
    sections = [
        title,
        "**Completed all-medium comparison:** Opus 5.5, Fable 5.1, and Sonnet 5.5 all ran at **medium effort**, verified from actual API metadata for all twelve participant conversations. This is the active 60-match report. Earlier high-effort Fable runs are excluded; their raw archives and the mixed-effort report were removed during cleanup.",
        f"Opus finished **{record(opus['wins'], opus['losses'])} ({opus['win_rate']:.1%})**, Fable **{record(fable['wins'], fable['losses'])} ({fable['win_rate']:.1%})**, and Sonnet **{record(sonnet['wins'], sonnet['losses'])} ({sonnet['win_rate']:.1%})**. Each model appeared 40 times: 20 against each opponent and 20 in each player position. All {v['eliminations']} matches ended by elimination; there were no draws.",
        image(0),
        "The x-axis is published **output-token list price**, not total match cost. Equal effort labels improve comparability but do not establish equal inference compute across different models. Results describe the complete agent systems used here.",
        "## Most interesting results",
        "- **Opus led both overall pairings:** 20–0 against Sonnet and 13–7 against Fable.\n"
        "- **The Opus–Fable result reversed with series orientation:** Opus lost 3–7 as Player 1, then won 10–0 as Player 2. A model-only explanation is insufficient.\n"
        "- **Fable and Sonnet split their matchup 10–10, with Player 1 winning every round:** Sonnet won 10–0 as Player 1, and Fable won 10–0 after positions switched. Side, chronology, and conversation history are intertwined; the scores do not identify which caused the result.\n"
        f"- **Sonnet remained fastest and made the fewest invalid routes:** {sonnet['mean_decision_seconds']:.2f}-second mean decision intervals and {sonnet['route_rejection_rate']:.1%} route rejection, alongside a {sonnet['win_rate']:.1%} win rate. Speed and valid geometry alone did not guarantee wins.\n"
        f"- **Opus also had the best pooled shooting results:** {opus['accuracy']:.1%} accuracy and {opus['damage_differential_per_match']:+.2f} damage per match. These outcomes do not prove a particular tactic caused its advantage.",
        "## Leaderboard", leaderboard, leaderboard_notes, efficiency_summary, image(4), tested_models,
        "All entries use medium effort. Shot accuracy pools hits and shots: " + "; ".join(f"{models[k]['label']} **{models[k]['hits']}/{models[k]['shots']}**" for k in ORDER) + ". Damage differential is total damage dealt minus opponents' damage dealt, divided by appearances. These are not averages of round-level percentages.",
        "## Head-to-head and player positions",
        table(["Focal model", "Opponent", "Focal as P1", "Focal as P2", "Combined wins–losses", "Win rate"], pair_rows), image(1),
        table(["Model", "Player 1 record", "Player 2 record"], side_rows), image(2),
        "Positions were swapped after each ten-round series. That balances appearances but does not randomize individual rounds or erase history. Extreme series reversals and small samples are reasons to report both orientations, rather than treating pooled rates as precise estimates of general model ability.",
        "## Cohort selection and completed series",
        "The primary cohort uses the **first completed medium-effort series for each ordered pairing**. It retains the original 20 Opus–Sonnet rounds, already at medium, and adds 40 medium-effort Fable rerun rounds. Selection follows completion chronology; it is **not claimed to have been preregistered**.",
        "An additional Sonnet-as-Player-1 versus Fable series, `session_fcc7bb2f60a8`, ended 5–5 and is preserved but excluded from the primary cohort. Including both same-orientation series would change weighting. That additional result also means the primary 10–0 outcome is not a repeatability guarantee. The four older Fable-high series and incomplete/restarted runs are excluded.",
        table(["#", "Archive", "Player 1", "Player 2", "P1–P2", "P1 observed cost", "P2 observed cost"], series_rows),
        "All six primary series are complete, with ten unique finished rounds each. The Opus–Sonnet folders under `med_reruns` contain retained originals, not newly played duplicates. Costs above use the primary-thread scope below, not complete bills.",
        "## Decision timing and route validation",
        table(["Model", "Intervals", "Mean", "Median", "95th percentile"], timing_rows),
        f"These **{v['decision_intervals']} intervals** run from observation completion to the start of a `set_participant_plan` call. They include orchestration, opening preparation, retries, rejected routes, and post-finish attempts: **not pure inference latency or time to a valid plan**. Another {no_intervals} calls have no qualifying interval; no duration is invented. Means pool individual intervals; the 95th percentile uses linear interpolation.",
        f"Fable's three largest intervals are **{tails}**, all accepted opening plans before its first accepted-plan completion in their respective rounds. They remain in the data. Across all models, {reused} additional intervals reuse an earlier observation, so retry timings are dependent. The historical high-effort Fable outliers are outside this cohort.", image(3),
        "**Route rejection rate = invalid routes / (accepted plans + invalid routes).** Every recorded attempt counts, including retries. Validation may return `accepted:false` with `is_error:false`; the analyzer counts that as rejection. Unknown error messages stop analysis for manual review.",
        table(["Model", "Accepted", "Diagonal", "Blocked", ">8 waypoints", "Stationary", "Invalid / validated", "Rejection rate"], route_rows),
        "Diagonal segments change row and column together; blocked routes enter or cross walls. Stationary rejection means the required explicit hold objective/policy was missing. Operational failures are excluded from both sides of the route-rate denominator:",
        table(["Model", "Post-finish", "Run mismatch", "All plan calls", "All rejected / all calls"], operation_rows),
        f"The {v['plan_calls']} plan calls comprise **{v['accepted_plan_calls']} accepted, {v['route_rejections']} route rejections, and {v['operational_plan_errors']} operational failures**. Another {non_plan_errors} post-finish failures came from `stop_participant_intent`, outside the plan tables. Combined error rates and route-rejection rates measure different things.",
        "## Primary-thread cost and token accounting",
        "**These are API-equivalent estimates for observed primary-model messages, not all-in tournament costs.** All twelve logs match the selected session, ten run IDs, side, alias, and actual model ID. Every recorded request, response effort field, and per-turn effort field reports medium. Included work covers tool discovery, startup, gameplay, between-round waits, retries, and final summaries; unrelated conversations are excluded.",
        table(["Model", "Observed primary-thread estimate", "Estimate / appearance", "Cost-state snapshots"], cost_rows),
        f"Observed primary-thread usage totals **${c['total_main_thread_api_equivalent_usd']:.8f}**. The audit deduplicates **{coverage['unique_api_messages']:,} API responses**, removing **{coverage['duplicate_assistant_content_rows_removed']:,} repeated assistant content rows**; each response counts once. Per-appearance costs divide four conversation totals by 40, rather than assigning tokens to individual rounds or plans.",
        table(["Usage category", "Opus 5.5", "Fable 5.1", "Sonnet 5.5"], token_rows),
        "Uncached input, cache reads, and cache writes are distinct input categories. All writes used a one-hour TTL; five-minute writes were zero. Thinking tokens are part of output and are not charged again. See the official [prompt-caching documentation](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) and [thinking-cost documentation](https://platform.claude.com/docs/en/build-with-claude/thinking-steering-and-cost).",
        "### Pricing and coverage",
        table(["Model", "Uncached input / M", "Cache read / M", "1-hour write / M", "Output / M"], price_rows),
        "USD per million tokens, checked **October 31, 2026**, against [official Claude API pricing](https://platform.claude.com/docs/en/about-claude/pricing), with Fable corroborated by its [model page](https://platform.claude.com/docs/en/models/fable-5-1/whats-new-fable-5-1). Requests used standard speed and global inference. [pricing.json](pricing.json) preserves the rates.",
        "```text\nEstimated USD = (uncached input × input rate\n               + cache-read input × read rate\n               + one-hour cache writes × write rate\n               + output × output rate) / 1,000,000\n```",
        f"There is **{coverage['api_requests_without_response_usage']} request without corresponding response usage**; no missing tokens or charge are invented. Cumulative snapshots exist for **{len(snapshots)}/{len(participants)} conversations**, with unequal coverage. Their partial sum is **${snapshot_total:.8f}**, and {extra_primary} include additional primary-model usage beyond the transcript. Auxiliary background usage appears too. These whole-conversation snapshots are not certified bounded tournament costs and must not replace or be added to the observed-message estimate.",
        "No later `/model` command was found in the selected conversations, but that does not make incomplete/background-inclusive snapshots a tournament bill. The leaderboard reports normalized wins per observed primary-thread dollar; a full-session cost-efficiency ranking remains unavailable. Subscription allocation, credits, tax, negotiated rates, and unseen work are outside the estimates. [cost_audit.json](cost_audit.json) preserves coverage and source hashes without publishing private conversations.",
        "## Methodology and limitations",
        "- **Control split:** Claude Code agents observe state and submit high-level routes through MCP. The shared Doom controller handles movement, aiming, firing, and recovery. Results apply to that agent-system setup.\n"
        f"- **Settings:** All {v['config_files']} available configs agree: E1M8 `duel_e1m8_blind_spawn`; seed 42; 180-second timeout; hierarchical routes; 25,000 ms configured intent duration; 750 ms decision cadence; fog and weapon pickups enabled; randomized spawns disabled. The first retained Opus–Sonnet round lacks its config and both prompts, preventing an independent check of its full setup from those artifacts.\n"
        f"- **Prompts:** The {v['prompt_files']} saved prompts have different raw hashes because of tokens and headers. From `BENCHMARK ISOLATION` onward, replacing controller-token values yields one identical game-instruction body per player across available prompts. This excludes preceding identity/alias/round headers and unsaved client context.\n"
        "- **Time and history:** Telemetry spans October 31, 2026, **01:39–05:44 UTC**: Toronto October 30 at **21:39** through October 31 at **01:44**. These are initialization/snapshot boundaries, not exact combat boundaries. Continuing conversations retain earlier-round history; rounds are not independent randomized trials.\n"
        "- **Effort:** All participants used medium, verified by archived evidence and private logs. Equal labels do not ensure equal compute. Changes from historical high-effort results also involve new sessions and chronology, so this is not an isolated causal test of effort.\n"
        f"- **Telemetry:** All {v['mcp_calls']:,} call totals reconcile. However, {len(audit['accepted_plan_vs_lifecycle_differences'])} rounds have one extra accepted-call record: **{v['accepted_plan_calls']} accepted plans versus {audit['summary_totals']['intent_lifecycles']} intent lifecycle records** overall. Error rates use calls; acceptance does not prove a distinct executed lifecycle. Two stale-run `get_match_result` records do not enter plan/timing metrics.\n"
        "- **Evidence limits:** Arena token-usage fields are empty; costs come from audited logs. Zero `rationales_logged` does not prove no reasoning occurred. Text-derived pickup counts are omitted because the parser can match plan words such as “shotgun”; no tactical causal explanation is inferred from them.",
        "## Reproduce and inspect", "From the repository root:",
        "```powershell\npython claude_sweep/analysis/analyze_claude.py\n# Optional: requires private Claude Code gameplay logs.\npython claude_sweep/analysis/cost_audit.py --log-root \"PATH_TO_PRIVATE_PROJECT_LOGS\"\npython claude_sweep/analysis/generate_figures.py\npython claude_sweep/analysis/build_report.py\n```",
        f"The core analyzer uses Python's standard library; figures require Matplotlib, NumPy, and Pillow. Without private logs, retain the cost audit and regenerate public metrics, figures, and Markdown. [metrics.json](metrics.json) contains round aggregates, timing samples, exclusions, six effort-verification sidecars, and hashes for **{inputs} existing inputs**, with **{missing} missing artifacts** recorded. Both analyzers pin selected sessions. Duplicate archives/run IDs, wrong models or effort, and unknown plan failures stop analysis.",
        "Artifacts: [analyzer](analyze_claude.py), [metrics](metrics.json), [cost script](cost_audit.py), [cost data](cost_audit.json), [pricing](pricing.json), [figure generator](generate_figures.py), [report generator](build_report.py). PNG and SVG downloads accompany every figure. [Sweep index](../README.md).",
    ]
    report = "\n\n".join(sections) + "\n"
    index = "\n\n".join([
        "# Claude Doom sweep",
        "[![All-medium Claude win rate versus output-token list price](analysis/figures/claude-output-token-price-vs-win-rate.png)](analysis/README.md)",
        "**All three models used medium effort**, verified from actual API metadata across twelve conversations. The active comparison contains **60 completed matches**, six ten-round series, 40 appearances per model, and no draws.",
        leaderboard, leaderboard_notes, efficiency_summary,
        "The token-price chart uses published output-token prices; the wins-per-dollar chart and leaderboard's cost-efficiency column use observed primary-thread usage costs. With no draws, draw-adjusted scores equal win rates. Read the **[full analysis](analysis/README.md)** for all five figures, player-position results, timing, route validity, audited usage, and coverage limits.",
        tested_models,
        "[Metrics](analysis/metrics.json) · [Cost audit](analysis/cost_audit.json) · [Pricing](analysis/pricing.json) · [Reproduction](analysis/README.md#reproduce-and-inspect)",
        "[![Claude wins per observed API-equivalent dollar: Opus 1.87, Sonnet 0.83, Fable 0.55](analysis/figures/claude-wins-per-dollar.png)](analysis/figures/claude-wins-per-dollar.png)",
        "[PNG](analysis/figures/claude-wins-per-dollar.png) · [SVG](analysis/figures/claude-wins-per-dollar.svg)",
    ]) + "\n"
    return report, index


def main():
    report, index = build(load("metrics.json"), load("cost_audit.json"), load("pricing.json"))
    (HERE / "README.md").write_text(report, encoding="utf-8", newline="\n")
    (HERE.parent / "README.md").write_text(index, encoding="utf-8", newline="\n")
    print(json.dumps({"report": str(HERE / "README.md"), "words": len(report.split()),
                      "index": str(HERE.parent / "README.md")}, indent=2))


if __name__ == "__main__":
    main()
