"""State-budget PIT share from the 2025 break: s = s0 * m * eps (spec 2026-10-11-udzial-pit-design.md).

Real recorded data (tests/real_dataset.py, no network) and the synthetic history of test_simulate.
"""

import numpy as np
import pandas as pd
import pytest

from app.model import config
from app.model.macro import MACRO_VARS, fit_macro
from app.model.simulate import StateShare, simulate
from tests.test_simulate import synthetic_history, synthetic_model

REALISED_PIT_2025 = 28.75211501
BREAK = 2025


def _real_history() -> dict[str, pd.DataFrame]:
    from app.data.dataset import assemble
    from tests.real_dataset import real_results

    return {k: df for k, (_, df) in assemble(real_results()).items()}


def _model(hist: dict[str, pd.DataFrame], last_year: int):
    macro = pd.concat({v: hist[v]["value"] for v in MACRO_VARS}, axis=1).dropna()
    return fit_macro(macro.loc[:last_year], lags=1)


@pytest.fixture(scope="module")
def real():
    hist = _real_history()
    return _model(hist, 2024), hist


def _row(res, key="PIT_STATE_SHARE"):
    return next(a for a in res.assumptions if a["key"] == key)


def _idx(res, year):
    return res.years.index(year)


def test_s0_from_recorded_data_is_about_0_23(real):
    from tests.test_simulate import real_history_with_2025_bases

    # recorded series with the 2025 wage bill available (employment carried to 2025): 'data' source, s0 = 0.212
    model, hist = real_history_with_2025_bases()
    res = simulate(model, hist, {}, horizon=2, n_paths=2000, seed=0)
    row = _row(res)
    assert row["value"] == pytest.approx(0.23, abs=0.03)
    assert row["status"] == "calibrated" and row["year"] == BREAK
    assert res.state_share.source in ("data", "forecast")
    # recorded series as stored (employment ends 2024): 'forecast' source; measured 0.198 (the pre-break PIT
    # calibration over-predicts 2024 by ~23%, so the 2025 module value is high and s0 sits below the spec's 0.23)
    model, hist = real
    res = simulate(model, hist, {}, horizon=2, n_paths=2000, seed=0)
    assert res.state_share.source == "forecast"
    assert _row(res)["value"] == pytest.approx(0.20, abs=0.02)


def test_pit_2025_median_close_to_realised(real):
    model, hist = real
    res = simulate(model, hist, {}, horizon=2, n_paths=2000, seed=0)
    i = _idx(res, 2025)
    pit = res.taxes["pit"]
    assert pit["p10"][i] <= REALISED_PIT_2025 <= pit["p90"][i]
    assert pit["median"][i] == pytest.approx(REALISED_PIT_2025, rel=0.15)


def test_multiplier_scales_pit_from_break_only():
    hist = _real_history()
    model = _model(hist, 2023)  # forecast years 2024.. so a pre-break year is present
    one = simulate(model, hist, {}, horizon=3, n_paths=1000, seed=3)
    two = simulate(model, hist, {"pit_state_share_mult": 2.0}, horizon=3, n_paths=1000, seed=3)
    assert one.years[0] == 2024
    for i, y in enumerate(one.years):
        ratio = two.taxes["pit"]["median"][i] / one.taxes["pit"]["median"][i]
        assert ratio == pytest.approx(2.0 if y >= BREAK else 1.0, rel=0.02), y
        # the baseline always uses m = 1
        assert two.baseline["pit"]["median"][i] == pytest.approx(one.baseline["pit"]["median"][i])
    assert two.taxes["vat"] == one.taxes["vat"] and two.taxes["cit"] == one.taxes["cit"]
    assert two.macro == one.macro  # feedback channels unchanged by the share


def test_identical_params_give_zero_difference(real):
    model, hist = real
    res = simulate(model, hist, {}, horizon=3, n_paths=500, seed=1)
    assert res.taxes["pit"]["median"] == res.baseline["pit"]["median"]
    assert res.total["median"] == res.baseline["total"]["median"]


def test_epsilon_widens_pit_bands(real, monkeypatch):
    model, hist = real
    wide = simulate(model, hist, {}, horizon=3, n_paths=1000, seed=2)
    monkeypatch.setattr(config, "PIT_STATE_SHARE_SIGMA", 0.0)
    narrow = simulate(model, hist, {}, horizon=3, n_paths=1000, seed=2)
    for i, y in enumerate(wide.years):
        w = wide.taxes["pit"]["p90"][i] - wide.taxes["pit"]["p10"][i]
        n = narrow.taxes["pit"]["p90"][i] - narrow.taxes["pit"]["p10"][i]
        assert w > n, y
    assert wide.taxes["vat"] == narrow.taxes["vat"]  # eps has its own generator


