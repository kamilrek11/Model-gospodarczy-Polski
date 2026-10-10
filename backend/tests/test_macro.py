import json

import numpy as np
import pytest

from app.model.macro import MACRO_VARS, InsufficientData, MacroModel, fit_macro
from tests.synthetic import A, C, synthetic_levels


def test_fit_macro_recovers_known_var_coefficients():
    model = fit_macro(synthetic_levels(2000), lags=1)
    assert model.variables == list(MACRO_VARS)
    assert model.lags == 1
    assert model.n_obs == 2000
    assert model.coefs.shape == (1 + len(MACRO_VARS), len(MACRO_VARS))
    np.testing.assert_allclose(model.coefs[1:].T, A, atol=0.08)
    np.testing.assert_allclose(model.coefs[0], C, atol=0.01)
    assert model.resid.shape == (2000 - 1 - 1, len(MACRO_VARS))
    assert model.resid.std(axis=0) == pytest.approx(np.full(5, 0.01), rel=0.1)


def test_fit_macro_raises_on_short_history():
    with pytest.raises(InsufficientData) as exc:
        fit_macro(synthetic_levels(10))
    assert exc.value.n_obs == 10
    assert exc.value.required == 15


def test_fit_macro_uses_latest_contiguous_complete_block():
    df = synthetic_levels(20)
    df.iloc[6, 2] = np.nan  # year 2006 incomplete -> usable block is 2007..2019 (13 years)
    with pytest.raises(InsufficientData) as exc:
        fit_macro(df)
    assert exc.value.n_obs == 13
    df = synthetic_levels(25)
    df.iloc[3, 1] = np.nan
    df = df.drop(index=[2010])  # missing year also breaks the block -> 2011..2024 (14 years)
    with pytest.raises(InsufficientData) as exc:
        fit_macro(df)
    assert exc.value.n_obs == 14


def test_fit_macro_two_lags_and_last_obs():
    df = synthetic_levels(30, seed=1)
    model = fit_macro(df, lags=2)
    assert model.coefs.shape == (1 + 2 * 5, 5)
    logd = np.diff(np.log(df.to_numpy()), axis=0)
    np.testing.assert_allclose(model.last_obs, logd[-2:])
    np.testing.assert_allclose(model.last_levels, df.to_numpy()[-1])
    assert model.last_year == 2029
    assert model.resid.shape == (29 - 2, 5)


def test_fit_macro_rejects_bad_input():
    with pytest.raises(ValueError):
        fit_macro(synthetic_levels(20), lags=3)
    bad = synthetic_levels(20)
    bad.iloc[5, 0] = -1.0
    with pytest.raises(ValueError, match="positive"):
        fit_macro(bad)
    with pytest.raises(ValueError, match="cpi"):
        fit_macro(synthetic_levels(20).drop(columns=["cpi"]))


def test_macro_model_dict_roundtrip_is_json_serialisable():
    model = fit_macro(synthetic_levels(25, seed=2), lags=1)
    payload = json.loads(json.dumps(model.to_dict()))
    back = MacroModel.from_dict(payload)
    assert back.variables == model.variables and back.lags == model.lags and back.n_obs == model.n_obs
    assert back.last_year == model.last_year
    for f in ("coefs", "resid", "last_obs", "last_levels"):
        np.testing.assert_allclose(getattr(back, f), getattr(model, f))
