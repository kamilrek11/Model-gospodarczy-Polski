import json
import math
import re

from tests.frontend_fixtures import SIMULATION_FIXTURE, build_simulation_fixture


HEX12 = re.compile(r"^[0-9a-f]{12}$")


def differing_keys(committed: dict, built: dict) -> list[str]:
    """Top-level fixture keys that differ. `model_version` is a hash of the stored model's JSON floats, so it changes
    with last-bit differences in the fitted coefficients (different CPU/BLAS); it is checked for shape only."""
    bad = [k for k in sorted(committed.keys() | built.keys()) if k != "model_version" and not (k in committed and k in built and same(committed[k], built[k]))]
    if not all(isinstance(d.get("model_version"), str) and HEX12.match(d["model_version"]) for d in (committed, built)):
        bad.append("model_version")
    return bad


def fixtures_match(committed: dict, built: dict) -> bool:
    return not differing_keys(committed, built)


def test_frontend_simulation_fixture_matches_backend_output():
    assert SIMULATION_FIXTURE.exists(), "run: python -m tests.frontend_fixtures"
    committed = json.loads(SIMULATION_FIXTURE.read_text(encoding="utf-8"))
    built = build_simulation_fixture()
    # floats compared with a tolerance (last-bit differences across platforms), everything else exactly
    bad = differing_keys(committed, built)
    assert not bad, f"keys differ: {bad} - regenerate frontend/src/testdata/simulation.json: python -m tests.frontend_fixtures"


def same(a, b) -> bool:
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    if isinstance(a, float) or isinstance(b, float):
        return not isinstance(a, bool) and not isinstance(b, bool) and math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)
    return type(a) is type(b) and a == b


def test_fixture_comparison_survives_last_bit_noise_in_the_fitted_model(monkeypatch):
    """Regression for a CI-only failure: other runner hardware fits the VAR with last-bit differences in the
    coefficients. `model_version` is a hash of the stored model JSON, so it changes with such noise while every
    number stays within tolerance. The fixture check must not depend on that hash."""
    import numpy as np

    import tests.test_simulate as ts
    from app.model.macro import MacroModel

    committed = build_simulation_fixture()
    real = ts.synthetic_model

    def one_ulp_off(hist):
        d = real(hist).to_dict()
        d["coefs"] = [[float(np.nextafter(c, np.inf)) for c in row] for row in d["coefs"]]
        return MacroModel.from_dict(d)

    monkeypatch.setattr(ts, "synthetic_model", one_ulp_off)
    noisy = build_simulation_fixture()

    assert noisy["model_version"] != committed["model_version"]  # the mechanism: the hash is bit-sensitive
    assert fixtures_match(committed, noisy), "fixture check must tolerate last-bit model noise"


def test_fixture_contains_the_non_scalar_assumption_shapes():
    data = build_simulation_fixture()
    shapes = {a["key"]: type(a["value"]).__name__ for a in data["assumptions"]}
    assert shapes["VAT_CONSUMPTION_SHARES"] == "dict"
    assert shapes["PIT_INCOME_DIST_DEFAULT"] == "list"
    assert data["synthetic"] is True
