"""
orbitval/ml/run_telemanom.py

Evaluate a detector on SMAP/MSL dev channels.

    python -m orbitval.ml.run_telemanom --data data/telemanom

Only the dev split is reachable from here. Scoring the held-out test
channels is reserved for the final reproduce run (stage 4), so test
results can't be looked at while still tuning.
"""

import argparse
import json
import math
from dataclasses import asdict
from pathlib import Path

from orbitval.ml.data.telemanom import SPACECRAFT, load_spacecraft, split_channels
from orbitval.ml.evaluate import evaluate
from orbitval.ml.models.baseline import PersistenceBaseline

DETECTORS = {"persistence": PersistenceBaseline}


def _fmt(v: float, spec: str) -> str:
    return "n/a" if isinstance(v, float) and math.isnan(v) else format(v, spec)


def main(argv: list[str] | None = None) -> dict:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    p.add_argument("--data", default="data/telemanom", help="telemanom data root")
    p.add_argument("--detector", default="persistence", choices=sorted(DETECTORS))
    p.add_argument("--spacecraft", nargs="+", default=list(SPACECRAFT), choices=SPACECRAFT)
    p.add_argument("--budget", type=float, default=2.0,
                   help="false alarms allowed per 10k validation steps")
    p.add_argument("--out", default=None, help="optional JSON output path")
    args = p.parse_args(argv)

    detector = DETECTORS[args.detector]()
    results = {}
    for sc in args.spacecraft:
        channels = load_spacecraft(args.data, sc)
        dev, _held_out = split_channels(channels)
        # Threshold from every channel's val series (normal data, not
        # test), metrics from dev channels' test series only.
        r = evaluate(detector, channels, dev, budget_per_10k=args.budget)
        results[sc] = {"calibration": asdict(r.calibration), "metrics": asdict(r.metrics)}

        m, cal = r.metrics, r.calibration
        print(f"\n{sc} — {r.detector} on {m.n_channels} dev channels "
              f"(threshold {cal.threshold:.3f}, val FA/10k {cal.false_alarms_per_10k:.2f})")
        print(f"  event recall        {m.n_detected}/{m.n_events} = {_fmt(m.event_recall, '.3f')}"
              f"   ({m.n_unscoreable} unscoreable)")
        print(f"  false alarms/10k    {_fmt(m.false_alarms_per_10k, '.2f')}"
              f"   ({m.n_false_alarms} over {m.n_normal_steps} normal steps)")
        print(f"  median delay        {_fmt(m.median_delay, '.0f')} steps")
        print(f"  point P / R / F1    {_fmt(m.point_precision, '.3f')} / "
              f"{_fmt(m.point_recall, '.3f')} / {_fmt(m.point_f1, '.3f')}")
        print(f"  PR-AUC              {_fmt(m.pr_auc, '.3f')}")

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"detector": args.detector, "budget_per_10k": args.budget,
                                   "results": results}, indent=2))
    return results


if __name__ == "__main__":
    main()
