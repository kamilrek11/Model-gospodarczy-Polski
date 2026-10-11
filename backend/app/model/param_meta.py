"""Metadata registry for the 13 non-user constants of app.model.config.

status: from_data (computed from loaded series), sourced (published source with url),
assumption (no verified source; `note` must say why).
Values stay in config.py; this module only describes them.
"""

from dataclasses import dataclass
from copy import deepcopy
from typing import Literal

from app.model import config

Status = Literal["from_data", "sourced", "assumption"]


@dataclass(frozen=True)
class ParamMeta:
    key: str
    status: Status
    source: str = ""
    year: int | None = None
    url: str = ""
    low: float | None = None
    high: float | None = None
    note: str = ""


def _a(key: str, note: str) -> ParamMeta:
    return ParamMeta(key=key, status="assumption", note=note)


_BUSINESS_SPLIT = (
    "Split of non-agricultural business income by taxation form (the three shares sum to 1): "
    "scale -> taxed on the scale together with wages, flat -> pit_flat_rate, "
    "lump -> pit_lump_rate_default applied to revenue (see PIT_LUMP_REVENUE_TO_INCOME). "
    "Assumption: rough split, no verified source."
)

PARAMETERS: dict[str, ParamMeta] = {
    m.key: m
    for m in (
        _a("VAT_CONSUMPTION_SHARES", "Share of nominal private consumption (gross of VAT) by VAT rate category. Keys map to parameters: standard -> vat_rate_standard, reduced1 -> vat_rate_reduced1, reduced2 -> vat_rate_reduced2, zero -> 0% / exempt (no output VAT). Assumption: rough split; should come from MF/GUS data on consumption by VAT rate."),
        _a("VAT_GAP", "VAT compliance gap as a fraction of theoretical revenue. Assumption: order of magnitude only; replace with the latest VAT gap estimate for Poland (e.g. the European Commission VAT Gap report) after verification."),
        _a("VAT_PRICE_ELASTICITY", "Price elasticity of real consumption demand w.r.t. the consumer price (gross of VAT); assumes full pass-through of VAT changes to consumer prices. Assumption: illustrative value, no literature source verified."),
        _a("CIT_SMALL_TAXPAYER_SHARE", "Share of the CIT tax base attributable to small taxpayers (9% rate). Assumption: should come from MF CIT-8 aggregate statistics."),
        _a("PIT_INCOME_DIST_DEFAULT", "Default taxable-income distribution of taxpayers on the tax scale (skala podatkowa), as (mean annual taxable income in zł, number of taxpayers in millions) per group. Assumption: synthetic distribution shaped to look plausible; should be replaced by MF 'Informacja dotycząca rozliczenia podatku dochodowego od osób fizycznych' bracket data once loaded."),
        _a("PIT_BUSINESS_SCALE_SHARE", _BUSINESS_SPLIT),
        _a("PIT_BUSINESS_FLAT_SHARE", _BUSINESS_SPLIT),
        _a("PIT_BUSINESS_LUMP_SHARE", _BUSINESS_SPLIT),
        _a("PIT_LUMP_REVENUE_TO_INCOME", "Ratio of recorded revenue (ryczałt base) to income for lump-sum taxpayers. Assumption: illustrative value."),
        _a("PIT_BUSINESS_INCOME_TO_WAGE_BILL", "Non-agricultural business income (PIT base outside wages) as a ratio to the wage bill. No business-income series is loaded, so the projection ties it to the wage bill. Assumption: illustrative ratio; should come from MF PIT statistics."),
        _a("HOUSEHOLD_MPC", "Marginal propensity to consume out of disposable income: a PIT change of dT (mld zł) moves nominal consumption by -HOUSEHOLD_MPC * dT. Assumption: illustrative value, no literature source verified."),
        _a("CONSUMPTION_GDP_SHARE", "Share of private consumption in GDP: a relative change of real consumption x moves real GDP by CONSUMPTION_GDP_SHARE * x (no import leakage or offsets modelled). Assumption: order of magnitude only; should come from GUS national accounts."),
        _a("EMPLOYMENT_GDP_ELASTICITY", "Elasticity of employment w.r.t. real GDP (short-run, Okun-type). Assumption: illustrative value, no literature source verified."),
    )
}


def assumption_rows() -> list[dict]:
    """One row per registered constant: current config value plus its metadata."""
    rows: list[dict] = []
    for key, m in PARAMETERS.items():
        value = deepcopy(getattr(config, key))
        rows.append({
            "key": key,
            "value": [list(r) for r in value] if isinstance(value, tuple) else value,
            "status": m.status,
            "note": m.note,
            "source": m.source,
            "year": m.year,
            "url": m.url,
            "low": m.low,
            "high": m.high,
        })
    return rows
