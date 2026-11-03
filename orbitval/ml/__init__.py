"""
orbitval/ml/

Detector-validation mode: inject faults into spacecraft telemetry and
measure how well anomaly detectors catch them — which faults, how fast,
and at what false-alarm rate.

Boundary with the rest of OrbitVal:
- Code here may import core OrbitVal (faults, orbits, registry, reporting).
- Core OrbitVal never imports from here. The only entry point back in is
  the lazily-imported `evaluate-detector` CLI subcommand.
- Everything except the neural models and the training loop is
  numpy-only, so it is testable without the optional [ml] extra.
- torch / streamlit are optional: `pip install orbitval[ml]`.

Every detector here is forecast-then-flag:
    1. forecast the next value from the past       (models/)
    2. score = smoothed absolute forecast error     (scoring.py)
    3. alarm when score > threshold                 (threshold.py)
Detectors differ ONLY in step 1, so differences in the results come
from the forecaster and not from post-processing.
"""
