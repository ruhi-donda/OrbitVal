"""
tests/test_cli_integration.py

End-to-end CLI integration tests — exercises the full command dispatch
path (cmd_list_faults, cmd_validate, cmd_run) as a stranger would invoke
it. Network is mocked throughout; no disk writes to the project tree.
"""

import sys
import types
import argparse
import pytest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from orbitval.cli import cmd_list_faults, cmd_validate, cmd_run

SATELLITE_YAML = str(Path(__file__).parent.parent / "satellite.yaml")

TLE1 = "1 25544U 98067A   24001.50000000  .00001000  00000+0  10000-4 0  9991"
TLE2 = "2 25544  51.6400 100.0000 0001000  90.0000 270.0000 15.50000000000010"


def _run_args(**kwargs) -> argparse.Namespace:
    """Build a minimal args Namespace for cmd_run with sensible defaults."""
    defaults = dict(
        verbose=False, quiet=False,
        config=SATELLITE_YAML,
        scenarios=None, autonomy=None,
        tle_name="ISS (ZARYA)", tle_line1=None, tle_line2=None,
        orbit_alt=None, orbit_inc=None, orbit_type="LEO",
        duration=1.0, step=60.0, seed=42,
        output=None,           # callers must set this to tmp_path
        ground_station=None,
    )
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


# ── list-faults ───────────────────────────────────────────────────────────────

class TestListFaults:
    def test_list_faults_exits_zero(self, capsys):
        args = argparse.Namespace()
        cmd_list_faults(args)   # should not raise or sys.exit

    def test_list_faults_names_known_scenarios(self, capsys):
        cmd_list_faults(argparse.Namespace())
        out = capsys.readouterr().out
        assert "gps_dropout" in out
        assert "power_brownout" in out
        assert "sensor_noise" in out

    def test_list_faults_shows_version(self, capsys):
        cmd_list_faults(argparse.Namespace())
        out = capsys.readouterr().out
        assert "1.0.0" in out


# ── validate ──────────────────────────────────────────────────────────────────

