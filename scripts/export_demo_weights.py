#!/usr/bin/env python3
"""
Copy trained OrbitVal weights, their calibrated thresholds and a summary
of the detectability maps into orbitval/ml/app/weights/ for the demo.
Every seed is exported, so the demo doesn't quietly feature the best one.

Usage: scripts/export_demo_weights.py [results/stage3]
"""

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "orbitval" / "ml" / "app" / "weights"


def build_manifest(results: list[dict]) -> dict:
    """Thresholds and weight file names, per detector and seed."""
    manifest = {}
    for result in results:
        threshold = result["calibration"]["threshold"]
        if result["model"] == "persistence":
            manifest["persistence"] = {"threshold": threshold}
        else:
            name = f"orbitval_{result['model']}_seed{result['seed']}.pt"
            manifest.setdefault(result["model"], {})[str(result["seed"])] = {
                "file": name, "threshold": threshold,
            }
    return manifest


def build_maps(results: list[dict]) -> dict:
    """What the Detectability tab and the preset notes show: pooled over seeds."""
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
    return maps


def load_orbitval_results(source: Path) -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted((source / "results").glob("orbitval_*.json"))]


def main() -> None:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "results" / "stage3"
    DEST.mkdir(parents=True, exist_ok=True)
    results = load_orbitval_results(source)
    manifest = build_manifest(results)
    for name, seeds in manifest.items():
        if name != "persistence":
            for entry in seeds.values():
                shutil.copy(source / "weights" / entry["file"], DEST / entry["file"])
    (DEST / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (DEST / "maps.json").write_text(json.dumps(build_maps(results), indent=2) + "\n")
    print(f"exported {sum(len(v) for k, v in manifest.items() if k != 'persistence')} weights to {DEST}")


if __name__ == "__main__":
    main()
