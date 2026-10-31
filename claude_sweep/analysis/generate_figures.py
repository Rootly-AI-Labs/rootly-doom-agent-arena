"""Render the all-medium Claude sweep figures from audited metrics and pricing.

Run from any directory with Python, Matplotlib, NumPy, and Pillow installed:
    python claude_sweep/analysis/generate_figures.py

Inputs: metrics.json, pricing.json, and cost_audit.json beside this script. Output-token price
is a published unit rate, never a measured match bill or full-session cost.
PNG exports are 240 dpi; companion SVG exports retain editable text.
The cohort and effort guards prevent stale mixed-effort metrics from being
rendered with all-medium labels. The historical analysis remains separate.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / "figures"
os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "rootly-doom-matplotlib"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch, Patch
from matplotlib.ticker import FixedLocator, FuncFormatter, MaxNLocator
from matplotlib.transforms import blended_transform_factory
import numpy as np
from PIL import Image

ORDER = ("opus", "fable", "sonnet")
COLORS = {"opus": "#69E8B3", "fable": "#FFE18A", "sonnet": "#DCC8FF"}
MARKERS = {"opus": "*", "fable": "D", "sonnet": "o"}
BG, FG, MUTED, GRID = "#050505", "#F4F4F4", "#ACACB4", "#242429"
plt.rcParams.update({
    "font.family": ["Arial", "DejaVu Sans"],
    "text.color": FG,
    "axes.labelcolor": FG,
    "xtick.color": FG,
    "ytick.color": FG,
    "svg.fonttype": "none",
    "svg.hashsalt": "rootly-claude-sweep",
    "figure.facecolor": BG,
    "axes.facecolor": BG,
})


def read_json(name: str) -> dict:
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def short_label(label: str) -> str:
    return label.removeprefix("Claude ")


def frame(title: str, subtitle: str, footnote: str, *, height: float = 9) -> plt.Figure:
    fig = plt.figure(figsize=(12, height), dpi=240, facecolor=BG)
    fig.add_artist(FancyBboxPatch(
        (.015, .02), .97, .96,
        boxstyle="round,pad=0,rounding_size=0.025",
        transform=fig.transFigure, facecolor="none", edgecolor="#303036",
        linewidth=1, zorder=0,
    ))
    fig.text(.063, .94, title, fontsize=23, weight="bold", va="top")
    fig.text(.063, .88, subtitle, fontsize=12, color=MUTED, va="top")
    fig.text(.063, .842, "All-medium sweep  |  Opus, Fable and Sonnet: medium effort",
             fontsize=10.5, color=MUTED, va="top")
    fig.text(.063, .058, footnote, fontsize=9.4, color=MUTED, va="center", linespacing=1.5)
    logo = ROOT / "src/assets/rootly-ai-logo-white.png"
    if logo.exists():
        logo_ax = fig.add_axes([.845, .035, .102, .043])
        logo_ax.imshow(Image.open(logo))
        logo_ax.set_axis_off()
    return fig


def model_legend(fig: plt.Figure, models: dict, *, y: float = .801) -> None:
    handles = [Line2D(
        [], [], linestyle="none", marker=MARKERS[key], markersize=14,
        color=COLORS[key], markeredgewidth=1.5,
        label=models[key]["label"],
    ) for key in ORDER]
    fig.legend(
        handles=handles, loc="center left", bbox_to_anchor=(.105, y),
        ncol=3, frameon=False, fontsize=13, handletextpad=.6, columnspacing=2.7,
    )


def axis_style(ax: plt.Axes, *, grid: str = "y") -> None:
    for name in ("top", "right"):
        ax.spines[name].set_visible(False)
    for name in ("left", "bottom"):
        ax.spines[name].set_color("#B9B9C1")
        ax.spines[name].set_linewidth(1)
    ax.tick_params(labelsize=12, pad=9, length=5)
    ax.grid(axis=grid, color=GRID, linewidth=.7, zorder=0)
    ax.set_axisbelow(True)


def save(fig: plt.Figure, stem: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    figure_bounds = fig.bbox
    outside_ticks = set()
    for ax in fig.axes:
        for axis in (ax.xaxis, ax.yaxis):
            lower, upper = sorted(axis.get_view_interval())
            for tick in axis.get_major_ticks() + axis.get_minor_ticks():
                if not lower <= tick.get_loc() <= upper:
                    outside_ticks.update((tick.label1, tick.label2))
    for text in fig.findobj(matplotlib.text.Text):
        if not text.get_visible() or not text.get_text() or text in outside_ticks:
            continue
        bounds = text.get_window_extent(renderer)
        if bounds.width and bounds.height and (
            bounds.x0 < -1 or bounds.y0 < -1
            or bounds.x1 > figure_bounds.width + 1
            or bounds.y1 > figure_bounds.height + 1
        ):
            raise RuntimeError(f"Clipped figure text in {stem}: {text.get_text()!r}")
    for ext in ("png", "svg"):
        path = OUT / f"{stem}.{ext}"
        fig.savefig(path, dpi=240, facecolor=BG, metadata={"Date": None} if ext == "svg" else None)
        print(path.relative_to(ROOT))
    plt.close(fig)


def output_prices(pricing: dict, models: dict) -> dict[str, float]:
    """Accept only the cost audit's explicitly verified Standard API prices."""
    return {
        key: float(pricing["models"][models[key]["model_id"]]["output_usd_per_million"])
        for key in ORDER
    }


