"""The committed demo snapshot (demo/real-data.db, REAL data) must work end to end through the API.

Regression for a click-through that showed "Brak danych źródłowych": the script and the snapshot were only
checked on /health, never on /history, /simulate and /backtest.
"""

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.refresh import get_store
from app.main import app
from app.store import Store

SNAPSHOT = Path(__file__).resolve().parents[2] / "demo" / "real-data.db"


@pytest.fixture
def client(tmp_path):
    db = tmp_path / "real-data.db"
    shutil.copy(SNAPSHOT, db)  # the app opens the file read-write; never touch the committed snapshot
    store = Store(str(db))
    app.dependency_overrides[get_store] = lambda: store
    yield TestClient(app)
    app.dependency_overrides.pop(get_store, None)


def test_snapshot_exists_and_is_marked_real():
    assert SNAPSHOT.exists(), "run: bash scripts/demo-real-data.sh needs demo/real-data.db"


def test_history_is_real_data(client):
    r = client.get("/history")
    assert r.status_code == 200
    assert r.json()["synthetic"] is False


def test_simulate_and_backtest_work_on_the_snapshot(client):
    sim = client.post("/simulate", json={"params": {}})
    assert sim.status_code == 200, sim.text
    body = sim.json()
    assert body["synthetic"] is False
    status = {a["key"]: a["status"] for a in body["assumptions"]}
    assert status["CONSUMPTION_GDP_SHARE"] == "from_data"
    assert client.get("/backtest").status_code == 200
