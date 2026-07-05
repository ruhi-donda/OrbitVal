"""
tests/test_registry.py

Tests for the append-only hash registry (orbitval/registry.py) and
its wiring into report generation, verify-report, and the
`orbitval registry verify` CLI command.
"""

import sys
import json
import hashlib
import argparse
import pytest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from orbitval.registry import (
    GENESIS_HASH,
    append_entry,
    verify_chain,
    check_provenance,
    resolve_registry_path,
    _hash_line,
)
from orbitval.reporting.json_report import _compute_integrity_hash
from orbitval.cli import cmd_verify_report, cmd_registry

SATELLITE_YAML = str(Path(__file__).parent.parent / "satellite.yaml")
TLE1 = "1 25544U 98067A   24001.50000000  .00001000  00000+0  10000-4 0  9991"
TLE2 = "2 25544  51.6400 100.0000 0001000  90.0000 270.0000 15.50000000000010"


# ── Helpers ───────────────────────────────────────────────────

def _write_fake_report(path: Path, payload: dict | None = None) -> str:
    """Write a minimal ORF-schema-valid report whose internal hash is
    valid. Returns the report's test_integrity_hash."""
    payload = dict(payload or {
        "orbitval_version": "1.1.0",
        "orf_spec_version": "1.0",
        "schema_version": "1.0",
        "report_id": "00000000-0000-0000-0000-000000000001",
        "generated_at": "2026-07-03T00:00:00Z",
        "mission_profile": {"orbit_type": "LEO"},
        "regulatory_jurisdiction": "none declared",
        "applicable_standard": "none declared",
        "hardware_generation": "COTS",
        "form_factor": "3U",
        "scenarios_run": [],
        "overall_result": "PASS",
        "certification_eligible": True,
    })
    stored_hash = _compute_integrity_hash(payload)
    payload["test_integrity_hash"] = stored_hash
    path.write_text(json.dumps(payload))
    return stored_hash


def _verify_args(report: str, registry: str | None = None):
    return argparse.Namespace(report=report, registry=registry)


def _registry_args(registry: str | None = None):
    return argparse.Namespace(registry_command="verify", registry=registry)


def _run_real_report(tmp_path) -> Path:
    """Run the full pipeline via cmd_run and return the JSON report path."""
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


# ── Registry module: append ───────────────────────────────────

class TestAppendEntry:
    def test_first_entry_has_genesis_prev_hash(self, tmp_path):
        reg = tmp_path / "reg.jsonl"
        entry = append_entry("a" * 64, "sat-1", reg)
        assert entry["prev_entry_hash"] == GENESIS_HASH

    def test_entry_fields(self, tmp_path):
        reg = tmp_path / "reg.jsonl"
        entry = append_entry("a" * 64, "sat-1", reg)
        assert set(entry) == {
            "report_hash", "timestamp", "satellite_id", "prev_entry_hash"
        }
        assert entry["report_hash"] == "a" * 64
        assert entry["satellite_id"] == "sat-1"

    def test_second_entry_chains_to_first(self, tmp_path):
        reg = tmp_path / "reg.jsonl"
        append_entry("a" * 64, "sat-1", reg)
        first_line = reg.read_text().splitlines()[0]
        entry2 = append_entry("b" * 64, "sat-2", reg)
        assert entry2["prev_entry_hash"] == _hash_line(first_line)
        assert entry2["prev_entry_hash"] == hashlib.sha256(
            first_line.encode()
        ).hexdigest()

    def test_appends_one_line_per_entry(self, tmp_path):
        reg = tmp_path / "reg.jsonl"
        for i in range(5):
            append_entry(f"{i}" * 64, f"sat-{i}", reg)
        assert len(reg.read_text().splitlines()) == 5

    def test_append_never_rewrites_existing_lines(self, tmp_path):
        reg = tmp_path / "reg.jsonl"
        append_entry("a" * 64, "sat-1", reg)
        before = reg.read_text().splitlines()[0]
        append_entry("b" * 64, "sat-2", reg)
        assert reg.read_text().splitlines()[0] == before

    def test_creates_parent_directories(self, tmp_path):
        reg = tmp_path / "deep" / "nested" / "reg.jsonl"
        append_entry("a" * 64, "sat-1", reg)
        assert reg.exists()


