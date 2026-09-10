"""
orbitval/config/hardware_3u_schema.py

3U CubeSat hardware configuration model for OrbitVal.
Loads and validates satellite.yaml against the ORF hardware schema.

Schema version: 1.0
Only 3U CubeSat form factor is supported in v1 (see ARCHITECTURE.md non-goals).
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import yaml


SUPPORTED_FORM_FACTORS = {"3U"}
SUPPORTED_SENSOR_TYPES = {"GPS", "star_tracker", "magnetometer", "sun_sensor", "gyroscope"}
SUPPORTED_ACTUATOR_TYPES = {"reaction_wheel", "magnetorquer", "thruster"}
SCHEMA_VERSION = "1.0"


@dataclass
class SensorConfig:
    """Configuration for a single onboard sensor."""
    type: str
    noise_sigma: float


@dataclass
class ActuatorConfig:
    """Configuration for a single onboard actuator."""
    type: str
    max_torque_nm: float


@dataclass
class PowerConfig:
    """Simplified power budget model."""
    battery_capacity_wh: float
    solar_panel_area_m2: float


@dataclass
class HardwareConfig:
    """
    Full 3U CubeSat hardware configuration.
    Loaded from satellite.yaml and validated against schema v1.0.
    """
    schema_version: str
    name: str
    form_factor: str
    mass_kg: float
    sensors: list[SensorConfig]
    actuators: list[ActuatorConfig]
    power: PowerConfig


class HardwareConfigError(Exception):
    """Raised when satellite.yaml fails validation."""
    pass


def load_hardware_config(config_path: str | Path) -> HardwareConfig:
    """
    Load and validate a satellite.yaml hardware config file.

    Args:
        config_path: path to satellite.yaml

    Returns:
        Validated HardwareConfig dataclass

    Raises:
        HardwareConfigError: if validation fails
        FileNotFoundError: if file does not exist
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Hardware config not found: {path}. "
            f"Create a satellite.yaml file using the template in TEMPLATES.md."
        )

    with open(path) as f:
        try:
            raw = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise HardwareConfigError(
                f"Invalid hardware config at {path}: not valid YAML.\n  {e}"
            ) from e

    return _validate(raw, path)


def _validate(raw: dict, path: Path) -> HardwareConfig:
    """Validate raw YAML dict against the hardware schema."""
    # An empty file parses to None, and a YAML list/scalar parses to a
    # non-dict; both used to raise AttributeError instead of a readable
    # config error.
    if not isinstance(raw, dict):
        got = "an empty file" if raw is None else f"a {type(raw).__name__}"
        raise HardwareConfigError(
            f"Invalid hardware config at {path}: expected a YAML mapping "
            f"of config keys, got {got}."
        )

    errors = []

    # schema_version
    sv = raw.get("schema_version")
    if sv != SCHEMA_VERSION:
        errors.append(
            f"schema_version must be '{SCHEMA_VERSION}', got '{sv}'."
        )

    # form_factor
    ff = raw.get("form_factor")
    if ff not in SUPPORTED_FORM_FACTORS:
        errors.append(
            f"form_factor must be one of {SUPPORTED_FORM_FACTORS}, got '{ff}'. "
            f"Only 3U is supported in v1."
        )

    # mass_kg
    mass = raw.get("mass_kg")
    if not isinstance(mass, (int, float)) or mass <= 0:
        errors.append(f"mass_kg must be a positive number, got '{mass}'.")

    # sensors
    sensors_raw = raw.get("sensors", [])
    if not sensors_raw:
        errors.append("At least one sensor must be defined.")
    if sensors_raw and not isinstance(sensors_raw, list):
        errors.append("sensors must be a list of {type, noise_sigma} entries.")
        sensors_raw = []
    sensors = []
    for i, s in enumerate(sensors_raw):
        if not isinstance(s, dict):
            errors.append(
                f"sensors[{i}] must be a mapping with 'type' and "
                f"'noise_sigma' keys, got {type(s).__name__}."
            )
            continue
        stype = s.get("type")
        noise = s.get("noise_sigma")
        if stype not in SUPPORTED_SENSOR_TYPES:
            errors.append(
                f"sensors[{i}].type '{stype}' not recognized. "
                f"Supported: {SUPPORTED_SENSOR_TYPES}"
            )
        if not isinstance(noise, (int, float)) or noise < 0:
            errors.append(
                f"sensors[{i}].noise_sigma must be a non-negative number."
            )
        if not errors:
            sensors.append(SensorConfig(type=stype, noise_sigma=float(noise)))

    # actuators
    actuators_raw = raw.get("actuators", [])
    if not actuators_raw:
        errors.append("At least one actuator must be defined.")
    if actuators_raw and not isinstance(actuators_raw, list):
        errors.append(
            "actuators must be a list of {type, max_torque_nm} entries."
        )
        actuators_raw = []
    actuators = []
    for i, a in enumerate(actuators_raw):
        if not isinstance(a, dict):
            errors.append(
                f"actuators[{i}] must be a mapping with 'type' and "
                f"'max_torque_nm' keys, got {type(a).__name__}."
            )
            continue
        atype = a.get("type")
        torque = a.get("max_torque_nm")
        if atype not in SUPPORTED_ACTUATOR_TYPES:
            errors.append(
                f"actuators[{i}].type '{atype}' not recognized. "
                f"Supported: {SUPPORTED_ACTUATOR_TYPES}"
            )
        if not isinstance(torque, (int, float)) or torque <= 0:
            errors.append(
                f"actuators[{i}].max_torque_nm must be a positive number."
            )
        if not errors:
            actuators.append(ActuatorConfig(type=atype, max_torque_nm=float(torque)))

    # power
    power_raw = raw.get("power", {})
    if not isinstance(power_raw, dict):
        errors.append(
            "power must be a mapping with battery_capacity_wh and "
            "solar_panel_area_m2."
        )
        power_raw = {}
    batt = power_raw.get("battery_capacity_wh")
    solar = power_raw.get("solar_panel_area_m2")
    if not isinstance(batt, (int, float)) or batt <= 0:
        errors.append("power.battery_capacity_wh must be a positive number.")
    if not isinstance(solar, (int, float)) or solar <= 0:
        errors.append("power.solar_panel_area_m2 must be a positive number.")

    if errors:
        error_list = "\n  - ".join(errors)
        raise HardwareConfigError(
            f"Invalid hardware config at {path}:\n  - {error_list}"
        )

    return HardwareConfig(
        schema_version=str(sv),
        name=raw.get("name", "Unnamed Satellite"),
        form_factor=ff,
        mass_kg=float(mass),
        sensors=sensors,
        actuators=actuators,
        power=PowerConfig(
            battery_capacity_wh=float(batt),
            solar_panel_area_m2=float(solar),
        ),
    )