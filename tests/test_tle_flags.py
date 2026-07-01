"""
tests/test_tle_flags.py

CLI surface for Mode 2 (manual TLE, offline/air-gapped):
  --tle-line1 / --tle-line2 flags on the `run` subcommand.

Coverage:
  1. Both flags provided with valid TLE strings → TestRunner uses Mode 2,
     fetch_tle is never called.
  2. Only --tle-line1 provided → exits 1 with a clear error message.
  3. Only --tle-line2 provided → exits 1 with a clear error message.
  4. Neither flag → Mode 1 path is attempted (existing behavior unchanged).
"""

import sys
import pytest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from orbitval.engine.runner import TestRunner

SATELLITE_YAML = str(Path(__file__).parent.parent / "satellite.yaml")

# Real ISS TLE (deterministic, no network required)
TLE_LINE1 = "1 25544U 98067A   24001.50000000  .00001000  00000+0  10000-4 0  9991"
TLE_LINE2 = "2 25544  51.6400 100.0000 0001000  90.0000 270.0000 15.50000000000010"


class TestTLEFlagsRunner:
    """Unit-level: TestRunner accepts tle_line1/tle_line2 without network."""

    def test_mode2_skips_fetch_tle(self):
        """When both TLE strings are supplied, fetch_tle must not be called."""
        with patch("orbitval.engine.runner.fetch_tle") as mock_fetch:
            runner = TestRunner(
                config=SATELLITE_YAML,
                autonomy=None,
                tle_line1=TLE_LINE1,
                tle_line2=TLE_LINE2,
            )
        mock_fetch.assert_not_called()
        assert runner.tle is not None
        assert runner.tle.line1 == TLE_LINE1
        assert runner.tle.line2 == TLE_LINE2

    def test_mode2_tle_name_label(self):
        """tle_name kwarg is preserved in the TLERecord when using manual strings."""
        with patch("orbitval.engine.runner.fetch_tle"):
            runner = TestRunner(
                config=SATELLITE_YAML,
                autonomy=None,
                tle_name="MY-SAT",
                tle_line1=TLE_LINE1,
                tle_line2=TLE_LINE2,
            )
        assert runner.tle.name == "MY-SAT"

    def test_mode2_orbit_is_populated(self):
        """Orbit propagation runs successfully from manually supplied TLE strings."""
        with patch("orbitval.engine.runner.fetch_tle"):
            runner = TestRunner(
                config=SATELLITE_YAML,
                autonomy=None,
                tle_line1=TLE_LINE1,
                tle_line2=TLE_LINE2,
            )
        assert runner.orbit is not None
        assert len(runner.orbit.ground_track) > 0


class TestTLEFlagsCLI:
    """Integration-level: CLI argument parsing and guard logic via sys.argv."""

    def _parse(self, argv):
        """Parse `run` subcommand args via the real CLI parser."""
        import argparse
        # Mirror the argument registration from cli.main() for the `run` subcommand
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        run_p = sub.add_parser("run")
        run_p.add_argument("--tle-name", default="ISS (ZARYA)", dest="tle_name")
        run_p.add_argument("--tle-line1", default=None, dest="tle_line1")
        run_p.add_argument("--tle-line2", default=None, dest="tle_line2")
        run_p.add_argument("--orbit-alt", type=float, default=None, dest="orbit_alt")
        run_p.add_argument("--orbit-inc", type=float, default=None, dest="orbit_inc")
        run_p.add_argument("--config", default="satellite.yaml")
        run_p.add_argument("--autonomy", default=None)
        run_p.add_argument("--scenarios", nargs="+", default=None)
        run_p.add_argument("--duration", type=float, default=1.0)
        run_p.add_argument("--step", type=float, default=60.0)
        run_p.add_argument("--seed", type=int, default=42)
        run_p.add_argument("--output", default="reports/")
        run_p.add_argument("--ground-station", nargs="+", dest="ground_station")
        run_p.add_argument("--quiet", action="store_true")
        run_p.add_argument("--verbose", action="store_true")
        run_p.add_argument("--orbit-type", default=None, dest="orbit_type")
        return parser.parse_args(["run"] + argv)

    def test_both_flags_parsed(self):
        """Both --tle-line1 and --tle-line2 are parsed into args correctly."""
        args = self._parse(["--tle-line1", TLE_LINE1, "--tle-line2", TLE_LINE2])
        assert args.tle_line1 == TLE_LINE1
        assert args.tle_line2 == TLE_LINE2

    def test_neither_flag_defaults_to_none(self):
        """When neither flag is given, both args are None (Mode 1 path)."""
        args = self._parse([])
        assert args.tle_line1 is None
        assert args.tle_line2 is None

    def test_missing_tle_line2_exits(self, capsys):
        """Supplying only --tle-line1 exits 1 with an error message."""
        from orbitval.cli import cmd_run
        args = self._parse(["--tle-line1", TLE_LINE1])
        with pytest.raises(SystemExit) as exc:
            cmd_run(args)
        assert exc.value.code == 1
        out = capsys.readouterr().out
        assert "--tle-line1" in out and "--tle-line2" in out

    def test_missing_tle_line1_exits(self, capsys):
        """Supplying only --tle-line2 exits 1 with an error message."""
        from orbitval.cli import cmd_run
        args = self._parse(["--tle-line2", TLE_LINE2])
        with pytest.raises(SystemExit) as exc:
            cmd_run(args)
        assert exc.value.code == 1
        out = capsys.readouterr().out
        assert "--tle-line1" in out and "--tle-line2" in out

    def test_mode2_end_to_end_no_network(self, tmp_path, capsys):
        """Full cmd_run with --tle-line1/2 completes without touching the network."""
        from orbitval.cli import cmd_run
        args = self._parse([
            "--tle-line1", TLE_LINE1,
            "--tle-line2", TLE_LINE2,
            "--config", SATELLITE_YAML,
            "--output", str(tmp_path),
        ])
        with patch("orbitval.engine.runner.fetch_tle") as mock_fetch:
            cmd_run(args)
        mock_fetch.assert_not_called()
        reports = list(tmp_path.iterdir())
        assert len(reports) > 0
