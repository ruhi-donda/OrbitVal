"""
orbitval/engine/injection.py

Fault injection engine for OrbitVal.
Applies named fault scenarios to a telemetry stream.
Records a full trace of every injection for the ORF report.
"""

from dataclasses import dataclass
from orbitval.faults.base import TelemetryFrame, FaultScenario


@dataclass
class InjectionEvent:
    """A single recorded fault injection event."""
    t: float
    fault_name: str
    fields_modified: list[str]


def run_injection(
    telemetry_stream: list[TelemetryFrame],
    scenarios: list,
) -> tuple[list[TelemetryFrame], list[InjectionEvent]]:
    """
    Apply fault scenarios to a telemetry stream.

    Args:
        telemetry_stream: list of TelemetryFrames from simulation
        scenarios: list of instantiated FaultScenario objects

    Returns:
        Tuple of:
        - injected telemetry stream
        - injection trace (list of InjectionEvent)
    """
    injected_stream = []
    trace = []

    for frame in telemetry_stream:
        modified_frame = frame
        for scenario in scenarios:
            if scenario.is_active(frame.t):
                before = modified_frame
                modified_frame = scenario.inject(modified_frame)
                # Record which fields changed
                changed = [
                    f for f in modified_frame.__dataclass_fields__
                    if getattr(modified_frame, f) != getattr(before, f)
                    and f != "flags"
                ]
                if changed:
                    trace.append(InjectionEvent(
                        t=frame.t,
                        fault_name=scenario.name,
                        fields_modified=changed,
                    ))
        injected_stream.append(modified_frame)

    return injected_stream, trace