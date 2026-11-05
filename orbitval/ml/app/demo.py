"""
orbitval/ml/app/demo.py

Live demo: inject a fault into simulated telemetry and watch detectors
respond. Runs on CPU from saved weights.

    streamlit run orbitval/ml/app/demo.py

Thresholds were set on clean validation data before any of this runs;
the demo never adjusts them.

Never a blank page: Streamlit reruns this script on every control change
and can interrupt a run midway. So each run first re-shows the last good
table and chart, then replaces them. Charts are embedded in the page as
data rather than served as temporary media files, which can disappear
mid-update and leave a broken image.
"""

import base64
import logging
import time
from pathlib import Path

import pandas as pd
import streamlit as st

from orbitval.config.hardware_3u_schema import load_hardware_config
from orbitval.logging import set_log_level
from orbitval.ml.app.core import (
    CHANNEL_LABELS, FAULT_CHANNEL, NO_FAULT, PRESETS, draw, draw_maps, event_in_eclipse,
    figure_png, load_demo_detector, load_manifest, load_maps, preset_rate_note, run_demo,
)
from orbitval.ml.evaluate import EVAL_WARMUP, EVENT_GRACE
from orbitval.ml.models.recurrent import MODELS
from orbitval.ml.sim.faults import FAULTS
from orbitval.ml.sim.missions import FAULT_STEPS
from orbitval.ml.sim.telemetry import CHANNELS

SATELLITE_YAML = Path(__file__).resolve().parents[3] / "satellite.yaml"
DETECTORS = ("persistence", *sorted(MODELS))
MISSION_STEPS = 1440

log = logging.getLogger(__name__)
set_log_level("WARNING")
st.set_page_config(page_title="OrbitVal detector demo", layout="wide")

# Fits the live view on a 1280x720 screen
COMPACT_CSS = """
<style>
.block-container { padding: 1.1rem 2rem 0.5rem 2rem; }
[data-testid="stSidebarHeader"] { padding-bottom: 0; height: 2rem; min-height: 2rem; }
[data-testid="stSidebarUserContent"] { padding-top: 0; }
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: 0.45rem; }
[data-testid="stSidebar"] h3 { padding: 0.3rem 0 0.5rem 0; }
[data-testid="stSidebar"] .stButton button { min-height: 2rem; padding: 0.1rem 0.5rem; }
.stTable table { font-size: 1.05rem; }
.stTable th, .stTable td { padding: 0.15rem 0.6rem !important; }
.demo-chart img { width: 100%; display: block; border-radius: 4px; }
</style>
"""

# Streamlit can't switch theme from a widget, so the projector option
# restyles the page directly.
LIGHT_CSS = """
<style>
body, .stApp { background: #ffffff !important; color: #1a1a1a !important; }
[data-testid="stHeader"] { background: transparent !important; }
[data-testid="stSidebar"], [data-testid="stSidebar"] > div { background: #f1f2f6 !important; }
.stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp p, .stApp label, .stApp span, .stApp li,
.stApp small, .stApp th, .stApp td, [data-testid="stWidgetLabel"], [data-testid="stCaptionContainer"] {
    color: #1a1a1a !important; }
.stTable table, .stTable th, .stTable td { background: #ffffff !important; border-color: #c9ccd3 !important; }
[data-baseweb="input"], [data-baseweb="input"] > div, [data-baseweb="base-input"], .stApp input {
    background: #ffffff !important; color: #1a1a1a !important; border-color: #9aa0ab !important; }
[data-testid="stSelectbox"] [role="group"], [data-testid="stSelectbox"] [role="group"] * {
    background: #ffffff !important; color: #1a1a1a !important; }
[data-testid="stSelectbox"] svg { fill: #1a1a1a !important; }
[data-testid="stNumberInputStepDown"], [data-testid="stNumberInputStepUp"] {
    background: #e6e8ee !important; color: #1a1a1a !important; }
[data-testid="stSelectboxVirtualDropdown"], [data-testid="stSelectboxVirtualDropdown"] * {
    background: #ffffff !important; color: #1a1a1a !important; }
[data-testid="stSelectboxVirtualDropdown"] [role="option"]:hover,
[data-testid="stSelectboxVirtualDropdown"] [role="option"]:hover *,
[data-testid="stSelectboxVirtualDropdown"] [aria-selected="true"],
[data-testid="stSelectboxVirtualDropdown"] [aria-selected="true"] * {
    background: #e0e3ea !important; }
.stButton button { background: #ffffff !important; color: #1a1a1a !important; border-color: #9aa0ab !important; }
.stButton button:disabled { color: #8a8f99 !important; }
.stButton button:hover { border-color: #b3161b !important; color: #b3161b !important; }
[data-testid="stAlert"] > div { background: #e4eefb !important; }
[data-baseweb="tab-list"] { border-bottom-color: #c9ccd3 !important; }
</style>
"""