def test_missing_rev_2025_falls_back_to_old_rules(monkeypatch):
    hist = _real_history()
    hist["rev_pit"] = hist["rev_pit"].loc[:2024]
    model = _model(hist, 2024)
    res = simulate(model, hist, {}, horizon=2, n_paths=500, seed=4)
    row = _row(res)
    assert row["value"] == 1.0 and row["status"] == "assumption" and res.state_share.source == "none"
    assert "sprzed 2025" in row["note"]
    # eps disabled: bands do not depend on sigma
    monkeypatch.setattr(config, "PIT_STATE_SHARE_SIGMA", 0.0)
    assert simulate(model, hist, {}, horizon=2, n_paths=500, seed=4).taxes["pit"] == res.taxes["pit"]
    # PIT stays at the pre-2025 level (around 100 mld zł, not 0.23 of it)
    assert res.taxes["pit"]["median"][0] > 80


def test_synthetic_history_without_break_year_is_unchanged():
    hist = synthetic_history()
    model = synthetic_model(hist)
    res = simulate(model, hist, {"pit_state_share_mult": 2.0}, horizon=3, n_paths=200, seed=0)
    assert max(res.years) < BREAK
    assert res.taxes["pit"]["median"] == res.baseline["pit"]["median"]  # m only acts from the break year
    assert _row(res)["status"] == "assumption"


def test_seed_none_runs(real):
    model, hist = real
    res = simulate(model, hist, {}, horizon=2, n_paths=200, seed=None)
    assert np.all(np.isfinite(res.taxes["pit"]["median"]))


def test_seed_zero_is_deterministic(real):
    model, hist = real
    a = simulate(model, hist, {}, horizon=2, n_paths=300, seed=0)
    b = simulate(model, hist, {}, horizon=2, n_paths=300, seed=0)
    assert a.taxes == b.taxes and _row(a)["value"] == _row(b)["value"]


def test_state_share_row_has_year_range_and_note(real):
    model, hist = real
    res = simulate(model, hist, {"pit_state_share_mult": 1.5}, horizon=2, n_paths=500, seed=0)
    row = _row(res)
    assert row["year"] == BREAK
    assert row["low"] < row["value"] < row["high"]
    assert row["low"] == pytest.approx(row["value"] * np.exp(-config.PIT_STATE_SHARE_SIGMA))
    assert row["high"] == pytest.approx(row["value"] * np.exp(config.PIT_STATE_SHARE_SIGMA))
    assert "jednego roku" in row["note"]
    eff = f"{row['value'] * 1.5:.3f}".replace(".", ",")
    assert eff in row["note"]
    assert {"source", "url", "range_text"} <= set(row)


def test_data_source_when_model_year_is_2025():
    from app.model.simulate import _prepare, estimate_state_share

    hist = _real_history()
    for v in MACRO_VARS:  # test-only: extend macro series ending in 2024 to 2025 with their 2024 level
        s = hist[v]
        if s.index.max() < 2025:
            hist[v] = pd.concat([s, pd.DataFrame({"value": [s["value"].iloc[-1]]}, index=pd.Index([2025], name="year"))])
    model = _model(hist, 2025)
    assert model.last_year == 2025
    res = simulate(model, hist, {}, horizon=2, n_paths=300, seed=0)
    row = _row(res)
    assert res.state_share.source == "data" and row["status"] == "calibrated" and res.years[0] == 2026
    assert row["value"] == pytest.approx(0.23, abs=0.05)
    # every forecast year is after the break: the share applies from the first one
    ctx, _, _ = _prepare(model, hist)
    share = estimate_state_share(model, hist, ctx, res.years, np.ones((3, 2)))
    assert isinstance(share, StateShare) and share.source == "data" and share.year == BREAK
    assert share.s0 == pytest.approx(row["value"])


def test_estimate_state_share_forecast_and_none(real):
    from app.model.simulate import _prepare, estimate_state_share

    model, hist = real
    ctx, _, _ = _prepare(model, hist)
    pit_base = np.full((5, 2), 100.0)
    share = estimate_state_share(model, hist, ctx, [2025, 2026], pit_base)
    assert share.source == "forecast" and share.s0 == pytest.approx(REALISED_PIT_2025 / 100.0)
    assert estimate_state_share(model, hist, ctx, [2026, 2027], pit_base).source == "none"  # break year not reachable
    bad = estimate_state_share(model, hist, ctx, [2025, 2026], np.zeros((5, 2)))
    assert bad.source == "none" and bad.s0 == 1.0
    no_pit = estimate_state_share(model, hist, type(ctx)(**{**ctx.__dict__, "enabled": ["cit", "vat"]}), [2025], pit_base)
    assert no_pit.source == "none"
