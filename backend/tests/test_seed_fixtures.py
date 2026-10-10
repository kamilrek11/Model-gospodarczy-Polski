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


@pytest.fixture
def seed_env(monkeypatch):
    monkeypatch.setenv("SEED_FIXTURES", "1")
    monkeypatch.delenv("BUDGET_DB_PATH", raising=False)


def test_refuses_default_path(seed_env, tmp_path, monkeypatch, capsys):
    default = tmp_path / "var" / "budget.db"
    monkeypatch.setattr(sf, "DEFAULT_DB_PATH", default)
    assert sf.main(["--db", str(default)]) == 2
    assert not default.exists()


def test_refuses_budget_db_path_env(seed_env, tmp_path, monkeypatch):
    real = tmp_path / "real.db"
    monkeypatch.setenv("BUDGET_DB_PATH", str(real))
    assert sf.main(["--db", str(real)]) == 2
    assert not real.exists()


def test_refuses_symlink_and_relative_to_default(seed_env, tmp_path, monkeypatch):
    default = tmp_path / "var" / "budget.db"
    default.parent.mkdir()
    monkeypatch.setattr(sf, "DEFAULT_DB_PATH", default)
    link = tmp_path / "link.db"
    link.symlink_to(default)
    assert sf.main(["--db", str(link)]) == 2
    monkeypatch.chdir(tmp_path)
    assert sf.main(["--db", "var/../var/budget.db"]) == 2
    assert not default.exists()


def test_refuses_existing_non_synthetic_store_unchanged(seed_env, tmp_path):
    import pandas as pd

    db = tmp_path / "real.db"
    store = Store(str(db))
    store.save_series("rev_vat", "gus", pd.DataFrame({"value": [1.0]}, index=pd.Index([2020], name="year")))
    assert sf.main(["--db", str(db)]) == 2
    assert store.load_series("rev_vat")["value"].tolist() == [1.0]
    assert store.load_model() is None and store.get_meta("synthetic") is None


def test_reseeding_synthetic_store_allowed(seed_env, tmp_path):
    db = tmp_path / "s.db"
    assert sf.main(["--db", str(db)]) == 0
    assert sf.main(["--db", str(db)]) == 0


def test_nonexistent_path_allowed(seed_env, tmp_path):
    assert sf.main(["--db", str(tmp_path / "new" / "x.db")]) == 0
