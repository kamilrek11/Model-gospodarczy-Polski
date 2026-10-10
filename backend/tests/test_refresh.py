import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.api.refresh import RefreshJob, get_clients, get_job, get_store, refresh
from app.data.base import SourceError
from app.main import app
from app.model.macro import MACRO_VARS, MacroModel
from app.store import Store
from tests.synthetic import synthetic_levels

# Everything below is synthetic and lives only in pytest's tmp_path stores.


class StubClient:
    def __init__(self, name: str, series: dict[str, pd.DataFrame]):
        self.name = name
        self.series = series

    def fetch(self) -> dict[str, pd.DataFrame]:
        return self.series


class FailingClient:
    def __init__(self, name: str, message: str = "HTTP 503 for https://stub.test"):
        self.name = name
        self.message = message

    def fetch(self) -> dict[str, pd.DataFrame]:
        raise SourceError(self.name, self.message)


def frames(levels: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {c: levels[[c]].rename(columns={c: "value"}) for c in levels.columns}


def good_clients(n_years: int = 20, seed: int = 3):
    macro = frames(synthetic_levels(n_years, seed=seed))
    idx = pd.Index(range(2015, 2025), dtype="int64", name="year")
    budget = {s: pd.DataFrame({"value": [float(i) for i in range(10)]}, index=idx) for s in ("rev_pit", "rev_cit", "rev_vat")}
    return [StubClient("gus_bdl", macro), StubClient("execution", budget)]


def snapshot(store: Store) -> dict:
    return {
        "series": {s: store.load_series(s) for s in (*MACRO_VARS, "rev_pit", "rev_cit", "rev_vat")},
        "model": store.load_model(),
        "updated_at": store.get_meta("updated_at"),
    }


def assert_same(a: dict, b: dict) -> None:
    assert a["model"] == b["model"] and a["updated_at"] == b["updated_at"]
    for s in a["series"]:
        pd.testing.assert_frame_equal(a["series"][s], b["series"][s])


def test_refresh_success_persists_series_model_and_meta(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    res = refresh(store, good_clients())
    assert res.ok and res.errors == {}
    assert res.updated_at == store.get_meta("updated_at")
    assert pd.Timestamp(res.updated_at).tzinfo is not None
    model = MacroModel.from_dict(store.load_model())
    assert model.n_obs == 20 and model.variables == list(MACRO_VARS)
    assert len(store.load_series("pkb_real")) == 20
    assert len(store.load_series("rev_vat")) == 10


def test_refresh_keeps_previous_state_when_a_source_fails(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    assert refresh(store, good_clients(seed=3)).ok
    before = snapshot(store)

    gus_ok = good_clients(seed=99)[0]  # different data that must NOT be written
    res = refresh(store, [gus_ok, FailingClient("execution")])

    assert res.ok is False
    assert res.errors == {"execution": "HTTP 503 for https://stub.test"}
    assert res.updated_at == before["updated_at"]
    assert_same(snapshot(store), before)


def test_refresh_reports_insufficient_data_as_model_error(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    assert refresh(store, good_clients(seed=3)).ok
    before = snapshot(store)

    res = refresh(store, good_clients(n_years=10))

    assert res.ok is False
    assert set(res.errors) == {"model"}
    assert "10" in res.errors["model"] and "15" in res.errors["model"]
    assert_same(snapshot(store), before)


def test_refresh_reports_missing_macro_series_as_model_error(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    clients = good_clients()
    del clients[0].series["cpi"]
    res = refresh(store, clients)
    assert res.ok is False and "cpi" in res.errors["model"]
    assert store.load_model() is None and store.get_meta("updated_at") is None


@pytest.fixture
def api(tmp_path):
    store_path = str(tmp_path / "api.db")
    state = {"clients": good_clients()}
    app.dependency_overrides[get_store] = lambda: Store(store_path)
    app.dependency_overrides[get_clients] = lambda: state["clients"]
    job = RefreshJob()
    app.dependency_overrides[get_job] = lambda: job
    yield TestClient(app), state, store_path
    app.dependency_overrides.clear()


def test_refresh_status_initially_idle(api):
    client, _, _ = api
    assert client.get("/refresh/status").json() == {"state": "idle", "errors": {}, "updated_at": None}


def test_refresh_endpoint_runs_job_and_reports_done(api):
    client, _, store_path = api
    r = client.post("/refresh")
    assert r.status_code == 202
    status = client.get("/refresh/status").json()
    assert status["state"] == "done" and status["errors"] == {}
    assert status["updated_at"] == Store(store_path).get_meta("updated_at") is not None


def test_refresh_status_reports_failed_source_name(api):
    client, state, store_path = api
    assert client.post("/refresh").status_code == 202
    good_at = client.get("/refresh/status").json()["updated_at"]

    state["clients"] = [good_clients()[0], FailingClient("execution", "HTTP 500 for https://mf.stub")]
    assert client.post("/refresh").status_code == 202
    status = client.get("/refresh/status").json()

    assert status["state"] == "failed"
    assert status["errors"] == {"execution": "HTTP 500 for https://mf.stub"}
    assert status["updated_at"] == good_at  # last good state still advertised


def test_refresh_rejects_concurrent_run(api):
    client, _, _ = api
    job = app.dependency_overrides[get_job]()
    job.state = "running"
    assert client.post("/refresh").status_code == 409


def test_default_clients_fail_on_unmapped_series(tmp_path):
    """Default factory (real clients, unverified ids) must fail cleanly, without touching the network."""
    store_path = str(tmp_path / "default.db")
    app.dependency_overrides[get_store] = lambda: Store(store_path)
    job = RefreshJob()
    app.dependency_overrides[get_job] = lambda: job
    try:
        client = TestClient(app)
        assert client.post("/refresh").status_code == 202
        status = client.get("/refresh/status").json()
    finally:
        app.dependency_overrides.clear()
    assert status["state"] == "failed"
    assert "not mapped" in status["errors"]["gus_bdl"]
    assert "not mapped" in status["errors"]["execution"]
    assert Store(store_path).load_model() is None


@pytest.mark.parametrize("fail_at", ["second_series", "meta"])
def test_refresh_write_failure_leaves_store_unchanged(tmp_path, monkeypatch, fail_at):
    db = tmp_path / "t.db"
    store = Store(str(db))
    assert refresh(store, good_clients(seed=3)).ok
    before = snapshot(store)
    raw_before = db.read_bytes()

    calls = {"n": 0}
    orig_series, orig_meta = Store._write_series, Store._write_meta

    def flaky_series(self, conn, name, source, df):
        calls["n"] += 1
        if fail_at == "second_series" and calls["n"] == 2:
            raise OSError("disk full (injected)")
        return orig_series(self, conn, name, source, df)

    def flaky_meta(self, conn, key, value):
        if fail_at == "meta":
            raise OSError("disk full (injected)")
        return orig_meta(self, conn, key, value)

    monkeypatch.setattr(Store, "_write_series", flaky_series)
    monkeypatch.setattr(Store, "_write_meta", flaky_meta)
    job = RefreshJob()
    assert job.try_start()
    job.run(store, good_clients(seed=99))

    assert job.state == "failed" and "disk full" in job.errors["refresh"]
    assert_same(snapshot(store), before)
    assert db.read_bytes() == raw_before
