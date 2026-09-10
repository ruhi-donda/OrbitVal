"""
tests/test_cli_main.py

Exercises the real argparse wiring in cli.main() (Q13).

Every other CLI test hand-builds an argparse.Namespace, and
test_tle_flags.py mirrors the parser definition instead of using it — so
the actual add_argument calls in main() had zero coverage and a broken
or renamed flag would have shipped unnoticed. These tests drive the
program the way a user does, through sys.argv.

Also covers the new surface: --epoch (Q2), --registry (Q10),
python -m orbitval (Q9) and the single-sourced version (Q6).
"""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from orbitval import __version__
from orbitval.cli import main

REPO = Path(__file__).parent.parent
SATELLITE_YAML = str(REPO / "satellite.yaml")


def run_cli(*argv) -> None:
    """Invoke cli.main() as if from the command line."""
    with patch.object(sys, "argv", ["orbitval", *argv]):
        main()


def run_cli_expect_exit(*argv) -> int:
    with pytest.raises(SystemExit) as exc:
        run_cli(*argv)
    return exc.value.code


def _prelaunch(tmp_path, *extra):
    return (
        "run", "--config", SATELLITE_YAML,
        "--orbit-alt", "550", "--orbit-inc", "53.0",
        "--epoch", "2026-09-08T00:00:00",
        "--scenarios", "gps_dropout",
        "--output", str(tmp_path),
        *extra,
    )


class TestParserWiring:
    def test_no_subcommand_exits_two(self):
        assert run_cli_expect_exit() == 2

    def test_unknown_subcommand_exits_two(self):
        assert run_cli_expect_exit("teleport") == 2

    def test_version_flag_reports_package_version(self, capsys):
        assert run_cli_expect_exit("--version") == 0
        assert __version__ in capsys.readouterr().out

    def test_list_faults_through_main(self, capsys):
        run_cli("list-faults")
        out = capsys.readouterr().out
        assert "gps_dropout" in out and "star_tracker_failure" in out

    def test_validate_through_main(self, capsys):
        run_cli("validate", "--config", SATELLITE_YAML)
        assert "✓" in capsys.readouterr().out

    def test_validate_bad_config_exits_one(self, tmp_path, capsys):
        bad = tmp_path / "bad.yaml"
        bad.write_text("schema_version: '9.9'\nform_factor: 6U\n")
        assert run_cli_expect_exit("validate", "--config", str(bad)) == 1

    def test_registry_verify_requires_subcommand(self):
        assert run_cli_expect_exit("registry") == 2

    def test_unknown_flag_exits_two(self, tmp_path):
        assert run_cli_expect_exit("run", "--not-a-flag", "x") == 2


class TestRunThroughMain:
    def test_prelaunch_run_writes_all_three_artifacts(self, tmp_path):
        run_cli(*_prelaunch(tmp_path))
        suffixes = {p.suffix for p in tmp_path.iterdir()}
        assert {".json", ".pdf", ".log"} <= suffixes

    def test_run_never_touches_network_in_prelaunch(self, tmp_path):
        with patch("orbitval.engine.runner.fetch_tle") as fetch:
            run_cli(*_prelaunch(tmp_path))
        fetch.assert_not_called()

    def test_failing_autonomy_exits_one(self, tmp_path):
        code = run_cli_expect_exit(
            *_prelaunch(tmp_path, "--autonomy",
                        str(REPO / "examples" / "bad_autonomy.py")))
        assert code == 1

    def test_step_flag_reaches_the_report(self, tmp_path):
        run_cli(*_prelaunch(tmp_path, "--step", "30"))
        report = json.loads(next(tmp_path.glob("*.json")).read_text())
        assert report["scenarios_run"][0]["duration_s"] % 30 == 0

    def test_seed_flag_reaches_the_report(self, tmp_path):
        run_cli(*_prelaunch(tmp_path, "--seed", "7"))
        report = json.loads(next(tmp_path.glob("*.json")).read_text())
        assert report["simulation"]["seed"] == 7

    def test_quiet_and_verbose_both_accepted(self, tmp_path):
        run_cli(*_prelaunch(tmp_path / "q", "--quiet"))
        run_cli(*_prelaunch(tmp_path / "v", "--verbose"))