def price_vs_win(metrics: dict, pricing: dict) -> None:
    models = metrics["models"]
    prices = output_prices(pricing, models)
    verified = pricing["retrieved_date_local"]
    leader = max(ORDER, key=lambda key: models[key]["wins"] / models[key]["matches"])
    fig = frame(
        f"{short_label(models[leader]['label'])} leads the all-medium Claude Doom sweep",
        f"{metrics['matches']} matches  /  {models['opus']['matches']} per model  /  both player positions",
        "Token price is not total match cost. Standard API output rates; no draws in this sample.\n"
        f"Source: platform.claude.com/docs/en/about-claude/pricing  |  Verified {verified}",
    )
    model_legend(fig, models)
    ax = fig.add_axes([.125, .175, .80, .565])
    axis_style(ax)
    max_price = max(prices.values())
    ax.set_xlim(-2, max_price * 1.10)
    ax.set_ylim(0, 100)
    ax.xaxis.set_major_locator(MaxNLocator(nbins=6, integer=True))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"${value:g}"))
    ax.yaxis.set_major_locator(FixedLocator([0, 20, 40, 60, 80, 100]))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:g}%"))
    ax.set_xlabel("Output-token price (USD per 1M tokens)", fontsize=14, labelpad=15)
    ax.set_ylabel("Win rate", fontsize=16, labelpad=16)
    ax.axhline(50, color="#92929A", linewidth=.9, linestyle=(0, (5, 4)), zorder=1)
    ax.text(max_price * 1.09, 51.6, "50% parity", ha="right", va="bottom", color=MUTED, fontsize=11)
    for key in ORDER:
        row = models[key]
        price, rate = prices[key], 100 * row["wins"] / row["matches"]
        ax.plot([price, price], [0, rate], linestyle=(0, (3, 5)), color=COLORS[key], alpha=.3, linewidth=1)
        ax.plot(price, rate, linestyle="none", marker=MARKERS[key], markersize=22 if key == "opus" else 16,
                color=COLORS[key], markeredgewidth=1.5, zorder=3)
        left = price > max_price * .75
        dx, ha = (-20, "right") if left else (21, "left")
        label_y, price_y = (28, 9) if rate < 15 else (6, -14)
        ax.annotate(f"{row['label']}  {rate:.1f}%", (price, rate), xytext=(dx, label_y),
                    textcoords="offset points", ha=ha, va="bottom", fontsize=15,
                    weight="bold", color=COLORS[key])
        ax.annotate(f"${price:.2f} / 1M output tokens", (price, rate), xytext=(dx, price_y),
                    textcoords="offset points", ha=ha, va="bottom", fontsize=12, color=MUTED)
    save(fig, "claude-output-token-price-vs-win-rate")


