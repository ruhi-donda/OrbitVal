"""
Tests for the telemanom loader, the dev/test channel split, and the
end-to-end evaluate() path — on a small fake dataset in the real
on-disk layout, so the suite never needs the download.
"""

import json
from dataclasses import replace

import numpy as np
import pytest

from orbitval.ml.data.telemanom import load_label_rows, load_spacecraft, split_channels
from orbitval.ml.evaluate import evaluate, score_test
from orbitval.ml.models.baseline import PersistenceBaseline
from orbitval.ml import run_telemanom

T_TRAIN, T_TEST = 1000, 1200


def _write_dataset(root, rows, rng):
    """rows: (chan_id, spacecraft, events, num_values, n_cols)"""
    (root / "train").mkdir(parents=True)
    (root / "test").mkdir()
    lines = ["chan_id,spacecraft,anomaly_sequences,class,num_values"]
    written = set()
    for chan, sc, events, n, cols in rows:
        lines.append(f'{chan},{sc},"{json.dumps(events)}",[point],{n}')
        if chan in written:
            continue
        written.add(chan)
        train = np.c_[np.sin(np.arange(T_TRAIN) / 10) + rng.normal(0, 0.01, T_TRAIN),
                      np.zeros((T_TRAIN, cols - 1))]
        test = np.c_[np.sin(np.arange(T_TEST) / 10) + rng.normal(0, 0.01, T_TEST),
                     np.zeros((T_TEST, cols - 1))]
        for start, end in events:
            test[start:end + 1, 0] += 2.0         # obvious level shift
        np.save(root / "train" / f"{chan}.npy", train)
        np.save(root / "test" / f"{chan}.npy", test)
    (root / "labeled_anomalies.csv").write_text("\n".join(lines) + "\n")


@pytest.fixture
def dataset(tmp_path):
    rng = np.random.default_rng(0)
    rows = [
        ("A-1", "SMAP", [[900, 950], [500, 520]], T_TEST, 25),   # unsorted events
        ("A-2", "SMAP", [[700, 760]], T_TEST, 25),
        ("A-2", "SMAP", [[10, 20]], 999, 25),                    # duplicate, wrong length (like P-2)
        ("B-1", "MSL", [[600, 640]], T_TEST, 55),
    ]
    _write_dataset(tmp_path, rows, rng)
    return tmp_path


def test_label_rows_parsed_and_sorted(dataset):
    rows = load_label_rows(dataset / "labeled_anomalies.csv")
    assert rows[0]["events"] == [(500, 520), (900, 950)]
    assert {r["spacecraft"] for r in rows} == {"SMAP", "MSL"}


def test_load_spacecraft_shapes_split_and_duplicate(dataset):
    smap = load_spacecraft(dataset, "SMAP", val_frac=0.2)
    assert [c.chan_id for c in smap] == ["A-1", "A-2"]
    c = smap[0]
    assert (c.train.shape, c.val.shape, c.test.shape) == ((800,), (200,), (T_TEST,))
    # univariate: column 0 only, and val is the chronological tail of train
    full = np.load(dataset / "train" / "A-1.npy")[:, 0]
    np.testing.assert_array_equal(np.r_[c.train, c.val], full)
    # duplicate A-2 row resolved by matching num_values
    assert smap[1].test_events == [(700, 760)]


def test_onset_labels_match_events(dataset):
    c = load_spacecraft(dataset, "SMAP")[0]
    labels = c.test_labels()
    assert labels.sum() == (520 - 500 + 1) + (950 - 900 + 1)
    assert not labels[499] and labels[500] and labels[520] and not labels[521]


def test_loader_errors(dataset, tmp_path):
    with pytest.raises(ValueError):
        load_spacecraft(dataset, "CASSINI")
    with pytest.raises(ValueError):
        load_spacecraft(dataset, "SMAP", val_frac=1.5)

    bad = tmp_path / "bad"
    _write_dataset(bad, [("C-1", "SMAP", [[5, 2000]], T_TEST, 2)], np.random.default_rng(1))
    with pytest.raises(ValueError, match="outside"):
        load_spacecraft(bad, "SMAP")

    nomatch = tmp_path / "nomatch"
    _write_dataset(nomatch, [("C-1", "SMAP", [[5, 6]], 7, 2)], np.random.default_rng(1))
    with pytest.raises(ValueError, match="no label row"):
        load_spacecraft(nomatch, "SMAP")


def test_disagreeing_duplicate_rows_skip_channel(tmp_path):
    # Like the real P-2: same length, different windows -> left out
    _write_dataset(tmp_path, [
        ("P-2", "SMAP", [[500, 600]], T_TEST, 2),
        ("P-2", "SMAP", [[550, 650]], T_TEST, 2),
        ("P-3", "SMAP", [[500, 600]], T_TEST, 2),
        ("P-3", "SMAP", [[500, 600]], T_TEST, 2),   # identical duplicate: fine
    ], np.random.default_rng(2))
    assert [c.chan_id for c in load_spacecraft(tmp_path, "SMAP")] == ["P-3"]


def test_split_channels_deterministic_and_disjoint(dataset):
    base = load_spacecraft(dataset, "SMAP")[0]
    chans = [replace(base, chan_id=f"X-{i}") for i in range(10)]
    dev1, test1 = split_channels(chans, dev_frac=0.3, seed=0)
    dev2, _ = split_channels(chans, dev_frac=0.3, seed=0)
    ids = lambda cs: [c.chan_id for c in cs]
    assert len(dev1) == 3 and len(test1) == 7
    assert ids(dev1) == ids(dev2)
    assert not set(ids(dev1)) & set(ids(test1))
    assert set(ids(dev1)) | set(ids(test1)) == set(ids(chans))


def test_evaluate_end_to_end_detects_level_shifts(dataset):
    chans = load_spacecraft(dataset, "SMAP")
    r = evaluate(PersistenceBaseline(), chans, chans, budget_per_10k=2.0)
    assert r.calibration.false_alarms_per_10k <= 2.0
    assert r.metrics.n_events == 3 and r.metrics.event_recall == 1.0
    assert r.metrics.median_delay <= 1        # shift shows up in the next error


def test_score_test_blanks_warmup_and_rejects_late_nans(dataset):
    chans = load_spacecraft(dataset, "MSL")
    s = score_test(PersistenceBaseline(), chans, warmup=320)[0]
    assert np.all(np.isnan(s[:320])) and np.all(np.isfinite(s[320:]))
    with pytest.raises(ValueError, match="NaN"):
        score_test(PersistenceBaseline(), chans, warmup=10)


def test_run_telemanom_cli(dataset, tmp_path, capsys):
    out = tmp_path / "res.json"
    results = run_telemanom.main(["--data", str(dataset), "--spacecraft", "SMAP",
                                  "--out", str(out)])
    assert "SMAP" in results and json.loads(out.read_text())["detector"] == "persistence"
    assert "event recall" in capsys.readouterr().out
