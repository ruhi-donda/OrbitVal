#!/usr/bin/env python3
"""
Slide figures from the frozen held-out run (and dev numbers where labeled).

Writes 1920x1080 PNGs on a light background to results/slides/:
    heldout_detectability.png   held-out heatmaps, persistence / LSTM / GRU
    heldout_recall.png          SMAP and MSL events caught, one dot per seed
    false_alarms_dev_vs_heldout.png   clean-mission false alarms per 10k

Reads results/heldout/heldout/*.json and results/stage3/two_sided/*.json.
Nothing is computed here that the reports don't already contain.

Usage: .venv/bin/python scripts/make_slide_figures.py
"""

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
HELDOUT = ROOT / "results" / "heldout" / "heldout"
DEV = ROOT / "results" / "stage3" / "two_sided"
OUT = ROOT / "results" / "slides"

# Validated palette (dataviz reference instance), light surface
SURFACE = "#ffffff"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e4e3df"
DEV_COLOR = "#2a78d6"        # categorical slot 1: dev
HELDOUT_COLOR = "#eb6834"    # categorical slot 2: held-out
BLUES = ["#f4f8fd", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]

DETECTORS = ("persistence", "lstm", "gru")
LABEL = {"persistence": "Persistence", "lstm": "LSTM", "gru": "GRU"}
FAULT_LABEL = {"power_brownout": "Brownout", "sensor_noise": "Sensor noise",
               "eclipse_power_stress": "Eclipse stress", "sensor_drift": "Sensor drift",
               "stuck_sensor": "Stuck sensor"}
SEVERITIES = (0.05, 0.1, 0.2, 0.35, 0.5, 0.75, 1.0)
SIZE = (19.2, 10.8)          # inches at 100 dpi = 1920x1080
DPI = 100

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "text.color": INK, "axes.labelcolor": INK_2, "xtick.color": INK_2, "ytick.color": INK_2,
    "axes.edgecolor": GRID, "font.size": 24, "axes.titlesize": 30, "axes.labelsize": 24,
    "xtick.labelsize": 22, "ytick.labelsize": 22, "legend.fontsize": 22,
    "axes.spines.top": False, "axes.spines.right": False, "font.family": "DejaVu Sans",
})


def load(folder: Path) -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(folder.glob("*.json"))]


def heatmaps(heldout: list[dict]) -> plt.Figure:
    """Missions caught per (fault, severity), one-sided at 2, seeds pooled."""
    fig, axes = plt.subplots(1, 3, figsize=SIZE, sharey=True, layout="constrained")
    cmap = LinearSegmentedColormap.from_list("blues", BLUES)
    faults = list(FAULT_LABEL)
    for ax, name in zip(axes, DETECTORS):
        rows = [x for r in heldout if r["dataset"] == "orbitval" and r["model"] == name
                for x in r["rows"]]
        n_seeds = len({r["seed"] for r in heldout if r["dataset"] == "orbitval" and r["model"] == name})
        caught = np.zeros((len(faults), len(SEVERITIES)))
        total = np.zeros_like(caught)
        for x in rows:
            i, j = faults.index(x["fault"]), SEVERITIES.index(x["severity"])
            caught[i, j] += x["one_sided"]
            total[i, j] += 1
        rate = caught / total
        ax.imshow(rate, vmin=0, vmax=1, cmap=cmap, aspect="auto")
        for i in range(len(faults)):
            for j in range(len(SEVERITIES)):
                ax.text(j, i, f"{int(caught[i, j])}", ha="center", va="center", fontsize=20,
                        color=SURFACE if rate[i, j] > 0.55 else INK)
        ax.set_xticks(range(len(SEVERITIES)), [f"{s:g}" for s in SEVERITIES], fontsize=18)
        ax.set_yticks(range(len(faults)), [FAULT_LABEL[f] for f in faults])
        ax.tick_params(length=0)
        for side in ax.spines.values():
            side.set_visible(False)
        ax.set_xlabel("Fault severity")
        per_cell = int(total[0, 0])
        ax.set_title(f"{LABEL[name]}\n{per_cell} missions per cell"
                     + (f" ({n_seeds} seeds)" if n_seeds > 1 else ""), fontsize=26)
    fig.suptitle("Held-out orbits: missions where the fault was caught (one-sided, 2 false alarms per 10k)",
                 fontsize=28)
    return fig


