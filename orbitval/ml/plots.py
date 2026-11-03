"""
orbitval/ml/plots.py

Figures for the report. matplotlib is imported here only, so the rest
of orbitval/ml stays numpy-only.
"""

from pathlib import Path

import numpy as np


def plot_detectability(result: dict, path: str | Path) -> None:
    """Heatmap of event recall: fault type (rows) x severity (columns)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    faults = list(dict.fromkeys(c["fault"] for c in result["cells"]))
    sevs = sorted({c["severity"] for c in result["cells"]})
    grid = np.full((len(faults), len(sevs)), np.nan)
    for c in result["cells"]:
        grid[faults.index(c["fault"]), sevs.index(c["severity"])] = c["metrics"]["event_recall"]

    fig, ax = plt.subplots(figsize=(1.1 * len(sevs) + 3, 0.6 * len(faults) + 1.6))
    im = ax.imshow(grid, vmin=0, vmax=1, cmap="viridis", aspect="auto")
    ax.set_xticks(range(len(sevs)), [f"{s:g}" for s in sevs])
    ax.set_yticks(range(len(faults)), faults)
    ax.set_xlabel("severity")
    ax.set_title(f"Detection rate — {result['detector']} ({result['split']}, "
                 f"{result['reps']} missions/cell)")
    for i in range(len(faults)):
        for j in range(len(sevs)):
            v = grid[i, j]
            ax.text(j, i, f"{v:.2f}", ha="center", va="center",
                    color="black" if v > 0.6 else "white", fontsize=8)
    fig.colorbar(im, ax=ax, label="event recall")
    fig.tight_layout()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
