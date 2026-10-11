"""Series-name -> source identifiers.

BDL ids are verified against the live API (docs/data-sources-discovery.md, 2026-10-10).
The MF budget-execution rows are verified against the published reports 2016-2025
(dane.gov.pl dataset 163, docs/data-sources-discovery.md section "MF – macierz lat").
"""

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

# MF "Część tabelaryczna sprawozdania z wykonania budżetu państwa", dane.gov.pl dataset 163:
# per-year ZIP -> "TOM I" ZIP -> "007- DOCHODY BP ZESTAWIENIE OGÓŁEM.xlsx", column "Wykonanie",
# values in tys. zł (state budget, cash). Rows are matched by their full label.
MF_DATASET_ID = 163
MF_EXECUTION_ROWS: dict[str, str] = {
    "rev_vat": "1.1. Podatek od towarów i usług",
    "rev_cit": "1.4. Podatek dochodowy od osób prawnych",
    "rev_pit": "1.5. Podatek dochodowy od osób fizycznych",
}
