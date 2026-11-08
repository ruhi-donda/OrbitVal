"""
orbitval/ml/run_two_sided.py

Run the two-sided setting on dev data, from saved weights. Nothing is
retrained, and no path here scores the held-out channels or test missions.

    python -m orbitval.ml.run_two_sided run --dataset orbitval --model gru --seed 0
    python -m orbitval.ml.run_two_sided summarize

Reads <outdir>/weights and writes <outdir>/two_sided.
"""

import argparse
import json
from collections import Counter
from pathlib import Path

import torch

from orbitval.config.hardware_3u_schema import load_hardware_config
from orbitval.logging import set_log_level
from orbitval.ml.data.telemanom import load_spacecraft, split_channels
from orbitval.ml.evaluate import EVENT_GRACE, SHORT_GRACE
from orbitval.ml.models.baseline import PersistenceBaseline
from orbitval.ml.models.recurrent import MODELS
from orbitval.ml.run_neural import DATASETS, _checkpoint_path, load_detector
from orbitval.ml.sim.missions import SEVERITIES
from orbitval.ml.two_sided import evaluate_orbitval, evaluate_telemanom

DETECTORS = ("persistence", "lstm", "gru")
ROWS_SHOWN = ("stuck_sensor", "sensor_drift")


def run_one(dataset: str, model: str, seed: int, outdir: Path, data_root: str,
            config_path: str, reps: int = 20, n_val: int = 30) -> dict:
    if model == "persistence":
        detector = PersistenceBaseline()
    else:
        detector, _ = load_detector(_checkpoint_path(outdir, dataset, model, seed))

    if DATASETS[dataset]:
        channels = load_spacecraft(data_root, DATASETS[dataset])
        dev, _held_out = split_channels(channels)
        result = evaluate_telemanom(detector, channels, dev)
    else:
        result = evaluate_orbitval(detector, load_hardware_config(config_path), reps, n_val)

    out = {"dataset": dataset, "model": model, "seed": seed, **result}
    path = outdir / "two_sided" / f"{dataset}_{model}_seed{seed}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2))
    print(f"wrote {path}", flush=True)
    return out


def outcome_counts(rows: list[dict]) -> dict:
    """What the two-sided setting did to the one-sided detector's events."""
    both = [r for r in rows if r["high"] or r["low"]]
    return {
        "events": len(rows),
        "one_sided": sum(r["one_sided"] for r in rows),
        "high": sum(r["high"] for r in rows),
        "low": sum(r["low"] for r in rows),
        "two_sided": len(both),
        # Caught before, caught by neither side now
        "lost": sum(r["one_sided"] and not (r["high"] or r["low"]) for r in rows),
        # The stricter high threshold missed it, but the low side caught it
        "kept_by_low": sum(r["one_sided"] and not r["high"] and r["low"] for r in rows),
        # Missed before, caught now (only the low side can add events)
        "gained": sum(r["low"] and not r["one_sided"] and not r["high"] for r in rows),
    }


def _thresholds(r: dict) -> str:
    c = r["calibration"]
    return (f"one-sided {c['one_sided']['threshold']:.2f}, high {c['high']['threshold']:.2f}, "
            f"low {c['low']['threshold']:.2f}")


def _fa(metrics: dict) -> str:
    """False alarms per setting at both grace periods, as runs."""
    parts = []
    for name in ("one_sided", "high_only", "low_only", "two_sided"):
        m = metrics[name]
        parts.append(f"{name} {m['n_false_alarms']}/{m['n_false_alarms_short_grace']} "
                     f"({m['false_alarms_per_10k']:.2f}/10k)")
    return ", ".join(parts)


def _orbit_row(rows: list[dict], fault: str, key) -> str:
    cells = []
    for severity in SEVERITIES:
        chosen = [r for r in rows if r["fault"] == fault and r["severity"] == severity]
        cells.append(f"{sum(key(r) for r in chosen)}/{len(chosen)}")
    return "".join(f"{c:>9}" for c in cells)


def _alarm_table(alarms: list[dict], shares: dict | None) -> None:
    # A rep shares its base mission across cells, so one alarm can recur.
    # Distinct alarms are the honest count.
    distinct = list({(a["seed"], a["start"]): a for a in alarms}.values())
    print(f"    {len(alarms)} runs, {len(distinct)} distinct "
          f"(mission, start); share of scored time: {shares}")
    if not distinct:
        return
    print(f"    lighting {dict(Counter(a['lighting'] for a in distinct))}")
    print(f"    channel  {dict(Counter(a['channel'] for a in distinct))}")
    since = [a["steps_since_lighting_change"] for a in distinct]
    print(f"    steps since lighting change: <=10 {sum(s is not None and s <= 10 for s in since)}, "
          f"11-30 {sum(s is not None and 10 < s <= 30 for s in since)}, "
          f">30 {sum(s is not None and s > 30 for s in since)}, none {since.count(None)}")
    lengths = sorted(a["length"] for a in distinct)
    print(f"    run length: median {lengths[len(lengths) // 2]}, longest {lengths[-1]}")


