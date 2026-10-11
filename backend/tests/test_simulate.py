import time

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.api.refresh import get_store
from app.main import app
from app.model.macro import MACRO_VARS, MacroModel, fit_macro
from app.model.params import defaults
from app.model import config, param_meta
from app.model.simulate import BANDS, simulate
from app.model.taxes.vat import vat_revenue
from app.store import Store
from tests.synthetic import synthetic_levels

# Everything below is synthetic and lives only in pytest's tmp_path stores / memory.

TAXES = ("pit", "cit", "vat")


def synthetic_history(n_years: int = 20, seed: int = 5) -> dict[str, pd.DataFrame]:
    levels = synthetic_levels(n_years, seed=seed)
    hist = {v: levels[[v]].rename(columns={v: "value"}) for v in MACRO_VARS}
    nominal_gdp = levels["pkb_real"] * levels["cpi"] / 100.0
    rng = np.random.default_rng(seed)
    noise = lambda: 1.0 + rng.normal(0, 0.01, n_years)  # noqa: E731
    gs = 0.4 * nominal_gdp * noise()
    wage_bill = levels["wage_nominal"] * levels["employment"] / 100.0
    hist["gross_surplus"] = pd.DataFrame({"value": gs})
    hist["gdp_nominal"] = pd.DataFrame({"value": levels["consumption_nominal"] / 0.57})  # synthetic, ratio 0.57
    hist["rev_pit"] = pd.DataFrame({"value": 0.08 * wage_bill * noise()})
    hist["rev_cit"] = pd.DataFrame({"value": 0.03 * gs * noise()})
    hist["rev_vat"] = pd.DataFrame({"value": 0.12 * levels["consumption_nominal"] * noise()})
    return hist


def synthetic_model(hist: dict[str, pd.DataFrame]) -> MacroModel:
    macro = pd.concat({v: hist[v]["value"] for v in MACRO_VARS}, axis=1)
    return fit_macro(macro, lags=1)


@pytest.fixture(scope="module")
def hist():
    return synthetic_history()


@pytest.fixture(scope="module")
def model(hist):
    return synthetic_model(hist)


def test_default_params_equal_baseline(model, hist):
    res = simulate(model, hist, defaults(), horizon=5, n_paths=500, seed=1)
    assert set(res.taxes) == set(TAXES) and res.disabled_modules == []
    for tax in TAXES:
        assert np.array_equal(res.taxes[tax]["median"], res.baseline[tax]["median"])
    assert np.array_equal(res.total["median"], res.baseline["total"]["median"])
    for var, paths in res.macro.items():
        assert np.array_equal(paths["median"], paths["baseline"]), var
    # partial parameter dicts are filled with current-law defaults
    res2 = simulate(model, hist, {}, horizon=5, n_paths=500, seed=1)
    assert res2.taxes == res.taxes


def test_higher_vat_raises_vat_median_and_dampens_consumption(model, hist):
    res = simulate(model, hist, {"vat_rate_standard": 0.25}, horizon=5, n_paths=500, seed=2)
    vat, vat_base = np.array(res.taxes["vat"]["median"]), np.array(res.baseline["vat"]["median"])
    assert np.all(vat > vat_base)
    c, c_base = np.array(res.macro["consumption_real"]["median"]), np.array(res.macro["consumption_real"]["baseline"])
    assert np.all(c < c_base)
    # second round reaches other bases: PIT falls through employment
    assert np.all(np.array(res.taxes["pit"]["median"]) < np.array(res.baseline["pit"]["median"]))


def _vat_ratio(p: dict) -> float:
    law = defaults()
    c = np.array([100.0])
    vr = lambda q: vat_revenue(c, config.VAT_CONSUMPTION_SHARES, q, config.VAT_GAP, config.VAT_PRICE_ELASTICITY, law)[0]  # noqa: E731
    return float(vr({**law, **p}) / vr(law))


def test_vat_change_counts_volume_response_exactly_once(model, hist):
    # VAT-only reform: no PIT change, so per path VAT_scen / VAT_base is the constant
    # vat_revenue(c, p, law) / vat_revenue(c, law, law). Feeding consumption_feedback into
    # the VAT base as well (double count) would multiply this by (1 + f_vat) != 1.
    p = {"vat_rate_standard": 0.25}
    res = simulate(model, hist, p, horizon=5, n_paths=500, seed=4)
    ratio = np.array(res.taxes["vat"]["median"]) / np.array(res.baseline["vat"]["median"])
    np.testing.assert_allclose(ratio, _vat_ratio(p), rtol=1e-12)


