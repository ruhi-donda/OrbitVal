#!/usr/bin/env bash
# Download the NASA SMAP/MSL telemanom dataset into data/telemanom/.
#
# The original S3 link (s3-us-west-2.amazonaws.com/telemanom/data.zip)
# returns 403 since 2025. The telemanom README now points to this Kaggle
# mirror, which needs a Kaggle API token (~/.kaggle/kaggle.json):
#     pip install kaggle
#
# Usage: scripts/download_telemanom.sh [dest]   (default: data/telemanom)
set -euo pipefail

DEST="${1:-data/telemanom}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

kaggle datasets download -d patrickfleith/nasa-anomaly-detection-dataset-smap-msl -p "$TMP"
unzip -q "$TMP"/*.zip -d "$TMP/unzipped"

# The archive nests train/ and test/ one or two levels down; find them.
TRAIN_DIR="$(find "$TMP/unzipped" -type d -name train | head -n 1)"
SRC="$(dirname "$TRAIN_DIR")"
mkdir -p "$DEST"
cp -R "$SRC/train" "$SRC/test" "$DEST/"

# Labels: from the archive if present, else from the telemanom repo
LABELS="$(find "$TMP/unzipped" -name labeled_anomalies.csv | head -n 1)"
if [ -n "$LABELS" ]; then
  cp "$LABELS" "$DEST/"
else
  curl -fsSL -o "$DEST/labeled_anomalies.csv" \
    https://raw.githubusercontent.com/khundman/telemanom/master/labeled_anomalies.csv
fi

echo "train: $(ls "$DEST/train" | wc -l | tr -d ' ') channels, test: $(ls "$DEST/test" | wc -l | tr -d ' ') channels -> $DEST"
