import json
import math

from tests.frontend_fixtures import SIMULATION_FIXTURE, build_simulation_fixture


def test_frontend_simulation_fixture_matches_backend_output():
    assert SIMULATION_FIXTURE.exists(), "run: python -m tests.frontend_fixtures"
    committed = json.loads(SIMULATION_FIXTURE.read_text(encoding="utf-8"))
    # floats compared with a tolerance (last-bit differences across platforms), everything else exactly
    assert same(committed, build_simulation_fixture()), "regenerate frontend/src/testdata/simulation.json: python -m tests.frontend_fixtures"


def same(a, b) -> bool:
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    if isinstance(a, float) or isinstance(b, float):
        return not isinstance(a, bool) and not isinstance(b, bool) and math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)
    return type(a) is type(b) and a == b


def test_fixture_contains_the_non_scalar_assumption_shapes():
    data = build_simulation_fixture()
    shapes = {a["key"]: type(a["value"]).__name__ for a in data["assumptions"]}
    assert shapes["VAT_CONSUMPTION_SHARES"] == "dict"
    assert shapes["PIT_INCOME_DIST_DEFAULT"] == "list"
    assert data["synthetic"] is True
