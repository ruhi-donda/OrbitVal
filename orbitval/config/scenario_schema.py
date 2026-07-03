"""
orbitval/config/scenario_schema.py

Scenario configuration model for OrbitVal.
Loads and validates a scenario.yaml file that names the fault
scenarios to run and their parameters — an alternative to
passing everything as CLI flags.

Schema version: 1.0

Example scenario.yaml:

    schema_version: "1.0"
    scenarios:
      - name: gps_dropout
        params:
          t_start: 60.0
          duration_s: 120.0
      - name: eclipse_power_stress
      - name: star_tracker_failure
        params:
          mode: degraded

Valid scenario names and parameters are derived from the fault
registry — the schema never needs updating when a new fault
scenario is registered in catalog.py.
"""

from dataclasses import dataclass, field
from inspect import signature
from pathlib import Path
import yaml

from orbitval.faults.catalog import FAULT_REGISTRY

SCHEMA_VERSION = "1.0"


@dataclass
class ScenarioSpec:
    """One validated scenario entry: name + constructor params."""
    name: str
    params: dict = field(default_factory=dict)


class ScenarioConfigError(Exception):
    """Raised when scenario.yaml fails validation."""
    pass


def load_scenario_config(config_path: str | Path) -> list[ScenarioSpec]:
    """
    Load and validate a scenario.yaml file.

    Args:
        config_path: path to scenario.yaml

    Returns:
        List of validated ScenarioSpec entries

    Raises:
        ScenarioConfigError: if validation fails
        FileNotFoundError: if file does not exist
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Scenario config not found: {path}."
        )

    with open(path) as f:
        raw = yaml.safe_load(f)

    return _validate(raw, path)


def _validate(raw: dict, path: Path) -> list[ScenarioSpec]:
    """Validate raw YAML dict against the scenario schema."""
    errors = []

    if not isinstance(raw, dict):
        raise ScenarioConfigError(
            f"Invalid scenario config at {path}: "
            f"expected a YAML mapping, got {type(raw).__name__}."
        )

    sv = raw.get("schema_version")
    if sv != SCHEMA_VERSION:
        errors.append(
            f"schema_version must be '{SCHEMA_VERSION}', got '{sv}'."
        )

    scenarios_raw = raw.get("scenarios")
    if not isinstance(scenarios_raw, list) or not scenarios_raw:
        errors.append("At least one scenario must be defined under 'scenarios'.")
        scenarios_raw = []

    specs = []
    for i, entry in enumerate(scenarios_raw):
        if not isinstance(entry, dict):
            errors.append(f"scenarios[{i}] must be a mapping with a 'name' key.")
            continue

        name = entry.get("name")
        if name not in FAULT_REGISTRY:
            errors.append(
                f"scenarios[{i}].name '{name}' not recognized. "
                f"Available: {list(FAULT_REGISTRY.keys())}"
            )
            continue

        params = entry.get("params") or {}
        if not isinstance(params, dict):
            errors.append(f"scenarios[{i}].params must be a mapping.")
            continue

        # Validate param names against the scenario's constructor
        accepted = set(signature(FAULT_REGISTRY[name].__init__).parameters) - {"self"}
        unknown = set(params) - accepted
        if unknown:
            errors.append(
                f"scenarios[{i}] ('{name}'): unknown param(s) "
                f"{sorted(unknown)}. Accepted: {sorted(accepted)}"
            )
            continue

        specs.append(ScenarioSpec(name=name, params=params))

    if errors:
        error_list = "\n  - ".join(errors)
        raise ScenarioConfigError(
            f"Invalid scenario config at {path}:\n  - {error_list}"
        )

    return specs