# ── Registry module: path resolution ──────────────────────────

class TestResolveRegistryPath:
    def test_explicit_path_wins(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ORBITVAL_REGISTRY", str(tmp_path / "env.jsonl"))
        explicit = tmp_path / "explicit.jsonl"
        assert resolve_registry_path(explicit) == explicit

    def test_env_var_used_when_no_explicit_path(self, tmp_path, monkeypatch):
        env_path = tmp_path / "env.jsonl"
        monkeypatch.setenv("ORBITVAL_REGISTRY", str(env_path))
        assert resolve_registry_path() == env_path

    def test_default_when_no_env(self, monkeypatch):
        monkeypatch.delenv("ORBITVAL_REGISTRY", raising=False)
        assert resolve_registry_path() == Path(".orbitval") / "registry.jsonl"


# ── Registry module: chain verification ───────────────────────

class TestVerifyChain:
    def test_intact_chain(self, tmp_path):
        reg = tmp_path / "reg.jsonl"
        for i in range(4):
            append_entry(f"{i}" * 64, f"sat-{i}", reg)
        result = verify_chain(reg)
        assert result.ok
        assert result.entry_count == 4
        assert result.error is None

    def test_missing_registry_is_empty_intact_chain(self, tmp_path):
        result = verify_chain(tmp_path / "nope.jsonl")
        assert result.ok
        assert result.entry_count == 0

    def test_edited_old_entry_breaks_chain(self, tmp_path):
        reg = tmp_path / "reg.jsonl"
        for i in range(3):
            append_entry(f"{i}" * 64, f"sat-{i}", reg)
        lines = reg.read_text().splitlines()
        tampered = json.loads(lines[0])
        tampered["satellite_id"] = "evil-sat"
        lines[0] = json.dumps(tampered, sort_keys=True, separators=(",", ":"))
        reg.write_text("\n".join(lines) + "\n")

        result = verify_chain(reg)
        assert not result.ok
        assert result.broken_at == 1  # entry after the edit no longer links

    def test_deleted_middle_entry_breaks_chain(self, tmp_path):
        reg = tmp_path / "reg.jsonl"
        for i in range(3):
            append_entry(f"{i}" * 64, f"sat-{i}", reg)
        lines = reg.read_text().splitlines()
        del lines[1]
        reg.write_text("\n".join(lines) + "\n")

        result = verify_chain(reg)
        assert not result.ok

    def test_tampered_first_entry_genesis_breaks_chain(self, tmp_path):
        reg = tmp_path / "reg.jsonl"
        append_entry("a" * 64, "sat-1", reg)
        entry = json.loads(reg.read_text())
        entry["prev_entry_hash"] = "f" * 64
        reg.write_text(json.dumps(entry, sort_keys=True) + "\n")

        result = verify_chain(reg)
        assert not result.ok
        assert result.broken_at == 0

    def test_malformed_line_breaks_chain(self, tmp_path):
        reg = tmp_path / "reg.jsonl"
        append_entry("a" * 64, "sat-1", reg)
        with reg.open("a") as f:
            f.write("this is not json\n")

        result = verify_chain(reg)
        assert not result.ok
        assert result.broken_at == 1
        assert "not valid JSON" in result.error

    def test_entry_missing_prev_hash_breaks_chain(self, tmp_path):
        reg = tmp_path / "reg.jsonl"
        reg.write_text(json.dumps({"report_hash": "a" * 64}) + "\n")
        result = verify_chain(reg)
        assert not result.ok
        assert "prev_entry_hash" in result.error


# ── Registry module: provenance lookup ────────────────────────

class TestCheckProvenance:
    def test_registered_hash_confirmed(self, tmp_path):
        reg = tmp_path / "reg.jsonl"
        append_entry("a" * 64, "sat-1", reg)
        status, entry = check_provenance("a" * 64, reg)
        assert status == "confirmed"
        assert entry["satellite_id"] == "sat-1"

    def test_unregistered_hash_not_found(self, tmp_path):
        reg = tmp_path / "reg.jsonl"
        append_entry("a" * 64, "sat-1", reg)
        status, entry = check_provenance("b" * 64, reg)
        assert status == "not found"
        assert entry is None

    def test_missing_registry_not_found(self, tmp_path):
        status, entry = check_provenance("a" * 64, tmp_path / "nope.jsonl")
        assert status == "not found"

    def test_broken_chain_reported_even_if_hash_present(self, tmp_path):
        reg = tmp_path / "reg.jsonl"
        append_entry("a" * 64, "sat-1", reg)
        append_entry("b" * 64, "sat-2", reg)
        lines = reg.read_text().splitlines()
        tampered = json.loads(lines[0])
        tampered["timestamp"] = "1999-01-01T00:00:00+00:00"
        lines[0] = json.dumps(tampered, sort_keys=True, separators=(",", ":"))
        reg.write_text("\n".join(lines) + "\n")

        status, entry = check_provenance("b" * 64, reg)
        assert status == "chain broken"
        assert entry is None


# ── verify-report CLI: dual result ─────────────────────────────

class TestVerifyReportProvenance:
    def test_valid_hash_and_registered_passes(self, tmp_path, capsys):
        report = tmp_path / "report.json"
        stored_hash = _write_fake_report(report)
        reg = tmp_path / "reg.jsonl"
        append_entry(stored_hash, "sat-1", reg)

        cmd_verify_report(_verify_args(str(report), str(reg)))  # no exit
        out = capsys.readouterr().out
        assert "Internal hash:       valid" in out
        assert "Registry provenance: confirmed" in out

    def test_valid_hash_but_missing_registry_entry_fails(
        self, tmp_path, capsys
    ):
        report = tmp_path / "report.json"
        _write_fake_report(report)
        reg = tmp_path / "reg.jsonl"
        append_entry("f" * 64, "other-sat", reg)  # some other report

        with pytest.raises(SystemExit) as exc:
            cmd_verify_report(_verify_args(str(report), str(reg)))
        assert exc.value.code == 1
        out = capsys.readouterr().out
        assert "Internal hash:       valid" in out
        assert "Registry provenance: not found" in out

    def test_valid_hash_but_no_registry_file_fails(self, tmp_path, capsys):
        report = tmp_path / "report.json"
        _write_fake_report(report)

        with pytest.raises(SystemExit) as exc:
            cmd_verify_report(
                _verify_args(str(report), str(tmp_path / "nope.jsonl"))
            )
        assert exc.value.code == 1
        out = capsys.readouterr().out
        assert "Registry provenance: not found" in out

    def test_valid_hash_but_broken_chain_fails(self, tmp_path, capsys):
        report = tmp_path / "report.json"
        stored_hash = _write_fake_report(report)
        reg = tmp_path / "reg.jsonl"
        append_entry("f" * 64, "sat-0", reg)
        append_entry(stored_hash, "sat-1", reg)
        # Tamper with the first (older) entry
        lines = reg.read_text().splitlines()
        tampered = json.loads(lines[0])
        tampered["satellite_id"] = "evil-sat"
        lines[0] = json.dumps(tampered, sort_keys=True, separators=(",", ":"))
        reg.write_text("\n".join(lines) + "\n")

        with pytest.raises(SystemExit) as exc:
            cmd_verify_report(_verify_args(str(report), str(reg)))
        assert exc.value.code == 1
        out = capsys.readouterr().out
        assert "Internal hash:       valid" in out
        assert "Registry provenance: chain broken" in out

    def test_tampered_report_shows_invalid_internal_hash(
        self, tmp_path, capsys
    ):
        report = tmp_path / "report.json"
        stored_hash = _write_fake_report(report)
        reg = tmp_path / "reg.jsonl"
        append_entry(stored_hash, "sat-1", reg)
        # Tamper with the report content (stored hash unchanged)
        data = json.loads(report.read_text())
        data["overall_result"] = "FAIL"
        report.write_text(json.dumps(data))

        with pytest.raises(SystemExit) as exc:
            cmd_verify_report(_verify_args(str(report), str(reg)))
        assert exc.value.code == 1
        out = capsys.readouterr().out
        # Both results reported separately
        assert "Internal hash:       invalid" in out
        assert "Registry provenance: confirmed" in out

    def test_uses_env_registry_when_no_flag(self, tmp_path, capsys, monkeypatch):
        report = tmp_path / "report.json"
        stored_hash = _write_fake_report(report)
        reg = tmp_path / "env-reg.jsonl"
        monkeypatch.setenv("ORBITVAL_REGISTRY", str(reg))
        append_entry(stored_hash, "sat-1")

        cmd_verify_report(_verify_args(str(report)))  # no --registry flag
        out = capsys.readouterr().out
        assert "Registry provenance: confirmed" in out


# ── registry verify CLI ────────────────────────────────────────

class TestRegistryVerifyCommand:
    def test_intact_chain_exits_zero(self, tmp_path, capsys):
        reg = tmp_path / "reg.jsonl"
        for i in range(3):
            append_entry(f"{i}" * 64, f"sat-{i}", reg)

        cmd_registry(_registry_args(str(reg)))  # should not raise
        out = capsys.readouterr().out
        assert "✓" in out
        assert "3 entries" in out

    def test_missing_registry_exits_one(self, tmp_path, capsys):
        with pytest.raises(SystemExit) as exc:
            cmd_registry(_registry_args(str(tmp_path / "nope.jsonl")))
        assert exc.value.code == 1
        out = capsys.readouterr().out
        assert "✗" in out

    def test_edited_old_entry_caught(self, tmp_path, capsys):
        reg = tmp_path / "reg.jsonl"
        for i in range(4):
            append_entry(f"{i}" * 64, f"sat-{i}", reg)
        lines = reg.read_text().splitlines()
        tampered = json.loads(lines[1])
        tampered["report_hash"] = "d" * 64
        lines[1] = json.dumps(tampered, sort_keys=True, separators=(",", ":"))
        reg.write_text("\n".join(lines) + "\n")

        with pytest.raises(SystemExit) as exc:
            cmd_registry(_registry_args(str(reg)))
        assert exc.value.code == 1
        out = capsys.readouterr().out
        assert "BROKEN" in out

    def test_uses_env_registry_when_no_flag(self, tmp_path, capsys, monkeypatch):
        reg = tmp_path / "env-reg.jsonl"
        monkeypatch.setenv("ORBITVAL_REGISTRY", str(reg))
        append_entry("a" * 64, "sat-1")

        cmd_registry(_registry_args())
        out = capsys.readouterr().out
        assert "✓" in out
        assert "1 entries" in out


# ── End-to-end: report generation auto-registers ───────────────

class TestEndToEnd:
    def test_run_appends_hash_to_registry(self, tmp_path):
        report_path = _run_real_report(tmp_path)
        report = json.loads(report_path.read_text())

        reg = resolve_registry_path()  # conftest points env var at tmp_path
        lines = reg.read_text().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["report_hash"] == report["test_integrity_hash"]
        assert entry["prev_entry_hash"] == GENESIS_HASH

    def test_full_happy_path(self, tmp_path, capsys):
        report_path = _run_real_report(tmp_path)

        cmd_verify_report(_verify_args(str(report_path)))  # exit 0
        out = capsys.readouterr().out
        assert "Internal hash:       valid" in out
        assert "Registry provenance: confirmed" in out

        cmd_registry(_registry_args())  # exit 0
        out = capsys.readouterr().out
        assert "✓" in out

    def test_real_report_with_deleted_registry_fails_provenance(
        self, tmp_path, capsys
    ):
        report_path = _run_real_report(tmp_path)
        resolve_registry_path().unlink()  # simulate registry deletion

        with pytest.raises(SystemExit) as exc:
            cmd_verify_report(_verify_args(str(report_path)))
        assert exc.value.code == 1
        out = capsys.readouterr().out
        assert "Internal hash:       valid" in out
        assert "Registry provenance: not found" in out