def test_pit_cut_raises_consumption_and_vat_consistently(model, hist):
    # PIT 12% -> 10%: disposable income up -> nominal consumption up by (1 + f_pit), VAT rates
    # unchanged. vat_revenue is linear in consumption at unchanged rates (pass-through 1),
    # so per path VAT_scen / VAT_base == consumption_scen / consumption_base == 1 + f_pit.
    # Expectation on medians: the two ratios agree within 0.1% and both exceed 1.
    res = simulate(model, hist, {"pit_rate_low": 0.10}, horizon=5, n_paths=1000, seed=5)
    vat_ratio = np.array(res.taxes["vat"]["median"]) / np.array(res.baseline["vat"]["median"])
    c = res.macro["consumption_nominal"]
    cons_ratio = np.array(c["median"]) / np.array(c["baseline"])
    assert np.all(vat_ratio > 1.0) and np.all(cons_ratio > 1.0)
    np.testing.assert_allclose(vat_ratio, cons_ratio, rtol=1e-3)
    assert np.all(np.array(res.taxes["pit"]["median"]) < np.array(res.baseline["pit"]["median"]))


def test_bands_are_ordered(model, hist):
    res = simulate(model, hist, {"pit_rate_low": 0.10, "cit_rate": 0.21}, horizon=5, n_paths=1000, seed=3)
    for bands in [*res.taxes.values(), res.total]:
        b = np.array([bands[k] for k in ("p2_5", "p10", "median", "p90", "p97_5")])
        assert b.shape == (5, 5)
        assert np.all(np.diff(b, axis=0) >= 0)
    assert tuple(BANDS) == ("median", "p10", "p90", "p2_5", "p97_5")
    assert res.years == list(range(model.last_year + 1, model.last_year + 6))


def test_seed_reproducible(model, hist):
    a = simulate(model, hist, {"cit_rate": 0.15}, n_paths=300, seed=42)
    b = simulate(model, hist, {"cit_rate": 0.15}, n_paths=300, seed=42)
    c = simulate(model, hist, {"cit_rate": 0.15}, n_paths=300, seed=43)
    assert a.taxes == b.taxes and a.total == b.total and a.macro == b.macro
    assert a.total != c.total


def test_simulate_runs_under_200ms(model, hist):
    simulate(model, hist, defaults(), horizon=5, n_paths=2000, seed=0)  # warm-up
    best = float("inf")
    for _ in range(3):
        t0 = time.perf_counter()
        simulate(model, hist, {"vat_rate_standard": 0.24, "pit_threshold": 150000}, horizon=5, n_paths=2000, seed=0)
        best = min(best, time.perf_counter() - t0)
    assert best < 0.2, f"simulate took {best * 1000:.1f} ms"


def test_calibration_reproduces_history_and_is_exposed(model, hist):
    res = simulate(model, hist, defaults(), n_paths=200, seed=0)
    for tax in TAXES:
        cal = res.calibration[tax]
        assert cal["factor"] > 0 and np.isfinite(cal["factor"])
        assert len(cal["years"]) == 3 and cal["years"][-1] == model.last_year
    keys = {a["key"] for a in res.assumptions}
    assert {"calibration.pit", "calibration.cit", "calibration.vat"} <= keys
    # first simulated year continues the last observed revenue level (calibrated, not invented)
    for tax in TAXES:
        last = float(hist[f"rev_{tax}"]["value"].iloc[-1])
        assert 0.8 * last < res.baseline[tax]["median"][0] < 1.3 * last


def test_assumptions_carry_status_and_source_from_meta(model, hist):
    res = simulate(model, hist, defaults(), n_paths=200, seed=0)
    by_key = {a["key"]: a for a in res.assumptions}
    for key in param_meta.PARAMETERS:
        a = by_key[key]
        assert a["status"] in ("from_data", "sourced", "assumption"), key
        assert a["note"], key
        assert {"source", "year", "url", "low", "high"} <= set(a), key
    assert all(a["note"] for a in res.assumptions)