def pairwise(metrics: dict) -> None:
    models = metrics["models"]
    matrix = np.full((len(ORDER), len(ORDER)), np.nan)
    for i, key in enumerate(ORDER):
        for j, opponent in enumerate(ORDER):
            if key != opponent:
                row = metrics["head_to_head"][key][opponent]
                matrix[i, j] = 100 * row["wins"] / row["matches"]
    fig = frame(
        "How each Claude model performed head to head",
        "Row model's win rate against column opponent  /  both player positions pooled",
        "Each pairing contains 20 matches: 10 in each player assignment. No self-play or draws.",
    )
    ax = fig.add_axes([.215, .19, .59, .59])
    cmap = LinearSegmentedColormap.from_list("rootly_wins", ["#1D1629", "#263E44", "#69E8B3"])
    cmap.set_bad("#111113")
    im = ax.imshow(np.ma.masked_invalid(matrix), cmap=cmap, vmin=0, vmax=100)
    labels = [short_label(models[key]["label"]) for key in ORDER]
    ax.set_xticks(range(len(ORDER)), labels, fontsize=14, weight="bold")
    ax.set_yticks(range(len(ORDER)), labels, fontsize=14, weight="bold")
    ax.tick_params(length=0, pad=13)
    for tick, key in zip(ax.get_xticklabels(), ORDER):
        tick.set_color(COLORS[key])
    for tick, key in zip(ax.get_yticklabels(), ORDER):
        tick.set_color(COLORS[key])
    ax.set_xlabel("Opponent", fontsize=12, color=MUTED, labelpad=14)
    ax.set_ylabel("Model", fontsize=12, color=MUTED, labelpad=14)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_xticks(np.arange(-.5, len(ORDER), 1), minor=True)
    ax.set_yticks(np.arange(-.5, len(ORDER), 1), minor=True)
    ax.grid(which="minor", color=BG, linewidth=7)
    ax.tick_params(which="minor", bottom=False, left=False)
    for i, key in enumerate(ORDER):
        for j, opponent in enumerate(ORDER):
            if key == opponent:
                ax.text(j, i, "—", fontsize=27, ha="center", va="center", color="#676770")
                continue
            row = metrics["head_to_head"][key][opponent]
            color = "#07150F" if matrix[i, j] >= 70 else FG
            ax.text(j, i - .08, f"{matrix[i, j]:.0f}%", fontsize=29, weight="bold", ha="center", va="center", color=color)
            ax.text(j, i + .19, f"{row['wins']} / {row['matches']} wins", fontsize=12, ha="center", va="center", color=color)
    cax = fig.add_axes([.85, .25, .018, .45])
    colorbar = fig.colorbar(im, cax=cax, ticks=[0, 50, 100])
    colorbar.ax.set_yticklabels(["0%", "50%", "100%"])
    colorbar.ax.tick_params(length=0, pad=8, labelsize=11)
    colorbar.outline.set_visible(False)
    save(fig, "claude-pairwise-win-rate")


