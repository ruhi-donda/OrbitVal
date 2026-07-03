"""
orbitval/faults/scenarios/star_tracker_failure.py

Free fault scenario: Star tracker failure.
Attitude determination degrades or fails outright — the star
tracker feeds bad or null quaternion data to the bus.

The dangerous failure mode is not the loss itself but silent
trust: downstream subsystems (pointing, momentum management,
comms scheduling) acting on garbage attitude data as if it were
valid. Autonomy code must flag degraded attitude confidence
rather than continuing nominal operations on bad quaternions.

Two modes:
- "failed":   star tracker offline, null quaternion (0,0,0,0 —
              mathematically invalid), attitude_valid=False
- "degraded": star tracker nominally up but the quaternion is
              corrupted with seeded noise and no longer normalized;
              attitude_valid=False signals the degraded solution

Tier: FREE (generic fault — no vendor-specific recovery model)
"""

from dataclasses import replace
import random
from orbitval.faults.base import TelemetryFrame, WindowedFault


class StarTrackerFailure(WindowedFault):
    """
    Simulates star tracker attitude determination failure.
    Tests that autonomy code detects degraded attitude confidence
    instead of silently trusting bad quaternion data.
    """

    name = "star_tracker_failure"
    description = (
        "Attitude determination failure — the star tracker feeds "
        "bad or null quaternion data. Tests that autonomy code "
        "flags degraded attitude confidence rather than silently "
        "trusting invalid attitude solutions."
    )
    version = "1.0.0"

    def __init__(
        self,
        t_start: float = 180.0,
        duration_s: float = 300.0,
        mode: str = "failed",
        noise_sigma: float = 0.3,
        seed: int = 42,
    ):
        """
        Args:
            t_start: mission time (seconds) when failure begins
            duration_s: how long it lasts
            mode: "failed" (offline, null quaternion) or
                  "degraded" (corrupted, unnormalized quaternion)
            noise_sigma: quaternion corruption magnitude in
                degraded mode
            seed: random seed for reproducibility (critical for ORF)
        """
        if mode not in ("failed", "degraded"):
            raise ValueError(
                f"mode must be 'failed' or 'degraded', got '{mode}'"
            )
        super().__init__(t_start=t_start, duration_s=duration_s)
        self.mode = mode
        self.noise_sigma = noise_sigma
        self.rng = random.Random(seed)

    def inject(self, telemetry: TelemetryFrame) -> TelemetryFrame:
        if not self.is_active(telemetry.t):
            return telemetry

        if self.mode == "failed":
            # Null quaternion — mathematically invalid (zero norm)
            return replace(
                telemetry,
                star_tracker_available=False,
                attitude_qw=0.0,
                attitude_qx=0.0,
                attitude_qy=0.0,
                attitude_qz=0.0,
                attitude_valid=False,
                flags={**telemetry.flags, "star_tracker_failure": True},
            )

        # Degraded: corrupted, unnormalized quaternion. The tracker
        # still reports "available" — only attitude_valid reveals
        # the solution can't be trusted.
        return replace(
            telemetry,
            attitude_qw=telemetry.attitude_qw + self.rng.gauss(0, self.noise_sigma),
            attitude_qx=telemetry.attitude_qx + self.rng.gauss(0, self.noise_sigma),
            attitude_qy=telemetry.attitude_qy + self.rng.gauss(0, self.noise_sigma),
            attitude_qz=telemetry.attitude_qz + self.rng.gauss(0, self.noise_sigma),
            attitude_valid=False,
            flags={**telemetry.flags, "star_tracker_failure": True},
        )