class TestEpochFlag:
    def test_epoch_recorded_as_provided(self, tmp_path):
        run_cli(*_prelaunch(tmp_path))
        report = json.loads(next(tmp_path.glob("*.json")).read_text())
        assert report["simulation"]["epoch_source"] == "provided"
        assert report["simulation"]["orbit_epoch"].startswith("2026-09-08")

    def test_two_runs_same_epoch_agree_on_everything_but_identity(self, tmp_path):
        run_cli(*_prelaunch(tmp_path / "a", "--scenarios",
                            "eclipse_power_stress", "--duration", "3"))
        run_cli(*_prelaunch(tmp_path / "b", "--scenarios",
                            "eclipse_power_stress", "--duration", "3"))
        a = json.loads(next((tmp_path / "a").glob("*.json")).read_text())
        b = json.loads(next((tmp_path / "b").glob("*.json")).read_text())
        assert a["eclipse_periods"] == b["eclipse_periods"]
        assert a["injection_trace"] == b["injection_trace"]
        assert a["scenarios_run"] == b["scenarios_run"]
        assert a["report_id"] != b["report_id"]

    def test_invalid_epoch_exits_one(self, tmp_path, capsys):
        code = run_cli_expect_exit(
            "run", "--config", SATELLITE_YAML,
            "--orbit-alt", "550", "--orbit-inc", "53.0",
            "--epoch", "not-a-date", "--output", str(tmp_path))
        assert code == 1
        assert "epoch" in capsys.readouterr().out.lower()

    def test_epoch_with_tle_mode_is_rejected(self, tmp_path, capsys):
        from tests.conftest import TLE1, TLE2
        code = run_cli_expect_exit(
            "run", "--config", SATELLITE_YAML,
            "--tle-line1", TLE1, "--tle-line2", TLE2,
            "--epoch", "2026-09-08T00:00:00", "--output", str(tmp_path))
        assert code == 1
        assert "pre-launch" in capsys.readouterr().out


class TestRegistryFlag:
    def test_run_registers_into_explicit_registry(self, tmp_path):
        registry = tmp_path / "custom" / "reg.jsonl"
        run_cli(*_prelaunch(tmp_path / "out", "--registry", str(registry)))
        assert registry.exists(), "--registry on run was ignored"
        report = json.loads(next((tmp_path / "out").glob("*.json")).read_text())
        assert report["test_integrity_hash"] in registry.read_text()

    def test_verify_report_confirms_against_that_registry(self, tmp_path, capsys):
        registry = tmp_path / "reg.jsonl"
        out = tmp_path / "out"
        run_cli(*_prelaunch(out, "--registry", str(registry)))
        report_path = next(out.glob("*.json"))
        run_cli("verify-report", str(report_path), "--registry", str(registry))
        assert "confirmed" in capsys.readouterr().out

    def test_registry_verify_reports_intact_chain(self, tmp_path, capsys):
        registry = tmp_path / "reg.jsonl"
        run_cli(*_prelaunch(tmp_path / "out", "--registry", str(registry)))
        run_cli("registry", "verify", "--registry", str(registry))
        assert "intact" in capsys.readouterr().out

    def test_missing_registry_exits_one(self, tmp_path):
        code = run_cli_expect_exit(
            "registry", "verify", "--registry", str(tmp_path / "nope.jsonl"))
        assert code == 1


class TestGroundStationParsing:
    def test_non_numeric_latitude_exits_one(self, tmp_path, capsys):
        code = run_cli_expect_exit(
            *_prelaunch(tmp_path, "--ground-station", "Rutgers,north,-74.4"))
        assert code == 1
        assert "numbers" in capsys.readouterr().out

    def test_out_of_range_latitude_exits_one(self, tmp_path, capsys):
        code = run_cli_expect_exit(
            *_prelaunch(tmp_path, "--ground-station", "Rutgers,999,-74.4"))
        assert code == 1
        assert "latitude" in capsys.readouterr().out

    def test_out_of_range_longitude_exits_one(self, tmp_path, capsys):
        code = run_cli_expect_exit(
            *_prelaunch(tmp_path, "--ground-station", "Rutgers,40.5,-999"))
        assert code == 1
        assert "longitude" in capsys.readouterr().out

    def test_too_few_fields_exits_one(self, tmp_path):
        assert run_cli_expect_exit(
            *_prelaunch(tmp_path, "--ground-station", "JustAName")) == 1


class TestModuleEntryPoint:
    def test_python_m_orbitval_runs(self):
        r = subprocess.run(
            [sys.executable, "-m", "orbitval", "--version"],
            cwd=REPO, capture_output=True, text=True,
        )
        assert r.returncode == 0, r.stderr
        assert __version__ in r.stdout


class TestVersionSingleSource:
    def test_cli_banner_matches_package_version(self, capsys):
        run_cli_expect_exit("--version")
        assert capsys.readouterr().out.strip() == f"OrbitVal {__version__}"

    def test_report_stamps_package_version(self, tmp_path):
        run_cli(*_prelaunch(tmp_path))
        report = json.loads(next(tmp_path.glob("*.json")).read_text())
        assert report["orbitval_version"] == __version__

    def test_user_agent_matches_package_version(self):
        from orbitval.orbits import tle
        assert tle.__version__ == __version__

    def test_pyproject_reads_version_from_the_package(self):
        import tomllib
        data = tomllib.loads((REPO / "pyproject.toml").read_text())
        assert "version" not in data["project"], (
            "version should be dynamic, not a second hardcoded copy"
        )
        attr = data["tool"]["setuptools"]["dynamic"]["version"]["attr"]
        assert attr == "orbitval._version.__version__"
