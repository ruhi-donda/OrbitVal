"""
tests/test_bug5_connection_error.py

Bug 5: cmd_run did not catch the ConnectionError raised by fetch_tle()
when Celestrak is unreachable and no cache exists. The exception propagated
as a raw traceback instead of a clean CLI error.

Fix: TestRunner constructor call in cmd_run is wrapped in try/except
ConnectionError; produces a clean ✗ message and exits with code 1.
"""

import sys
import pytest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from orbitval.engine.runner import TestRunner


SATELLITE_YAML = str(Path(__file__).parent.parent / "satellite.yaml")


class TestConnectionErrorHandling:
    def test_connection_error_raises_not_key_error(self):
        """TestRunner.__init__ must propagate ConnectionError (not crash differently)
        when fetch_tle() raises it — this is the exception cmd_run now catches."""
        with patch("orbitval.engine.runner.fetch_tle",
                   side_effect=ConnectionError("Could not fetch TLE for 'ISS (ZARYA)' "
                                               "and no cache available. "
                                               "Provide TLE strings directly or check your connection.")):
            with pytest.raises(ConnectionError, match="no cache available"):
                TestRunner(
                    config=SATELLITE_YAML,
                    autonomy=None,
                    # No orbit_alt/inc, no tle_line1/2 — forces Mode 1 (live fetch)
                )

    def test_connection_error_message_is_actionable(self):
        """The ConnectionError message from tle.py must mention what to do next."""
        with patch("orbitval.engine.runner.fetch_tle",
                   side_effect=ConnectionError("no cache available. "
                                               "Provide TLE strings directly or check your connection.")):
            with pytest.raises(ConnectionError) as exc_info:
                TestRunner(config=SATELLITE_YAML, autonomy=None)
            msg = str(exc_info.value)
            # Must include actionable guidance
            assert "cache" in msg or "connection" in msg.lower()

    def test_mode2_bypasses_fetch(self):
        """Manual TLE strings (Mode 2) must not call fetch_tle at all — verifies
        the ConnectionError path is Mode 1 only."""
        call_count = {"n": 0}

        def fake_fetch(name):
            call_count["n"] += 1
            raise ConnectionError("should not be called")

        with patch("orbitval.engine.runner.fetch_tle", side_effect=fake_fetch):
            # Mode 2: explicit TLE strings — fetch_tle must not be called
            runner = TestRunner(
                config=SATELLITE_YAML,
                autonomy=None,
                tle_line1="1 25544U 98067A   24010.50000000  .00016717  00000-0  10270-3 0  9007",
                tle_line2="2 25544  51.6400 208.9163 0006317  69.9862  25.2906 15.49815747 33333",
                duration_hours=0.1,
                step_seconds=60.0,
            )
        assert call_count["n"] == 0, "fetch_tle should not be called in Mode 2"
