#!/usr/bin/env python3
"""
Copy trained OrbitVal weights, their calibrated thresholds and a summary
of the detectability maps into orbitval/ml/app/weights/ for the demo. Every seed is exported, so the
demo doesn't quietly feature the best one.

Usage: scripts/export_demo_weights.py [results/stage3]
"""

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
source = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "results" / "stage3"
dest = ROOT / "orbitval" / "ml" / "app" / "weights"
dest.mkdir(parents=True, exist_ok=True)

manifest = {}
results = [json.loads(p.read_text()) for p in sorted((source / "results").glob("orbitval_*.json"))]
for result in results:
    threshold = result["calibration"]["threshold"]
    if result["model"] == "persistence":
        manifest["persistence"] = {"threshold": threshold}
        continue
    name = f"orbitval_{result['model']}_seed{result['seed']}.pt"
    shutil.copy(source / "weights" / name, dest / name)
    manifest.setdefault(result["model"], {})[str(result["seed"])] = {
        "file": name, "threshold": threshold,
    }

# What the Detectability tab and the preset notes show: pooled over seeds
maps = {}
for name in sorted({r["model"] for r in results}):
    rows = [r for r in results if r["model"] == name]
    cells = {}
    for row in rows:
        for c in row["cells"]:
            cell = cells.setdefault((c["fault"], c["severity"]), {"detected": 0, "total": 0})
            cell["detected"] += c["metrics"]["n_detected"]
            cell["total"] += c["metrics"]["n_events"]
    lighting = {}
    for row in rows:
        for key, g in row["error_analysis"]["stuck_sensor"]["by_lighting"].items():
            entry = lighting.setdefault(key, {"n_detected": 0, "n": 0})
            entry["n_detected"] += g["n_detected"]
            entry["n"] += g["n"]
    maps[name] = {
        "seeds": len(rows),
        "reps": rows[0]["reps"],
        "cells": [{"fault": f, "severity": s, "recall": v["detected"] / v["total"], **v}
                  for (f, s), v in cells.items()],
        "stuck_by_lighting": lighting,
    }

(dest / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
(dest / "maps.json").write_text(json.dumps(maps, indent=2) + "\n")
print(f"exported {sum(len(v) for k, v in manifest.items() if k != 'persistence')} weights to {dest}")
