"""
orbitval/ml/app/core.py

The demo's logic, kept apart from its Streamlit page so it can be tested
and walked through on its own. It reuses the real evaluation pieces:
make_mission, mission_scores and the thresholds calibrated on clean
validation missions, so what the demo shows is what the results measure.

Missions come from the dev seed range. The demo never flies test orbits.
"""

import json
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import numpy as np

from orbitval.config.hardware_3u_schema import HardwareConfig
from orbitval.ml.evaluate import EVENT_GRACE
from orbitval.ml.metrics import runs
from orbitval.ml.models.baseline import PersistenceBaseline
from orbitval.ml.run_neural import load_detector
from orbitval.ml.sim.missions import FAULT_STEPS, STEP_S, make_mission, mission_scores, mission_seed
from orbitval.ml.sim.telemetry import CHANNELS

WEIGHTS_DIR = Path(__file__).parent / "weights"
MANIFEST = WEIGHTS_DIR / "manifest.json"
MAPS = WEIGHTS_DIR / "maps.json"
NO_FAULT = "none"
ZOOM_STEPS = 150

# Which channel each fault mainly affects, shown by default
FAULT_CHANNEL = {
    NO_FAULT: "solar_power_w",
    "power_brownout": "solar_power_w",
    "sensor_noise": "magnetometer_y",
    "eclipse_power_stress": "solar_power_w",
    "sensor_drift": "temperature_c",
    "stuck_sensor": "solar_power_w",
}


def load_manifest(path: Path = MANIFEST) -> dict:
    """Thresholds and file names written by scripts/export_demo_weights.py."""
    return json.loads(Path(path).read_text())


def load_demo_detector(name: str, seed: int, manifest: dict, weights_dir: Path = WEIGHTS_DIR):
    """Returns (detector, threshold). `seed` is ignored for persistence."""
    if name == "persistence":
        return PersistenceBaseline(), manifest["persistence"]["threshold"]
    entry = manifest[name][str(seed)]
    detector, _ = load_detector(Path(weights_dir) / entry["file"])
    return detector, entry["threshold"]


@dataclass
class AlarmSummary:
    detected: bool
    delay_steps: int | None        # steps from fault start to first alarm inside it
    in_fault: int                  # alarm runs touching the fault window
    recovery: int                  # alarm runs in the grace period after it
    false: int                     # all other alarm runs


def classify_alarms(alarms: np.ndarray, event: tuple[int, int] | None) -> AlarmSummary:
    """Sort alarm runs the same way metrics.count_channel does."""
    in_fault = recovery = false = 0
    for a, b in runs(alarms):
        if event is not None and a <= event[1] and b >= event[0]:
            in_fault += 1
        elif event is not None and event[1] < a <= event[1] + EVENT_GRACE:
            recovery += 1
        else:
            false += 1
    delay = None
    if event is not None:
        hits = np.flatnonzero(alarms[event[0]:event[1] + 1])
        if hits.size:
            delay = int(hits[0])
    return AlarmSummary(delay is not None, delay, in_fault, recovery, false)


@dataclass
class DemoRun:
    name: str
    threshold: float
    data: np.ndarray               # (T, C) measured telemetry
    clean: np.ndarray              # (T, C) the same mission with no fault
    forecast: np.ndarray           # (T,) forecast for the shown channel
    scores: np.ndarray             # (T,) mission score, max over channels
    alarms: np.ndarray             # (T,) bool
    event: tuple[int, int] | None
    illumination: np.ndarray       # (T,)
    channel: str
    summary: AlarmSummary

    @property
    def t_hours(self) -> np.ndarray:
        return np.arange(len(self.data)) * STEP_S / 3600.0


def run_demo(
    detector,
    threshold: float,
    hardware: HardwareConfig,
    fault: str,
    severity: float,
    onset: int,
    mission_index: int,
    channel: str,
) -> DemoRun:
    """Fly one dev mission, inject the fault, and score it."""
    seed = mission_seed("dev", mission_index)
    clean = make_mission(hardware, seed)
    if fault == NO_FAULT:
        mission = clean
    else:
        mission = make_mission(hardware, seed, fault, severity, onset=onset)
    event = mission.events[0] if mission.events else None

    scores = mission_scores(detector, mission.data)
    alarms = np.where(np.isfinite(scores), scores, -np.inf) > threshold
    c = CHANNELS.index(channel)
    forecast = detector.forecast(mission.data[:, c], channel=c)
    return DemoRun(
        name=detector.name,
        threshold=threshold,
        data=mission.data,
        clean=clean.data,
        forecast=forecast,
        scores=scores,
        alarms=alarms,
        event=event,
        illumination=mission.illumination,
        channel=channel,
        summary=classify_alarms(alarms, event),
    )


def event_in_eclipse(illumination: np.ndarray, onset: int) -> bool:
    """True if a fault at this onset overlaps shadow."""
    return bool(np.any(illumination[onset:onset + FAULT_STEPS] < 1.0))


