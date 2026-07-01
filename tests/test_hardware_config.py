"""
tests/test_hardware_config.py

Boundary and failure-mode tests for orbitval/config/hardware_3u_schema.py.
Covers every validation branch in _validate() plus the happy path.
"""

import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from orbitval.config.hardware_3u_schema import (
    load_hardware_config,
    HardwareConfig,
    HardwareConfigError,
)

# ── Minimal valid config dict ──────────────────────────────────────────────────

VALID = {
    "schema_version": "1.0",
    "name": "TestSat",
    "form_factor": "3U",
    "mass_kg": 4.0,
    "sensors": [{"type": "GPS", "noise_sigma": 0.5}],
    "actuators": [{"type": "reaction_wheel", "max_torque_nm": 0.01}],
    "power": {"battery_capacity_wh": 30.0, "solar_panel_area_m2": 0.04},
}


def _bad(overrides: dict) -> dict:
    """Return VALID with specified keys overridden (shallow merge)."""
    cfg = {**VALID}
    cfg.update(overrides)
    return cfg


def _validate(raw: dict) -> HardwareConfig:
    from orbitval.config.hardware_3u_schema import _validate
    return _validate(raw, Path("satellite.yaml"))


class TestValidConfig:
    def test_valid_config_returns_hardware_config(self):
        hw = _validate(VALID)
        assert isinstance(hw, HardwareConfig)

    def test_valid_name_preserved(self):
        assert _validate(VALID).name == "TestSat"

    def test_valid_form_factor(self):
        assert _validate(VALID).form_factor == "3U"

    def test_valid_mass(self):
        assert _validate(VALID).mass_kg == 4.0

    def test_valid_sensor_count(self):
        assert len(_validate(VALID).sensors) == 1

    def test_valid_actuator_count(self):
        assert len(_validate(VALID).actuators) == 1


class TestSchemaVersion:
    def test_wrong_schema_version_raises(self):
        with pytest.raises(HardwareConfigError, match="schema_version"):
            _validate(_bad({"schema_version": "2.0"}))

    def test_missing_schema_version_raises(self):
        raw = {k: v for k, v in VALID.items() if k != "schema_version"}
        with pytest.raises(HardwareConfigError, match="schema_version"):
            _validate(raw)


class TestFormFactor:
    def test_unsupported_form_factor_raises(self):
        with pytest.raises(HardwareConfigError, match="form_factor"):
            _validate(_bad({"form_factor": "6U"}))

    def test_error_mentions_3u(self):
        with pytest.raises(HardwareConfigError, match="3U"):
            _validate(_bad({"form_factor": "1U"}))


class TestMassKg:
    def test_zero_mass_raises(self):
        with pytest.raises(HardwareConfigError, match="mass_kg"):
            _validate(_bad({"mass_kg": 0}))

    def test_negative_mass_raises(self):
        with pytest.raises(HardwareConfigError, match="mass_kg"):
            _validate(_bad({"mass_kg": -1.5}))

    def test_string_mass_raises(self):
        with pytest.raises(HardwareConfigError, match="mass_kg"):
            _validate(_bad({"mass_kg": "heavy"}))


class TestSensors:
    def test_empty_sensors_raises(self):
        with pytest.raises(HardwareConfigError, match="sensor"):
            _validate(_bad({"sensors": []}))

    def test_unknown_sensor_type_raises(self):
        with pytest.raises(HardwareConfigError, match="not recognized"):
            _validate(_bad({"sensors": [{"type": "lidar", "noise_sigma": 0.1}]}))

    def test_unknown_sensor_type_error_names_it(self):
        with pytest.raises(HardwareConfigError, match="lidar"):
            _validate(_bad({"sensors": [{"type": "lidar", "noise_sigma": 0.1}]}))

    def test_negative_noise_sigma_raises(self):
        with pytest.raises(HardwareConfigError, match="noise_sigma"):
            _validate(_bad({"sensors": [{"type": "GPS", "noise_sigma": -0.1}]}))

    def test_zero_noise_sigma_is_valid(self):
        hw = _validate(_bad({"sensors": [{"type": "GPS", "noise_sigma": 0.0}]}))
        assert hw.sensors[0].noise_sigma == 0.0


class TestActuators:
    def test_empty_actuators_raises(self):
        with pytest.raises(HardwareConfigError, match="actuator"):
            _validate(_bad({"actuators": []}))

    def test_unknown_actuator_type_raises(self):
        with pytest.raises(HardwareConfigError, match="not recognized"):
            _validate(_bad({"actuators": [{"type": "ion_drive", "max_torque_nm": 0.01}]}))

    def test_zero_max_torque_raises(self):
        with pytest.raises(HardwareConfigError, match="max_torque_nm"):
            _validate(_bad({"actuators": [{"type": "reaction_wheel", "max_torque_nm": 0}]}))

    def test_negative_max_torque_raises(self):
        with pytest.raises(HardwareConfigError, match="max_torque_nm"):
            _validate(_bad({"actuators": [{"type": "reaction_wheel", "max_torque_nm": -1}]}))


class TestPower:
    def test_zero_battery_capacity_raises(self):
        raw = _bad({"power": {"battery_capacity_wh": 0, "solar_panel_area_m2": 0.04}})
        with pytest.raises(HardwareConfigError, match="battery_capacity_wh"):
            _validate(raw)

    def test_negative_solar_area_raises(self):
        raw = _bad({"power": {"battery_capacity_wh": 30.0, "solar_panel_area_m2": -1}})
        with pytest.raises(HardwareConfigError, match="solar_panel_area_m2"):
            _validate(raw)

    def test_missing_power_block_raises(self):
        raw = {k: v for k, v in VALID.items() if k != "power"}
        raw["power"] = {}
        with pytest.raises(HardwareConfigError):
            _validate(raw)


class TestMultipleErrors:
    def test_all_errors_reported_in_one_raise(self):
        """Multiple bad fields should produce one exception listing all failures."""
        raw = _bad({
            "schema_version": "9.9",
            "form_factor": "6U",
            "mass_kg": -1,
        })
        with pytest.raises(HardwareConfigError) as exc:
            _validate(raw)
        msg = str(exc.value)
        assert "schema_version" in msg
        assert "form_factor" in msg
        assert "mass_kg" in msg


class TestLoadFromFile:
    def test_nonexistent_file_raises_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_hardware_config(tmp_path / "nope.yaml")

    def test_valid_yaml_file_loads(self):
        config_path = Path(__file__).parent.parent / "satellite.yaml"
        hw = load_hardware_config(config_path)
        assert isinstance(hw, HardwareConfig)
