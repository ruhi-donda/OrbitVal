"""
orbitval/faults/catalog.py

Registry of all available fault scenarios.
Discovers and returns named fault scenarios by name.
"""

from orbitval.faults.scenarios.gps_dropout import GpsDropout
from orbitval.faults.scenarios.power_brownout import PowerBrownout
from orbitval.faults.scenarios.sensor_noise import SensorNoise


# Registry of all free built-in fault scenarios
FAULT_REGISTRY = {
    "gps_dropout": GpsDropout,
    "power_brownout": PowerBrownout,
    "sensor_noise": SensorNoise,
}


def list_faults() -> list[dict]:
    """Return metadata for all available fault scenarios."""
    return [
        {
            "name": cls.name,
            "description": cls.description,
            "version": cls.version,
        }
        for cls in FAULT_REGISTRY.values()
    ]


def get_fault(name: str, **kwargs):
    """
    Instantiate a fault scenario by name.

    Args:
        name: fault scenario name e.g. "gps_dropout"
        **kwargs: passed to the fault scenario constructor

    Returns:
        Instantiated fault scenario

    Raises:
        ValueError: if fault name not found
    """
    if name not in FAULT_REGISTRY:
        raise ValueError(
            f"Fault scenario '{name}' not found. "
            f"Available: {list(FAULT_REGISTRY.keys())}"
        )
    return FAULT_REGISTRY[name](**kwargs)