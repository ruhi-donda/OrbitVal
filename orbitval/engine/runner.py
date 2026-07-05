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
2. Fetches or accepts a TLE — or synthesizes orbit from params
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
from orbitval.orbits.propagation import propagate_from_tle, propagate_from_params
from orbitval.orbits.comms_windows import (
    compute_comms_windows, annotate_blackouts, GroundStation
)
from orbitval.faults.catalog import FAULT_REGISTRY, get_fault
from orbitval.engine.injection import run_injection
from orbitval.reporting.json_report import generate_json_report
from orbitval.reporting.pdf_report import generate_pdf_report
from orbitval.logging import get_logger, init_run_log, clear_run_events

log = get_logger("runner")


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
                pass
    """

    def process(self, telemetry: TelemetryFrame) -> str:
        """
        Process a telemetry frame and return a response string.

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
    primary_response: str
    fault_trace: list[dict]
    failure_reason: str | None = None


def _evaluate_scenario(
    scenario_name: str,
    injected_frames: list[TelemetryFrame],
    responses: list[str],
    trace: list,
    seed: int,
    expected_safe_responses: list[str],
    fault: object | None = None,
) -> ScenarioResult:
    """
    Evaluate pass/fail for a scenario based on autonomy responses.

    Pass: autonomy code returned at least one safe response
          during active fault injection.
    Fail: autonomy code only returned "nominal" during fault —
          it didn't detect or respond to the fault.

    Args:
        fault: the actual fault instance used for injection. Must be
            passed when the fault was built with non-default args
            (e.g. real eclipse windows) so the evaluation window
            matches the injection window. Falls back to a
            default-constructed instance when omitted.
    """
    scenario = fault if fault is not None else get_fault(scenario_name)

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

    responded_safely = any(r in expected_safe_responses for r in active_responses)

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

    Supports three orbit input modes:
    1. TLE by name    — fetches live from Celestrak
    2. TLE by strings — provided directly (offline/air-gapped)
    3. Pre-launch     — synthesized from altitude + inclination
                        (no TLE exists yet — satellite hasn't launched)

    Usage:
        from orbitval import TestRunner

        # Mode 1: live TLE
        runner = TestRunner(config="satellite.yaml", autonomy=MyAutonomy())

        # Mode 2: manual TLE strings
        runner = TestRunner(
            config="satellite.yaml",
            autonomy=MyAutonomy(),
            tle_line1="1 25544U ...",
            tle_line2="2 25544 ...",
        )

        # Mode 3: pre-launch (no TLE)
        runner = TestRunner(
            config="satellite.yaml",
            autonomy=MyAutonomy(),
            orbit_alt_km=550,
            orbit_inc_deg=53.0,
        )
    """

    def __init__(
        self,
        config: str | Path,
        autonomy: object,
        tle_name: str = "ISS (ZARYA)",
        tle_line1: str | None = None,
        tle_line2: str | None = None,
        orbit_alt_km: float | None = None,
        orbit_inc_deg: float | None = None,
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
            orbit_alt_km: orbital altitude in km (pre-launch mode)
            orbit_inc_deg: orbital inclination in degrees (pre-launch mode)
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

        # ── Orbit input: three modes ──────────────────────────
        if orbit_alt_km is not None and orbit_inc_deg is not None:
            # Mode 3: pre-launch — synthesize orbit from parameters
            # Most common use case: satellite hasn't launched yet,
            # team knows their planned orbit but has no TLE
            log.info(
                "Pre-launch mode — synthesizing orbit "
                "(alt=%.0fkm, inc=%.1f°)",
                orbit_alt_km, orbit_inc_deg
            )
            self.tle = None
            self.orbit = propagate_from_params(
                alt_km=orbit_alt_km,
                inc_deg=orbit_inc_deg,
                duration_hours=duration_hours,
                step_seconds=step_seconds,
            )

        elif tle_line1 and tle_line2:
            # Mode 2: manual TLE strings — offline/air-gapped
            log.info("Using provided TLE strings for '%s'", tle_name)
            self.tle = tle_from_strings(tle_name, tle_line1, tle_line2)
            log.info("Propagating orbit...")
            self.orbit = propagate_from_tle(
                tle_line1=self.tle.line1,
                tle_line2=self.tle.line2,
                tle_name=self.tle.name,
                duration_hours=duration_hours,
                step_seconds=step_seconds,
            )

        else:
            # Mode 1: fetch live TLE from Celestrak (default)
            log.info("Fetching TLE for '%s'", tle_name)
            self.tle = fetch_tle(tle_name)
            log.info("Propagating orbit...")
            self.orbit = propagate_from_tle(
                tle_line1=self.tle.line1,
                tle_line2=self.tle.line2,
                tle_name=self.tle.name,
                duration_hours=duration_hours,
                step_seconds=step_seconds,
            )

        # Build base telemetry stream
        self._base_telemetry = self._build_telemetry()

        # ── Comms windows ─────────────────────────────────────
        if self.ground_stations and self.tle is not None:
            log.info("Computing comms windows...")
            self.comms_windows = compute_comms_windows(
                tle_line1=self.tle.line1,
                tle_line2=self.tle.line2,
                tle_name=self.tle.name,
                ground_stations=self.ground_stations,
                duration_hours=duration_hours,
                step_seconds=10.0,
            )
            log.info("Found %d comms window(s)", len(self.comms_windows))
        elif self.ground_stations and self.tle is None:
            log.warning(
                "Comms windows unavailable in pre-launch mode "
                "(no TLE — synthetic orbit only)"
            )
            self.comms_windows = []
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
            output_dir: where to write JSON + PDF + log reports
            expected_safe_responses: responses that count as PASS
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

        # Start the run's audit trail BEFORE scenarios execute, so the
        # events they log end up in both the .log file and the report's
        # embedded run_log. Clearing here (not at report time) is what
        # keeps each run's trail scoped to that run.
        from datetime import datetime
        clear_run_events()
        timestamp = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
        sat_name = self.hardware.name.replace(" ", "_").lower()
        report_stem = f"{sat_name}_{timestamp}"

        init_run_log(Path(output_dir) / f"{report_stem}.log")

        scenario_results = []

        for scenario_name in scenarios:
            log.info("Running scenario: %s", scenario_name)

            # Reset autonomy state between scenarios
            self.autonomy.reset()

            # Build fault scenario
            # Only pass seed to scenarios that accept it
            from inspect import signature
            if scenario_name not in FAULT_REGISTRY:
                raise ValueError(
                    f"Fault scenario '{scenario_name}' not found. "
                    f"Available: {list(FAULT_REGISTRY.keys())}"
                )
            scenario_class = FAULT_REGISTRY[scenario_name]
            accepted_params = signature(scenario_class.__init__).parameters
            default_kw = {"seed": self.seed} if "seed" in accepted_params else {}
            # Scenarios that accept eclipse_windows get the real
            # umbra/penumbra intervals from the propagated orbit,
            # so the fault fires during actual shadow passages.
            if "eclipse_windows" in accepted_params and self.orbit.eclipse_periods:
                default_kw["eclipse_windows"] = [
                    (p["start_t"], p["end_t"])
                    for p in self.orbit.eclipse_periods
                ]
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
                    log.error(
                        "Autonomy code raised exception at t=%.0fs: %s",
                        frame.t, e
                    )
                    responses.append(f"exception: {e}")

            # Evaluate pass/fail
            result = _evaluate_scenario(
                scenario_name=scenario_name,
                injected_frames=injected,
                responses=responses,
                trace=trace,
                seed=self.seed,
                expected_safe_responses=safe,
                fault=fault,
            )
            scenario_results.append(result)

            if result.result == "PASS":
                log.info(
                    "PASS — %s (primary: %s)",
                    scenario_name, result.primary_response
                )
            else:
                log.error(
                    "FAIL — %s (primary: %s)",
                    scenario_name, result.primary_response
                )
                if result.failure_reason:
                    log.error("  reason: %s", result.failure_reason)

        # ── Generate reports ──────────────────────────────────
        log.info("Generating reports...")

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

        # Collect all injection events across all scenarios into a flat list
        # for the top-level injection_trace field in the ORF report.
        injection_trace = [
            event
            for r in scenario_results
            for event in r.fault_trace
        ]

        report = generate_json_report(
            satellite_name=self.hardware.name,
            hardware=self.hardware,
            scenarios_run=scenarios_run,
            injection_trace=injection_trace,
            comms_windows=self.comms_windows,
            eclipse_periods=self.orbit.eclipse_periods,
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