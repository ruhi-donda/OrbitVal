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