CHANNEL_LABELS = {
    "solar_power_w": "solar power (W)",
    "battery_charge_wh": "battery (Wh)",
    "temperature_c": "temperature (°C)",
    "magnetometer_x": "magnetometer x (µT)",
    "magnetometer_y": "magnetometer y (µT)",
    "magnetometer_z": "magnetometer z (µT)",
}

# Plot colours for each page theme. Light is the projector option.
PALETTES = {
    "light": {"bg": "#ffffff", "fg": "#1a1a1a", "grid": "#d5d5d5", "shadow": "#dddddd",
              "fault": "#f6b8b8", "measured": "#174a7c", "forecast": "#d9731a",
              "score": "#1f7a4d", "alarm": "#b3161b"},
    "dark": {"bg": "#0e1117", "fg": "#e8e8e8", "grid": "#3a3f4b", "shadow": "#2b303b",
             "fault": "#6e2f35", "measured": "#7db8ea", "forecast": "#f2a65a",
             "score": "#6fd19b", "alarm": "#ff6b6b"},
}


def _rc(theme: str, base_size: float = 14.0) -> dict:
    """matplotlib settings: projector-sized fonts in the page's colours."""
    c = PALETTES[theme]
    return {
        "font.size": base_size, "axes.labelsize": base_size, "axes.titlesize": base_size + 1,
        "xtick.labelsize": base_size - 1, "ytick.labelsize": base_size - 1,
        "legend.fontsize": base_size - 2,
        "figure.facecolor": c["bg"], "axes.facecolor": c["bg"], "savefig.facecolor": c["bg"],
        "text.color": c["fg"], "axes.labelcolor": c["fg"], "axes.edgecolor": c["fg"],
        "xtick.color": c["fg"], "ytick.color": c["fg"],
        "legend.facecolor": c["bg"], "legend.edgecolor": c["grid"], "legend.framealpha": 1.0,
    }


def draw(run: DemoRun, upto: int | None = None, zoom: bool = False, theme: str = "light"):
    """
    Two panels: telemetry with the forecast, then the surprise score (the
    rolling z-score of the smoothed forecast error) against the alarm
    line. Returns a matplotlib Figure.

    upto: draw only steps up to this index, for playback.
    zoom: show ZOOM_STEPS either side of the fault instead of the whole
        mission. The score axis is capped at 3x the threshold either way,
        so a huge spike can't flatten the alarm line.
    """
    import matplotlib
    from matplotlib.figure import Figure
    from matplotlib.patches import Patch

    c = PALETTES[theme]
    n = len(run.data) if upto is None else upto + 1
    t = run.t_hours
    ch = CHANNELS.index(run.channel)

    with matplotlib.rc_context(_rc(theme)):
        fig = Figure(figsize=(11, 3.85), layout="constrained")
        top, bottom = fig.subplots(2, 1, sharex=True)

        for ax in (top, bottom):
            # Shade shadow so eclipses read as normal behaviour
            for a, b in runs(run.illumination < 1.0):
                ax.axvspan(t[a], t[b], color=c["shadow"], lw=0)
            if run.event is not None:
                ax.axvspan(t[run.event[0]], t[run.event[1]], color=c["fault"], lw=0)
            if zoom and run.event is not None:
                ax.set_xlim(t[max(run.event[0] - ZOOM_STEPS, 0)],
                            t[min(run.event[1] + ZOOM_STEPS, len(t) - 1)])
            else:
                ax.set_xlim(t[0], t[-1])

        measured, = top.plot(t[:n], run.data[:n, ch], color=c["measured"], lw=1.8)
        forecast, = top.plot(t[:n], run.forecast[:n], color=c["forecast"], lw=1.6)
        # Horizontal labels: readable from a distance, and they can't collide
        top.set_ylabel(CHANNEL_LABELS[run.channel].replace(" (", "\n("), rotation=0, ha="right", va="center")
        top.legend(
            [measured, forecast, Patch(color=c["shadow"]), Patch(color=c["fault"])],
            ["measured", f"{run.name} forecast", "shadow (normal)", "fault"],
            loc="lower right", bbox_to_anchor=(1.0, 1.0), ncols=4, borderaxespad=0.2)

        score, = bottom.plot(t[:n], run.scores[:n], color=c["score"], lw=1.8)
        line = bottom.axhline(run.threshold, color=c["alarm"], ls="--", lw=1.6)
        handles, labels = [score, line], ["surprise score", "alarm line"]
        fired = np.flatnonzero(run.alarms[:n])
        if fired.size:
            # Spikes above the capped axis are drawn on its top edge
            top_of_axis = 3.0 * run.threshold
            handles.append(bottom.scatter(t[fired], np.minimum(run.scores[fired], top_of_axis),
                                          color=c["alarm"], s=26, zorder=3, clip_on=False))
            labels.append("alarm")
        bottom.set_ylim(-3.0, 3.0 * run.threshold)
        bottom.set_ylabel("surprise score\n(higher =\nmore unusual)", rotation=0, ha="right", va="center")
        bottom.set_xlabel("mission time (hours)")
        bottom.legend(handles, labels, loc="upper right", ncols=3, framealpha=0.8)
    return fig


