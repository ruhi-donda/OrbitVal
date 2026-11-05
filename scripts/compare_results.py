#!/usr/bin/env python3
"""
Check that a rerun reproduced earlier results.

Always checks the new OrbitVal results against the demo's tracked
thresholds and map counts. With a reference directory, also compares
every result file, number by number. Only training time is allowed to
differ. Exits 1 if anything else does.

Usage: scripts/compare_results.py NEW_DIR [REFERENCE_DIR]

Runs are repeatable on one machine. Another CPU or library version can
change floating-point results, and so training.
"""

import json
import math
import sys
from pathlib import Path

from export_demo_weights import DEST, build_manifest, build_maps, load_orbitval_results

IGNORED = {"train_seconds"}
TOLERANCE = 1e-9


def differences(a, b, path: str = "") -> list[str]:
    """Every place two JSON values differ, as readable lines."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for key in sorted((a.keys() | b.keys()) - IGNORED):
            if key not in a or key not in b:
                out.append(f"{path}/{key}: only in {'new' if key in a else 'reference'}")
            else:
                out += differences(a[key], b[key], f"{path}/{key}")
        return out
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return [f"{path}: length {len(a)} vs {len(b)}"]
        return [d for i, (x, y) in enumerate(zip(a, b)) for d in differences(x, y, f"{path}[{i}]")]
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if (math.isnan(a) and math.isnan(b)) or math.isclose(a, b, abs_tol=TOLERANCE):
            return []
    elif a == b:
        return []
    return [f"{path}: {a} vs {b}"]


def compare_dirs(new: Path, reference: Path) -> list[str]:
    new_files = {p.name for p in (new / "results").glob("*.json")}
    ref_files = {p.name for p in (reference / "results").glob("*.json")}
    out = [f"{name}: only in {'new' if name in new_files else 'reference'}"
           for name in sorted(new_files ^ ref_files)]
    for name in sorted(new_files & ref_files):
        a = json.loads((new / "results" / name).read_text())
        b = json.loads((reference / "results" / name).read_text())
        out += [f"{name}{d}" for d in differences(a, b)]
    return out


def compare_with_demo(new: Path, demo: Path = DEST) -> list[str]:
    """The demo's tracked numbers must be what this pipeline produces."""
    results = load_orbitval_results(new)
    out = []
    for name, built in (("manifest.json", build_manifest(results)), ("maps.json", build_maps(results))):
        out += [f"demo {name}{d}" for d in differences(built, json.loads((demo / name).read_text()))]
    return out


def main() -> int:
    new = Path(sys.argv[1])
    found = compare_with_demo(new)
    print(f"demo thresholds and maps: {len(found)} differences")
    if len(sys.argv) > 2:
        between = compare_dirs(new, Path(sys.argv[2]))
        print(f"all results vs {sys.argv[2]}: {len(between)} differences")
        found += between
    for line in found[:30]:
        print(" ", line)
    if len(found) > 30:
        print(f"  ...and {len(found) - 30} more")
    print("REPRODUCED" if not found else "NOT REPRODUCED")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
