"""Synthetic (test-only) macro data with known VAR(1) dynamics in log differences."""
import numpy as np
import pandas as pd

from app.model.macro import MACRO_VARS

# Known VAR(1) on log differences (rows = equation, cols = lagged variable). Stable: spectral radius < 1.
A = np.array(
    [
        [0.40, 0.10, 0.00, -0.10, 0.05],
        [0.20, 0.30, 0.00, 0.00, 0.00],
        [0.10, 0.10, 0.30, 0.20, 0.00],
        [0.00, 0.00, 0.10, 0.50, 0.00],
        [0.10, 0.00, 0.20, 0.10, 0.30],
    ]
)
C = np.array([0.02, 0.005, 0.03, 0.01, 0.02])


def synthetic_levels(n_years: int, seed: int = 0, sd: float = 0.01) -> pd.DataFrame:
    """Levels whose log differences follow d_t = C + A d_{t-1} + e_t (synthetic, test-only)."""
    rng = np.random.default_rng(seed)
    k = len(MACRO_VARS)
    d = np.zeros((n_years - 1 + 50, k))
    d[0] = np.linalg.solve(np.eye(k) - A, C)
    for t in range(1, len(d)):
        d[t] = C + A @ d[t - 1] + rng.normal(0, sd, k)
    d = d[50:]  # burn-in
    levels = 100 * np.exp(np.vstack([np.zeros(k), np.cumsum(d, axis=0)]))
    idx = pd.Index(range(2000, 2000 + n_years), dtype="int64", name="year")
    return pd.DataFrame(levels, index=idx, columns=list(MACRO_VARS))
