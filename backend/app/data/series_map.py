"""Series-name -> source identifiers.

ALL entries are unverified: the sandbox had no access to bdl.stat.gov.pl / MF / ZUS.
Sentinels starting with TODO_VERIFY make clients raise SourceError("series not mapped").
"""

UNVERIFIED_PREFIX = "TODO_VERIFY"

# PLACEHOLDER-UNVERIFIED: confirm against live API
BDL_SERIES: dict[str, dict] = {
    "pkb_real": {"var_id": "TODO_VERIFY_PKB_REAL", "unit": "Polska"},  # PLACEHOLDER-UNVERIFIED: confirm against live API
    "employment": {"var_id": "TODO_VERIFY_EMPLOYMENT", "unit": "Polska"},  # PLACEHOLDER-UNVERIFIED: confirm against live API
    "wage_nominal": {"var_id": "TODO_VERIFY_WAGE_NOMINAL", "unit": "Polska"},  # PLACEHOLDER-UNVERIFIED: confirm against live API
    "cpi": {"var_id": "TODO_VERIFY_CPI", "unit": "Polska"},  # PLACEHOLDER-UNVERIFIED: confirm against live API
    "consumption_nominal": {"var_id": "TODO_VERIFY_CONSUMPTION", "unit": "Polska"},  # PLACEHOLDER-UNVERIFIED: confirm against live API
    "gross_surplus": {"var_id": "TODO_VERIFY_GROSS_SURPLUS", "unit": "Polska"},  # PLACEHOLDER-UNVERIFIED: confirm against live API
}

# PLACEHOLDER-UNVERIFIED: confirm against live API (values in mld zl)
EXECUTION_ENDPOINTS: dict[str, str] = {
    "rev_pit": "TODO_VERIFY_URL_PIT",  # PLACEHOLDER-UNVERIFIED: confirm against live API
    "rev_cit": "TODO_VERIFY_URL_CIT",  # PLACEHOLDER-UNVERIFIED: confirm against live API
    "rev_vat": "TODO_VERIFY_URL_VAT",  # PLACEHOLDER-UNVERIFIED: confirm against live API
}


def is_unmapped(value: str | None) -> bool:
    return not value or str(value).startswith(UNVERIFIED_PREFIX)
