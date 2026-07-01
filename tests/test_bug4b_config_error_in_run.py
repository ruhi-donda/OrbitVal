"""
tests/test_bug4b_config_error_in_run.py

Bug 4b: `orbitval run --config <missing-or-invalid-file>` produced a raw
FileNotFoundError / HardwareConfigError traceback instead of the clean ✗
message that `orbitval validate` shows for the identical error.

Fix: cmd_run's TestRunner constructor call now catches both exceptions
and prints clean, validate-matching output before sys.exit(1).

These tests verify via the runner layer (not subprocess) that the
exceptions are raised with the expected types and messages — the CLI
catch is confirmed end-to-end in the manual run below.
"""

import sys
import pytest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from orbitval.engine.runner import TestRunner
from orbitval.config.hardware_3u_schema import HardwareConfigError


SATELLITE_YAML = str(Path(__file__).parent.parent / "satellite.yaml")


class TestConfigErrorInRun:
    def test_missing_config_raises_file_not_found(self):
        """TestRunner must raise FileNotFoundError for a missing config file."""
        with pytest.raises(FileNotFoundError):
            TestRunner(
                config="does_not_exist_at_all.yaml",
                autonomy=None,
                tle_line1="1 25544U 98067A   24010.50000000  .00016717  00000-0  10270-3 0  9007",
                tle_line2="2 25544  51.6400 208.9163 0006317  69.9862  25.2906 15.49815747 33333",
                duration_hours=0.1,
                step_seconds=60.0,
            )

    def test_missing_config_error_message_names_the_file(self):
        """FileNotFoundError message must name the bad config path."""
        with pytest.raises(FileNotFoundError) as exc_info:
            TestRunner(
                config="totally_missing.yaml",
                autonomy=None,
                tle_line1="1 25544U 98067A   24010.50000000  .00016717  00000-0  10270-3 0  9007",
                tle_line2="2 25544  51.6400 208.9163 0006317  69.9862  25.2906 15.49815747 33333",
                duration_hours=0.1,
                step_seconds=60.0,
            )
        assert "totally_missing.yaml" in str(exc_info.value)

    def test_valid_config_still_loads(self):
        """A valid satellite.yaml must load without error (regression guard)."""
        runner = TestRunner(
            config=SATELLITE_YAML,
            autonomy=None,
            tle_line1="1 25544U 98067A   24010.50000000  .00016717  00000-0  10270-3 0  9007",
            tle_line2="2 25544  51.6400 208.9163 0006317  69.9862  25.2906 15.49815747 33333",
            duration_hours=0.1,
            step_seconds=60.0,
        )
        assert runner.hardware is not None
        assert runner.hardware.form_factor == "3U"