def recall(heldout: list[dict]) -> plt.Figure:
    """SMAP and MSL held-out events caught, one dot per seed, persistence as a line."""
    fig, axes = plt.subplots(1, 2, figsize=SIZE, layout="constrained")
    for ax, ds in zip(axes, ("smap", "msl")):
        runs = [r for r in heldout if r["dataset"] == ds]
        n_events = runs[0]["metrics"]["one_sided"]["n_events"]
        base = next(r for r in runs if r["model"] == "persistence")["metrics"]["one_sided"]["n_detected"]
        ax.axhline(base, color=INK_2, linewidth=2, linestyle=(0, (6, 4)))
        ax.text(1.85, base, f"Persistence: {base}", va="bottom", ha="right", color=INK_2, fontsize=20)
        for x, name in enumerate(("lstm", "gru")):
            seeds = sorted((r for r in runs if r["model"] == name), key=lambda r: r["seed"])
            counts = [r["metrics"]["one_sided"]["n_detected"] for r in seeds]
            offsets = np.linspace(-0.22, 0.22, len(counts))
            ax.scatter(x + offsets, counts, s=260, color=HELDOUT_COLOR, edgecolor=SURFACE,
                       linewidth=2, zorder=3)
            for dx, c, r in zip(offsets, counts, seeds):
                below = c < base                # keep the label off the persistence line
                ax.text(x + dx, c + n_events * (-0.025 if below else 0.025), f"{c}",
                        va="top" if below else "bottom", ha="center", fontsize=20, color=INK)
        ax.set_xticks([0, 1], ["LSTM", "GRU"])
        ax.set_xlim(-0.5, 1.9)
        ax.set_ylim(0, n_events)
        ax.yaxis.grid(True, color=GRID, linewidth=1)
        ax.set_axisbelow(True)
        ax.set_ylabel(f"Events caught (of {n_events})")
        n_channels = runs[0]["metrics"]["one_sided"]["n_channels"]
        ax.set_title(f"{ds.upper()}: {n_channels} held-out channels")
    fig.suptitle("Held-out channels: events caught, one dot per training seed (one-sided)", fontsize=28)
    return fig


def false_alarms(dev: list[dict], heldout: list[dict]) -> plt.Figure:
    """One-sided false alarms per 10k on clean missions: dev orbits vs held-out orbits."""
    fig, ax = plt.subplots(figsize=SIZE, layout="constrained")
    width = 0.34
    for x, name in enumerate(DETECTORS):
        for k, (label, results, key, color) in enumerate((
                ("Dev orbits", dev, "clean_dev", DEV_COLOR),
                ("Held-out orbits", heldout, "clean_test", HELDOUT_COLOR))):
            rates = [r[key]["one_sided"]["per_10k"] for r in results
                     if r["dataset"] == "orbitval" and r["model"] == name]
            pos = x + (k - 0.5) * (width + 0.04)
            mean = float(np.mean(rates))
            ax.bar(pos, mean, width, color=color, alpha=0.35, label=label if x == 0 else None)
            ax.scatter([pos] * len(rates), rates, s=200, color=color, edgecolor=SURFACE,
                       linewidth=2, zorder=3)
            ax.text(pos, max(rates) + 0.25, f"{mean:.2f}", ha="center", va="bottom", fontsize=20)
    ax.axhline(2.0, color=INK_2, linewidth=2, linestyle=(0, (6, 4)))
    ax.text(3.05, 2.08, "Budget set on validation: 2", va="bottom", ha="right", color=INK_2, fontsize=20)
    ax.set_xticks(range(len(DETECTORS)), [LABEL[n] for n in DETECTORS])
    ax.set_xlim(-0.6, 3.1)
    ax.set_ylim(0, 7)
    ax.yaxis.grid(True, color=GRID, linewidth=1)
    ax.set_axisbelow(True)
    ax.set_ylabel("False alarms per 10,000 steps")
    ax.legend(loc="upper left", frameon=False)
    ax.set_title("False alarms on clean missions (20 per orbit set): bar = mean, dot = seed",
                 fontsize=28)
    return fig


def main() -> int:
    heldout, dev = load(HELDOUT), load(DEV)
    if not heldout or not dev:
        print("missing results/heldout or results/stage3/two_sided", file=sys.stderr)
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    for name, fig in (("heldout_detectability.png", heatmaps(heldout)),
                      ("heldout_recall.png", recall(heldout)),
                      ("false_alarms_dev_vs_heldout.png", false_alarms(dev, heldout))):
        fig.savefig(OUT / name, dpi=DPI)
        plt.close(fig)
        print(f"wrote {OUT / name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