def test_missing_series_disables_module_without_inventing_data(model, hist):
    partial = {k: v for k, v in hist.items() if k != "gross_surplus"}
    res = simulate(model, partial, defaults(), n_paths=200, seed=0)
    assert "cit" not in res.taxes and "cit" not in res.baseline
    assert [d["module"] for d in res.disabled_modules] == ["cit"]
    assert "gross_surplus" in res.disabled_modules[0]["message"]
    expected = np.array(res.baseline["pit"]["median"]) + np.array(res.baseline["vat"]["median"])
    assert np.allclose(res.baseline["total"]["median"], expected, rtol=0.05)


EXTREMES = [
    {"vat_rate_standard": 0.0, "vat_rate_reduced1": 0.0, "vat_rate_reduced2": 0.0},
    {"vat_rate_standard": 1.0, "vat_rate_reduced1": 1.0, "vat_rate_reduced2": 1.0},
    {"pit_rate_low": 0.0, "pit_rate_high": 0.0, "pit_flat_rate": 0.0, "pit_lump_rate_default": 0.0},
    {"pit_rate_low": 1.0, "pit_rate_high": 1.0, "pit_flat_rate": 1.0, "pit_lump_rate_default": 1.0},
    {"pit_threshold": 0.0},
    {"pit_tax_free": 200_000.0, "pit_threshold": 50_000.0},
    {"cit_rate": 0.0, "cit_rate_small": 0.0},
    {"cit_rate": 1.0, "cit_rate_small": 1.0},
]


@pytest.mark.parametrize("params", EXTREMES)
def test_extreme_params_finite_nonnegative(model, hist, params):
    res = simulate(model, hist, params, n_paths=300, seed=0)
    arrays = [np.array(v) for bands in [*res.taxes.values(), res.total] for v in bands.values()]
    arrays += [np.array(v) for paths in res.macro.values() for v in paths.values()]
    for a in arrays:
        assert np.all(np.isfinite(a)) and np.all(a >= 0)


def test_simulate_rejects_invalid_params(model, hist):
    with pytest.raises(ValueError, match="poza zakresem"):
        simulate(model, hist, {"vat_rate_standard": 2.0}, n_paths=10, seed=0)


# ---------------------------------------------------------------- API


@pytest.fixture
def client_with(tmp_path):
    def make(populated: bool) -> TestClient:
        store = Store(str(tmp_path / "t.db"))
        if populated:
            h = synthetic_history()
            store.save_snapshot({k: ("synthetic", v) for k, v in h.items()}, synthetic_model(h).to_dict(), {"updated_at": "2026-01-01T00:00:00+00:00"})
        app.dependency_overrides[get_store] = lambda: store
        return TestClient(app)

    yield make
    app.dependency_overrides.clear()


def test_simulate_endpoint_409_without_model(client_with):
    r = client_with(False).post("/simulate", json={})
    assert r.status_code == 409
    assert r.json()["detail"] == "brak danych – uruchom odświeżenie"


def test_simulate_endpoint_422_for_invalid_params(client_with):
    r = client_with(True).post("/simulate", json={"params": {"cit_rate": 5}})
    assert r.status_code == 422
    assert "cit_rate" in r.json()["detail"] and "poza zakresem" in r.json()["detail"]
    r = client_with(True).post("/simulate", json={"params": {"nope": 1}})
    assert r.status_code == 422 and "Nieznany parametr" in r.json()["detail"]


def test_simulate_endpoint_returns_full_response(client_with):
    client = client_with(True)
    r = client.post("/simulate", json={"params": {"vat_rate_standard": 0.24}, "n_paths": 300, "seed": 7})
    assert r.status_code == 200
    body = r.json()
    assert set(body) >= {
        "taxes", "baseline", "total", "macro", "years", "calibration",
        "assumptions", "disabled_modules", "model_version", "data_updated_at",
    }
    assert set(body["taxes"]) == set(TAXES) and set(body["taxes"]["vat"]) == set(BANDS)
    assert len(body["years"]) == 5 and body["disabled_modules"] == []
    assert body["data_updated_at"] == "2026-01-01T00:00:00+00:00"
    assert isinstance(body["model_version"], str) and len(body["model_version"]) == 12
    again = client.post("/simulate", json={"params": {"vat_rate_standard": 0.24}, "n_paths": 300, "seed": 7}).json()
    assert again == body


# ---------------------------------------------------------------- real data: 2025 PIT structural break

PIT_BREAK_NOTE = (
    "PIT w budżecie państwa: zmiana zasad podziału od 2025 r. (reforma finansowania JST); kalibracja do 2024; "
    "wykonanie 2025 nie jest porównywalne z prognozą przy dotychczasowych zasadach."
)


