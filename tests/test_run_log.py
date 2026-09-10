"""
tests/test_run_log.py

Regression tests for the embedded audit trail (run_log) in ORF
reports. The event buffer used to be cleared right before report
generation, so every report shipped with an empty run_log — only
the log-file header survived. These tests pin the fixed behavior:
scenario events recorded during the run must appear in both the
report's run_log field and the .log file.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def _messages(report: dict) -> list[str]:
    return [e["msg"] for e in report["run_log"]]


class TestRunLogEmbedded:
    def test_run_log_is_not_empty(self, prelaunch_runner, tmp_path):
        report = prelaunch_runner.run(
            scenarios=["gps_dropout"], output_dir=tmp_path
        )
        assert len(report["run_log"]) > 1

    def test_run_log_contains_scenario_events(
        self, prelaunch_runner, tmp_path
    ):
        report = prelaunch_runner.run(
            scenarios=["gps_dropout", "power_brownout"], output_dir=tmp_path
        )
        msgs = _messages(report)
        assert any("Running scenario: gps_dropout" in m for m in msgs)
        assert any("Running scenario: power_brownout" in m for m in msgs)

    def test_run_log_contains_injection_events(
        self, prelaunch_runner, tmp_path
    ):
        report = prelaunch_runner.run(
            scenarios=["gps_dropout"], output_dir=tmp_path
        )
        msgs = _messages(report)
        assert any("Injection complete" in m for m in msgs)

    def test_run_log_contains_scenario_verdicts(
        self, prelaunch_runner, tmp_path
    ):
        # ResponsiveAutonomy handles gps_dropout, so a PASS is logged
        report = prelaunch_runner.run(
            scenarios=["gps_dropout"], output_dir=tmp_path
        )
        msgs = _messages(report)
        assert any("PASS — gps_dropout" in m for m in msgs)

    def test_run_log_entries_have_expected_fields(
        self, prelaunch_runner, tmp_path
    ):
        report = prelaunch_runner.run(
            scenarios=["gps_dropout"], output_dir=tmp_path
        )
        for event in report["run_log"]:
            assert set(event) == {"timestamp", "level", "module", "msg"}


class TestOrbitProvenance:
    """Q4: the run log must record where the orbit came from.

    clear_run_events() used to fire at the top of run(), wiping every
    event logged during TestRunner.__init__ — TLE cache hit vs live fetch
    vs stale fallback, the propagation summary, the eclipse scan. So the
    report's embedded audit trail never said which orbit it was built on,
    which is exactly what an auditor would check first.
    """

    def test_run_log_records_prelaunch_synthesis(
        self, prelaunch_runner, tmp_path
    ):
        report = prelaunch_runner.run(
            scenarios=["gps_dropout"], output_dir=tmp_path
        )
        msgs = _messages(report)
        assert any("Pre-launch mode" in m for m in msgs), (
            "run_log does not say the orbit was synthesized"
        )

    def test_run_log_records_propagation(self, prelaunch_runner, tmp_path):
        report = prelaunch_runner.run(
            scenarios=["gps_dropout"], output_dir=tmp_path
        )
        assert any("Propagating" in m for m in _messages(report))

    def test_run_log_records_eclipse_scan(self, prelaunch_runner, tmp_path):
        report = prelaunch_runner.run(
            scenarios=["gps_dropout"], output_dir=tmp_path
        )
        assert any("Eclipse scan" in m for m in _messages(report))

    def test_provenance_precedes_scenario_events(
        self, prelaunch_runner, tmp_path
    ):
        report = prelaunch_runner.run(
            scenarios=["gps_dropout"], output_dir=tmp_path
        )
        msgs = _messages(report)
        setup = next(i for i, m in enumerate(msgs) if "Propagating" in m)
        scenario = next(i for i, m in enumerate(msgs)
                        if "Running scenario" in m)
        assert setup < scenario

    def test_log_file_also_carries_provenance(
        self, prelaunch_runner, tmp_path
    ):
        prelaunch_runner.run(scenarios=["gps_dropout"], output_dir=tmp_path)
        content = list(tmp_path.glob("*.log"))[0].read_text()
        assert "Pre-launch mode" in content
        assert "Propagating" in content

    def test_tle_mode_records_its_source(self, tmp_path):
        from unittest.mock import patch
        from orbitval.engine.runner import TestRunner
        from tests.conftest import SATELLITE_YAML, TLE1, TLE2, ResponsiveAutonomy
        with patch("orbitval.engine.runner.fetch_tle"):
            runner = TestRunner(
                config=SATELLITE_YAML, autonomy=ResponsiveAutonomy(),
                tle_name="MY-SAT", tle_line1=TLE1, tle_line2=TLE2,
            )
        report = runner.run(scenarios=["gps_dropout"], output_dir=tmp_path)
        assert any("TLE strings" in m for m in _messages(report))

    def test_second_run_does_not_duplicate_setup_events(
        self, prelaunch_runner, tmp_path
    ):
        prelaunch_runner.run(scenarios=["gps_dropout"],
                             output_dir=tmp_path / "a")
        report = prelaunch_runner.run(scenarios=["gps_dropout"],
                                      output_dir=tmp_path / "b")
        msgs = _messages(report)
        assert sum("Pre-launch mode" in m for m in msgs) == 1


class TestRunLogFile:
    def test_log_file_contains_scenario_events(
        self, prelaunch_runner, tmp_path
    ):
        prelaunch_runner.run(scenarios=["gps_dropout"], output_dir=tmp_path)
        logs = list(tmp_path.glob("*.log"))
        assert len(logs) == 1
        content = logs[0].read_text()
        assert "Running scenario: gps_dropout" in content
        assert "Injection complete" in content

    def test_second_run_does_not_leak_into_first_log(
        self, prelaunch_runner, tmp_path
    ):
        out1 = tmp_path / "run1"
        out2 = tmp_path / "run2"
        prelaunch_runner.run(scenarios=["gps_dropout"], output_dir=out1)
        prelaunch_runner.run(scenarios=["power_brownout"], output_dir=out2)

        log1 = list(out1.glob("*.log"))[0].read_text()
        assert log1.count("OrbitVal run started") == 1
        assert "power_brownout" not in log1

    def test_each_run_gets_its_own_run_log(self, prelaunch_runner, tmp_path):
        prelaunch_runner.run(scenarios=["gps_dropout"], output_dir=tmp_path / "a")
        report2 = prelaunch_runner.run(
            scenarios=["power_brownout"], output_dir=tmp_path / "b"
        )
        msgs = _messages(report2)
        assert any("power_brownout" in m for m in msgs)
        assert not any("gps_dropout" in m for m in msgs)
