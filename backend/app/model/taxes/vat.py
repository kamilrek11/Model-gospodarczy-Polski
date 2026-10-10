"""VAT revenue module (mld zł).

Consumption is nominal and gross of VAT at the baseline rates (base_p). For each rate
category k with consumption share s_k:
    net_base_k = C * s_k / (1 + t_k_base)              (net-of-VAT spending at baseline)
    volume_k   = ((1 + t_k) / (1 + t_k_base)) ** e     (full pass-through, demand response)
    revenue    = (1 - gap) * sum_k t_k * net_base_k * volume_k
With e = 0 revenue is linear in each rate.
"""

import numpy as np

RATE_KEYS: dict[str, str | None] = {
    "standard": "vat_rate_standard",
    "reduced1": "vat_rate_reduced1",
    "reduced2": "vat_rate_reduced2",
    "zero": None,
}


def _rate(p: dict, category: str) -> float:
    if category not in RATE_KEYS:
        raise ValueError(f"Nieznana kategoria stawki VAT: {category}")
    key = RATE_KEYS[category]
    return 0.0 if key is None else float(p[key])


def _price_volume(rate_before: float, rate_after: float, elasticity: float) -> float:
    ratio = (1.0 + rate_after) / (1.0 + rate_before)
    return ratio**elasticity


def vat_revenue(
    consumption: np.ndarray,
    shares: dict[str, float],
    p: dict,
    gap: float,
    elasticity: float,
    base_p: dict,
) -> np.ndarray:
    """VAT revenue (mld zł) for each element of `consumption`.

    Contract (second-round effects counted exactly once):
    - `consumption` MUST be the pre-feedback path: nominal private consumption gross of VAT
      at the baseline rates `base_p`, i.e. BEFORE any consumption_feedback adjustment.
    - This function OWNS the demand (volume) response to VAT rate changes via
      ((1 + t) / (1 + t_base)) ** elasticity per rate category.
    - Do not pass consumption already scaled by (1 + consumption_feedback(...)) here
      while `base_p` is still the baseline: that applies the volume response twice.
    """
    cons = np.maximum(np.asarray(consumption, dtype=float), 0.0)
    gap = min(max(float(gap), 0.0), 1.0)
    total = np.zeros_like(cons)
    for category, share in shares.items():
        t_new = _rate(p, category)
        t_base = _rate(base_p, category)
        net_base = cons * max(float(share), 0.0) / (1.0 + t_base)
        total = total + t_new * net_base * _price_volume(t_base, t_new, elasticity)
    return (1.0 - gap) * total


def effective_vat_rate(shares: dict[str, float], p: dict) -> float:
    """Consumption-share weighted average statutory VAT rate."""
    return sum(max(float(s), 0.0) * _rate(p, k) for k, s in shares.items())


def consumption_feedback(vat_before: float, vat_after: float, elasticity: float) -> float:
    """Relative change in real consumption after a move of the effective VAT rate.

    vat_before / vat_after are effective (average) VAT rates; full pass-through to prices.

    Contract: this is for the macro block only, to propagate the VAT-driven consumption
    change to OTHER variables (employment, wages, other tax bases). The adjusted
    consumption must not be fed back into vat_revenue (with baseline base_p), because
    vat_revenue already applies the same volume response; doing both double counts it.
    For VAT itself, always pass the pre-feedback consumption path to vat_revenue.
    """
    return float(_price_volume(float(vat_before), float(vat_after), elasticity) - 1.0)
