#!/usr/bin/env python3
"""
Find the demo's preset scenes in the exported weights, by rules written
down here rather than by eye. Prints the first dev mission and onset that
meets each rule; the result is pasted into PRESETS in orbitval/ml/app/core.py.

Model seed 0 only, so a scene can't be picked by shopping for a lucky seed.
A scene shows one mission, so the page quotes the overall rate beside it.

    python scripts/pick_demo_presets.py
"""

from pathlib import Path

import numpy as np

from orbitval.config.hardware_3u_schema import load_hardware_config
from orbitval.logging import set_log_level
from orbitval.ml.app.core import load_demo_detector, load_manifest, run_demo
from orbitval.ml.evaluate import EVAL_WARMUP
from orbitval.ml.sim.missions import FAULT_STEPS, make_mission, mission_seed

SEED = 0
DETECTORS = ("persistence", "lstm", "gru")
# Full sun for this many steps either side of the fault (sunlit stretches last about 55)
SUN_MARGIN = 8
# A crossing must have this many steps on both sides of the light change
CROSSING_MARGIN = 8

# name: (fault, severity, channel, lighting, detectors that must catch it)
# Everything not listed must miss it, with no false alarm from anyone.
CASES = {
    "brownout in sunlight": ("power_brownout", 0.1, "solar_power_w", "sunlit", {"lstm", "gru"}),
    "stuck in sunlight": ("stuck_sensor", 0.0, "solar_power_w", "sunlit", set()),
    "stuck across eclipse edge": ("stuck_sensor", 0.0, "solar_power_w", "crossing", {"lstm", "gru"}),
    "sensor drift": ("sensor_drift", 1.0, "temperature_c", "sunlit", set()),
}


def onsets_for(illumination: np.ndarray, lighting: str) -> list[int]:
    """Onsets whose fault window has this lighting, in a fixed order."""
    sun = illumination >= 1.0
    out = []
    for onset in range(EVAL_WARMUP + 20, len(sun) - FAULT_STEPS - 60):
        if lighting == "sunlit":
            if sun[onset - SUN_MARGIN:onset + FAULT_STEPS + SUN_MARGIN].all():
                out.append(onset)
        else:
            head = sun[onset:onset + CROSSING_MARGIN]
            tail = sun[onset + FAULT_STEPS - CROSSING_MARGIN:onset + FAULT_STEPS]
            if (head.all() and not tail.any()) or (tail.all() and not head.any()):
                out.append(onset)
    return out


def main() -> None:
    set_log_level("WARNING")
    hardware = load_hardware_config(Path(__file__).parents[1] / "satellite.yaml")
    manifest = load_manifest()
    loaded = {name: load_demo_detector(name, SEED, manifest) for name in DETECTORS}

    for label, (fault, severity, channel, lighting, must_catch) in CASES.items():
        found = None
        tried = 0
        for mission in range(20):
            clean = make_mission(hardware, mission_seed("dev", mission))
            onsets = onsets_for(clean.illumination, lighting)
            # Middle of the qualifying stretch: furthest from other events
            for onset in sorted(onsets, key=lambda o: abs(o - np.median(onsets))):
                tried += 1
                summaries = {
                    name: run_demo(det, thr, hardware, fault, severity, onset, mission, channel).summary
                    for name, (det, thr) in loaded.items()
                }
                caught = {n for n, s in summaries.items() if s.detected}
                if caught == must_catch and not any(s.false for s in summaries.values()):
                    found = (mission, onset, summaries)
                    break
            if found:
                break
        if found is None:
            print(f"{label}: NOTHING after {tried} scenes")
            continue
        mission, onset, summaries = found
        delays = {n: s.delay_steps for n, s in summaries.items()}
        print(f"{label}: mission={mission} onset={onset} severity={severity} "
              f"caught={sorted(must_catch)} delays={delays} (scene {tried} tried)")


if __name__ == "__main__":
    main()
