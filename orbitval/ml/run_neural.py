"""
orbitval/ml/run_neural.py

Train and evaluate forecasters. Dev data only: no path here scores the
held-out channels or the test missions.

    python -m orbitval.ml.run_neural train --dataset smap --model lstm --seed 0
    python -m orbitval.ml.run_neural eval  --dataset smap --model lstm --seed 0
    python -m orbitval.ml.run_neural eval  --dataset orbitval --model persistence
    python -m orbitval.ml.run_neural summarize

Weights go to <outdir>/weights, results to <outdir>/results.
"""

import argparse
import json
import math
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np
import torch

from orbitval.config.hardware_3u_schema import load_hardware_config
from orbitval.logging import set_log_level
from orbitval.ml.data.telemanom import load_spacecraft, split_channels
from orbitval.ml.data.training_sets import orbitval_training_set, telemanom_training_set
from orbitval.ml.evaluate import evaluate
from orbitval.ml.models.baseline import PersistenceBaseline
from orbitval.ml.models.neural_detector import NeuralDetector
from orbitval.ml.models.recurrent import HIDDEN_SIZE, MODELS, WINDOW
from orbitval.ml.sim.missions import SEVERITIES, detectability_map, fault_error_analysis
from orbitval.ml.train import TrainConfig, train_forecaster

DATASETS = {"smap": "SMAP", "msl": "MSL", "orbitval": None}
SEEDS = (0, 1, 2)


def _checkpoint_path(outdir: Path, dataset: str, model: str, seed: int) -> Path:
    return outdir / "weights" / f"{dataset}_{model}_seed{seed}.pt"


def _result_path(outdir: Path, dataset: str, model: str, seed: int) -> Path:
    return outdir / "results" / f"{dataset}_{model}_seed{seed}.json"


def train_one(dataset: str, model_name: str, seed: int, outdir: Path,
              data_root: str, config_path: str, config: TrainConfig = TrainConfig()) -> dict:
    """Train one model on normal data and save its checkpoint."""
    if DATASETS[dataset]:
        tset = telemanom_training_set(load_spacecraft(data_root, DATASETS[dataset]), WINDOW)
    else:
        tset = orbitval_training_set(load_hardware_config(config_path), WINDOW)

    torch.manual_seed(seed)                # controls the initial weights
    model = MODELS[model_name](HIDDEN_SIZE)
    n_params = sum(p.numel() for p in model.parameters())
    tag = f"{dataset}/{model_name}/seed{seed}"
    print(f"{tag}: {len(tset.X_train)} train windows, {len(tset.X_val)} val, {n_params} params", flush=True)

    started = time.time()
    result = train_forecaster(model, tset.X_train, tset.y_train, tset.X_val, tset.y_val,
                              config, seed=seed,
                              log=lambda msg: print(f"{tag} {msg}", flush=True))
    checkpoint = {
        "dataset": dataset, "model": model_name, "seed": seed,
        "hidden_size": HIDDEN_SIZE, "window": WINDOW,
        "mean": tset.mean, "std": tset.std,
        "state_dict": model.state_dict(),
        "history": asdict(result),
        "n_params": n_params,
        "train_seconds": time.time() - started,
    }
    path = _checkpoint_path(outdir, dataset, model_name, seed)
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(checkpoint, path)
    print(f"{tag}: best epoch {result.best_epoch}, val MSE {result.best_val_loss:.6f}, "
          f"{checkpoint['train_seconds']:.0f}s", flush=True)
    return checkpoint


def load_detector(path: str | Path) -> tuple[NeuralDetector, dict]:
    """Rebuild a detector from a checkpoint. Runs on CPU."""
    ckpt = torch.load(path, map_location="cpu", weights_only=True)
    model = MODELS[ckpt["model"]](ckpt["hidden_size"])
    model.load_state_dict(ckpt["state_dict"])
    return NeuralDetector(model, ckpt["mean"], ckpt["std"], ckpt["window"]), ckpt


