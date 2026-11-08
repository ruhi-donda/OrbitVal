"""
orbitval/ml/run_heldout.py

The one held-out run (D34): persistence, LSTM and GRU, one-sided and
two-sided, on the held-out SMAP/MSL channels and the held-out-orbit
OrbitVal missions. Run it once, after every dev decision is frozen.
Nothing may be retuned from these numbers.

    scripts/run_heldout.sh results/heldout results/stage3      # the whole run

which does
    python -m orbitval.ml.run_heldout freeze --outdir D --weights W
    python -m orbitval.ml.run_heldout run --dataset smap --model gru --seed 0 --outdir D --weights W
    python -m orbitval.ml.run_heldout summarize --outdir D

Thresholds come from the same clean validation data as on dev, so the
held-out data is only ever scored, never used to choose anything.
"""

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path

import numpy as np
import torch

from orbitval.config.hardware_3u_schema import load_hardware_config
from orbitval.logging import set_log_level
from orbitval.ml.data.telemanom import load_spacecraft, split_channels
from orbitval.ml.evaluate import EVENT_GRACE, SHORT_GRACE
from orbitval.ml.models.baseline import PersistenceBaseline
from orbitval.ml.models.recurrent import MODELS
from orbitval.ml.run_neural import DATASETS, load_detector
from orbitval.ml.run_two_sided import DETECTORS, summarize as summarize_two_sided
from orbitval.ml.sim.missions import SEVERITIES
from orbitval.ml.two_sided import evaluate_orbitval, evaluate_telemanom

REPO = Path(__file__).resolve().parents[2]
SUB = "heldout"


def git_state() -> tuple[str, str]:
    """(commit, uncommitted changes to code) of this checkout."""
    def git(*args):
        return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True,
                              check=True).stdout.strip()
    return git("rev-parse", "HEAD"), git("status", "--porcelain", "--", "orbitval", "scripts",
                                         "pyproject.toml")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze(outdir: Path, weights: Path) -> dict:
    """
    Record what is about to be scored, before anything is. Refuses if
    this folder has a held-out run already, or if the code has
    uncommitted changes, so every number traces to one commit.
    """
    if (outdir / "frozen.json").exists() or (outdir / SUB).exists():
        raise SystemExit(f"{outdir} already has a held-out run. It is run once; not rerunning.")
    commit, dirty = git_state()
    if dirty:
        raise SystemExit(f"uncommitted changes, commit first:\n{dirty}")
    record = {
        "commit": commit,
        "weights_dir": str(weights),
        "weights_sha256": {p.name: _sha256(p) for p in sorted((weights / "weights").glob("*.pt"))},
        "frozen_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "frozen.json").write_text(json.dumps(record, indent=2))
    print(f"froze commit {commit[:7]} and {len(record['weights_sha256'])} checkpoints", flush=True)
    return record


def run_one(dataset: str, model: str, seed: int, outdir: Path, weights: Path, data_root: str,
            config_path: str, reps: int = 20, n_val: int = 30) -> dict:
    frozen_path = outdir / "frozen.json"
    if not frozen_path.exists():
        raise SystemExit("run `freeze` first")
    frozen = json.loads(frozen_path.read_text())
    if git_state() != (frozen["commit"], ""):
        raise SystemExit("the code changed since freeze")
    path = outdir / SUB / f"{dataset}_{model}_seed{seed}.json"
    if path.exists():
        raise SystemExit(f"{path} exists. The held-out run is run once; not rerunning.")

    if model == "persistence":
        detector = PersistenceBaseline()
    else:
        checkpoint = weights / "weights" / f"{dataset}_{model}_seed{seed}.pt"
        if _sha256(checkpoint) != frozen["weights_sha256"][checkpoint.name]:
            raise SystemExit(f"{checkpoint} changed since freeze")
        detector, _ = load_detector(checkpoint)

    if DATASETS[dataset]:
        channels = load_spacecraft(data_root, DATASETS[dataset])
        _dev, held_out = split_channels(channels)
        result = evaluate_telemanom(detector, channels, held_out, label="held_out")
    else:
        result = evaluate_orbitval(detector, load_hardware_config(config_path), reps, n_val,
                                   split="test")

    out = {"dataset": dataset, "model": model, "seed": seed, "split": "held_out", **result}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2))
    print(f"wrote {path}", flush=True)
    return out


