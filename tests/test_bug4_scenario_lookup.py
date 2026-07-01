"""
tests/test_bug4_scenario_lookup.py

Bug 4: runner.run() was using an unsafe __import__().FAULT_REGISTRY[name]
lookup that crashed with a raw KeyError on an unknown scenario name,
bypassing get_fault()'s clean ValueError handling.

Fix: explicit `if name not in FAULT_REGISTRY` guard raises ValueError;
cmd_run in cli.py catches ValueError and prints a clean error message.
"""

import pytest
import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

# Ensure the package root is on the path when running from tests/
sys.path.insert(0, str(Path(__file__).parent.parent))

from orbitval.engine.runner import TestRunner


# ---------------------------------------------------------------------------
# Minimal autonomy stub for use in tests that need to instantiate TestRunner
# ---------------------------------------------------------------------------
class _NoopAutonomy:
    def process(self, telemetry):
        return "nominal"

    def reset(self):
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
SATELLITE_YAML = str(Path(__file__).parent.parent / "satellite.yaml")


def _make_runner():
    """Create a TestRunner using manual TLE strings (no network required)."""
    return TestRunner(
        config=SATELLITE_YAML,
        autonomy=_NoopAutonomy(),
        tle_line1="1 25544U 98067A   24010.50000000  .00016717  00000-0  10270-3 0  9007",
        tle_line2="2 25544  51.6400 208.9163 0006317  69.9862  25.2906 15.49815747 33333",
        duration_hours=0.1,
        step_seconds=60.0,
        seed=42,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestUnknownScenarioRaisesCleanError:
    def test_unknown_scenario_raises_value_error(self, tmp_path):
        """runner.run() must raise ValueError (not KeyError) for an unknown scenario name."""
        runner = _make_runner()
        with pytest.raises(ValueError, match="not found"):
            runner.run(
                scenarios=["totally_fake_fault"],
                output_dir=str(tmp_path),
                mission_profile={"orbit_type": "LEO", "altitude_band_km": None,
                                  "inclination_deg": None, "operational_lifetime_years": None},
            )

    def test_error_message_lists_available_scenarios(self, tmp_path):
        """ValueError message must name the available scenarios so user knows what to use."""
        runner = _make_runner()
        with pytest.raises(ValueError) as exc_info:
            runner.run(
                scenarios=["nonexistent"],
                output_dir=str(tmp_path),
                mission_profile={"orbit_type": "LEO", "altitude_band_km": None,
                                  "inclination_deg": None, "operational_lifetime_years": None},
            )
        msg = str(exc_info.value)
        assert "gps_dropout" in msg
        assert "power_brownout" in msg
        assert "sensor_noise" in msg

    def test_known_scenarios_still_work(self, tmp_path):
        """Valid scenario names must continue working after the fix."""
        runner = _make_runner()
        report = runner.run(
            scenarios=["gps_dropout"],
            output_dir=str(tmp_path),
            mission_profile={"orbit_type": "LEO", "altitude_band_km": None,
                              "inclination_deg": None, "operational_lifetime_years": None},
        )
        assert report["scenarios_run"][0]["name"] == "gps_dropout"
        assert report["scenarios_run"][0]["result"] in ("PASS", "FAIL", "SKIP")

    def test_unknown_scenario_not_key_error(self, tmp_path):
        """Confirm the old crash (KeyError) is gone — only ValueError is acceptable."""
        runner = _make_runner()
        with pytest.raises(ValueError):
            runner.run(
                scenarios=["bad_name"],
                output_dir=str(tmp_path),
                mission_profile={"orbit_type": "LEO", "altitude_band_km": None,
                                  "inclination_deg": None, "operational_lifetime_years": None},
            )
        # If we reach here without a KeyError, the fix is in place.
        # pytest.raises(ValueError) above would have failed if KeyError was raised.
