"""
orbitval/engine/runner.py

Autonomy harness for OrbitVal.
Wraps user-provided autonomy code and runs it against
injected telemetry streams, recording responses and
evaluating pass/fail per scenario.

From TEMPLATES.md:
    from orbitval import TestRunner
    runner = TestRunner(config="satellite.yaml", autonomy=MyAutonomyClass)
    runner.run(scenarios=["gps_dropout", "reaction_wheel_degradation"])

The harness:
1. Loads and validates satellite.yaml
2. Fetches or accepts a TLE
3. Propagates the orbit
4. Builds a telemetry stream
5. For each scenario: injects faults, runs autonomy code,
   records responses, evaluates pass/fail
6. Generates ORF JSON + PDF report

No monkey-patching. No modifications to user code required
beyond implementing the AutonomyInterface and wrapping in
TestRunner.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable
from orbitval.faults.base import TelemetryFrame
from orbitval.config.hardware_3u_schema import load_hardware_config
from orbitval.orbits.tle import fetch_tle, tle_from_strings, TLERecord
from orbitval.orbits.propagation import propagate_from_tle
from orbitval.orbits.comms_windows import (
    compute_comms_windows, annotate_blackouts, GroundStation
)
from orbitval.faults.catalog import get_fault
from orbitval.engine.injection import run_injection
from orbitval.reporting.json_report import generate_json_report
from orbitval.reporting.pdf_report import generate_pdf_report


# ── Autonomy interface ────────────────────────────────────────

@runtime_checkable
class AutonomyInterface(Protocol):
    """
    Interface that user autonomy code must implement to work
    with the OrbitVal harness.

    Teams implement this class wrapping their onboard
    decision-making logic. OrbitVal feeds it telemetry
    frames and observes the response.

    Example:
        class MyAutonomy:
            def process(self, telemetry: TelemetryFrame) -> str:
                if not telemetry.gps_available:
                    return "safe_mode"
                return "nominal"

            def reset(self) -> None:
                pass  # reset internal state between scenarios
    """

    def process(self, telemetry: TelemetryFrame) -> str:
        """
        Process a telemetry frame and return a response string.
        The response describes what the autonomy code decided to do.

        Examples:
            "nominal"
            "safe_mode"
            "failover_to_dead_reckoning"
            "emergency_shutdown"

        Args:
            telemetry: current TelemetryFrame (may be fault-injected)

        Returns:
            string describing the autonomy decision
        """
        ...

    def reset(self) -> None:
        """
        Reset internal state between scenario runs.
        Called by the harness before each new fault scenario.
        """
        ...


# ── Pass/fail evaluation ──────────────────────────────────────

@dataclass
class ScenarioResult:
    """Result of running a single fault scenario."""
    name: str
    version: str
    result: str           # PASS | FAIL | SKIP
    duration_s: float
    seed: int
    autonomy_responses: list[str]
    primary_response: str  # most common response during fault
    fault_trace: list[dict]
    failure_reason: str | None = None


def _evaluate_scenario(
    scenario_name: str,
    injected_frames: list[TelemetryFrame],
    responses: list[str],
    trace: list,
    seed: int,
    expected_safe_responses: list[str],
) -> ScenarioResult:
    """
    Evaluate pass/fail for a scenario based on autonomy responses.

    Pass criteria: during active fault injection, the autonomy
    code must return at least one response from
    expected_safe_responses (e.g. "safe_mode", "failover").

    Fail criteria: during active fault injection, the autonomy
    code only returns "nominal" — meaning it didn't detect
    or respond to the fault.
    """
    from orbitval.faults.catalog import get_fault as _get_fault
    scenario = get_fault(scenario_name)

    # Get responses during active fault injection only
    active_responses = [
        responses[i]
        for i, frame in enumerate(injected_frames)
        if scenario.is_active(frame.t)
    ]

    if not active_responses:
        return ScenarioResult(
            name=scenario_name,
            version=scenario.version,
            result="SKIP",
            duration_s=0.0,
            seed=seed,
            autonomy_responses=responses,
            primary_response="none",
            fault_trace=[e.__dict__ for e in trace],
            failure_reason="Fault was never active during simulation",
        )

    # Check if any safe response was given during fault
    responded_safely = any(
        r in expected_safe_responses
        for r in active_responses
    )

    # Most common response during fault
    from collections import Counter
    primary = Counter(active_responses).most_common(1)[0][0]

    if responded_safely:
        return ScenarioResult(
            name=scenario_name,
            version=scenario.version,
            result="PASS",
            duration_s=len(active_responses) * 60.0,
            seed=seed,
            autonomy_responses=responses,
            primary_response=primary,
            fault_trace=[e.__dict__ for e in trace],
        )
    else:
        return ScenarioResult(
            name=scenario_name,
            version=scenario.version,
            result="FAIL",
            duration_s=len(active_responses) * 60.0,
            seed=seed,
            autonomy_responses=responses,
            primary_response=primary,
            fault_trace=[e.__dict__ for e in trace],
            failure_reason=(
                f"Autonomy code returned '{primary}' during active fault. "
                f"Expected one of: {expected_safe_responses}"
            ),
        )


# ── Test runner ───────────────────────────────────────────────

class TestRunner:
    """
    The OrbitVal autonomy harness.

    Loads satellite config, fetches orbit, builds telemetry,
    runs fault scenarios against user autonomy code, and
    produces an ORF-compliant report.

    Usage:
        from orbitval import TestRunner

        class MyAutonomy:
            def process(self, telemetry):
                if not telemetry.gps_available:
                    return "safe_mode"
                return "nominal"
            def reset(self):
                pass

        runner = TestRunner(
            config="satellite.yaml",
            autonomy=MyAutonomy(),
        )
        runner.run(
            scenarios=["gps_dropout", "power_brownout"],
            output_dir="reports/",
        )
    """

    def __init__(
        self,
        config: str | Path,
        autonomy: object,
        tle_name: str = "ISS (ZARYA)",
        tle_line1: str | None = None,
        tle_line2: str | None = None,
        duration_hours: float = 1.0,
        step_seconds: float = 60.0,
        seed: int = 42,
        ground_stations: list[GroundStation] | None = None,
    ):
        """
        Args:
            config: path to satellite.yaml
            autonomy: object implementing AutonomyInterface
            tle_name: satellite name to fetch from Celestrak
            tle_line1: optional manual TLE line 1 (skips Celestrak)
            tle_line2: optional manual TLE line 2 (skips Celestrak)
            duration_hours: simulation duration
            step_seconds: telemetry time step
            seed: random seed for reproducibility
            ground_stations: optional list of GroundStation objects
        """
        self.hardware = load_hardware_config(config)
        self.autonomy = autonomy
        self.duration_hours = duration_hours
        self.step_seconds = step_seconds
        self.seed = seed
        self.ground_stations = ground_stations or []

        # Load TLE
        if tle_line1 and tle_line2:
            self.tle = tle_from_strings(tle_name, tle_line1, tle_line2)
        else:
            print(f"[orbitval] Fetching TLE for '{tle_name}'...")
            self.tle = fetch_tle(tle_name)

        # Propagate orbit
        print("[orbitval] Propagating orbit...")
        self.orbit = propagate_from_tle(
            tle_line1=self.tle.line1,
            tle_line2=self.tle.line2,
            tle_name=self.tle.name,
            duration_hours=duration_hours,
            step_seconds=step_seconds,
        )

        # Build base telemetry stream
        self._base_telemetry = self._build_telemetry()

        # Compute comms windows
        if self.ground_stations:
            print("[orbitval] Computing comms windows...")
            self.comms_windows = compute_comms_windows(
                tle_line1=self.tle.line1,
                tle_line2=self.tle.line2,
                tle_name=self.tle.name,
                ground_stations=self.ground_stations,
                duration_hours=duration_hours,
                step_seconds=10.0,
            )
            print(f"[orbitval] Found {len(self.comms_windows)} comms windows")
        else:
            self.comms_windows = []

    def _build_telemetry(self) -> list[TelemetryFrame]:
        """Build base telemetry stream from propagated orbit."""
        stream = []
        for i, point in enumerate(self.orbit.ground_track):
            stream.append(TelemetryFrame(
                t=float(i * self.step_seconds),
                gps_lat=point.lat_deg,
                gps_lon=point.lon_deg,
                gps_alt_km=point.alt_km,
                gps_available=True,
                magnetometer_x=25.0,
                magnetometer_y=-10.0,
                magnetometer_z=40.0,
                star_tracker_available=True,
                battery_charge_wh=self.hardware.power.battery_capacity_wh,
                solar_power_w=5.0,
                reaction_wheel_speed_rpm=100.0,
            ))
        return stream

    def run(
        self,
        scenarios: list[str],
        scenario_kwargs: dict | None = None,
        output_dir: str | Path = "reports/",
        expected_safe_responses: list[str] | None = None,
        mission_profile: dict | None = None,
    ) -> dict:
        """
        Run fault scenarios against user autonomy code.

        Args:
            scenarios: list of fault scenario names
            scenario_kwargs: optional per-scenario kwargs
                e.g. {"gps_dropout": {"t_start": 60, "duration_s": 120}}
            output_dir: where to write JSON + PDF reports
            expected_safe_responses: responses that count as PASS
                defaults to ["safe_mode", "failover",
                "failover_to_dead_reckoning", "emergency_shutdown"]
            mission_profile: optional mission context for ORF report

        Returns:
            ORF report dict
        """
        kwargs = scenario_kwargs or {}
        safe = expected_safe_responses or [
            "safe_mode",
            "failover",
            "failover_to_dead_reckoning",
            "emergency_shutdown",
            "reduced_ops",
        ]

        scenario_results = []

        for scenario_name in scenarios:
            print(f"[orbitval] Running scenario: {scenario_name}...")

            # Reset autonomy state between scenarios
            self.autonomy.reset()

           # Build fault scenario
            # Only pass seed to scenarios that accept it
            from inspect import signature
            scenario_class = __import__(
                'orbitval.faults.catalog', fromlist=['FAULT_REGISTRY']
            ).FAULT_REGISTRY[scenario_name]
            accepted_params = signature(scenario_class.__init__).parameters
            default_kw = {"seed": self.seed} if "seed" in accepted_params else {}
            scenario_kw = kwargs.get(scenario_name, default_kw)
            fault = get_fault(scenario_name, **scenario_kw)

            # Inject faults
            injected, trace = run_injection(
                self._base_telemetry,
                [fault],
            )

            # Annotate comms blackouts
            if self.comms_windows:
                injected = annotate_blackouts(injected, self.comms_windows)

            # Run autonomy code against injected telemetry
            # Flags are stripped before passing to autonomy code —
            # onboard software cannot see OrbitVal's internal metadata.
            # Autonomy code must detect anomalies from raw sensor
            # data only, exactly as it would in orbit.
            responses = []
            for frame in injected:
                try:
                    from dataclasses import replace
                    clean_frame = replace(frame, flags={})
                    response = self.autonomy.process(clean_frame)
                    responses.append(str(response))
                except Exception as e:
                    responses.append(f"exception: {e}")

            # Evaluate pass/fail
            result = _evaluate_scenario(
                scenario_name=scenario_name,
                injected_frames=injected,
                responses=responses,
                trace=trace,
                seed=self.seed,
                expected_safe_responses=safe,
            )
            scenario_results.append(result)

            status = "✓ PASS" if result.result == "PASS" else "✗ FAIL"
            print(f"[orbitval] {status} — {scenario_name} "
                  f"(primary response: {result.primary_response})")
            if result.failure_reason:
                print(f"[orbitval]   reason: {result.failure_reason}")

        # Generate reports
        print("[orbitval] Generating reports...")
        scenarios_run = [
            {
                "name": r.name,
                "version": r.version,
                "result": r.result,
                "duration_s": r.duration_s,
                "seed": r.seed,
                "autonomy_response": r.primary_response,
                "fault_trace": r.fault_trace,
                "failure_reason": r.failure_reason,
            }
            for r in scenario_results
        ]

        from datetime import datetime
        timestamp = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
        sat_name = self.hardware.name.replace(" ", "_").lower()
        report_stem = f"{sat_name}_{timestamp}"

        report = generate_json_report(
            satellite_name=self.hardware.name,
            hardware=self.hardware,
            scenarios_run=scenarios_run,
            injection_trace=[],
            orbit_epoch=self.orbit.epoch,
            duration_s=self.orbit.duration_s,
            seed=self.seed,
            output_path=Path(output_dir) / f"{report_stem}.json",
            mission_profile=mission_profile,
        )

        generate_pdf_report(
            report=report,
            output_path=Path(output_dir) / f"{report_stem}.pdf",
        )

        return report