FAULT_SHORT = {"power_brownout": "brownout", "sensor_noise": "noise",
               "eclipse_power_stress": "eclipse\nstress", "sensor_drift": "drift",
               "stuck_sensor": "stuck"}


def draw_maps(maps: dict, theme: str = "light"):
    """Detectability heatmaps side by side, one panel per detector."""
    import matplotlib
    from matplotlib.figure import Figure

    names = [n for n in ("persistence", "lstm", "gru") if n in maps]
    faults = list(dict.fromkeys(cell["fault"] for cell in maps[names[0]]["cells"]))
    sevs = sorted({cell["severity"] for cell in maps[names[0]]["cells"]})

    with matplotlib.rc_context(_rc(theme, base_size=14.0)):
        fig = Figure(figsize=(10.5, 4.6), layout="constrained")
        axes = fig.subplots(1, len(names), sharey=True, squeeze=False)[0]
        for ax, name in zip(axes, names):
            grid = np.zeros((len(faults), len(sevs)))
            for cell in maps[name]["cells"]:
                grid[faults.index(cell["fault"]), sevs.index(cell["severity"])] = cell["recall"]
            image = ax.imshow(grid, vmin=0, vmax=1, cmap="viridis", aspect="auto")
            ax.set_xticks(range(len(sevs)), [f"{s:g}" for s in sevs], fontsize=10)
            ax.set_yticks(range(len(faults)), [FAULT_SHORT[f] for f in faults])
            ax.set_xlabel("fault severity")
            seeds = maps[name]["seeds"]
            ax.set_title(f"{name} ({seeds} seed{'s' if seeds > 1 else ''})")
            for i in range(len(faults)):
                for j in range(len(sevs)):
                    ax.text(j, i, f"{grid[i, j]:.2f}", ha="center", va="center", fontsize=9.5,
                            color="black" if grid[i, j] > 0.6 else "white")
        fig.colorbar(image, ax=list(axes), label="fraction of faults caught", shrink=0.9)
    return fig


def figure_png(fig, dpi: int = 110) -> bytes:
    """Figure -> PNG bytes."""
    buffer = BytesIO()
    fig.savefig(buffer, format="png", dpi=dpi)
    return buffer.getvalue()


def load_maps(path: Path = MAPS) -> dict:
    """Detectability summaries written by scripts/export_demo_weights.py."""
    return json.loads(Path(path).read_text())


@dataclass(frozen=True)
class Preset:
    """One button: a scene chosen in advance for the live presentation."""
    label: str
    fault: str
    severity: float
    onset: int
    mission: int
    channel: str
    shown: str
    model_seed: int
    lighting: str | None   # for stuck_sensor: which lighting's overall rate to quote
    caught_by: tuple[str, ...]  # checked by tests/ml/test_demo.py
    blurb: str


# Found by scripts/pick_demo_presets.py in the final weights, model seed 0.
PRESETS = (
    Preset("Brownout in sun", "power_brownout", 0.1, 768, 0, "solar_power_w", "lstm", 0,
           None, ("lstm", "gru"),
           "A small power sag during steady sun: the models notice, the baseline can't."),
    Preset("Stuck in sun", "stuck_sensor", 0.0, 768, 0, "solar_power_w", "gru", 0,
           "sunlit", (),
           "A frozen reading in steady sun is easy to predict, so error falls: no alarm during the fault."),
    Preset("Stuck at eclipse edge", "stuck_sensor", 0.0, 829, 0, "solar_power_w", "gru", 0,
           "crossing", ("lstm", "gru"),
           "Frozen as the light changes: power should move and doesn't, so error rises."),
    Preset("Sensor drift", "sensor_drift", 1.0, 767, 0, "temperature_c", "lstm", 0,
           None, (),
           "A slow drift: the forecast follows it, so no alarm during the fault, only at the snap back."),
)


def preset_rate_note(preset: Preset, maps: dict) -> str:
    """
    How often this happens across all dev missions, so a single chosen
    scene isn't mistaken for the overall result.
    """
    parts = []
    for name in ("persistence", "lstm", "gru"):
        if preset.lighting:
            group = maps[name]["stuck_by_lighting"][preset.lighting]
            parts.append(f"{name} {group['n_detected']}/{group['n']}")
        else:
            cell = next(c for c in maps[name]["cells"]
                        if c["fault"] == preset.fault and c["severity"] == preset.severity)
            parts.append(f"{name} {cell['detected']}/{cell['total']}")
    where = f"fault windows of this kind ({preset.lighting})" if preset.lighting else \
        "missions at this severity"
    return f"Across all dev {where}, faults caught: " + " · ".join(parts) + "."
