"""Macro block: annual reduced-form VAR on log differences (spec §5).

Endogenous variables (levels, annual): real GDP, employment, nominal average wage,
CPI (price index level), nominal private consumption. The VAR is estimated on
d_t = log(x_t) - log(x_{t-1}) with a constant and 1-2 lags (small sample).
Wide uncertainty is expected; residuals are kept for bootstrap simulation.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from statsmodels.tsa.api import VAR

MACRO_VARS: tuple[str, ...] = ("pkb_real", "employment", "wage_nominal", "cpi", "consumption_nominal")
MIN_OBS = 15
ALLOWED_LAGS = (1, 2)


class InsufficientData(Exception):
    def __init__(self, n_obs: int, required: int = MIN_OBS):
        super().__init__(f"insufficient data: {n_obs} complete annual observations, required {required}")
        self.n_obs = n_obs
        self.required = required


@dataclass
class MacroModel:
    variables: list[str]
    lags: int
    coefs: np.ndarray  # (1 + k*lags, k): row 0 = const, then lag-1 block (k rows), lag-2 block...; column = equation
    resid: np.ndarray  # (n_obs - 1 - lags, k) residuals in log-difference space (for bootstrap)
    last_obs: np.ndarray  # (lags, k) last `lags` log-difference rows, oldest first
    last_levels: np.ndarray  # (k,) levels in the final sample year
    last_year: int
    n_obs: int  # complete, contiguous annual level observations used

    def to_dict(self) -> dict:
        return {
            "variables": list(self.variables),
            "lags": int(self.lags),
            "coefs": self.coefs.tolist(),
            "resid": self.resid.tolist(),
            "last_obs": self.last_obs.tolist(),
            "last_levels": self.last_levels.tolist(),
            "last_year": int(self.last_year),
            "n_obs": int(self.n_obs),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MacroModel":
        return cls(
            variables=list(d["variables"]),
            lags=int(d["lags"]),
            coefs=np.asarray(d["coefs"], dtype=float),
            resid=np.asarray(d["resid"], dtype=float),
            last_obs=np.asarray(d["last_obs"], dtype=float),
            last_levels=np.asarray(d["last_levels"], dtype=float),
            last_year=int(d["last_year"]),
            n_obs=int(d["n_obs"]),
        )


def _latest_contiguous_block(df: pd.DataFrame) -> pd.DataFrame:
    """Latest run of consecutive years with all variables present (no gaps, no NaN)."""
    complete = df.dropna().sort_index()
    if complete.empty:
        return complete
    years = complete.index.to_numpy()
    breaks = np.flatnonzero(np.diff(years) != 1)
    start = breaks[-1] + 1 if breaks.size else 0
    return complete.iloc[start:]


def fit_macro(data: pd.DataFrame, lags: int = 1) -> MacroModel:
    """Fit a VAR(lags) with constant on log differences of MACRO_VARS levels indexed by year."""
    if lags not in ALLOWED_LAGS:
        raise ValueError(f"lags must be one of {ALLOWED_LAGS}, got {lags}")
    missing = [v for v in MACRO_VARS if v not in data.columns]
    if missing:
        raise ValueError(f"missing macro series: {', '.join(missing)}")
    block = _latest_contiguous_block(data[list(MACRO_VARS)].astype(float))
    n_obs = len(block)
    if n_obs < MIN_OBS:
        raise InsufficientData(n_obs, MIN_OBS)
    levels = block.to_numpy()
    if (levels <= 0).any():
        raise ValueError("macro levels must be strictly positive for log differences")
    d = np.diff(np.log(levels), axis=0)
    res = VAR(d).fit(lags, trend="c")
    return MacroModel(
        variables=list(MACRO_VARS),
        lags=lags,
        coefs=np.asarray(res.params, dtype=float),
        resid=np.asarray(res.resid, dtype=float),
        last_obs=d[-lags:].copy(),
        last_levels=levels[-1].copy(),
        last_year=int(block.index[-1]),
        n_obs=n_obs,
    )
