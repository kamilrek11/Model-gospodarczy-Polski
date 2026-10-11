import sqlite3
from contextlib import closing

import httpx
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.api import refresh as refresh_mod
from app.api.refresh import ClientBundle, RefreshJob, get_clients, get_job, get_store, refresh
from app.data.base import SourceError
from app.data.eurostat import EurostatClient
from app.data.gus_bdl import GusBdlClient
from app.data.mf_execution import MfBudgetExecutionClient
from app.main import app
from app.model.macro import MACRO_VARS, MacroModel
from app.store import Store
from tests.real_dataset import real_clients, real_stub_clients

# Data: the REAL recorded public responses (tests/fixtures/real) run through the real client classes
# (tests/real_dataset.py); everything lives only in pytest's tmp_path stores. No network.

ALL_SERIES = (*MACRO_VARS, "gross_surplus", "gdp_nominal", "rev_pit", "rev_cit", "rev_vat")


class FailingClient:
    def __init__(self, name: str, message: str = "HTTP 503 for https://stub.test"):
        self.name = name
        self.message = message

    def fetch(self) -> dict[str, pd.DataFrame]:
        raise SourceError(self.name, self.message)


def good_clients(scale: float = 1.0):
    """Real recorded series; scale != 1 gives different (still plausible) data for overwrite checks."""
    return real_stub_clients(None if scale == 1.0 else (lambda s, df: df * scale))


def snapshot(store: Store) -> dict:
    return {
        "series": {s: store.load_series(s) for s in ALL_SERIES},
        "model": store.load_model(),
        "updated_at": store.get_meta("updated_at"),
        "synthetic": store.get_meta("synthetic"),
    }


def assert_same(a: dict, b: dict) -> None:
    assert a["model"] == b["model"] and a["updated_at"] == b["updated_at"] and a["synthetic"] == b["synthetic"]
    for s in a["series"]:
        pd.testing.assert_frame_equal(a["series"][s], b["series"][s])


def sources(path: str) -> dict[str, set[str]]:
    with closing(sqlite3.connect(path)) as c:
        rows = c.execute("SELECT name, source FROM series").fetchall()
    out: dict[str, set[str]] = {}
    for name, source in rows:
        out.setdefault(name, set()).add(source)
    return out


