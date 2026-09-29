"""Reproduce the GPT-6 chart using the original README token-price/win-score metrics.

Requires matplotlib, numpy and Pillow. Reads the committed match summaries and
cost_analysis.json; writes PNG and SVG files beside this script.
"""
from pathlib import Path
import json
import os
import tempfile
from collections import Counter

HERE = Path(__file__).resolve().parent
os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "rootly-doom-matplotlib"))
ROOT = HERE.parents[1]

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.path import Path as MarkerPath
from matplotlib.patches import FancyBboxPatch
from matplotlib.lines import Line2D
from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator
import numpy as np
from PIL import Image

RESULTS = ROOT / "benchmarks/results/gpt-6-model-comparison"
cost_report = json.loads((RESULTS / "expanded_analysis.json").read_text())
assert cost_report['matches'] == 120
ORDER = ('sol61', 'astra', 'sol', 'luna')
LABELS = dict(sol61='GPT-6.1 Sol', astra='GPT-6 Astra', sol='GPT-6 Sol', luna='GPT-6 Luna')
DATA = {
    "logo_path": str(ROOT / "src/assets/rootly-ai-logo-white.png"),
    "models": {m: {
        "matches": cost_report['models'][m]['matches'], "wins": cost_report['models'][m]['wins'],
        "output_price": cost_report['rates'][m][3],
    } for m in ORDER},
}
assert [DATA["models"][m]["output_price"] for m in ("astra", "sol", "luna")] == [50, 10, .5]
COLORS = {"sol61": "#69E8B3", "astra": "#3788FF", "sol": "#FFE18A", "luna": "#DCC8FF"}
BG, FG, MUTED = "#050505", "#F4F4F4", "#ACACB4"
plt.rcParams.update({"font.family": "Arial", "text.color": FG,
                     "axes.labelcolor": FG, "xtick.color": FG,
                     "ytick.color": FG, "svg.fonttype": "none"})


def sun():
    pieces = [MarkerPath.unit_circle().transformed(matplotlib.transforms.Affine2D().scale(.52))]
    for theta in np.linspace(0, 2 * np.pi, 8, endpoint=False):
        unit = np.array([np.cos(theta), np.sin(theta)])
        pieces.append(MarkerPath([unit * .72, unit], [MarkerPath.MOVETO, MarkerPath.LINETO]))
    return MarkerPath.make_compound_path(*pieces)


def moon():
    r, d = .95, .5
    x = (1 - r * r + d * d) / (2 * d)
    y = np.sqrt(1 - x * x)
    a = np.arctan2(y, x)
    b = np.arctan2(y, x - d)
    outside = np.linspace(a, 2 * np.pi - a, 100)
    inside = np.linspace(-b, b - 2 * np.pi, 100)
    vertices = np.vstack([np.column_stack([np.cos(outside), np.sin(outside)]),
                          np.column_stack([d + r * np.cos(inside), r * np.sin(inside)])])
    vertices = np.vstack([vertices, vertices[0]])
    codes = [MarkerPath.MOVETO] + [MarkerPath.LINETO] * (len(vertices) - 2) + [MarkerPath.CLOSEPOLY]
    return MarkerPath(vertices, codes)


MARKERS = {"sol61": sun(), "astra": "*", "sol": sun(), "luna": moon()}
fig = plt.figure(figsize=(12, 9), dpi=200, facecolor=BG)
border = FancyBboxPatch((.015, .02), .97, .96, boxstyle="round,pad=0,rounding_size=0.025",
                       facecolor="none", edgecolor="#303036", linewidth=1,
                       transform=fig.transFigure, zorder=0)
fig.add_artist(border)
fig.text(.063, .939, "GPT-6.1 Sol leads the expanded Doom benchmark",
         fontsize=23, weight="bold", color=FG, va="top")
fig.text(.063, .878, "120 matches  /  60 per model  /  medium reasoning  /  both player positions", fontsize=12, color=MUTED)

# Use the white, transparent version of the supplied logo on the dark chart.
logo_ax = fig.add_axes([.835, .031, .11, .048], facecolor=BG)
logo_ax.imshow(Image.open(DATA["logo_path"]))
logo_ax.set_axis_off()

handles = [Line2D([], [], linestyle="none", marker=MARKERS[m], markersize=17,
                  color=COLORS[m], markeredgewidth=1.7, label=LABELS[m])
           for m in ORDER]
fig.legend(handles=handles, loc="center left", bbox_to_anchor=(.111, .806),
           ncol=4, frameon=False, fontsize=13, handletextpad=.65, columnspacing=1.8)

ax = fig.add_axes([.125, .149, .800, .591], facecolor=BG)
ax.set_xlim(-2, 55)
ax.set_ylim(0, 100)
ax.xaxis.set_major_locator(FixedLocator([0, 10, 20, 30, 40, 50]))
ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"${x:g}"))
ax.xaxis.set_minor_locator(NullLocator())
ax.yaxis.set_major_locator(FixedLocator([0, 20, 40, 60, 80, 100]))
ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{y:g}%"))
ax.tick_params(labelsize=13, pad=10, length=6, width=1)
for name in ("top", "right"):
    ax.spines[name].set_visible(False)
for name in ("left", "bottom"):
    ax.spines[name].set_color("#D4D4D8")
    ax.spines[name].set_linewidth(1.1)
ax.set_ylabel("Draw-adjusted win score", fontsize=16, labelpad=16)
ax.set_xlabel("Output-token price ($ per 1M tokens)", fontsize=14, labelpad=15)
ax.grid(axis="y", color="#242429", linewidth=.6, zorder=0)
ax.axhline(50, color="#92929A", linewidth=.9, linestyle=(0, (5, 4)), zorder=1)
ax.text(54.5, 51.5, "50% parity", color=MUTED, fontsize=11, ha="right", va="bottom")

for m in ('luna', 'sol', 'astra', 'sol61'):
    row = DATA["models"][m]
    cost = row["output_price"]
    win_rate = row["wins"] / row["matches"] * 100
    ax.plot([cost, cost], [0, win_rate], linestyle=(0, (3, 5)), color=COLORS[m],
            alpha=.27, linewidth=1, zorder=1)
    ax.plot(cost, win_rate, marker=MARKERS[m], markersize=22, linestyle="none",
            markeredgewidth=1.8, color=COLORS[m], zorder=3)
    dx, align = (-20, "right") if m == "astra" else (21, "left")
    label_y, price_y = (-30, -49) if m == 'luna' else (5, -14)
    ax.annotate(f"{LABELS[m]}  {win_rate:.1f}%", (cost, win_rate),
                xytext=(dx, label_y), textcoords="offset points", color=COLORS[m],
                fontsize=15, weight="bold", ha=align, va="bottom")
    ax.annotate(f"${cost:.2f} / 1M output tokens", (cost, win_rate),
                xytext=(dx, price_y), textcoords="offset points", color=MUTED,
                fontsize=12, ha=align, va="bottom")

fig.text(.063, .045, "Token price is not total match cost. Standard API rates; no draws in this sample.", fontsize=10, color=MUTED)
for ext in ("png", "svg"):
    out = HERE / f"gpt-6.1-output-token-price-vs-win-rate.{ext}"
    fig.savefig(out, dpi=200, facecolor=BG)
    if ext == "svg":
        out.write_text("\n".join(line.rstrip() for line in out.read_text().splitlines()) + "\n")
    print(out)
plt.close(fig)