@st.cache_resource
def hardware():
    return load_hardware_config(SATELLITE_YAML)


@st.cache_resource
def detector_and_threshold(name: str, seed: int):
    return load_demo_detector(name, seed, load_manifest())


@st.cache_resource
def maps():
    return load_maps()


@st.cache_data(show_spinner=False)
def fly(name, model_seed, fault, severity, onset, mission, channel):
    detector, threshold = detector_and_threshold(name, model_seed)
    return run_demo(detector, threshold, hardware(), fault, severity, onset, mission, channel)


@st.cache_data(show_spinner=False)
def chart_html(name, model_seed, fault, severity, onset, mission, channel, zoom, theme):
    run = fly(name, model_seed, fault, severity, onset, mission, channel)
    return image_html(figure_png(draw(run, zoom=zoom, theme=theme)))


@st.cache_data(show_spinner=False)
def maps_html(theme):
    return image_html(figure_png(draw_maps(maps(), theme=theme), dpi=120))


def image_html(png: bytes) -> str:
    encoded = base64.b64encode(png).decode("ascii")
    return f'<div class="demo-chart"><img alt="chart" src="data:image/png;base64,{encoded}"></div>'


def page_theme(light: bool) -> str:
    if light:
        return "light"
    return "dark" if st.context.theme.type == "dark" else "light"


def apply_preset(index: int) -> None:
    preset = PRESETS[index]
    st.session_state.update(
        fault=preset.fault, severity=preset.severity, onset=preset.onset,
        mission=preset.mission, channel=preset.channel, shown=preset.shown,
        model_seed=preset.model_seed, zoom=True, active_preset=index,
    )


def on_fault_change() -> None:
    st.session_state.channel = FAULT_CHANNEL[st.session_state.fault]
    st.session_state.active_preset = None


def on_control_change() -> None:
    st.session_state.active_preset = None


def summary_table(runs_by_name: dict, shown: str) -> pd.DataFrame:
    rows = []
    for name, r in runs_by_name.items():
        rows.append({
            "Detector": f"▶ {name}" if name == shown else name,
            "Caught the fault?": "—" if r.event is None else ("Yes" if r.summary.detected else "No"),
            "Delay (min)": "—" if r.summary.delay_steps is None else str(r.summary.delay_steps),
            f"Alarms ≤{EVENT_GRACE} min after": str(r.summary.recovery),
            "False alarms": str(r.summary.false),
        })
    return pd.DataFrame(rows).set_index("Detector")


# A new session opens on the first preset, brownout in sun
if "fault" not in st.session_state:
    apply_preset(0)

with st.sidebar:
    st.subheader("Presets")
    for i, preset in enumerate(PRESETS):
        st.button(preset.label, key=f"preset_{i}", width="stretch", on_click=apply_preset, args=(i,))
    light = st.toggle("Light theme (for projectors)", key="light")
    st.subheader("Or inject a fault")
    fault = st.selectbox("Fault type", [NO_FAULT, *FAULTS], key="fault", on_change=on_fault_change)
    no_fault = fault == NO_FAULT
    severity = st.slider("Severity", 0.0, 1.0, step=0.05, key="severity", on_change=on_control_change,
                         disabled=no_fault or fault == "stuck_sensor")
    if fault == "stuck_sensor":
        st.caption("A frozen sensor has no severity, so this slider has no effect.")
    onset = st.slider("Onset (step, 1 step = 1 minute)", EVAL_WARMUP, MISSION_STEPS - FAULT_STEPS,
                      key="onset", on_change=on_control_change, disabled=no_fault)
    mission = st.number_input("Mission", 0, 19, key="mission", on_change=on_control_change,
                              help="Dev missions: each has its own orbit and noise.")
    st.subheader("Show")
    shown = st.selectbox("Detector", DETECTORS, key="shown", on_change=on_control_change)
    model_seed = st.selectbox("Model seed", (0, 1, 2), key="model_seed", on_change=on_control_change,
                              help="Each model was trained with 3 seeds.")
    channel = st.selectbox("Channel", CHANNELS, key="channel", on_change=on_control_change,
                           format_func=CHANNEL_LABELS.get)
    zoom = st.toggle("Zoom to the fault", key="zoom", disabled=no_fault)