def _metric_line(m: dict) -> str:
    return (f"recall {m['n_detected']}/{m['n_events']}  "
            f"FA {m['n_false_alarms']}/{m['n_false_alarms_short_grace']} runs "
            f"({m['false_alarms_per_10k']:.2f}/{m['false_alarms_per_10k_short_grace']:.2f} per 10k)  "
            f"delay {m['median_delay']:.0f}  F1 {m['point_f1']:.3f}  PR-AUC {m['pr_auc']:.3f}")


def _map(rows: list[dict], key) -> None:
    print(f"{'':<24}" + "".join(f"{s:>9}" for s in SEVERITIES))
    for fault in dict.fromkeys(x["fault"] for x in rows):
        cells = []
        for s in SEVERITIES:
            chosen = [x for x in rows if x["fault"] == fault and x["severity"] == s]
            cells.append(f"{sum(key(x) for x in chosen)}/{len(chosen)}")
        print(f"  {fault:<22}" + "".join(f"{c:>9}" for c in cells))


def summarize(outdir: Path) -> None:
    results = [json.loads(p.read_text()) for p in sorted((outdir / SUB).glob("*.json"))]
    frozen = json.loads((outdir / "frozen.json").read_text())
    print(f"HELD-OUT RUN, commit {frozen['commit'][:7]}, frozen {frozen['frozen_at']}")
    print(f"False alarms shown as grace {EVENT_GRACE}/grace {SHORT_GRACE}.")

    for ds in ("smap", "msl"):
        print(f"\n=== {ds.upper()} held-out channels: headline (one-sided at 2), then two-sided ===")
        for name in DETECTORS:
            for r in (r for r in results if r["dataset"] == ds and r["model"] == name):
                n_channels = r["metrics"]["one_sided"]["n_channels"]
                print(f"{name:<12} seed {r['seed']}  ({n_channels} channels)")
                print(f"    one-sided  {_metric_line(r['metrics']['one_sided'])}")
                print(f"    two-sided  {_metric_line(r['metrics']['two_sided'])}")

    orbit = [r for r in results if r["dataset"] == "orbitval"]
    for name in DETECTORS:
        rows = [x for r in orbit if r["model"] == name for x in r["rows"]]
        if not rows:
            continue
        seeds = sorted(r["seed"] for r in orbit if r["model"] == name)
        print(f"\n=== OrbitVal held-out orbits, {name}, seeds {seeds} pooled: missions detected ===")
        print("one-sided at 2 (headline)")
        _map(rows, lambda x: x["one_sided"])
        print("one-sided at 2, alarm not also in the clean twin")
        _map(rows, lambda x: x["one_sided"] and not x["one_sided_in_twin"])
        print("two-sided")
        _map(rows, lambda x: x["high"] or x["low"])
        print("low side, attributable")
        _map(rows, lambda x: x["low_attributable"])
        for setting in ("one_sided", "two_sided"):
            cells = [c["metrics"][setting] for r in orbit if r["model"] == name for c in r["cells"]]
            print(f"{setting} false alarms per 10k on faulted missions, mean over cells: "
                  f"{np.mean([c['false_alarms_per_10k'] for c in cells]):.2f}/"
                  f"{np.mean([c['false_alarms_per_10k_short_grace'] for c in cells]):.2f}; "
                  f"on clean twins: {np.mean([r['clean_test'][setting]['per_10k'] for r in orbit if r['model'] == name]):.2f}")

    print("\n\n######## Two-sided detail, same tables as on dev ########")
    summarize_two_sided(outdir, sub=SUB, split="test", channels_label="held_out")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="The one held-out run.")
    p.add_argument("command", choices=("freeze", "run", "summarize"))
    p.add_argument("--dataset", choices=sorted(DATASETS))
    p.add_argument("--model", choices=sorted(MODELS) + ["persistence"])
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--data", default="data/telemanom")
    p.add_argument("--config", default="satellite.yaml")
    p.add_argument("--outdir", default="results/heldout")
    p.add_argument("--weights", default="results/stage3", help="folder holding weights/")
    p.add_argument("--threads", type=int, default=None, help="torch CPU threads")
    args = p.parse_args(argv)

    set_log_level("WARNING")
    if args.threads:
        torch.set_num_threads(args.threads)
    outdir, weights = Path(args.outdir), Path(args.weights)
    if args.command == "freeze":
        freeze(outdir, weights)
    elif args.command == "summarize":
        summarize(outdir)
    else:
        if not args.dataset or not args.model:
            p.error("run needs --dataset and --model")
        run_one(args.dataset, args.model, args.seed, outdir, weights, args.data, args.config)


if __name__ == "__main__":
    main()
