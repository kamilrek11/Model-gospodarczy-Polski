"""Metadata registry for the 13 non-user constants of app.model.config.

status: from_data (computed from loaded series), sourced (published source with url),
assumption (no verified source; `note` must say why).
Values stay in config.py; this module only describes them.
"""

from dataclasses import dataclass
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
    "Split of non-agricultural business income by taxation form (shares sum to 1): rough split; "
    "no verified source."
)

PARAMETERS: dict[str, ParamMeta] = {
    m.key: m
    for m in (
        _a("VAT_CONSUMPTION_SHARES", "Rough split of consumption by VAT rate; should come from MF/GUS data on consumption by VAT rate."),
        _a("VAT_GAP", "Order of magnitude only; replace with the latest VAT gap estimate for Poland (e.g. the European Commission VAT Gap report) after verification."),
        _a("VAT_PRICE_ELASTICITY", "Illustrative value, no literature source verified."),
        _a("CIT_SMALL_TAXPAYER_SHARE", "Should come from MF CIT-8 aggregate statistics."),
        _a("PIT_INCOME_DIST_DEFAULT", "Synthetic distribution shaped to look plausible; should be replaced by MF 'Informacja dotycząca rozliczenia podatku dochodowego od osób fizycznych' bracket data once loaded."),
        _a("PIT_BUSINESS_SCALE_SHARE", _BUSINESS_SPLIT),
        _a("PIT_BUSINESS_FLAT_SHARE", _BUSINESS_SPLIT),
        _a("PIT_BUSINESS_LUMP_SHARE", _BUSINESS_SPLIT),
        _a("PIT_LUMP_REVENUE_TO_INCOME", "Illustrative value."),
        _a("PIT_BUSINESS_INCOME_TO_WAGE_BILL", "Illustrative ratio; should come from MF PIT statistics."),
        _a("HOUSEHOLD_MPC", "Illustrative value, no literature source verified."),
        _a("CONSUMPTION_GDP_SHARE", "Order of magnitude only; should come from GUS national accounts."),
        _a("EMPLOYMENT_GDP_ELASTICITY", "Illustrative value, no literature source verified."),
    )
}


def assumption_rows() -> list[dict]:
    """One row per registered constant: current config value plus its metadata."""
    rows: list[dict] = []
    for key, m in PARAMETERS.items():
        value = getattr(config, key)
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