theme = page_theme(light)
st.markdown(COMPACT_CSS + (LIGHT_CSS if light else ""), unsafe_allow_html=True)

st.markdown("#### Can a detector catch this fault?")
live_tab, maps_tab = st.tabs(["Live demo", "Detectability maps"])

with maps_tab:
    st.markdown(maps_html(theme), unsafe_allow_html=True)
    st.caption(
        f"Fraction of injected faults caught, pooled over seeds, with {maps()['gru']['reps']} "
        "missions per cell. Dev data. `stuck_sensor` has no severity, so its row is flat by design."
    )

with live_tab:
    play = st.columns([1, 4])[0].button("▶ Play", key="play", type="primary", width="stretch",
                                        disabled=no_fault)

    note_slot = st.empty()
    table_slot = st.empty()
    chart_slot = st.empty()

    # Show the last good view at once, so a rerun never starts from nothing
    if "last_table" in st.session_state:
        table_slot.table(st.session_state.last_table)
        chart_slot.markdown(st.session_state.last_chart, unsafe_allow_html=True)
    else:
        chart_slot.info("Loading the detectors…")

    # Values that don't affect a run are fixed, so it hits the cache
    params = (fault, 0.0 if no_fault or fault == "stuck_sensor" else float(severity),
              800 if no_fault else int(onset), int(mission), channel)
    try:
        runs_by_name = {name: fly(name, model_seed, *params) for name in DETECTORS}
        table = summary_table(runs_by_name, shown)
        chart = chart_html(shown, model_seed, *params, zoom, theme)
    except Exception:
        # Keep showing the last good view rather than an error page.
        # Streamlit's own rerun signal isn't an Exception, so it still works.
        log.exception("demo run failed for %s", params)
        st.warning("That combination could not be computed. Showing the previous result.")
    else:
        run = runs_by_name[shown]
        table_slot.table(table)
        st.session_state.last_table = table

        active = st.session_state.active_preset
        if active is not None:
            note_slot.caption(f"{PRESETS[active].blurb} {preset_rate_note(PRESETS[active], maps())}")
        elif run.event is not None and event_in_eclipse(run.illumination, run.event[0]):
            note_slot.caption("This fault window overlaps shadow. Eclipses themselves are normal "
                              "behaviour. Overall rates are in the Detectability maps tab.")
        else:
            note_slot.caption("One mission. Overall rates are in the Detectability maps tab.")

        if play and run.event is not None:
            first = max(run.event[0] - 60, EVAL_WARMUP)
            last = min(run.event[1] + 60, MISSION_STEPS - 1)
            for step in range(first, last, 4):
                frame = figure_png(draw(run, upto=step, zoom=zoom, theme=theme), dpi=80)
                chart_slot.markdown(image_html(frame), unsafe_allow_html=True)
                time.sleep(0.02)
        chart_slot.markdown(chart, unsafe_allow_html=True)
        st.session_state.last_chart = chart

# Last, so it never delays the first view: prepare every preset, which
# makes the buttons instant during the talk.
try:
    for preset in PRESETS:
        scene = (preset.fault, preset.severity, preset.onset, preset.mission, preset.channel)
        for name in DETECTORS:
            fly(name, preset.model_seed, *scene)
        chart_html(preset.shown, preset.model_seed, *scene, True, theme)
except Exception:
    log.exception("could not prepare the presets")
