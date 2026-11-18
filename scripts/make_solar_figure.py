#!/usr/bin/env python3
"""
Slide 2 figure: solar power over the first 400 steps (about 4 orbits) of
one clean dev mission (seed 200000). Data, not a result.

Writes results/slides/clean_solar_power.png at 1920x1080.
Usage: .venv/bin/python scripts/make_solar_figure.py
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from orbitval.config.hardware_3u_schema import load_hardware_config  # noqa: E402
from orbitval.ml.sim.missions import STEP_S, make_mission, mission_seed  # noqa: E402
from orbitval.ml.sim.telemetry import CHANNELS  # noqa: E402

hw = load_hardware_config(str(ROOT / "satellite.yaml"))
m = make_mission(hw, mission_seed("dev", 0))
n = 400                                   # ~4 orbits at 60 s per step
hours = np.arange(n) * STEP_S / 3600
solar = m.data[:n, CHANNELS.index("solar_power_w")]
illum = m.illumination[:n]

plt.rcParams.update({"font.size": 26, "axes.spines.top": False, "axes.spines.right": False,
                     "font.family": "DejaVu Sans", "axes.edgecolor": "#e4e3df",
                     "xtick.color": "#52514e", "ytick.color": "#52514e", "axes.labelcolor": "#52514e"})
fig, ax = plt.subplots(figsize=(19.2, 10.8), dpi=100)
# shade steps not in full sun (umbra or penumbra)
dark = illum < 1.0
edges = np.flatnonzero(np.diff(np.r_[0, dark.astype(int), 0]))
for a, b in zip(edges[::2], edges[1::2]):
    ax.axvspan(hours[a], hours[min(b, n - 1)], color="#e4e3df", lw=0)
ax.plot(hours, solar, color="#2a78d6", lw=3)
ax.set_xlabel("Time (hours)")
ax.set_ylabel("Solar power (W)")
ax.set_title("One clean simulated mission: solar power (grey = Earth's shadow)", fontsize=30, color="#0b0b0b")
ax.set_xlim(0, hours[-1])
ax.set_ylim(bottom=0)
ax.grid(axis="y", color="#e4e3df")
fig.tight_layout()
out = ROOT / "results" / "slides" / "clean_solar_power.png"
fig.savefig(out)
print(out, "orbit", m.orbit, "seed", m.seed, "max W", solar.max().round(2))