def test_refresh_success_persists_series_model_and_meta(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    res = refresh(store, good_clients())
    assert res.ok and res.errors == {}
    assert res.updated_at == store.get_meta("updated_at")
    assert pd.Timestamp(res.updated_at).tzinfo is not None
    model = MacroModel.from_dict(store.load_model())
    assert model.variables == list(MACRO_VARS)
    assert model.n_obs == 20 and model.last_year == 2024  # employment 2005-2024 limits the common sample
    assert store.load_series("rev_vat").loc[2024, "value"] == pytest.approx(287.68336891)
    assert store.load_series("gross_surplus").index.max() == 2025


def test_refresh_success_writes_synthetic_zero_and_all_series_with_sources(tmp_path):
    path = str(tmp_path / "t.db")
    store = Store(path)
    store.set_meta("synthetic", "1")  # e.g. a store seeded earlier
    https: list[httpx.Client] = []
    try:
        res = refresh(store, real_clients(https))  # the real client classes on recorded responses
    finally:
        for h in https:
            h.close()
    assert res.ok, res.errors
    assert store.get_meta("synthetic") == "0" and store.is_synthetic() is False
    assert sources(path) == {
        "pkb_real": {"gus_bdl"},
        "employment": {"gus_bdl"},
        "wage_nominal": {"gus_bdl"},
        "cpi": {"gus_bdl"},
        "gdp_nominal": {"gus_bdl"},
        "gross_surplus": {"gus_bdl+eurostat"},
        "consumption_nominal": {"eurostat"},
        "rev_vat": {"mf_execution"},
        "rev_cit": {"mf_execution"},
        "rev_pit": {"mf_execution"},
    }
    assert store.load_series("rev_pit").loc[2025, "value"] == pytest.approx(28.75211501)  # stored as published


def test_refresh_with_failed_gate_keeps_previous_state_and_names_violations(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    assert refresh(store, good_clients()).ok
    before = snapshot(store)

    def unit_errors(name, df):  # consumption in mln instead of mld, VAT in tys. instead of mld
        return df * 1000.0 if name in ("consumption_nominal", "rev_vat") else df * 1.01

    res = refresh(store, real_stub_clients(unit_errors))

    assert res.ok is False
    assert set(res.errors) == {"dataset"}
    msg = res.errors["dataset"]
    assert "konsumpcj" in msg and "rev_vat" in msg  # all violations listed
    assert res.updated_at == before["updated_at"]
    assert_same(snapshot(store), before)


def test_refresh_keeps_previous_state_when_a_source_fails(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    assert refresh(store, good_clients()).ok
    before = snapshot(store)

    gus_ok, eu_ok, _ = good_clients(scale=1.02)  # different data that must NOT be written
    res = refresh(store, [gus_ok, eu_ok, FailingClient("mf_execution")])

    assert res.ok is False
    assert res.errors == {"mf_execution": "HTTP 503 for https://stub.test"}
    assert res.updated_at == before["updated_at"]
    assert_same(snapshot(store), before)


def test_refresh_reports_too_short_sample_as_dataset_error(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    assert refresh(store, good_clients()).ok
    before = snapshot(store)

    res = refresh(store, real_stub_clients(lambda s, df: df.loc[2015:] if s == "employment" else df))

    assert res.ok is False
    assert set(res.errors) == {"dataset"}
    assert "10" in res.errors["dataset"] and "15" in res.errors["dataset"]
    assert_same(snapshot(store), before)


def test_refresh_reports_estimation_failure_as_model_error(tmp_path, monkeypatch):
    store = Store(str(tmp_path / "t.db"))

    def broken(*a, **k):
        raise np.linalg.LinAlgError("singular matrix")

    monkeypatch.setattr(refresh_mod, "fit_macro", broken)
    res = refresh(store, good_clients())
    assert res.ok is False and "singular" in res.errors["model"]
    assert store.load_model() is None and store.get_meta("updated_at") is None


def test_refresh_reports_missing_macro_series_as_dataset_error(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    clients = good_clients()
    del clients[0].series["cpi"]
    res = refresh(store, clients)
    assert res.ok is False and "cpi" in res.errors["dataset"]
    assert store.load_model() is None and store.get_meta("updated_at") is None


def test_refresh_collects_source_warnings_without_failing(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    clients = good_clients()
    clients[2].warnings = ["2015: legacy .xls report is not supported"]
    res = refresh(store, clients)
    assert res.ok
    assert res.warnings == ["mf_execution: 2015: legacy .xls report is not supported"]


def test_refresh_reports_warnings_also_on_failure(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    clients = good_clients()
    clients[2].warnings = ["2015: unsupported"]
    res = refresh(store, [*clients[:2], clients[2], FailingClient("other")])
    assert res.ok is False and res.warnings == ["mf_execution: 2015: unsupported"]


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.delenv("REFRESH_DISABLED", raising=False)
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
    assert client.get("/refresh/status").json() == {
        "state": "idle",
        "errors": {},
        "warnings": [],
        "updated_at": None,
        "synthetic": False,
        "disabled": False,
    }


def test_refresh_endpoint_runs_job_and_reports_done(api):
    client, _, store_path = api
    r = client.post("/refresh")
    assert r.status_code == 202
    status = client.get("/refresh/status").json()
    assert status["state"] == "done" and status["errors"] == {}
    assert status["updated_at"] == Store(store_path).get_meta("updated_at") is not None


def test_refresh_status_lists_source_warnings(api):
    client, state, _ = api
    state["clients"][2].warnings = ["2015: legacy .xls report is not supported"]
    assert client.post("/refresh").status_code == 202
    status = client.get("/refresh/status").json()
    assert status["state"] == "done"
    assert status["warnings"] == ["mf_execution: 2015: legacy .xls report is not supported"]


def test_refresh_status_reports_failed_source_name(api):
    client, state, store_path = api
    assert client.post("/refresh").status_code == 202
    good_at = client.get("/refresh/status").json()["updated_at"]

    state["clients"] = [*good_clients()[:2], FailingClient("mf_execution", "HTTP 500 for https://mf.stub")]
    assert client.post("/refresh").status_code == 202
    status = client.get("/refresh/status").json()

    assert status["state"] == "failed"
    assert status["errors"] == {"mf_execution": "HTTP 500 for https://mf.stub"}
    assert status["updated_at"] == good_at  # last good state still advertised


def test_refresh_status_reports_dataset_violations(api):
    client, state, store_path = api
    state["clients"] = real_stub_clients(lambda s, df: df * 1000.0 if s == "consumption_nominal" else df)
    assert client.post("/refresh").status_code == 202
    status = client.get("/refresh/status").json()
    assert status["state"] == "failed" and set(status["errors"]) == {"dataset"}
    assert "konsumpcj" in status["errors"]["dataset"]
    assert Store(store_path).load_model() is None


def test_refresh_rejects_concurrent_run(api):
    client, _, _ = api
    job = app.dependency_overrides[get_job]()
    job.state = "running"
    assert client.post("/refresh").status_code == 409


def test_refresh_disabled_returns_403_and_status_flag(api, monkeypatch):
    client, _, store_path = api
    monkeypatch.setenv("REFRESH_DISABLED", "1")
    r = client.post("/refresh")
    assert r.status_code == 403
    assert r.json() == {"detail": "odświeżanie wyłączone w tej instancji"}
    status = client.get("/refresh/status").json()
    assert status["disabled"] is True and status["state"] == "idle"  # no job started
    assert Store(store_path).load_model() is None


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", " Yes "])
def test_refresh_disabled_accepts_true_and_yes(api, monkeypatch, value):
    client, _, _ = api
    monkeypatch.setenv("REFRESH_DISABLED", value)
    assert client.get("/refresh/status").json()["disabled"] is True
    assert client.post("/refresh").status_code == 403


@pytest.mark.parametrize("value", ["", "0", "false", "no"])
def test_refresh_enabled_unless_flag_is_set(api, monkeypatch, value):
    client, _, _ = api
    monkeypatch.setenv("REFRESH_DISABLED", value)
    assert client.get("/refresh/status").json()["disabled"] is False
    assert client.post("/refresh").status_code == 202


def test_real_clients_fail_cleanly_offline(tmp_path, monkeypatch):
    """Real client classes with an injected failing transport: errors surface per source, no network."""
    monkeypatch.delenv("REFRESH_DISABLED", raising=False)
    https: list[httpx.Client] = []

    def clients():
        def failing():
            h = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503)))
            https.append(h)
            return h

        no_sleep = lambda s: None  # noqa: E731
        return ClientBundle(
            [
                GusBdlClient("https://bdl.test/api/v1", failing(), sleep=no_sleep),
                EurostatClient(failing(), base_url="https://eurostat.test/api/data", sleep=no_sleep),
                MfBudgetExecutionClient(failing(), None, sleep=no_sleep),
            ],
            https,
        )

    store_path = str(tmp_path / "default.db")
    app.dependency_overrides[get_store] = lambda: Store(store_path)
    app.dependency_overrides[get_clients] = clients
    job = RefreshJob()
    app.dependency_overrides[get_job] = lambda: job
    try:
        client = TestClient(app)
        assert client.post("/refresh").status_code == 202
        status = client.get("/refresh/status").json()
    finally:
        app.dependency_overrides.clear()
    assert status["state"] == "failed"
    assert set(status["errors"]) == {"gus_bdl", "eurostat", "mf_execution"}
    assert all("503" in m for m in status["errors"].values()), status["errors"]
    assert Store(store_path).load_model() is None
    assert https and all(h.is_closed for h in https)  # the job closed the per-source HTTP clients


def test_default_get_clients_builds_real_clients(tmp_path, monkeypatch):
    db = tmp_path / "data" / "budget.db"
    monkeypatch.setenv("BUDGET_DB_PATH", str(db))
    monkeypatch.setenv("BDL_CLIENT_ID", "abc-123")
    monkeypatch.delenv("BUDGET_CACHE_DIR", raising=False)

    bundle = get_clients()
    try:
        assert [type(c) for c in bundle] == [GusBdlClient, EurostatClient, MfBudgetExecutionClient]
        assert [c.name for c in bundle] == ["gus_bdl", "eurostat", "mf_execution"]
        bdl, eu, mf = bundle
        assert bdl.base_url == "https://bdl.stat.gov.pl/api/v1" and bdl.client_id == "abc-123"
        assert eu.base_url.startswith("https://ec.europa.eu/")
        assert str(mf.cache_dir) == str(tmp_path / "data" / "cache")  # default: next to the db
        https = [bdl.http, eu.http, mf.http]
        assert len({id(h) for h in https}) == 3  # one HTTP client per source
        for h in https:
            assert isinstance(h, httpx.Client) and h.timeout.read is not None and h.timeout.connect is not None
    finally:
        bundle.close()
    assert all(h.is_closed for h in https)


def test_default_get_clients_cache_dir_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("BUDGET_DB_PATH", str(tmp_path / "budget.db"))
    monkeypatch.delenv("BDL_CLIENT_ID", raising=False)
    monkeypatch.setenv("BUDGET_CACHE_DIR", str(tmp_path / "elsewhere"))
    bundle = get_clients()
    try:
        assert str(bundle[2].cache_dir) == str(tmp_path / "elsewhere")
        assert bundle[0].client_id is None
    finally:
        bundle.close()

    monkeypatch.setenv("BUDGET_CACHE_DIR", "")  # empty = cache disabled
    bundle = get_clients()
    try:
        assert bundle[2].cache_dir is None
    finally:
        bundle.close()


def test_refresh_job_closes_clients_even_when_refresh_crashes(tmp_path, monkeypatch):
    closed = []

    class Bundle(list):
        def close(self):
            closed.append(True)

    def boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(refresh_mod, "refresh", boom)
    job = RefreshJob()
    assert job.try_start()
    job.run(Store(str(tmp_path / "t.db")), Bundle(good_clients()))
    assert job.state == "failed" and closed == [True]


def test_rejected_post_closes_the_clients(api, monkeypatch):
    client, state, _ = api
    closed = []

    class Bundle(list):
        def close(self):
            closed.append(True)

    state["clients"] = Bundle(good_clients())
    job = app.dependency_overrides[get_job]()
    job.state = "running"
    assert client.post("/refresh").status_code == 409
    monkeypatch.setenv("REFRESH_DISABLED", "1")
    job.state = "idle"
    assert client.post("/refresh").status_code == 403
    assert closed == [True, True]


@pytest.mark.parametrize("fail_at", ["second_series", "meta"])
def test_refresh_write_failure_leaves_store_unchanged(tmp_path, monkeypatch, fail_at):
    db = tmp_path / "t.db"
    store = Store(str(db))
    assert refresh(store, good_clients()).ok
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
    job.run(store, good_clients(scale=1.02))

    assert job.state == "failed" and "disk full" in job.errors["refresh"]
    assert_same(snapshot(store), before)
    assert db.read_bytes() == raw_before


# --- final wave: revenues never get shorter than the stored ones (I1) -------------------------


def test_refresh_missing_latest_revenue_years_is_rejected(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    assert refresh(store, good_clients()).ok
    assert store.load_series("rev_pit").index.max() == 2025
    before = snapshot(store)

    res = refresh(store, real_stub_clients(lambda s, df: df.loc[:2024] if s.startswith("rev_") else df))

    assert res.ok is False and set(res.errors) == {"dataset"}
    msg = res.errors["dataset"]
    assert "rev_pit" in msg and "2024" in msg and "2025" in msg
    assert_same(snapshot(store), before)


def test_shorter_revenues_accepted_over_synthetic_seed(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    longer = pd.DataFrame({"value": [100.0, 110.0]}, index=pd.Index([2025, 2026], dtype="int64", name="year"))
    for name in ("rev_vat", "rev_cit", "rev_pit"):
        store.save_series(name, "synthetic", longer)
    store.set_meta("synthetic", "1")
    assert refresh(store, good_clients()).ok
    assert store.load_series("rev_pit").index.max() == 2025


class _Closable:
    def __init__(self, fail: bool = False):
        self.fail, self.closed = fail, False

    def close(self):
        self.closed = True
        if self.fail:
            raise RuntimeError("close failed")


def test_client_bundle_close_continues_after_a_raising_close():
    hs = [_Closable(), _Closable(fail=True), _Closable()]
    bundle = ClientBundle([], hs)
    with pytest.raises(RuntimeError, match="close failed"):
        bundle.close()
    assert all(h.closed for h in hs)


def test_get_clients_closes_built_http_clients_when_a_constructor_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("BUDGET_DB_PATH", str(tmp_path / "budget.db"))
    built: list[httpx.Client] = []
    real_client = httpx.Client

    def tracking(*a, **k):
        h = real_client(*a, **k)
        built.append(h)
        return h

    def broken(*a, **k):
        raise ValueError("bad config")

    monkeypatch.setattr(refresh_mod.httpx, "Client", tracking)
    monkeypatch.setattr(refresh_mod, "EurostatClient", broken)
    with pytest.raises(ValueError, match="bad config"):
        get_clients()
    assert len(built) == 3 and all(h.is_closed for h in built)
