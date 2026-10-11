"""The human-readable parameter register (docs/model-parameters.md) must agree with param_meta.PARAMETERS."""

from pathlib import Path

import pytest

from app.model import config
from app.model.param_meta import PARAMETERS

REGISTRY = Path(__file__).resolve().parents[2] / "docs" / "model-parameters.md"

COLUMNS = ["Klucz", "Wartość", "Jednostka", "Status", "Źródło (rok, adres)", "Zakres", "Uwagi", "Wynik przed→po"]
LABELS = {"from_data": "z danych", "sourced": "ze źródła", "assumption": "założenie"}

# config values at the base commit of this change (before the source research), see git ae1c5a6
PRE_VALUES = {
    "VAT_CONSUMPTION_SHARES": {"standard": 0.55, "reduced1": 0.15, "reduced2": 0.12, "zero": 0.18},
    "VAT_GAP": 0.07,
    "VAT_PRICE_ELASTICITY": -0.5,
    "CIT_SMALL_TAXPAYER_SHARE": 0.10,
    "PIT_INCOME_DIST_DEFAULT": (
        (5_000, 3.0), (15_000, 2.5), (25_000, 2.5), (35_000, 2.5), (45_000, 2.5), (55_000, 2.2), (65_000, 1.9),
        (77_000, 2.2), (92_000, 1.5), (109_000, 1.2), (133_000, 0.8), (170_000, 0.5), (240_000, 0.25), (520_000, 0.15),
    ),
    "PIT_BUSINESS_SCALE_SHARE": 0.35,
    "PIT_BUSINESS_FLAT_SHARE": 0.40,
    "PIT_BUSINESS_LUMP_SHARE": 0.25,
    "PIT_LUMP_REVENUE_TO_INCOME": 2.0,
    "PIT_BUSINESS_INCOME_TO_WAGE_BILL": 0.25,
    "HOUSEHOLD_MPC": 0.6,
    "CONSUMPTION_GDP_SHARE": 0.57,
    "EMPLOYMENT_GDP_ELASTICITY": 0.5,
}


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_registry(path: Path) -> dict[str, dict]:
    """Rows of the first markdown table whose header is COLUMNS: key (without backticks) -> {column: cell}."""
    lines = path.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if line.lstrip().startswith("|") and _cells(line) == COLUMNS:
            break
    else:
        raise AssertionError(f"no table with columns {COLUMNS} in {path}")
    rows: dict[str, dict] = {}
    for line in lines[i + 2:]:
        if not line.lstrip().startswith("|"):
            break
        cells = _cells(line)
        assert len(cells) == len(COLUMNS), f"wrong number of cells ({len(cells)}): {line}"
        key = cells[0].strip("`")
        assert key not in rows, f"duplicate row {key}"
        rows[key] = dict(zip(COLUMNS, cells))
    return rows


@pytest.fixture(scope="module")
def registry() -> dict[str, dict]:
    assert REGISTRY.exists(), f"missing {REGISTRY}"
    return parse_registry(REGISTRY)


def test_registry_covers_exactly_the_13_parameters(registry):
    assert len(PARAMETERS) == 13
    assert set(registry) == set(PARAMETERS), set(registry) ^ set(PARAMETERS)


def test_registry_status_matches_code(registry):
    for key, meta in PARAMETERS.items():
        assert registry[key]["Status"] == LABELS[meta.status], key


def test_sourced_entries_have_source_year_and_url(registry):
    for key, meta in PARAMETERS.items():
        if meta.status == "sourced":
            assert meta.source.strip() and meta.year and meta.url.startswith("http"), key
            cell = registry[key]["Źródło (rok, adres)"]
            assert str(meta.year) in cell and meta.url in cell, key
        if meta.status == "from_data":
            assert meta.source.strip(), key
            assert registry[key]["Źródło (rok, adres)"], key
        if meta.status != "assumption":
            assert registry[key]["Zakres"], key


def test_assumptions_explain_missing_source(registry):
    for key, meta in PARAMETERS.items():
        if meta.status == "assumption":
            assert meta.note.strip(), key
            assert registry[key]["Uwagi"], key
            assert registry[key]["Zakres"], key


def test_changed_values_have_before_after(registry):
    assert set(PRE_VALUES) == set(PARAMETERS)
    for key, before in PRE_VALUES.items():
        if getattr(config, key) != before:
            assert registry[key]["Wynik przed→po"], f"{key} changed but has no before→after result"


def test_registry_has_income_distribution_section():
    text = REGISTRY.read_text(encoding="utf-8")
    assert "## Rozkład dochodów PIT" in text