def real_history_with_2025_bases() -> tuple[MacroModel, dict[str, pd.DataFrame]]:
    """REAL recorded series (tests/real_dataset.py), assembled. Employment is extended to 2025 with its 2024
    level (test-only, so that PIT 2025 would fall inside the last-3-years window without the break rule)."""
    from app.data.dataset import assemble
    from tests.real_dataset import real_results

    hist = {k: df for k, (_, df) in assemble(real_results()).items()}
    emp = hist["employment"]
    hist["employment"] = pd.concat([emp, pd.DataFrame({"value": [emp["value"].iloc[-1]]}, index=pd.Index([2025], name="year"))])
    macro = pd.concat({v: hist[v]["value"] for v in MACRO_VARS}, axis=1).dropna()
    return fit_macro(macro.loc[:2024], lags=1), hist


def test_calibration_years_cut_series_at_structural_break():
    from app.model.simulate import calibration_years

    assert config.STRUCTURAL_BREAKS == {"rev_pit": 2025}
    assert calibration_years("rev_pit", [2022, 2023, 2024, 2025, 2026]) == [2022, 2023, 2024]
    assert calibration_years("rev_vat", [2023, 2024, 2025]) == [2023, 2024, 2025]


def test_calibration_ignores_pit_years_from_2025():
    model, hist = real_history_with_2025_bases()
    assert hist["rev_pit"].loc[2025, "value"] == pytest.approx(28.75211501)
    res = simulate(model, hist, defaults(), horizon=1, n_paths=50, seed=0)
    cal = res.calibration["pit"]
    assert max(cal["years"]) <= 2024 and len(cal["years"]) == 3
    assert cal["years"] == [2018, 2023, 2024]  # recorded MF years before the break

    # the 2025 value has no influence at all on the factor
    for v in (1e-3, 500.0):
        other = dict(hist)
        pit = hist["rev_pit"].copy()
        pit.loc[2025, "value"] = v
        other["rev_pit"] = pit
        assert simulate(model, other, defaults(), horizon=1, n_paths=50, seed=0).calibration["pit"]["factor"] == cal["factor"]
    # other taxes still use 2025 (no break declared for them)
    assert 2025 in res.calibration["vat"]["years"]


def test_assumptions_contain_pit_break_note(model, hist):
    res = simulate(model, hist, defaults(), n_paths=50, seed=0)
    notes = {a["key"]: a for a in res.assumptions}
    assert any(a["note"] == PIT_BREAK_NOTE for a in res.assumptions)
    assert notes["STRUCTURAL_BREAKS"]["value"] == {"rev_pit": 2025}
    # all sources now deliver mld zł; the unit is enforced by the dataset gate, not by a placeholder factor
    assert "CONSUMPTION_SERIES_TO_MLD_ZL" not in notes
    assert not hasattr(config, "CONSUMPTION_SERIES_TO_MLD_ZL")


# ---------------------------------------------------------------- constants computed from stored data


def _real_history() -> dict[str, pd.DataFrame]:
    from app.data.dataset import assemble
    from tests.real_dataset import real_results

    return {k: df for k, (_, df) in assemble(real_results()).items()}


def _assumption(res, key):
    return next(a for a in res.assumptions if a["key"] == key)


def test_consumption_gdp_share_computed_from_history():
    from app.model.simulate import resolve_constants

    hist = _real_history()
    got = resolve_constants(hist)["CONSUMPTION_GDP_SHARE"]
    assert got == pytest.approx(0.563, abs=0.01)
    both = pd.concat([hist["consumption_nominal"]["value"], hist["gdp_nominal"]["value"]], axis=1, join="inner").dropna()
    assert got == pytest.approx(both.iloc[-1, 0] / both.iloc[-1, 1])

    model, h = real_history_with_2025_bases()
    res = simulate(model, h, defaults(), horizon=1, n_paths=50, seed=0)
    a = _assumption(res, "CONSUMPTION_GDP_SHARE")
    assert a["status"] == "from_data" and a["value"] == pytest.approx(got) and a["year"] == int(both.index[-1])
    assert param_meta.PARAMETERS["CONSUMPTION_GDP_SHARE"].status == "from_data"  # registry stays static


