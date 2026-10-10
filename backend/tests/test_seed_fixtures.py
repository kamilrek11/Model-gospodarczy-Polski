import pytest
from fastapi.testclient import TestClient

from app.api.refresh import get_store
from app.main import app
from app.store import Store
from scripts import seed_fixtures as sf


def test_refuses_without_env(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("SEED_FIXTURES", raising=False)
    db = tmp_path / "x.db"
    assert sf.main(["--db", str(db)]) == 2
    assert not db.exists()
    assert "SEED_FIXTURES=1" in capsys.readouterr().err


def test_refuses_without_db(monkeypatch, capsys):
    monkeypatch.setenv("SEED_FIXTURES", "1")
    assert sf.main([]) == 2
    assert "--db" in capsys.readouterr().err


def test_env_must_be_exactly_one():
    with pytest.raises(sf.SeedRefused):
        sf.check_guards("a.db", {"SEED_FIXTURES": "true"})


def test_seed_marks_synthetic_warns_and_simulates(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SEED_FIXTURES", "1")
    db = tmp_path / "s.db"
    assert sf.main(["--db", str(db)]) == 0
    assert "SYNTHETIC" in capsys.readouterr().err
    store = Store(str(db))
    assert store.get_meta("synthetic") == "1"
    assert len(store.load_series("rev_vat")) >= 20
    app.dependency_overrides[get_store] = lambda: Store(str(db))
    try:
        r = TestClient(app).post("/simulate", json={"params": {"vat_rate_standard": 0.25}, "n_paths": 200, "seed": 1})
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200
    assert r.json()["disabled_modules"] == []


def test_deterministic(tmp_path, monkeypatch):
    monkeypatch.setenv("SEED_FIXTURES", "1")
    a, b = tmp_path / "a.db", tmp_path / "b.db"
    sf.main(["--db", str(a)])
    sf.main(["--db", str(b)])
    assert Store(str(a)).load_model() == Store(str(b)).load_model()