def player_sides(metrics: dict) -> None:
    models = metrics["models"]
    totals = {
        side: sum(models[key]["side_counts"][side]["wins"] for key in ORDER)
        for side in ("player_1", "player_2")
    }
    fig = frame(
        "Claude performance by player position",
        f"Overall: Player 1 won {totals['player_1']}/{metrics['matches']}  /  Player 2 won {totals['player_2']}/{metrics['matches']}",
        "Descriptive results from this sweep; player assignments also differ in session and round order.",
    )
    ax = fig.add_axes([.205, .18, .70, .57])
    axis_style(ax, grid="x")
    ax.spines["left"].set_visible(False)
    ax.set_xlim(0, 110)
    ax.set_ylim(2.6, -.6)
    ax.xaxis.set_major_locator(FixedLocator([0, 20, 40, 60, 80, 100]))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:g}%"))
    ax.set_yticks(range(3), [short_label(models[key]["label"]) for key in ORDER], fontsize=15, weight="bold")
    ax.tick_params(axis="y", length=0, pad=16)
    ax.set_xlabel("Win rate", fontsize=14, labelpad=15)
    for tick, key in zip(ax.get_yticklabels(), ORDER):
        tick.set_color(COLORS[key])
    for i, key in enumerate(ORDER):
        for offset, side in ((-.17, "player_1"), (.17, "player_2")):
            row = models[key]["side_counts"][side]
            rate = 100 * row["wins"] / row["matches"]
            ax.barh(i + offset, rate, height=.26, color=COLORS[key],
                    alpha=1 if side == "player_1" else .3,
                    edgecolor=COLORS[key], linewidth=1, zorder=2)
            ax.text(rate + 1.5, i + offset, f"{rate:.0f}%  ({row['wins']}/{row['matches']})",
                    va="center", ha="left", color=FG, fontsize=12)
    fig.legend(handles=[
        Patch(facecolor="#DDDEE5", edgecolor="#DDDEE5", label="Player 1"),
        Patch(facecolor="#47484E", edgecolor="#DDDEE5", label="Player 2"),
    ], loc="center left", bbox_to_anchor=(.203, .80), frameon=False, ncol=2, fontsize=13,
        columnspacing=3)
    save(fig, "claude-player-side-performance")


def decisions_and_routes(metrics: dict) -> None:
    models = metrics["models"]
    fig = frame(
        "Decision timing and route validity",
        f"Recorded model decisions and route submissions across all {metrics['matches']} matches",
        "Decision time includes host orchestration. Invalid routes exclude post-finish / run-mismatch calls.\n"
        "Lower is better on both panels; averages summarize tool-event telemetry, not pure inference.",
    )
    left = fig.add_axes([.195, .20, .29, .56])
    right = fig.add_axes([.66, .20, .25, .56])
    values = [models[key]["mean_decision_seconds"] for key in ORDER]
    rates = [100 * models[key]["route_rejection_rate"] for key in ORDER]
    for ax in (left, right):
        axis_style(ax, grid="x")
        ax.spines["left"].set_visible(False)
        ax.set_ylim(2.6, -.6)
        ax.tick_params(axis="y", length=0, pad=13)
        ax.set_yticks(range(3))
    left.set_yticklabels([short_label(models[key]["label"]) for key in ORDER], fontsize=13, weight="bold")
    for tick, key in zip(left.get_yticklabels(), ORDER):
        tick.set_color(COLORS[key])
    right.set_yticklabels([])
    left.set_xlim(0, max(values) * 1.5)
    right.set_xlim(0, max(rates) * 1.6)
    left.xaxis.set_major_locator(MaxNLocator(nbins=4))
    right.xaxis.set_major_locator(MaxNLocator(nbins=4, steps=[1, 2, 2.5, 5, 10]))
    right.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:g}%"))
    left.set_title("Mean decision time", fontsize=15, weight="bold", pad=18, loc="left")
    right.set_title("Invalid-route rate", fontsize=15, weight="bold", pad=18, loc="left")
    left.set_xlabel("Seconds", fontsize=13, labelpad=15)
    right.set_xlabel("Rejected / route attempts", fontsize=12, labelpad=15)
    for i, key in enumerate(ORDER):
        row = models[key]
        left.barh(i, values[i], height=.36, color=COLORS[key], zorder=2)
        right.barh(i, rates[i], height=.36, color=COLORS[key], zorder=2)
        left.text(values[i] + max(values) * .035, i - .065, f"{values[i]:.2f}s", fontsize=13, weight="bold", va="center")
        left.text(values[i] + max(values) * .035, i + .11, f"n={row['decision_count']}", fontsize=10, color=MUTED, va="center")
        right.text(rates[i] + max(rates) * .04, i - .065, f"{rates[i]:.1f}%", fontsize=13, weight="bold", va="center")
        right.text(rates[i] + max(rates) * .04, i + .11,
                   f"{row['route_rejections']}/{row['route_validation_attempts']}", fontsize=10, color=MUTED, va="center")
    save(fig, "claude-decision-time-and-route-validity")


