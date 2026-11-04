"""
Tests for the demo: alarm classification, core logic, and the Streamlit
page itself, run headless. Skipped without the optional [ml] extra.
"""

from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("torch")
pytest.importorskip("streamlit")
pytest.importorskip("matplotlib")

from matplotlib.colors import to_hex  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

from orbitval import logging as ov_logging  # noqa: E402
from orbitval.config.hardware_3u_schema import load_hardware_config  # noqa: E402
from orbitval.ml.app.core import (  # noqa: E402
    FAULT_CHANNEL, NO_FAULT, PALETTES, classify_alarms, draw, draw_maps, event_in_eclipse,
    PRESETS, figure_png, load_demo_detector, load_manifest, load_maps, preset_rate_note, run_demo,
)
from orbitval.ml.evaluate import EVAL_WARMUP, EVENT_GRACE  # noqa: E402
from orbitval.ml.models.recurrent import MODELS  # noqa: E402
from orbitval.ml.sim.faults import FAULTS  # noqa: E402
from orbitval.ml.sim.missions import FAULT_STEPS  # noqa: E402
from orbitval.ml.sim.telemetry import CHANNELS  # noqa: E402
from tests.conftest import SATELLITE_YAML  # noqa: E402

DEMO_PAGE = str(Path(__file__).parents[2] / "orbitval" / "ml" / "app" / "demo.py")


@pytest.fixture(scope="module")
def hw():
    ov_logging.set_log_level("WARNING")
    return load_hardware_config(SATELLITE_YAML)


def _alarms(n, on):
    a = np.zeros(n, dtype=bool)
    a[list(on)] = True
    return a


def test_classify_alarms_sorts_runs_like_the_metrics():
    # false at 10; in the fault from 105; recovery 20 steps after it ends;
    # false again just past the grace period
    late = 129 + EVENT_GRACE + 1
    s = classify_alarms(_alarms(400, [10, 105, 106, 150, late]), (100, 129))
    assert (s.detected, s.delay_steps) == (True, 5)
    assert (s.in_fault, s.recovery, s.false) == (1, 1, 2)


def test_classify_alarms_recovery_alarm_is_not_a_detection():
    s = classify_alarms(_alarms(400, [150]), (100, 129))
    assert (s.detected, s.delay_steps, s.recovery) == (False, None, 1)


def test_classify_alarms_without_a_fault():
    s = classify_alarms(_alarms(100, [5, 50]), None)
    assert (s.detected, s.delay_steps, s.in_fault, s.false) == (False, None, 0, 2)


def test_every_catalogue_fault_has_a_default_channel():
    assert set(FAULT_CHANNEL) == {NO_FAULT, *FAULTS}
    assert set(FAULT_CHANNEL.values()) <= set(CHANNELS)


def test_manifest_covers_every_detector_and_seed():
    manifest = load_manifest()
    assert set(manifest) == {"persistence", *MODELS}
    for name in MODELS:
        assert set(manifest[name]) == {"0", "1", "2"}
        detector, threshold = load_demo_detector(name, 0, manifest)
        assert detector.name == name and threshold > 0


@pytest.mark.parametrize("name", ["persistence", "gru"])
def test_run_demo_places_the_fault_at_the_chosen_onset(hw, name):
    detector, threshold = load_demo_detector(name, 0, load_manifest())
    run = run_demo(detector, threshold, hw, "power_brownout", 1.0, 800, 0, "solar_power_w")
    assert run.event == (800, 800 + FAULT_STEPS - 1)
    assert run.summary.detected                 # a full brownout is a large step
    assert run.data.shape == run.clean.shape == (1440, len(CHANNELS))
    assert not run.alarms[:EVAL_WARMUP].any()   # the warm-up applies here too
    changed = np.any(run.data != run.clean, axis=1)
    assert changed[800] and not changed[:800].any() and not changed[830:].any()


def test_run_demo_with_no_fault(hw):
    detector, threshold = load_demo_detector("persistence", 0, load_manifest())
    run = run_demo(detector, threshold, hw, NO_FAULT, 0.0, 800, 1, "temperature_c")
    assert run.event is None and not run.summary.detected
    np.testing.assert_array_equal(run.data, run.clean)


def test_event_in_eclipse():
    illum = np.ones(100)
    illum[50:60] = 0.0
    assert event_in_eclipse(illum, 40) and not event_in_eclipse(illum, 60)


def test_draw_full_partial_and_zoom(hw):
    detector, threshold = load_demo_detector("persistence", 0, load_manifest())
    run = run_demo(detector, threshold, hw, "sensor_drift", 1.0, 800, 0, "temperature_c")
    assert len(draw(run).axes) == 2
    partial = draw(run, upto=810).axes[0].lines[0].get_xdata()
    assert len(partial) == 811
    fig = draw(run, zoom=True)
    left, right = fig.axes[0].get_xlim()
    assert left == pytest.approx((800 - 150) / 60) and right == pytest.approx((829 + 150) / 60)
    assert fig.axes[1].get_ylim()[1] == pytest.approx(3 * threshold)
    assert "higher = more unusual" in fig.axes[1].get_ylabel().replace("\n", " ")


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_draw_uses_theme_colours_and_large_fonts(hw, theme):
    detector, threshold = load_demo_detector("persistence", 0, load_manifest())
    run = run_demo(detector, threshold, hw, "power_brownout", 1.0, 800, 0, "solar_power_w")
    fig = draw(run, theme=theme)
    assert to_hex(fig.get_facecolor()) == PALETTES[theme]["bg"]
    assert fig.axes[0].yaxis.label.get_size() >= 14
    assert figure_png(fig)[:4] == b"\x89PNG"


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_draw_maps_has_one_panel_per_detector(theme):
    fig = draw_maps(load_maps(), theme=theme)
    panels = [ax for ax in fig.axes if ax.get_title()]
    assert [ax.get_title().split()[0] for ax in panels] == ["persistence", "lstm", "gru"]


