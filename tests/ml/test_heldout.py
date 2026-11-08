"""
Tests for the held-out run's wiring and its safeguards. None of these
tests scores real held-out data: OrbitVal test-split requests are
redirected to dev missions, and SMAP/MSL use a small fake dataset.
"""

import json

import pytest

pytest.importorskip("torch")

from orbitval import logging as ov_logging  # noqa: E402
from orbitval.config.hardware_3u_schema import load_hardware_config  # noqa: E402
from orbitval.ml import run_heldout  # noqa: E402
from orbitval.ml import two_sided as module  # noqa: E402
from orbitval.ml.data.telemanom import load_spacecraft, split_channels  # noqa: E402
from orbitval.ml.models.baseline import PersistenceBaseline  # noqa: E402
from orbitval.ml.sim.missions import SPLIT_SEED_BASE  # noqa: E402
from tests.conftest import SATELLITE_YAML  # noqa: E402
from tests.ml.test_telemanom_pipeline import dataset  # noqa: E402, F401  (fixture)

TEST_TO_DEV = SPLIT_SEED_BASE["test"] - SPLIT_SEED_BASE["dev"]


@pytest.fixture(scope="module")
def hw():
    ov_logging.set_log_level("WARNING")
    return load_hardware_config(SATELLITE_YAML)


def test_orbitval_test_split_requests_only_test_missions(hw, monkeypatch, tmp_path, capsys):
    requested_seeds, requested_splits = [], []
    real_make, real_clean = module.make_mission, module.clean_missions

    def make(hardware, seed, *args, **kwargs):
        requested_seeds.append(seed)
        # Score a dev mission in its place: the test must not see held-out data
        return real_make(hardware, seed - TEST_TO_DEV if seed >= SPLIT_SEED_BASE["test"] else seed,
                         *args, **kwargs)

    def clean(hardware, split, n):
        requested_splits.append(split)
        return real_clean(hardware, "dev" if split == "test" else split, n)

    monkeypatch.setattr(module, "make_mission", make)
    monkeypatch.setattr(module, "clean_missions", clean)
    r = module.evaluate_orbitval(PersistenceBaseline(), hw, n_reps=2, n_val=2,
                                 faults=("stuck_sensor",), severities=(1.0,), split="test")
    assert requested_splits == ["val", "test"]          # thresholds from val, twins from test
    assert requested_seeds and all(s >= SPLIT_SEED_BASE["test"] for s in requested_seeds)
    assert {"clean_test", "low_alarms", "rows"} <= r.keys() and "clean_dev" not in r
    assert set(r["low_alarms"]) == {"val", "clean_test", "faulted_test"}

    # The summary reads these keys; feed it this (dev-substituted) result
    (tmp_path / "heldout").mkdir()
    (tmp_path / "frozen.json").write_text(json.dumps({"commit": "abc123", "frozen_at": "now"}))
    (tmp_path / "heldout" / "orbitval_persistence_seed0.json").write_text(json.dumps(
        {"dataset": "orbitval", "model": "persistence", "seed": 0, **r}))
    capsys.readouterr()
    run_heldout.summarize(tmp_path)
    out = capsys.readouterr().out
    assert "OrbitVal held-out orbits, persistence" in out and "OrbitVal test missions" in out


def test_orbitval_rejects_other_splits(hw):
    with pytest.raises(ValueError):
        module.evaluate_orbitval(PersistenceBaseline(), hw, n_reps=1, n_val=1, split="val")


def test_telemanom_held_out_scores_only_held_out_channels(dataset):  # noqa: F811
    channels = load_spacecraft(dataset, "SMAP")
    dev, held_out = split_channels(channels)
    r = module.evaluate_telemanom(PersistenceBaseline(), channels, held_out, label="held_out")
    assert {x["channel"] for x in r["rows"]} <= {c.chan_id for c in held_out}
    assert not {x["channel"] for x in r["rows"]} & {c.chan_id for c in dev}
    assert set(r["low_alarms"]) == {"val", "held_out"}


@pytest.fixture
def clean_git(monkeypatch):
    monkeypatch.setattr(run_heldout, "git_state", lambda: ("abc123", ""))


def _weights(tmp_path):
    w = tmp_path / "w"
    (w / "weights").mkdir(parents=True)
    (w / "weights" / "smap_lstm_seed0.pt").write_bytes(b"not a real checkpoint")
    return w


def test_freeze_records_commit_and_weight_hashes(tmp_path, clean_git):
    record = run_heldout.freeze(tmp_path / "out", _weights(tmp_path))
    saved = json.loads((tmp_path / "out" / "frozen.json").read_text())
    assert saved == record and record["commit"] == "abc123"
    assert list(record["weights_sha256"]) == ["smap_lstm_seed0.pt"]


def test_freeze_refuses_uncommitted_code(tmp_path, monkeypatch):
    monkeypatch.setattr(run_heldout, "git_state", lambda: ("abc123", " M orbitval/ml/x.py"))
    with pytest.raises(SystemExit):
        run_heldout.freeze(tmp_path / "out", _weights(tmp_path))
    assert not (tmp_path / "out" / "frozen.json").exists()


def test_freeze_refuses_a_second_held_out_run(tmp_path, clean_git):
    weights = _weights(tmp_path)
    run_heldout.freeze(tmp_path / "out", weights)
    with pytest.raises(SystemExit, match="run once"):
        run_heldout.freeze(tmp_path / "out", weights)


def _run(tmp_path, dataset_root, model="persistence"):  # noqa: F811
    run_heldout.main(["run", "--dataset", "smap", "--model", model, "--outdir", str(tmp_path / "out"),
                      "--weights", str(tmp_path / "w"), "--data", str(dataset_root)])


def test_run_needs_freeze_and_runs_each_detector_once(tmp_path, dataset, clean_git):  # noqa: F811
    _weights(tmp_path)
    with pytest.raises(SystemExit):
        _run(tmp_path, dataset)                         # not frozen yet
    run_heldout.freeze(tmp_path / "out", tmp_path / "w")
    _run(tmp_path, dataset)
    saved = json.loads((tmp_path / "out" / "heldout" / "smap_persistence_seed0.json").read_text())
    assert saved["split"] == "held_out" and saved["metrics"]["one_sided"]["n_events"] > 0
    with pytest.raises(SystemExit):
        _run(tmp_path, dataset)                         # never twice


def test_run_refuses_changed_code_or_weights(tmp_path, dataset, clean_git, monkeypatch):  # noqa: F811
    _weights(tmp_path)
    run_heldout.freeze(tmp_path / "out", tmp_path / "w")
    (tmp_path / "w" / "weights" / "smap_lstm_seed0.pt").write_bytes(b"different")
    with pytest.raises(SystemExit, match="changed since freeze"):
        _run(tmp_path, dataset, model="lstm")
    monkeypatch.setattr(run_heldout, "git_state", lambda: ("def456", ""))
    with pytest.raises(SystemExit, match="code changed"):
        _run(tmp_path, dataset)


def test_summarize_prints_the_headline(tmp_path, dataset, clean_git, capsys):  # noqa: F811
    _weights(tmp_path)
    run_heldout.freeze(tmp_path / "out", tmp_path / "w")
    _run(tmp_path, dataset)
    capsys.readouterr()
    run_heldout.main(["summarize", "--outdir", str(tmp_path / "out")])
    out = capsys.readouterr().out
    assert "HELD-OUT RUN, commit abc123" in out
    assert "SMAP held-out channels" in out and "one-sided  recall" in out
