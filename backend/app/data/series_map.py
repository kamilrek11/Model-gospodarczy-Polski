"""Series-name -> source identifiers.

BDL ids are verified against the live API (docs/data-sources-discovery.md, 2026-10-10).
The execution (MF) endpoints are still unverified placeholders: sentinels starting with
TODO_VERIFY make that client raise SourceError("series not mapped").
"""

UNVERIFIED_PREFIX = "TODO_VERIFY"

# BDL variable ids. The national unit is requested with `unit-level=0` and must be
# id "000000000000" (name "POLSKA").
BDL_SERIES: dict[str, str] = {
    "pkb_growth": "458431",  # GDP real, previous year = 100 (index)
    "gdp_nominal": "458271",  # mln zl
    "employment": "154173",  # average paid employment (etaty)
    "wage_nominal": "64428",  # zl / month, gross
    "cpi_growth": "217230",  # CPI, previous year = 100 (index)
    "gross_surplus": "458419",  # mln zl
}
BDL_NATIONAL_UNIT_ID = "000000000000"

# PLACEHOLDER-UNVERIFIED: confirm against live API (values in mld zl)
EXECUTION_ENDPOINTS: dict[str, str] = {
    "rev_pit": "TODO_VERIFY_URL_PIT",  # PLACEHOLDER-UNVERIFIED: confirm against live API
    "rev_cit": "TODO_VERIFY_URL_CIT",  # PLACEHOLDER-UNVERIFIED: confirm against live API
    "rev_vat": "TODO_VERIFY_URL_VAT",  # PLACEHOLDER-UNVERIFIED: confirm against live API
}


def is_unmapped(value: str | None) -> bool:
    return not value or str(value).startswith(UNVERIFIED_PREFIX)
