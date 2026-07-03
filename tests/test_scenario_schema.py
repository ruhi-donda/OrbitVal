"""
tests/test_scenario_schema.py

Scenario config schema (scenario.yaml) — validation of scenario
names and parameters against the fault registry.
"""

import pytest

from orbitval.config.scenario_schema import (
    load_scenario_config,
    ScenarioSpec,
    ScenarioConfigError,
)


def _write(tmp_path, content: str):
    p = tmp_path / "scenario.yaml"
    p.write_text(content)
    return p


class TestValidConfig:
    def test_minimal_valid_config(self, tmp_path):
        p = _write(tmp_path, """
schema_version: "1.0"
scenarios:
  - name: gps_dropout
""")
        specs = load_scenario_config(p)
        assert specs == [ScenarioSpec(name="gps_dropout", params={})]

    def test_params_passed_through(self, tmp_path):
        p = _write(tmp_path, """
schema_version: "1.0"
scenarios:
  - name: gps_dropout
    params:
      t_start: 30.0
      duration_s: 60.0
""")
        specs = load_scenario_config(p)
        assert specs[0].params == {"t_start": 30.0, "duration_s": 60.0}

    def test_all_six_registered_scenarios_valid(self, tmp_path):
        p = _write(tmp_path, """
schema_version: "1.0"
scenarios:
  - name: gps_dropout
  - name: power_brownout
  - name: sensor_noise
  - name: eclipse_power_stress
  - name: comms_blackout
  - name: star_tracker_failure
""")
        specs = load_scenario_config(p)
        assert len(specs) == 6

    def test_new_scenario_params_validated(self, tmp_path):
        p = _write(tmp_path, """
schema_version: "1.0"
scenarios:
  - name: star_tracker_failure
    params:
      mode: degraded
      seed: 7
""")
        specs = load_scenario_config(p)
        assert specs[0].params["mode"] == "degraded"


class TestInvalidConfig:
    def test_missing_file_raises_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_scenario_config(tmp_path / "nope.yaml")

    def test_wrong_schema_version(self, tmp_path):
        p = _write(tmp_path, """
schema_version: "9.9"
scenarios:
  - name: gps_dropout
""")
        with pytest.raises(ScenarioConfigError, match="schema_version"):
            load_scenario_config(p)

    def test_unknown_scenario_name(self, tmp_path):
        p = _write(tmp_path, """
schema_version: "1.0"
scenarios:
  - name: warp_core_breach
""")
        with pytest.raises(ScenarioConfigError, match="warp_core_breach"):
            load_scenario_config(p)

    def test_error_lists_available_scenarios(self, tmp_path):
        p = _write(tmp_path, """
schema_version: "1.0"
scenarios:
  - name: warp_core_breach
""")
        with pytest.raises(ScenarioConfigError, match="gps_dropout"):
            load_scenario_config(p)

    def test_unknown_param_rejected(self, tmp_path):
        p = _write(tmp_path, """
schema_version: "1.0"
scenarios:
  - name: gps_dropout
    params:
      warp_factor: 9
""")
        with pytest.raises(ScenarioConfigError, match="warp_factor"):
            load_scenario_config(p)

    def test_empty_scenarios_rejected(self, tmp_path):
        p = _write(tmp_path, """
schema_version: "1.0"
scenarios: []
""")
        with pytest.raises(ScenarioConfigError, match="At least one"):
            load_scenario_config(p)

    def test_non_mapping_document_rejected(self, tmp_path):
        p = _write(tmp_path, "- just\n- a\n- list\n")
        with pytest.raises(ScenarioConfigError, match="mapping"):
            load_scenario_config(p)

    def test_multiple_errors_reported_together(self, tmp_path):
        p = _write(tmp_path, """
schema_version: "9.9"
scenarios:
  - name: warp_core_breach
  - name: gps_dropout
    params:
      warp_factor: 9
""")
        with pytest.raises(ScenarioConfigError) as exc:
            load_scenario_config(p)
        msg = str(exc.value)
        assert "schema_version" in msg
        assert "warp_core_breach" in msg
        assert "warp_factor" in msg
