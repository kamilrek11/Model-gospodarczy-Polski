import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.store import Store


def test_save_and_load_series_roundtrip(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    df = pd.DataFrame({"value": [100.5, 110.0, 120.25]}, index=pd.Index([2021, 2022, 2023], name="year"))
    store.save_series("pkb", "test", df)
    out = store.load_series("pkb")
    pd.testing.assert_frame_equal(out, df, check_index_type=True)
    assert out.index.dtype.kind == "i"


def test_load_model_empty_returns_none(tmp_path):
    assert Store(str(tmp_path / "t.db")).load_model() is None


def test_model_and_meta_roundtrip(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    store.save_model({"a": 1, "b": [1, 2]})
    assert store.load_model() == {"a": 1, "b": [1, 2]}
    store.set_meta("k", "v")
    store.set_meta("k", "v2")
    assert store.get_meta("k") == "v2"
    assert store.get_meta("missing") is None


def test_health():
    from app.main import app
    r = TestClient(app).get("/health")
    assert r.json() == {"status": "ok"}


def _snap(store):
    return (store.load_series("a"), store.load_series("b"), store.load_model(), store.get_meta("updated_at"))


def test_save_snapshot_writes_everything(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    df = pd.DataFrame({"value": [1.0, 2.0]}, index=pd.Index([2020, 2021], name="year"))
    store.save_snapshot({"a": ("src1", df), "b": ("src2", df * 2)}, {"m": 1}, {"updated_at": "T1"})
    pd.testing.assert_frame_equal(store.load_series("b"), df * 2)
    assert store.load_model() == {"m": 1} and store.get_meta("updated_at") == "T1"


def test_save_snapshot_is_atomic_on_mid_write_failure(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    df = pd.DataFrame({"value": [1.0, 2.0]}, index=pd.Index([2020, 2021], name="year"))
    store.save_snapshot({"a": ("s", df), "b": ("s", df)}, {"m": 1}, {"updated_at": "T1"})
    before = _snap(store)
    bad = pd.DataFrame({"value": ["oops"]}, index=pd.Index([2022], name="year"))  # fails on 2nd series
    with pytest.raises(ValueError):
        store.save_snapshot({"a": ("s", df * 10), "b": ("s", bad)}, {"m": 2}, {"updated_at": "T2"})
    after = _snap(store)
    pd.testing.assert_frame_equal(after[0], before[0])
    pd.testing.assert_frame_equal(after[1], before[1])
    assert after[2:] == before[2:]
