#!/usr/bin/env python3
"""
Figures for the 3-slide deck (results/slides/14_Ruhi_Donda.pptx), drawn on
the deck's warm-gray background:

    short_brownout_stuck.png   held-out heatmap cropped to the brownout and
                               stuck-sensor rows, all three detectors
    short_solar.png            solar power over about 4 orbits of one clean
                               dev mission (seed 200000); data, not a result

The heatmap reads results/heldout/heldout/*.json and counts exactly as
scripts/make_slide_figures.py does (one-sided, seeds pooled).

Usage: .venv/bin/python scripts/make_short_deck_figures.py
"""

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from make_slide_figures import BLUES, DETECTORS, HELDOUT, LABEL, SEVERITIES, load  # noqa: E402

OUT = ROOT / "results" / "slides"
BG = "#f5f3ef"           # deck background (warm gray)
INK = "#1f1e1c"
INK_2 = "#5f5d58"
ACCENT = "#2a78d6"
ROWS = (("power_brownout", "Brownout"), ("stuck_sensor", "Stuck sensor\n(no severity)"))

plt.rcParams.update({
    "figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG,
    "text.color": INK, "axes.labelcolor": INK_2, "xtick.color": INK_2, "ytick.color": INK,
    "font.family": "DejaVu Sans", "font.size": 24,
})


def cropped_heatmap() -> plt.Figure:
    heldout = load(HELDOUT)
    cmap = LinearSegmentedColormap.from_list("blues", BLUES)
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.4), sharey=True, layout="constrained")
    faults = [f for f, _ in ROWS]
    for ax, name in zip(axes, DETECTORS):
        runs = [r for r in heldout if r["dataset"] == "orbitval" and r["model"] == name]
        caught = np.zeros((len(faults), len(SEVERITIES)))
        total = np.zeros_like(caught)
        for x in (x for r in runs for x in r["rows"]):
            if x["fault"] in faults:
                i, j = faults.index(x["fault"]), SEVERITIES.index(x["severity"])
                caught[i, j] += x["one_sided"]
                total[i, j] += 1
        rate = caught / total
        ax.imshow(rate, vmin=0, vmax=1, cmap=cmap, aspect="auto")
        for i in range(len(faults)):
            for j in range(len(SEVERITIES)):
                ax.text(j, i, f"{int(caught[i, j])}", ha="center", va="center", fontsize=26,
                        fontweight="bold", color="#ffffff" if rate[i, j] > 0.55 else INK)
        ax.set_xticks(range(len(SEVERITIES)), [f"{s:g}" for s in SEVERITIES], fontsize=20)
        ax.set_yticks(range(len(faults)), [label for _, label in ROWS], fontsize=24)
        ax.tick_params(length=0)
        for side in ax.spines.values():
            side.set_visible(False)
        ax.set_xlabel("Fault severity", fontsize=22)
        per_cell = int(total[0, 0])
        seeds = len(runs)
        ax.set_title(f"{LABEL[name]} (of {per_cell}" + (f", {seeds} seeds)" if seeds > 1 else ")"),
                     fontsize=26, fontweight="bold")
    return fig


def solar() -> plt.Figure:
    from orbitval.config.hardware_3u_schema import load_hardware_config
    from orbitval.ml.sim.missions import STEP_S, make_mission, mission_seed
    from orbitval.ml.sim.telemetry import CHANNELS

    m = make_mission(load_hardware_config(str(ROOT / "satellite.yaml")), mission_seed("dev", 0))
    n = 400
    hours = np.arange(n) * STEP_S / 3600
    watts = m.data[:n, CHANNELS.index("solar_power_w")]
    dark = m.illumination[:n] < 1.0
    fig, ax = plt.subplots(figsize=(8, 3.6), layout="constrained")
    edges = np.flatnonzero(np.diff(np.r_[0, dark.astype(int), 0]))
    for a, b in zip(edges[::2], edges[1::2]):
        ax.axvspan(hours[a], hours[min(b, n - 1)], color="#dcd8d0", lw=0)
    ax.plot(hours, watts, color=ACCENT, lw=3)
    ax.set_xlim(0, hours[-1])
    ax.set_ylim(0, 26)
    ax.set_yticks([0, 10, 20])
    ax.set_xlabel("hours")
    ax.set_ylabel("W")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#cfcac1")
    return fig


def main() -> int:
    for name, make, dpi in (("short_brownout_stuck.png", cropped_heatmap, 150),
                            ("short_solar.png", solar, 150)):
        fig = make()
        fig.savefig(OUT / name, dpi=dpi)
        plt.close(fig)
        print(f"wrote {OUT / name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