def eval_one(dataset: str, model_name: str, seed: int, outdir: Path, data_root: str,
             config_path: str, reps: int = 20, n_val: int = 30, budget: float = 2.0) -> dict:
    """Evaluate one trained model (or the baseline) on dev data, and save JSON."""
    if model_name == "persistence":
        detector, ckpt = PersistenceBaseline(), None
    else:
        detector, ckpt = load_detector(_checkpoint_path(outdir, dataset, model_name, seed))

    out = {"dataset": dataset, "model": model_name, "seed": seed, "budget_per_10k": budget}
    if ckpt:
        out["history"] = ckpt["history"]
        out["n_params"] = ckpt["n_params"]
        out["train_seconds"] = ckpt["train_seconds"]

    if DATASETS[dataset]:
        channels = load_spacecraft(data_root, DATASETS[dataset])
        dev, _held_out = split_channels(channels)
        r = evaluate(detector, channels, dev, budget_per_10k=budget)
        out["calibration"] = asdict(r.calibration)
        out["metrics"] = asdict(r.metrics)
    else:
        hardware = load_hardware_config(config_path)
        cal, cells = detectability_map(detector, hardware, split="dev", n_reps=reps,
                                       n_val=n_val, budget_per_10k=budget)
        out["calibration"] = asdict(cal)
        out["reps"] = reps
        out["cells"] = [{"fault": c.fault, "severity": c.severity, "metrics": asdict(c.metrics)}
                        for c in cells]
        out["error_analysis"] = {
            "stuck_sensor": fault_error_analysis(detector, hardware, "stuck_sensor", 1.0,
                                                 "solar_power_w", cal.threshold, n_reps=reps),
            "sensor_drift": fault_error_analysis(detector, hardware, "sensor_drift", 1.0,
                                                 "temperature_c", cal.threshold, n_reps=reps),
        }

    path = _result_path(outdir, dataset, model_name, seed)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2))
    print(f"wrote {path}", flush=True)
    return out


def _mean_std(values: list[float]) -> str:
    v = [x for x in values if not math.isnan(x)]
    if not v:
        return "n/a"
    return f"{np.mean(v):.2f}±{np.std(v):.2f}"


def _plot_maps(orbit: list[dict], outdir: Path) -> None:
    """One heatmap per detector: event recall averaged over seeds."""
    try:
        from orbitval.ml.plots import plot_detectability
    except ImportError:
        return
    for name in ("persistence", "lstm", "gru"):
        rows = [r for r in orbit if r["model"] == name]
        if not rows:
            continue
        cells = [
            {"fault": c["fault"], "severity": c["severity"], "metrics": {"event_recall": float(np.mean(
                [other["metrics"]["event_recall"] for r in rows for other in r["cells"]
                 if other["fault"] == c["fault"] and other["severity"] == c["severity"]]))}}
            for c in rows[0]["cells"]
        ]
        plot_detectability(
            {"detector": f"{name}, mean of {len(rows)} seed(s)", "split": "dev",
             "reps": rows[0]["reps"], "cells": cells},
            outdir / f"map_{name}.png")


