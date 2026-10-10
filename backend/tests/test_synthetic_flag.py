"""C-1: the synthetic marker (meta synthetic == "1") is exposed by the API and cleared by a real refresh."""

import pytest
from fastapi.testclient import TestClient

from app.api.refresh import RefreshJob, get_clients, get_job, get_store, refresh
from app.main import app
from app.store import Store
from tests.test_refresh import FailingClient, good_clients
from tests.test_simulate import synthetic_history, synthetic_model


def seeded(path, synthetic: str | None) -> Store:
    store = Store(str(path))
    h = synthetic_history()
    meta = {"updated_at": "2026-01-01T00:00:00+00:00"}
    if synthetic is not None:
        meta["synthetic"] = synthetic
    store.save_snapshot({k: ("synthetic", v) for k, v in h.items()}, synthetic_model(h).to_dict(), meta)
    return store


@pytest.fixture
def client_for():
    def make(store: Store, clients=None) -> TestClient:
        app.dependency_overrides[get_store] = lambda: store
        job = RefreshJob()
        app.dependency_overrides[get_job] = lambda: job
        if clients is not None:
            app.dependency_overrides[get_clients] = lambda: clients
        return TestClient(app)

    yield make
    app.dependency_overrides.clear()


@pytest.mark.parametrize(("marker", "expected"), [("1", True), ("0", False), (None, False)])
def test_endpoints_expose_synthetic_flag(tmp_path, client_for, marker, expected):
    c = client_for(seeded(tmp_path / "t.db", marker))
    sim = c.post("/simulate", json={"n_paths": 100, "seed": 1}).json()
    assert sim["synthetic"] is expected
    assert c.get("/history").json()["synthetic"] is expected
    assert c.get("/refresh/status").json()["synthetic"] is expected


def test_refresh_status_on_empty_store_is_not_synthetic(tmp_path, client_for):
    c = client_for(Store(str(tmp_path / "t.db")))
    assert c.get("/refresh/status").json() == {"state": "idle", "errors": {}, "updated_at": None, "synthetic": False}


def test_successful_refresh_clears_synthetic_flag(tmp_path):
    store = seeded(tmp_path / "t.db", "1")
    assert refresh(store, good_clients()).ok
    assert store.get_meta("synthetic") == "0"


def test_failed_refresh_leaves_synthetic_flag_untouched(tmp_path):
    store = seeded(tmp_path / "t.db", "1")
    res = refresh(store, [good_clients()[0], FailingClient("execution")])
    assert not res.ok
    assert store.get_meta("synthetic") == "1"


def test_refresh_writes_flag_in_the_same_snapshot_transaction(tmp_path, monkeypatch):
    store = seeded(tmp_path / "t.db", "1")
    calls = []
    orig = Store.save_snapshot

    def spy(self, series, model, meta):
        calls.append(dict(meta))
        return orig(self, series, model, meta)

    monkeypatch.setattr(Store, "save_snapshot", spy)
    monkeypatch.setattr(Store, "set_meta", lambda *a, **k: pytest.fail("meta must be written inside save_snapshot"))
    assert refresh(store, good_clients()).ok
    assert calls and calls[0]["synthetic"] == "0"


def test_endpoint_refresh_clears_flag_then_seed_guard_refuses(tmp_path, client_for):
    from scripts.seed_fixtures import SeedRefused, check_guards

    path = tmp_path / "demo.db"
    store = seeded(path, "1")
    c = client_for(store, good_clients())
    assert c.post("/refresh").status_code == 202
    assert c.get("/refresh/status").json()["synthetic"] is False
    with pytest.raises(SeedRefused, match="not marked synthetic"):
        check_guards(str(path), env={"SEED_FIXTURES": "1"})
