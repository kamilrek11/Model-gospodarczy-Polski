"""Generate frontend test fixtures from REAL backend output (synthetic tmp store, fixed seed).

    cd backend && .venv/bin/python -m tests.frontend_fixtures   # rewrites frontend/src/testdata/simulation.json

tests/test_frontend_fixtures.py fails when the committed JSON drifts from what this produces.
The data behind it is SYNTHETIC (tests.synthetic) and only exercises shapes/rendering.
"""

import json
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.refresh import get_store
from app.main import app
from app.store import Store

SIMULATION_FIXTURE = Path(__file__).resolve().parents[2] / "frontend" / "src" / "testdata" / "simulation.json"
REQUEST = {"params": {}, "horizon": 2, "n_paths": 100, "seed": 1}


def build_simulation_fixture() -> dict:
    from tests.test_simulate import synthetic_history, synthetic_model

    with tempfile.TemporaryDirectory() as d:
        store = Store(str(Path(d) / "fixture.db"))
        h = synthetic_history()
        meta = {"updated_at": "2026-01-01T00:00:00+00:00", "synthetic": "1"}
        store.save_snapshot({k: ("synthetic", v) for k, v in h.items()}, synthetic_model(h).to_dict(), meta)
        app.dependency_overrides[get_store] = lambda: store
        try:
            r = TestClient(app).post("/simulate", json=REQUEST)
        finally:
            app.dependency_overrides.pop(get_store, None)
    r.raise_for_status()
    return r.json()


def write() -> None:
    SIMULATION_FIXTURE.write_text(json.dumps(build_simulation_fixture(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    write()
    print(f"wrote {SIMULATION_FIXTURE}")
