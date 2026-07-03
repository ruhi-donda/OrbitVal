"""
orbitval/faults/scenarios/comms_blackout.py

Free fault scenario: Communication blackout.
Total loss of ground contact for a configurable duration —
antenna failure, ground segment outage, or extended pass gap.

During the blackout the satellite must operate fully autonomously:
no commands can be received and no telemetry reaches the ground.
The autonomy code sees ground_contact=False in the telemetry and
must respond by conserving resources and buffering data. On
reacquisition (ground_contact returns True) it should resume
nominal operations.

Tier: FREE (generic fault)
"""

from dataclasses import replace
from orbitval.faults.base import TelemetryFrame, WindowedFault


class CommsBlackout(WindowedFault):
    """
    Simulates a total communication blackout — the satellite has
    no ground contact for the fault window. Tests autonomous
    operation without ground intervention and recovery detection
    when contact is reacquired.
    """

    name = "comms_blackout"
    description = (
        "Total loss of ground contact for a configurable duration. "
        "Tests fully autonomous operation during the blackout and "
        "recovery detection on reacquisition."
    )
    version = "1.0.0"

    def __init__(self, t_start: float = 300.0, duration_s: float = 900.0):
        """
        Args:
            t_start: mission time (seconds) when contact is lost
            duration_s: how long the blackout lasts
        """
        super().__init__(t_start=t_start, duration_s=duration_s)

    def inject(self, telemetry: TelemetryFrame) -> TelemetryFrame:
        if not self.is_active(telemetry.t):
            return telemetry
        return replace(
            telemetry,
            ground_contact=False,
            flags={**telemetry.flags, "comms_blackout_fault": True},
        )
