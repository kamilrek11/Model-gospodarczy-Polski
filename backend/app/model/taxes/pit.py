"""PIT revenue module (mld zł; incomes, thresholds and tax-free amount in zł).

Scale taxpayers (skala podatkowa): the income distribution (IncomeDist) is used only to
get the effective average tax rate of the scale, which is then applied to the macro base
    scale_base_t = wage_bill_t + business_scale_share * business_income_t.
Incomes of the distribution are scaled by scale_base_t / reference_base, where
reference_base is a FIXED data-year value (mld zł), by default the distribution total
sum(taxpayers * incomes). The effective rate therefore reacts to the level of the base
(a cut vs baseline lowers it) and, with fixed thresholds, rises with nominal growth
(bracket creep). It never depends on other elements of the input array (other years/paths).
If the distribution covers a wider income concept than scale_base (e.g. pensions), the
caller should pass reference_base = baseline data-year scale base instead.

Per-person scale tax (2022+ construction, "kwota zmniejszająca podatek" = low * tax_free):
    tax(y) = max(0, low * min(y, thr) + high * max(y - thr, 0) - low * tax_free)

Business income outside the scale:
    flat: business_flat_share * business_income * pit_flat_rate
    lump: business_lump_share * business_income * lump_revenue_to_income * pit_lump_rate_default

    revenue_t = calib * (eff_rate_t * scale_base_t + flat_t + lump_t)
"""

from dataclasses import dataclass, field

import numpy as np

from app.model import config


@dataclass
class IncomeDist:
    incomes: np.ndarray  # representative annual taxable income per group, zł
    taxpayers: np.ndarray  # number of taxpayers per group, in millions
    business_scale_share: float = config.PIT_BUSINESS_SCALE_SHARE
    business_flat_share: float = config.PIT_BUSINESS_FLAT_SHARE
    business_lump_share: float = config.PIT_BUSINESS_LUMP_SHARE
    lump_revenue_to_income: float = config.PIT_LUMP_REVENUE_TO_INCOME
    # scale base (mld zł) at which `incomes` were observed (fixed data year);
    # None -> distribution total sum(taxpayers[mln] * incomes[zł]) / 1000
    reference_base: float | None = field(default=None)

    def __post_init__(self):
        self.incomes = np.asarray(self.incomes, dtype=float)
        self.taxpayers = np.asarray(self.taxpayers, dtype=float)
        if self.incomes.ndim != 1 or self.incomes.shape != self.taxpayers.shape:
            raise ValueError("incomes i taxpayers muszą być wektorami tej samej długości")
        if self.incomes.size == 0:
            raise ValueError("Rozkład dochodów nie może być pusty")
        if not (np.all(np.isfinite(self.incomes)) and np.all(np.isfinite(self.taxpayers))):
            raise ValueError("Rozkład dochodów zawiera wartości nieskończone")
        if np.any(self.incomes < 0) or np.any(self.taxpayers < 0):
            raise ValueError("Dochody i liczby podatników muszą być nieujemne")
        shares = (self.business_scale_share, self.business_flat_share, self.business_lump_share)
        if any(s < 0 for s in shares) or abs(sum(shares) - 1.0) > 1e-9:
            raise ValueError("Udziały form opodatkowania działalności muszą być nieujemne i sumować się do 1")
        if self.lump_revenue_to_income < 0:
            raise ValueError("lump_revenue_to_income musi być nieujemne")
        if self.reference_base is None:
            self.reference_base = float(np.sum(self.taxpayers * self.incomes)) / 1000.0
        if not np.isfinite(self.reference_base) or self.reference_base < 0:
            raise ValueError("reference_base musi być skończone i nieujemne")


def default_income_dist() -> IncomeDist:
    rows = np.array(config.PIT_INCOME_DIST_DEFAULT, dtype=float)
    return IncomeDist(incomes=rows[:, 0], taxpayers=rows[:, 1])


def scale_tax(incomes: np.ndarray, p: dict) -> np.ndarray:
    """Per-person tax on the scale (zł), never negative."""
    y = np.asarray(incomes, dtype=float)
    low, high = float(p["pit_rate_low"]), float(p["pit_rate_high"])
    thr, free = float(p["pit_threshold"]), float(p["pit_tax_free"])
    tax = low * np.minimum(y, thr) + high * np.maximum(y - thr, 0.0) - low * free
    return np.maximum(tax, 0.0)


def _effective_rate(dist: IncomeDist, growth: float, p: dict) -> float:
    y = dist.incomes * growth
    total_income = float(np.sum(dist.taxpayers * y))
    if total_income <= 0.0:
        return 0.0
    return float(np.sum(dist.taxpayers * scale_tax(y, p))) / total_income


def pit_revenue(
    wage_bill: np.ndarray,
    business_income: np.ndarray,
    income_dist: IncomeDist,
    p: dict,
    calib: float,
) -> np.ndarray:
    wage = np.maximum(np.asarray(wage_bill, dtype=float), 0.0)
    bus = np.maximum(np.asarray(business_income, dtype=float), 0.0)
    wage, bus = np.broadcast_arrays(wage, bus)
    d = income_dist

    scale_base = wage + d.business_scale_share * bus
    ref = float(d.reference_base)
    growth = scale_base / ref if ref > 0 else np.ones_like(scale_base)

    eff = np.vectorize(lambda g: _effective_rate(d, float(g), p), otypes=[float])(growth)
    flat = d.business_flat_share * bus * float(p["pit_flat_rate"])
    lump = d.business_lump_share * bus * d.lump_revenue_to_income * float(p["pit_lump_rate_default"])
    return max(float(calib), 0.0) * (eff * scale_base + flat + lump)
