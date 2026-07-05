"""
tests/test_verify_report.py

Tests for `orbitval verify-report` — integrity hash verification
of ORF JSON reports.
"""

import sys
import json
import hashlib
import argparse
import pytest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from orbitval.cli import cmd_verify_report
from orbitval.reporting.json_report import _compute_integrity_hash

SATELLITE_YAML = str(Path(__file__).parent.parent / "satellite.yaml")
TLE1 = "1 25544U 98067A   24001.50000000  .00001000  00000+0  10000-4 0  9991"
TLE2 = "2 25544  51.6400 100.0000 0001000  90.0000 270.0000 15.50000000000010"


def _make_args(path: str) -> argparse.Namespace:
    return argparse.Namespace(report=path)


def _fresh_report(tmp_path) -> Path:
    """Generate a real ORF report and return its path."""
    from orbitval.cli import cmd_run
    out = tmp_path / "reports"
    args = argparse.Namespace(
        verbose=False, quiet=False,
        config=SATELLITE_YAML,
        scenarios=["gps_dropout"],
        autonomy=None,
        tle_name="ISS (ZARYA)", tle_line1=TLE1, tle_line2=TLE2,
        orbit_alt=None, orbit_inc=None, orbit_type="LEO",
        duration=1.0, step=60.0, seed=42,
        output=str(out),
        ground_station=None,
    )
    with patch("orbitval.engine.runner.fetch_tle"):
        cmd_run(args)
    reports = list(out.glob("*.json"))
    assert reports, "No JSON report was generated"
    return reports[0]


class TestVerifyReportClean:
    def test_clean_report_exits_zero(self, tmp_path, capsys):
        report_path = _fresh_report(tmp_path)
        cmd_verify_report(_make_args(str(report_path)))   # should not raise

    def test_clean_report_prints_tick(self, tmp_path, capsys):
        report_path = _fresh_report(tmp_path)
        cmd_verify_report(_make_args(str(report_path)))
        out = capsys.readouterr().out
        assert "✓" in out

    def test_clean_report_shows_hash(self, tmp_path, capsys):
        report_path = _fresh_report(tmp_path)
        cmd_verify_report(_make_args(str(report_path)))
        out = capsys.readouterr().out
        assert "Integrity hash" in out


class TestVerifyReportTampered:
    def test_tampered_overall_result_exits_one(self, tmp_path, capsys):
        report_path = _fresh_report(tmp_path)
        data = json.loads(report_path.read_text())
        data["overall_result"] = "FAIL"   # tamper
        report_path.write_text(json.dumps(data))

        with pytest.raises(SystemExit) as exc:
            cmd_verify_report(_make_args(str(report_path)))
        assert exc.value.code == 1

    def test_tampered_report_prints_mismatch(self, tmp_path, capsys):
        report_path = _fresh_report(tmp_path)
        data = json.loads(report_path.read_text())
        data["certification_eligible"] = False   # tamper
        report_path.write_text(json.dumps(data))

        with pytest.raises(SystemExit):
            cmd_verify_report(_make_args(str(report_path)))
        out = capsys.readouterr().out
        assert "✗" in out
        assert "mismatch" in out.lower() or "tampered" in out.lower()

    def test_tampered_report_shows_both_hashes(self, tmp_path, capsys):
        report_path = _fresh_report(tmp_path)
        data = json.loads(report_path.read_text())
        data["overall_result"] = "FAIL"
        report_path.write_text(json.dumps(data))

        with pytest.raises(SystemExit):
            cmd_verify_report(_make_args(str(report_path)))
        out = capsys.readouterr().out
        assert "Stored" in out
        assert "Computed" in out


class TestVerifyReportBadInputs:
    def test_missing_file_exits_one(self, capsys):
        with pytest.raises(SystemExit) as exc:
            cmd_verify_report(_make_args("/no/such/report.json"))
        assert exc.value.code == 1

    def test_missing_file_prints_error(self, capsys):
        with pytest.raises(SystemExit):
            cmd_verify_report(_make_args("/no/such/report.json"))
        out = capsys.readouterr().out
        assert "✗" in out

    def test_invalid_json_exits_one(self, tmp_path, capsys):
        bad = tmp_path / "bad.json"
        bad.write_text("this is not { json }")
        with pytest.raises(SystemExit) as exc:
            cmd_verify_report(_make_args(str(bad)))
        assert exc.value.code == 1

    def test_invalid_json_prints_error(self, tmp_path, capsys):
        bad = tmp_path / "bad.json"
        bad.write_text("this is not { json }")
        with pytest.raises(SystemExit):
            cmd_verify_report(_make_args(str(bad)))
        out = capsys.readouterr().out
        assert "✗" in out

    def test_missing_hash_field_exits_one(self, tmp_path, capsys):
        report = tmp_path / "nohash.json"
        report.write_text(json.dumps({"overall_result": "PASS"}))
        with pytest.raises(SystemExit) as exc:
            cmd_verify_report(_make_args(str(report)))
        assert exc.value.code == 1

    def test_missing_hash_field_prints_error(self, tmp_path, capsys):
        report = tmp_path / "nohash.json"
        report.write_text(json.dumps({"overall_result": "PASS"}))
        with pytest.raises(SystemExit):
            cmd_verify_report(_make_args(str(report)))
        out = capsys.readouterr().out
        assert "✗" in out
        assert "test_integrity_hash" in out


class TestVerifyReportSchema:
    """A self-consistent hash on a non-ORF document must be rejected."""

    def test_non_orf_hash_consistent_file_rejected(self, tmp_path, capsys):
        payload = {"totally": "not an ORF report", "foo": 42}
        payload["test_integrity_hash"] = _compute_integrity_hash(payload)
        fake = tmp_path / "fake.json"
        fake.write_text(json.dumps(payload))

        with pytest.raises(SystemExit) as exc:
            cmd_verify_report(_make_args(str(fake)))
        assert exc.value.code == 1
        out = capsys.readouterr().out
        assert "Not a valid ORF report" in out
        assert "missing required field" in out

    def test_wrong_field_type_rejected(self, tmp_path, capsys):
        report_path = _fresh_report(tmp_path)
        data = json.loads(report_path.read_text())
        data["scenarios_run"] = "not-a-list"
        # Keep the hash self-consistent so only the schema check trips
        del data["test_integrity_hash"]
        data["test_integrity_hash"] = _compute_integrity_hash(data)
        report_path.write_text(json.dumps(data))

        with pytest.raises(SystemExit) as exc:
            cmd_verify_report(_make_args(str(report_path)))
        assert exc.value.code == 1
        out = capsys.readouterr().out
        assert "Not a valid ORF report" in out
        assert "scenarios_run" in out

    def test_real_report_passes_schema(self, tmp_path, capsys):
        report_path = _fresh_report(tmp_path)
        cmd_verify_report(_make_args(str(report_path)))  # no exit
        out = capsys.readouterr().out
        assert "Not a valid ORF report" not in out
        assert "✓" in out
