#!/usr/bin/env bash
# The one held-out run (D34): freeze the code and weights, score every
# detector one-sided and two-sided on the held-out SMAP/MSL channels and
# held-out-orbit OrbitVal missions, then write the report. CPU only.
# Refuses to run into a folder that already has a held-out run, or from
# uncommitted code.
#
# Usage: scripts/run_heldout.sh OUTDIR WEIGHTS_DIR [parallel jobs]
#   WEIGHTS_DIR is the folder holding weights/, e.g. results/stage3
set -euo pipefail

OUT="$1"
W="$2"
JOBS="${3:-4}"
PY="${PYTHON:-.venv/bin/python}"
RUN="$PY -m orbitval.ml.run_heldout"

$RUN freeze --outdir "$OUT" --weights "$W"

for ds in msl smap orbitval; do
  echo "run --dataset $ds --model persistence"
  for m in lstm gru; do for s in 0 1 2; do
    echo "run --dataset $ds --model $m --seed $s"
  done; done
done | xargs -P "$JOBS" -I{} sh -c "$RUN {} --outdir $OUT --weights $W --threads 2"

$RUN summarize --outdir "$OUT" > "$OUT/heldout_report.txt"
echo "report: $OUT/heldout_report.txt"
