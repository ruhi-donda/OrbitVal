#!/usr/bin/env bash
# Train LSTM and GRU on all three datasets with 3 seeds, then evaluate
# them and the persistence baseline on dev data. CPU only.
#
# Usage: scripts/run_stage3.sh [outdir] [parallel jobs]
# TRAIN_ARGS and EVAL_ARGS add options, used by reproduce.sh --quick.
set -euo pipefail

OUT="${1:-results/stage3}"
JOBS="${2:-4}"
PY="${PYTHON:-.venv/bin/python}"
RUN="$PY -m orbitval.ml.run_neural"
TRAIN_ARGS="${TRAIN_ARGS:-}"
EVAL_ARGS="${EVAL_ARGS:-}"
mkdir -p "$OUT"

for ds in msl smap orbitval; do for m in lstm gru; do for s in 0 1 2; do
  echo "train --dataset $ds --model $m --seed $s"
done; done; done | xargs -P "$JOBS" -I{} sh -c "$RUN {} --outdir $OUT --threads 2 $TRAIN_ARGS"

for ds in msl smap orbitval; do
  echo "eval --dataset $ds --model persistence"
  for m in lstm gru; do for s in 0 1 2; do
    echo "eval --dataset $ds --model $m --seed $s"
  done; done
done | xargs -P "$JOBS" -I{} sh -c "$RUN {} --outdir $OUT --threads 2 $EVAL_ARGS"

$RUN summarize --outdir "$OUT"