def summarize(outdir: Path) -> None:
    results = [json.loads(p.read_text()) for p in sorted((outdir / "two_sided").glob("*.json"))]
    print(f"\nFalse alarms are runs, shown as grace {EVENT_GRACE}/grace {SHORT_GRACE}.")

    orbit = [r for r in results if r["dataset"] == "orbitval"]
    print("\n=== OrbitVal dev missions: thresholds and clean false alarms per side ===")
    for r in orbit:
        print(f"{r['model']:<12} seed {r['seed']}  {_thresholds(r)}")
        for name in ("val", "clean_dev"):
            c = r[name]
            print(f"    {name:<10} {c['normal_steps']} steps: "
                  + ", ".join(f"{s} {c[s]['false_alarms']}" for s in
                              ("one_sided", "high_only", "low_only", "two_sided"))
                  + f"; time in low alarm {100 * c['low_alarm_step_fraction']:.2f}%, "
                    f"lowest z {c['lowest_z']:.2f}")

    print("\n=== OrbitVal: detected missions, all seeds pooled ===")
    for fault in ROWS_SHOWN:
        print(f"\n{fault}\n{'':<30}" + "".join(f"{s:>9}" for s in SEVERITIES))
        for name in DETECTORS:
            rows = [x for r in orbit if r["model"] == name for x in r["rows"]]
            if not rows:
                continue
            for label, key in (
                ("one-sided at 2", lambda x: x["one_sided"]),
                ("high side at 1", lambda x: x["high"]),
                ("low side at 1", lambda x: x["low"]),
                ("  on a changed channel", lambda x: x["low_on_affected"]),
                ("  and not in clean twin", lambda x: x["low_attributable"]),
                ("  also in clean twin", lambda x: x["low_in_twin"]),
                ("two-sided", lambda x: x["high"] or x["low"]),
            ):
                print(f"{name:<12}{label:<18}" if not label.startswith(" ")
                      else f"{'':<8}{label:<22}", end="")
                print(_orbit_row(rows, fault, key))

    print("\n=== OrbitVal: stuck_sensor by lighting, all severities and seeds ===")
    for name in DETECTORS:
        rows = [x for r in orbit if r["model"] == name for x in r["rows"]
                if x["fault"] == "stuck_sensor"]
        for lighting in ("sunlit", "eclipse", "crossing"):
            chosen = [x for x in rows if x["lighting"] == lighting]
            if chosen:
                c = outcome_counts(chosen)
                attributable = sum(x["low_attributable"] for x in chosen)
                print(f"{name:<12} {lighting:<9} n={c['events']:<4} one-sided {c['one_sided']:<4} "
                      f"low {c['low']:<4} attributable {attributable:<4} two-sided {c['two_sided']}")

    print("\n=== OrbitVal: how low z gets on the changed channel, severity 1.0 ===")
    for name in DETECTORS:
        for r in (r for r in orbit if r["model"] == name):
            tail = r["low_tail"]
            print(f"{name:<12} seed {r['seed']}  low threshold {tail['low_threshold']:.2f}; lowest clean z: "
                  + ", ".join(f"{k} {v:.2f}" for k, v in tail["val_lowest_z_by_channel"].items()))
            for fault in ROWS_SHOWN:
                for lighting in ("sunlit", "eclipse", "crossing"):
                    chosen = [x for x in tail[fault]["rows"] if x["lighting"] == lighting]
                    if chosen:
                        print(f"    {fault:<13} {lighting:<9} n={len(chosen):<3} "
                              f"lowest z {min(x['lowest_z'] for x in chosen):.2f}, "
                              f"mean {sum(x['lowest_z'] for x in chosen) / len(chosen):.2f}; "
                              f"mean floor there {sum(x['floor_there'] for x in chosen) / len(chosen):.2f}")

    print("\n=== OrbitVal: events lost and gained, per fault, all seeds pooled ===")
    print("(no twin) = the alarm did not also fire on the clean twin in the same steps")
    for name in DETECTORS:
        rows = [x for r in orbit if r["model"] == name for x in r["rows"]]
        for fault in dict.fromkeys(x["fault"] for x in rows):
            chosen = [x for x in rows if x["fault"] == fault]
            c = outcome_counts(chosen)
            gained_attr = sum(x["low_attributable"] and not x["one_sided"] and not x["high"]
                              for x in chosen)
            caught_no_twin = sum(x["one_sided"] and not x["one_sided_in_twin"] for x in chosen)
            lost_no_twin = sum(x["one_sided"] and not x["one_sided_in_twin"]
                               and not (x["high"] or x["low"]) for x in chosen)
            print(f"{name:<12} {fault:<22} one-sided {c['one_sided']:>4}/{c['events']} "
                  f"({caught_no_twin} no twin)  high {c['high']:>4}  two-sided {c['two_sided']:>4}  "
                  f"lost {c['lost']:>3} ({lost_no_twin} no twin)  kept by low {c['kept_by_low']:>3}  "
                  f"gained {c['gained']:>3} ({gained_attr} attributable)")

    print("\n=== OrbitVal: false alarms on faulted missions, mean per 10k over all cells ===")
    for name in DETECTORS:
        for r in (r for r in orbit if r["model"] == name):
            line = []
            for s in ("one_sided", "high_only", "low_only", "two_sided"):
                long = [c["metrics"][s]["false_alarms_per_10k"] for c in r["cells"]]
                short = [c["metrics"][s]["false_alarms_per_10k_short_grace"] for c in r["cells"]]
                line.append(f"{s} {sum(long) / len(long):.2f}/{sum(short) / len(short):.2f}")
            print(f"{name:<12} seed {r['seed']}  " + ", ".join(line))

    print("\n=== OrbitVal: where low-side false alarms happen, all seeds ===")
    for name in DETECTORS:
        rows = [r for r in orbit if r["model"] == name]
        for split, shares in (("val", "val"), ("clean_dev", "clean_dev"), ("faulted_dev", "clean_dev")):
            print(f"{name}, {split}")
            alarms = [{**a, "seed": (r["seed"], a["seed"])} for r in rows for a in r["low_alarms"][split]]
            _alarm_table(alarms, rows[0]["lighting_shares"][shares] if rows else None)

    for ds in ("smap", "msl"):
        print(f"\n=== {ds.upper()} dev channels ===")
        for name in DETECTORS:
            for r in (r for r in results if r["dataset"] == ds and r["model"] == name):
                c = outcome_counts(r["rows"])
                val = r["val"]
                print(f"{name:<12} seed {r['seed']}  {_thresholds(r)}")
                print(f"    recall: one-sided {c['one_sided']}/{c['events']}, high {c['high']}, "
                      f"low {c['low']}, two-sided {c['two_sided']}; lost {c['lost']}, "
                      f"kept by low {c['kept_by_low']}, gained {c['gained']}")
                print(f"    false alarms: {_fa(r['metrics'])}")
                print(f"    val: low {val['low_only']['false_alarms']} runs in {val['normal_steps']} steps, "
                      f"time in low alarm {100 * val['low_alarm_step_fraction']:.2f}%, "
                      f"lowest z {val['lowest_z']:.2f}")
                lost = [f"{x['channel']}#{x['event']}" for x in r["rows"]
                        if x["one_sided"] and not (x["high"] or x["low"])]
                gained = [f"{x['channel']}#{x['event']}" for x in r["rows"]
                          if x["low"] and not x["one_sided"] and not x["high"]]
                print(f"    lost {lost}; gained {gained}")
                print("    low-side false alarms by channel (flat share): " + ", ".join(
                    f"{a['channel']} {a['false_alarms']} ({a['flat_fraction']:.2f})"
                    for a in r["low_alarms"]["dev"]))


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Two-sided setting on dev data, from saved weights.")
    p.add_argument("command", choices=("run", "summarize"))
    p.add_argument("--dataset", choices=sorted(DATASETS))
    p.add_argument("--model", choices=sorted(MODELS) + ["persistence"])
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--data", default="data/telemanom")
    p.add_argument("--config", default="satellite.yaml")
    p.add_argument("--outdir", default="results/stage3")
    p.add_argument("--reps", type=int, default=20)
    p.add_argument("--val", type=int, default=30)
    p.add_argument("--threads", type=int, default=None, help="torch CPU threads")
    args = p.parse_args(argv)

    set_log_level("WARNING")
    if args.threads:
        torch.set_num_threads(args.threads)
    outdir = Path(args.outdir)
    if args.command == "summarize":
        summarize(outdir)
        return
    if not args.dataset or not args.model:
        p.error("run needs --dataset and --model")
    run_one(args.dataset, args.model, args.seed, outdir, args.data, args.config, args.reps, args.val)


if __name__ == "__main__":
    main()
