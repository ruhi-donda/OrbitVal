"""
orbitval/ml/run_detectability.py

Detectability map on OrbitVal-generated telemetry: event recall per
fault type x severity, for one detector.

    python -m orbitval.ml.run_detectability --plot results/map.png

--split dev (default) is for looking at results while building; the
test split is for scripts/reproduce.sh only.
"""

import argparse
import json
import math
from dataclasses import asdict
from pathlib import Path

from orbitval.config.hardware_3u_schema import load_hardware_config
from orbitval.logging import set_log_level
from orbitval.ml.models.baseline import PersistenceBaseline
from orbitval.ml.sim.missions import SEVERITIES, detectability_map

DETECTORS = {"persistence": PersistenceBaseline}


def _fmt(v: float, spec: str) -> str:
    return "  -" if math.isnan(v) else format(v, spec)


def main(argv: list[str] | None = None) -> dict:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    p.add_argument("--config", default="satellite.yaml")
    p.add_argument("--detector", default="persistence", choices=sorted(DETECTORS))
    p.add_argument("--split", default="dev", choices=("dev", "test"))
    p.add_argument("--reps", type=int, default=20, help="faulted missions per cell")
    p.add_argument("--val", type=int, default=30, help="clean missions for the threshold")
    p.add_argument("--budget", type=float, default=2.0, help="false alarms per 10k steps")
    p.add_argument("--out", default=None, help="optional JSON output")
    p.add_argument("--plot", default=None, help="optional heatmap PNG (needs matplotlib)")
    args = p.parse_args(argv)

    set_log_level("WARNING")    # injection logs one INFO line per mission
    hardware = load_hardware_config(args.config)
    detector = DETECTORS[args.detector]()
    cal, cells = detectability_map(detector, hardware, split=args.split, n_reps=args.reps,
                                   n_val=args.val, budget_per_10k=args.budget)

    print(f"\n{detector.name} on {args.split} — threshold {cal.threshold:.3f} "
          f"(val FA/10k {cal.false_alarms_per_10k:.2f}, budget {args.budget})")
    print("\nevent recall (median delay in steps)")
    print(f"{'fault':<22}" + "".join(f"{s:>12}" for s in SEVERITIES))
    for fault in dict.fromkeys(c.fault for c in cells):
        row = [c for c in cells if c.fault == fault]
        print(f"{fault:<22}" + "".join(
            f"{_fmt(c.metrics.event_recall, '.2f'):>6} ({_fmt(c.metrics.median_delay, '.0f'):>3})"
            for c in row))
    fa = [c.metrics.false_alarms_per_10k for c in cells]
    print(f"\nfalse alarms/10k on faulted missions (outside events): "
          f"mean {sum(fa) / len(fa):.2f}, max {max(fa):.2f}")

    result = {
        "detector": detector.name,
        "split": args.split,
        "reps": args.reps,
        "calibration": asdict(cal),
        "cells": [{"fault": c.fault, "severity": c.severity, "metrics": asdict(c.metrics)}
                  for c in cells],
    }
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2))
    if args.plot:
        from orbitval.ml.plots import plot_detectability
        plot_detectability(result, args.plot)
    return result


if __name__ == "__main__":
    main()