def summarize(outdir: Path) -> None:
    """Print every table in the stage report from the saved result files."""
    results = [json.loads(p.read_text()) for p in sorted((outdir / "results").glob("*.json"))]

    print("\n=== SMAP/MSL dev channels: event recall as counts, per seed ===")
    for ds in ("smap", "msl"):
        for name in ("persistence", "lstm", "gru"):
            rows = [r for r in results if r["dataset"] == ds and r["model"] == name]
            if not rows:
                continue
            m = [r["metrics"] for r in rows]
            counts = ", ".join(f"{x['n_detected']}/{x['n_events']}" for x in m)
            print(f"{ds:<5}{name:<12} recall {counts:<20} "
                  f"rate {_mean_std([x['event_recall'] for x in m])}  "
                  f"FA/10k {_mean_std([x['false_alarms_per_10k'] for x in m])}  "
                  f"(FA runs {[x['n_false_alarms'] for x in m]})  "
                  f"delay {_mean_std([x['median_delay'] for x in m])}  "
                  f"F1 {_mean_std([x['point_f1'] for x in m])}  "
                  f"PR-AUC {_mean_std([x['pr_auc'] for x in m])}  "
                  f"unscoreable {[x['n_unscoreable'] for x in m]}  "
                  f"thr {[round(r['calibration']['threshold'], 2) for r in rows]}")

    orbit = [r for r in results if r["dataset"] == "orbitval"]
    print("\n=== OrbitVal dev missions: event recall, mean over seeds ===")
    for name in ("persistence", "lstm", "gru"):
        rows = [r for r in orbit if r["model"] == name]
        if not rows:
            continue
        print(f"\n{name} ({len(rows)} seed(s)), thresholds "
              f"{[round(r['calibration']['threshold'], 2) for r in rows]}, "
              f"val FA/10k {[round(r['calibration']['false_alarms_per_10k'], 2) for r in rows]}")
        print(f"{'fault':<22}" + "".join(f"{s:>11}" for s in SEVERITIES))
        for fault in dict.fromkeys(c["fault"] for c in rows[0]["cells"]):
            line = f"{fault:<22}"
            for s in SEVERITIES:
                recalls = [c["metrics"]["event_recall"] for r in rows for c in r["cells"]
                           if c["fault"] == fault and c["severity"] == s]
                line += f"{_mean_std(recalls):>11}"
            print(line)
        fa = [c["metrics"]["false_alarms_per_10k"] for r in rows for c in r["cells"]]
        print(f"false alarms/10k on faulted missions: mean {np.mean(fa):.2f}, max {np.max(fa):.2f}")

    _plot_maps(orbit, outdir)

    print("\n=== Forecast error inside the fault window vs the same steps with no fault ===")
    for fault in ("stuck_sensor", "sensor_drift"):
        print(f"\n{fault}")
        for name in ("persistence", "lstm", "gru"):
            for r in (r for r in orbit if r["model"] == name):
                a = r["error_analysis"][fault]
                for lighting, g in a["by_lighting"].items():
                    print(f"  {name:<12} seed {r['seed']} {lighting:<9} n={g['n']:<3} "
                          f"clean {g['mean_error_clean']:.3f}  faulted {g['mean_error_faulted']:.3f}  "
                          f"error went down {g['n_error_down']}/{g['n']}  "
                          f"detected {g['n_detected']}/{g['n']}  "
                          f"mean peak z {g['mean_peak_score']:.2f}")

    print("\n=== Training ===")
    for r in results:
        if "history" in r:
            h = r["history"]
            print(f"{r['dataset']:<9}{r['model']:<5} seed {r['seed']}  best epoch {h['best_epoch']:>2}  "
                  f"epochs run {len(h['val_losses']):>2}  val MSE {h['best_val_loss']:.6f}  "
                  f"params {r['n_params']}  {r['train_seconds']:.0f}s")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Train and evaluate forecasters on dev data.")
    p.add_argument("command", choices=("train", "eval", "summarize"))
    p.add_argument("--dataset", choices=sorted(DATASETS))
    p.add_argument("--model", choices=sorted(MODELS) + ["persistence"])
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--data", default="data/telemanom")
    p.add_argument("--config", default="satellite.yaml")
    p.add_argument("--outdir", default="results/stage3")
    p.add_argument("--max-epochs", type=int, default=TrainConfig.max_epochs)
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
        p.error(f"{args.command} needs --dataset and --model")
    if args.command == "train":
        if args.model == "persistence":
            p.error("persistence has nothing to train")
        train_one(args.dataset, args.model, args.seed, outdir, args.data, args.config,
                  TrainConfig(max_epochs=args.max_epochs))
    else:
        eval_one(args.dataset, args.model, args.seed, outdir, args.data, args.config,
                 reps=args.reps, n_val=args.val)


if __name__ == "__main__":
    main()