def test_missing_series_falls_back_and_is_reported_as_assumption(model, hist):
    from app.model.simulate import resolve_constants

    hist = {k: v for k, v in hist.items() if k != "gdp_nominal"}
    assert resolve_constants(hist)["CONSUMPTION_GDP_SHARE"] == config.CONSUMPTION_GDP_SHARE
    a = _assumption(simulate(model, hist, defaults(), n_paths=50, seed=0), "CONSUMPTION_GDP_SHARE")
    assert a["status"] == "assumption" and a["value"] == config.CONSUMPTION_GDP_SHARE and a["year"] is None
    assert "gdp_nominal" in a["note"] and "zapasowej" in a["note"]
    assert param_meta.PARAMETERS["CONSUMPTION_GDP_SHARE"].status == "from_data"


def test_out_of_range_ratio_falls_back_and_is_reported(model, hist):
    from app.model.simulate import resolve_constants

    bad = dict(hist)
    bad["gdp_nominal"] = pd.DataFrame({"value": hist["consumption_nominal"]["value"] * 5.0})  # ratio 0.2
    assert resolve_constants(bad)["CONSUMPTION_GDP_SHARE"] == config.CONSUMPTION_GDP_SHARE
    a = _assumption(simulate(model, bad, defaults(), n_paths=50, seed=0), "CONSUMPTION_GDP_SHARE")
    assert a["status"] == "assumption" and "poza dopuszczalnym zakresem" in a["note"]


def test_simulate_uses_computed_share_not_config(model, hist):
    p = {"pit_rate_low": 0.10}
    base = simulate(model, hist, p, horizon=2, n_paths=100, seed=3)
    with_share = dict(hist)
    with_share["gdp_nominal"] = pd.DataFrame({"value": hist["consumption_nominal"]["value"] / 0.65})  # ratio 0.65
    res = simulate(model, with_share, p, horizon=2, n_paths=100, seed=3)
    assert _assumption(res, "CONSUMPTION_GDP_SHARE")["value"] == pytest.approx(0.65)
    d_base = base.macro["pkb_real"]["median"][0] / base.macro["pkb_real"]["baseline"][0] - 1
    d_new = res.macro["pkb_real"]["median"][0] / res.macro["pkb_real"]["baseline"][0] - 1
    assert d_new != pytest.approx(d_base) and abs(d_new) > abs(d_base)  # larger share -> larger GDP response


def test_no_common_year_and_zero_or_nan_gdp_fall_back(model, hist):
    from app.model.simulate import resolve_constants

    cons = hist["consumption_nominal"]
    disjoint = {"consumption_nominal": cons, "gdp_nominal": pd.DataFrame({"value": [1000.0]}, index=pd.Index([1800], name="year"))}
    assert resolve_constants(disjoint)["CONSUMPTION_GDP_SHARE"] == config.CONSUMPTION_GDP_SHARE
    for bad_gdp in (0.0, float("nan")):
        h = {"consumption_nominal": cons, "gdp_nominal": pd.DataFrame({"value": bad_gdp}, index=cons.index)}
        assert resolve_constants(h)["CONSUMPTION_GDP_SHARE"] == config.CONSUMPTION_GDP_SHARE


def test_api_simulate_and_backtest_use_stored_gdp_nominal(tmp_path):
    from app.data.dataset import assemble
    from tests.real_dataset import real_results

    series = assemble(real_results())
    assert "gdp_nominal" in series
    store = Store(str(tmp_path / "real.db"))
    hist = {k: df for k, (_, df) in series.items()}
    store.save_snapshot(series, synthetic_model_real(hist).to_dict(), {"updated_at": "2026-01-01T00:00:00+00:00", "synthetic": "0"})
    app.dependency_overrides[get_store] = lambda: store
    try:
        client = TestClient(app)
        r = client.post("/simulate", json={"n_paths": 100, "horizon": 1, "seed": 1})
        assert r.status_code == 200
        a = next(x for x in r.json()["assumptions"] if x["key"] == "CONSUMPTION_GDP_SHARE")
        assert a["status"] == "from_data" and a["year"] == 2024 and a["value"] == pytest.approx(0.563, abs=0.01)
        assert "zapasowej" not in a["note"]
        assert client.get("/backtest").status_code == 200
    finally:
        app.dependency_overrides.clear()


def synthetic_model_real(hist):
    macro = pd.concat({v: hist[v]["value"] for v in MACRO_VARS}, axis=1).dropna()
    return fit_macro(macro, lags=1)