class TestValidate:
    def test_valid_config_exits_zero(self, capsys):
        args = argparse.Namespace(config=SATELLITE_YAML)
        cmd_validate(args)   # should not raise

    def test_valid_config_prints_tick(self, capsys):
        args = argparse.Namespace(config=SATELLITE_YAML)
        cmd_validate(args)
        out = capsys.readouterr().out
        assert "✓" in out

    def test_nonexistent_config_exits_one(self, capsys):
        args = argparse.Namespace(config="/this/does/not/exist.yaml")
        with pytest.raises(SystemExit) as exc:
            cmd_validate(args)
        assert exc.value.code == 1

    def test_nonexistent_config_prints_error(self, capsys):
        args = argparse.Namespace(config="/this/does/not/exist.yaml")
        with pytest.raises(SystemExit):
            cmd_validate(args)
        out = capsys.readouterr().out
        assert "✗" in out

    def test_invalid_config_exits_one(self, capsys, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("schema_version: '9.9'\nform_factor: 6U\n")
        args = argparse.Namespace(config=str(bad))
        with pytest.raises(SystemExit) as exc:
            cmd_validate(args)
        assert exc.value.code == 1

    def test_invalid_config_prints_error_detail(self, capsys, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("schema_version: '9.9'\nform_factor: 6U\n")
        args = argparse.Namespace(config=str(bad))
        with pytest.raises(SystemExit):
            cmd_validate(args)
        out = capsys.readouterr().out
        assert "✗" in out


# ── run — pre-launch mode ─────────────────────────────────────────────────────

class TestRunPrelaunch:
    def test_prelaunch_mode_exits_zero(self, tmp_path):
        args = _run_args(orbit_alt=500.0, orbit_inc=53.0, output=str(tmp_path))
        cmd_run(args)   # should not raise

    def test_prelaunch_mode_writes_report(self, tmp_path):
        args = _run_args(orbit_alt=500.0, orbit_inc=53.0, output=str(tmp_path))
        cmd_run(args)
        assert any(tmp_path.iterdir())

    def test_prelaunch_mode_no_network(self, tmp_path):
        args = _run_args(orbit_alt=500.0, orbit_inc=53.0, output=str(tmp_path))
        with patch("orbitval.engine.runner.fetch_tle") as mock_fetch:
            cmd_run(args)
        mock_fetch.assert_not_called()


# ── run — Mode 2 (manual TLE) ─────────────────────────────────────────────────

class TestRunModeTwoTLE:
    def test_mode2_exits_zero(self, tmp_path):
        args = _run_args(tle_line1=TLE1, tle_line2=TLE2, output=str(tmp_path))
        with patch("orbitval.engine.runner.fetch_tle"):
            cmd_run(args)

    def test_mode2_writes_report(self, tmp_path):
        args = _run_args(tle_line1=TLE1, tle_line2=TLE2, output=str(tmp_path))
        with patch("orbitval.engine.runner.fetch_tle"):
            cmd_run(args)
        assert any(tmp_path.iterdir())


# ── run — bad inputs ──────────────────────────────────────────────────────────

class TestRunBadInputs:
    def test_unknown_scenario_exits_one(self, tmp_path, capsys):
        args = _run_args(
            orbit_alt=500.0, orbit_inc=53.0,
            scenarios=["totally_fake_scenario"],
            output=str(tmp_path),
        )
        with pytest.raises(SystemExit) as exc:
            cmd_run(args)
        assert exc.value.code == 1

    def test_unknown_scenario_prints_error(self, tmp_path, capsys):
        args = _run_args(
            orbit_alt=500.0, orbit_inc=53.0,
            scenarios=["totally_fake_scenario"],
            output=str(tmp_path),
        )
        with pytest.raises(SystemExit):
            cmd_run(args)
        out = capsys.readouterr().out
        assert "✗" in out or "totally_fake_scenario" in out

    def test_only_tle_line1_exits_one(self, tmp_path, capsys):
        args = _run_args(tle_line1=TLE1, tle_line2=None, output=str(tmp_path))
        with pytest.raises(SystemExit) as exc:
            cmd_run(args)
        assert exc.value.code == 1

    def test_only_tle_line2_exits_one(self, tmp_path, capsys):
        args = _run_args(tle_line1=None, tle_line2=TLE2, output=str(tmp_path))
        with pytest.raises(SystemExit) as exc:
            cmd_run(args)
        assert exc.value.code == 1

    def test_missing_config_exits_one(self, tmp_path, capsys):
        args = _run_args(
            config="/no/such/satellite.yaml",
            orbit_alt=500.0, orbit_inc=53.0,
            output=str(tmp_path),
        )
        with pytest.raises(SystemExit) as exc:
            cmd_run(args)
        assert exc.value.code == 1

    def test_corrupted_config_exits_one(self, tmp_path, capsys):
        bad = tmp_path / "bad.yaml"
        bad.write_text("schema_version: '9.9'\nform_factor: 6U\n")
        args = _run_args(
            config=str(bad),
            orbit_alt=500.0, orbit_inc=53.0,
            output=str(tmp_path / "out"),
        )
        with pytest.raises(SystemExit) as exc:
            cmd_run(args)
        assert exc.value.code == 1

    def test_bad_autonomy_module_exits_one(self, tmp_path, capsys):
        bad_py = tmp_path / "broken.py"
        bad_py.write_text("raise ImportError('nope')\n")
        args = _run_args(
            orbit_alt=500.0, orbit_inc=53.0,
            autonomy=str(bad_py),
            output=str(tmp_path / "out"),
        )
        with pytest.raises(SystemExit) as exc:
            cmd_run(args)
        assert exc.value.code == 1

    def test_invalid_ground_station_format_exits_one(self, tmp_path, capsys):
        args = _run_args(
            orbit_alt=500.0, orbit_inc=53.0,
            ground_station=["BadFormat"],   # missing lat/lon
            output=str(tmp_path),
        )
        with pytest.raises(SystemExit) as exc:
            cmd_run(args)
        assert exc.value.code == 1
