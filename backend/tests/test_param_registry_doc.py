"""The human-readable parameter register (docs/model-parameters.md) must agree with param_meta.PARAMETERS."""

import re
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
    "PIT_STATE_SHARE_SIGMA": 0.2,  # added later; unchanged by definition
}


NUM = r"[−-]?\d+(?:,\d+)?"


def _num(text: str) -> float:
    """Polish number ('−0,5', '520 000', '0,109') -> float."""
    return float(text.replace(" ", "").replace("−", "-").replace(",", "."))


def _first_number(cell: str) -> float:
    m = re.search(NUM, cell)
    assert m, cell
    return _num(m[0])


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


def test_registry_covers_exactly_the_14_parameters(registry):
    assert len(PARAMETERS) == 14
    assert set(registry) == set(PARAMETERS), set(registry) ^ set(PARAMETERS)


def test_registry_status_matches_code(registry):
    for key, meta in PARAMETERS.items():
        assert registry[key]["Status"] == LABELS[meta.status], key


def test_source_cell_carries_year_and_url(registry):
    """Year as '(YYYY, ' (data year followed by the address), url verbatim; sourced needs all three fields."""
    for key, meta in PARAMETERS.items():
        cell = registry[key]["Źródło (rok, adres)"]
        if meta.status == "sourced":
            assert meta.source.strip() and meta.year and meta.url.startswith("http"), key
        if meta.status == "from_data":
            # computed from stored series: source names the series and the rule, year = last observation,
            # url = the source series (there is no publication of the constant itself)
            assert meta.source.strip() and meta.year and meta.url.startswith("http"), key
            assert "ostatni wspólny rok" in meta.source, key
        if meta.year is not None:
            assert f"({meta.year}, " in cell, f"{key}: '({meta.year}, ' missing in source cell"
        if meta.url:
            assert meta.url in cell, f"{key}: url missing in source cell"


def test_value_column_matches_config(registry):
    for key in PARAMETERS:
        value = getattr(config, key)
        cell = registry[key]["Wartość"]
        if isinstance(value, dict):
            pairs = dict(re.findall(r"(\w+)\s+([−-]?\d+(?:,\d+)?)", cell))
            assert {k: _num(v) for k, v in pairs.items()} == value, key
        elif isinstance(value, tuple):
            m = re.match(r"(\d+) grup.*od \(([\d ]+); ([\d,]+)\) do \(([\d ]+); ([\d,]+)\)", cell)
            assert m, key
            assert int(m[1]) == len(value), key
            assert (_num(m[2]), _num(m[3])) == tuple(value[0]), key
            assert (_num(m[4]), _num(m[5])) == tuple(value[-1]), key
        else:
            assert _first_number(cell) == value, f"{key}: register {cell!r} vs config {value}"


def test_range_column_matches_meta(registry):
    for key, meta in PARAMETERS.items():
        cell = registry[key]["Zakres"]
        if meta.low is not None or meta.high is not None:
            m = re.match(rf"({NUM})–({NUM})", cell)
            assert m, f"{key}: Zakres must start with 'low–high': {cell!r}"
            assert (_num(m[1]), _num(m[2])) == (meta.low, meta.high), key


def test_range_text_matches_register(registry):
    for key, meta in PARAMETERS.items():
        cell = registry[key]["Zakres"]
        if meta.range_text:
            assert cell.startswith(meta.range_text), f"{key}: {meta.range_text!r} vs {cell!r}"
        if meta.status == "assumption":
            assert (meta.low is not None and meta.high is not None) or meta.range_text, f"{key}: no range to display"


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