def test_maps_summary_matches_its_counts():
    for summary in load_maps().values():
        for cell in summary["cells"]:
            assert cell["recall"] == cell["detected"] / cell["total"]
            assert cell["total"] == summary["seeds"] * summary["reps"]


def _app():
    return AppTest.from_file(DEMO_PAGE, default_timeout=120).run()


def test_page_renders_table_chart_and_maps():
    app = _app()
    assert not app.exception
    assert len(app.table[0].value) == 3                 # persistence, gru, lstm
    embedded = [m.value for m in app.markdown if "data:image/png" in m.value]
    assert len(embedded) == 2                           # live chart and maps tab
    assert [t.label for t in app.tabs] == ["Live demo", "Detectability maps"]


def test_controls_change_the_result():
    app = _app()
    app.selectbox(key="fault").set_value("power_brownout")
    app.slider(key="severity").set_value(1.0)
    app.run()
    assert not app.exception
    assert app.table[0].value["Caught the fault?"].eq("Yes").all()

    app.selectbox(key="fault").set_value(NO_FAULT)
    app.run()
    assert not app.exception
    assert app.table[0].value["Caught the fault?"].eq("—").all()
    assert app.button(key="play").disabled


def test_changing_fault_moves_the_channel_to_the_affected_one():
    app = _app()
    app.selectbox(key="fault").set_value("sensor_drift")
    app.run()
    assert app.selectbox(key="channel").value == "temperature_c"
    # ...but a channel picked by hand stays
    app.selectbox(key="channel").set_value("battery_charge_wh")
    app.run()
    assert app.selectbox(key="channel").value == "battery_charge_wh"


def test_every_fault_and_theme_renders_without_error():
    app = _app()
    for light in (False, True):
        app.toggle(key="light").set_value(light)
        for fault in (NO_FAULT, *FAULTS):
            app.selectbox(key="fault").set_value(fault)
            app.run()
            assert not app.exception, fault
            assert any("data:image/png" in m.value for m in app.markdown)


def test_a_failed_run_keeps_the_last_view(monkeypatch):
    app = _app()
    good = [m.value for m in app.markdown if "data:image/png" in m.value]

    # Break the mission generator behind the page, with an uncached input
    import orbitval.ml.app.core as core
    def boom(*args, **kwargs):
        raise RuntimeError("simulated failure")
    monkeypatch.setattr(core, "make_mission", boom)
    app.number_input(key="mission").set_value(19)
    app.slider(key="onset").set_value(901)
    app.run()
    assert not app.exception
    assert app.warning and "previous result" in app.warning[0].value
    assert [m.value for m in app.markdown if "data:image/png" in m.value] == good


@pytest.mark.parametrize("preset", PRESETS, ids=lambda p: p.label)
def test_preset_shows_what_it_claims(hw, preset):
    manifest = load_manifest()
    caught = set()
    for name in MODELS.keys() | {"persistence"}:
        detector, threshold = load_demo_detector(name, preset.model_seed, manifest)
        run = run_demo(detector, threshold, hw, preset.fault, preset.severity,
                       preset.onset, preset.mission, preset.channel)
        assert run.summary.false == 0, name
        if run.summary.detected:
            caught.add(name)
    assert caught == set(preset.caught_by)
    in_window = run.illumination[preset.onset:preset.onset + FAULT_STEPS]
    if preset.lighting == "crossing":
        assert in_window.min() < 1.0 and in_window.max() == 1.0
    else:
        assert np.all(in_window == 1.0)


@pytest.mark.parametrize("preset", PRESETS, ids=lambda p: p.label)
def test_preset_note_quotes_the_overall_rate(preset):
    note = preset_rate_note(preset, load_maps())
    for name in ("persistence", "lstm", "gru"):
        assert name in note


def test_preset_buttons_set_the_controls_and_note():
    app = _app()
    for i, preset in enumerate(PRESETS):
        app.button(key=f"preset_{i}").click().run()
        assert not app.exception
        assert app.selectbox(key="fault").value == preset.fault
        assert app.number_input(key="mission").value == preset.mission
        assert app.slider(key="onset").value == preset.onset
        assert app.selectbox(key="channel").value == preset.channel
        table = app.table[0].value["Caught the fault?"]
        for name in ("persistence", "lstm", "gru"):
            row = f"▶ {name}" if name == preset.shown else name
            assert table[row] == ("Yes" if name in preset.caught_by else "No")
        assert any(preset.blurb in c.value for c in app.caption)
