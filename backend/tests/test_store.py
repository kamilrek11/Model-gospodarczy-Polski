import pandas as pd
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