def validate_metrics(metrics: dict) -> None:
    if metrics.get("cohort") != "all_medium_60_round_sweep":
        raise ValueError("Expected the selected all-medium 60-round cohort; regenerate metrics.json first.")
    if metrics.get("effort") != "medium" or not metrics["validation"].get("all_participants_medium_verified"):
        raise ValueError("All twelve participant effort settings must be verified as medium before charting.")
    if metrics["matches"] != 60 or metrics["validation"]["duplicate_run_ids"] != 0:
        raise ValueError("The selected cohort must contain exactly 60 unique matches.")
    assert set(ORDER).issubset(metrics["models"])
    assert sum(metrics["models"][key]["matches"] for key in ORDER) == 2 * metrics["matches"]
    assert sum(metrics["models"][key]["wins"] for key in ORDER) == metrics["matches"]
    assert all(metrics["models"][key]["draws"] == 0 for key in ORDER)


def wins_per_dollar(metrics: dict, audit: dict) -> None:
    """Rank wins per observed primary-thread API-equivalent USD, not full bills."""
    validate_metrics(metrics)
    if audit.get("cohort") != metrics["cohort"] or audit.get("required_effort") != "medium":
        raise ValueError("Cost audit and metrics must describe the same all-medium cohort.")
    session_ids = {row["session_id"] for row in metrics["series"]}
    if (len(session_ids) != 6 or session_ids != set(metrics["pinned_session_ids"])
            or session_ids != set(audit["pinned_arena_session_ids"])):
        raise ValueError("Cost audit and metrics must pin the same six arena sessions.")
    if not audit.get("uniform_main_thread_usage_available_for_all"):
        raise ValueError("Observed primary-thread usage must cover all twelve participants.")
    participants = audit["participants"]
    expected = {(session, side) for session in session_ids for side in ("player_1", "player_2")}
    observed = {(row["arena_session_id"], row["participant_id"]) for row in participants}
    if len(participants) != 12 or observed != expected:
        raise ValueError("Expected exactly one audited log for each participant in all six sessions.")
    for row in participants:
        for field in ("effort_by_message_count", "effort_by_api_request_count"):
            if set(row[field]) != {"medium"} or row[field]["medium"] <= 0:
                raise ValueError("Every audited participant must have verified medium-effort usage.")
        if row["matched_rounds"] != 10:
            raise ValueError("Each audited participant must cover its ten-round series.")

    models, costs = metrics["models"], {}
    for key in ORDER:
        model_id = models[key]["model_id"]
        cost_row = audit["by_model"][model_id]
        model_logs = [row for row in participants if row["model_id"] == model_id]
        if (cost_row["round_appearances"] != models[key]["matches"]
                or sum(row["matched_rounds"] for row in model_logs) != models[key]["matches"]
                or cost_row["participant_sessions"] != len(model_logs)):
            raise ValueError(f"Cost coverage does not match appearances for {model_id}.")
        cost = float(cost_row["main_thread_api_equivalent"]["total_usd"])
        log_cost = sum(row["main_thread_api_equivalent"]["total_usd"] for row in model_logs)
        if not math.isfinite(cost) or cost <= 0 or not math.isclose(cost, log_cost, rel_tol=1e-10):
            raise ValueError(f"Invalid or unreconciled observed primary-thread cost for {model_id}.")
        costs[key] = cost
    efficiency = {key: models[key]["wins"] / costs[key] for key in ORDER}
    ranked = sorted(ORDER, key=lambda key: efficiency[key], reverse=True)
    leader = ranked[0]

    fig = plt.figure(figsize=(12, 9), dpi=240, facecolor=BG)
    fig.add_artist(FancyBboxPatch(
        (.015, .02), .97, .96, boxstyle="round,pad=0,rounding_size=0.025",
        transform=fig.transFigure, facecolor="none", edgecolor="#303036", linewidth=1, zorder=0,
    ))
    leader_name = short_label(models[leader]["label"]).split()[0]
    fig.text(.063, .94, f"{leader_name}: most wins per dollar on Doom Agent Arena",
             fontsize=25, weight="bold", va="top", color=COLORS[leader])
    fig.text(.063, .878,
             f"{metrics['matches']} matches  /  all models: medium effort  /  {models[leader]['matches']} appearances each",
             fontsize=12, color=MUTED, va="top")
    fig.text(.063, .838, "Observed primary-thread API-equivalent usage only",
             fontsize=11, color=MUTED, va="top")
    logo = ROOT / "src/assets/rootly-ai-logo-white.png"
    if logo.exists():
        logo_ax = fig.add_axes([.79, .802, .145, .065])
        logo_ax.imshow(Image.open(logo))
        logo_ax.set_axis_off()

    ax = fig.add_axes([.30, .19, .625, .54])
    axis_style(ax, grid="x")
    ax.spines["left"].set_visible(False)
    ax.set_ylim(len(ranked) - .35, -.65)
    maximum = max(efficiency.values())
    ax.set_xlim(0, maximum * 1.15)
    ax.xaxis.set_major_locator(MaxNLocator(nbins=5, steps=[1, 2, 2.5, 5, 10]))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:g}"))
    ax.set_yticks([])
    ax.set_xlabel("Wins per estimated API dollar (observed primary thread)", fontsize=13, labelpad=18)
    marker_transform = blended_transform_factory(fig.transFigure, ax.transData)
    for i, key in enumerate(ranked):
        value = efficiency[key]
        ax.barh(i, value, height=.40, color=COLORS[key], zorder=2)
        ax.text(value + maximum * .025, i, f"{value:.2f}", va="center", ha="left",
                fontsize=23, weight="bold", color=COLORS[key])
        ax.text(-.06, i, models[key]["label"], transform=ax.get_yaxis_transform(),
                fontsize=17.5, weight="bold", ha="right", va="center", color=COLORS[key])
        ax.plot(.066, i, marker=MARKERS[key], markersize=18 if key == "opus" else 14,
                color=COLORS[key], linestyle="none", transform=marker_transform, clip_on=False)
    fig.text(.063, .067,
             "Includes recorded primary-thread input, cache writes/reads and output across all 12 gameplay conversations.\n"
             f"Excludes background/unobserved usage; not full-session costs or actual invoices. Standard rates, {audit['pricing_checked_date']}.",
             fontsize=9.4, color=MUTED, va="center", linespacing=1.5)
    save(fig, "claude-wins-per-dollar")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wins-per-dollar-only", action="store_true",
                        help="Render only the observed primary-thread cost-efficiency figure.")
    args = parser.parse_args()
    metrics, pricing = read_json("metrics.json"), read_json("pricing.json")
    audit = read_json("cost_audit.json")
    validate_metrics(metrics)
    if args.wins_per_dollar_only:
        wins_per_dollar(metrics, audit)
        return
    price_vs_win(metrics, pricing)
    pairwise(metrics)
    player_sides(metrics)
    decisions_and_routes(metrics)
    wins_per_dollar(metrics, audit)


if __name__ == "__main__":
    main()
