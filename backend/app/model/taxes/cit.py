"""CIT revenue module (mld zł).

    revenue = gross_surplus * calib * ((1 - small_share) * cit_rate + small_share * cit_rate_small)

calib maps gross operating surplus to the CIT tax base (share of CIT payers, profit vs
surplus, deductions) and is fitted to recent outturns elsewhere.
"""

import numpy as np


def cit_revenue(gross_surplus: np.ndarray, small_share: float, p: dict, calib: float) -> np.ndarray:
    base = np.maximum(np.asarray(gross_surplus, dtype=float), 0.0) * max(float(calib), 0.0)
    s = min(max(float(small_share), 0.0), 1.0)
    rate = (1.0 - s) * float(p["cit_rate"]) + s * float(p["cit_rate_small"])
    return base * rate
