#!/usr/bin/env bash
# Rebuild the project's dev results from a clean checkout:
#   1. check the data and Python setup
#   2. run the test suite
#   3. train LSTM and GRU (3 seeds) and evaluate them and persistence
#   4. write the tables to <outdir>/report.txt
#   5. check the results against the demo's tracked numbers, and against
#      a reference directory if one is given
#
# Dev data only. Nothing here scores the held-out channels or the test
# missions. CPU only. The full run took about 30 minutes with 4 jobs.
#
# Usage: scripts/reproduce.sh [--outdir DIR] [--jobs N] [--compare DIR] [--quick]
#   --quick   1 training epoch and few missions, to check the pipeline
#             runs (a few minutes). Its numbers mean nothing, so it skips
#             step 5.
#
# Setup:
#   python -m venv .venv && .venv/bin/pip install -e ".[ml,dev]"
#   scripts/download_telemanom.sh
set -euo pipefail

OUT="results/reproduce"
JOBS=4
COMPARE=""
QUICK=0
while [ $# -gt 0 ]; do
  case "$1" in
    --outdir)  OUT="$2"; shift 2 ;;
    --jobs)    JOBS="$2"; shift 2 ;;
    --compare) COMPARE="$2"; shift 2 ;;
    --quick)   QUICK=1; shift ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

export PYTHON="${PYTHON:-.venv/bin/python}"

echo "== 1. Checking setup"
for sub in train test labeled_anomalies.csv; do
  if [ ! -e "data/telemanom/$sub" ]; then
    echo "data/telemanom/$sub is missing: run scripts/download_telemanom.sh" >&2
    exit 1
  fi
done
"$PYTHON" -c "import torch, streamlit, matplotlib" || {
  echo "the [ml] extra is missing: pip install -e '.[ml,dev]'" >&2
  exit 1
}
# Never mix a new run into old results
if [ -e "$OUT/results" ] || [ -e "$OUT/weights" ]; then
  echo "$OUT already has results: choose another --outdir or remove them" >&2
  exit 1
fi
mkdir -p "$OUT"
{
  echo "commit: $(git rev-parse HEAD)"
  echo "uncommitted changes: $(git status --porcelain -- orbitval scripts pyproject.toml | wc -l | tr -d ' ')"
  "$PYTHON" -c "import platform, numpy, torch; print('python', platform.python_version()); print('numpy', numpy.__version__); print('torch', torch.__version__); print('machine', platform.platform())"
} > "$OUT/environment.txt"
cat "$OUT/environment.txt"

echo "== 2. Running tests"
"$PYTHON" -m pytest -q

echo "== 3. Training and evaluating, log in $OUT/run.log"
if [ "$QUICK" = 1 ]; then
  export TRAIN_ARGS="--max-epochs 1" EVAL_ARGS="--reps 2 --val 3"
fi
scripts/run_stage3.sh "$OUT" "$JOBS" > "$OUT/run.log" 2>&1 || {
  echo "training or evaluation failed, last lines of $OUT/run.log:" >&2
  tail -20 "$OUT/run.log" >&2
  exit 1
}

echo "== 4. Writing tables to $OUT/report.txt"
"$PYTHON" -m orbitval.ml.run_neural summarize --outdir "$OUT" > "$OUT/report.txt"

if [ "$QUICK" = 1 ]; then
  echo "== Quick run finished. Its numbers mean nothing; step 5 skipped."
  exit 0
fi

echo "== 5. Comparing"
# shellcheck disable=SC2086
"$PYTHON" scripts/compare_results.py "$OUT" $COMPARE
