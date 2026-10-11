import ast
from pathlib import Path

import pytest

from app.model import config
from app.model.param_meta import PARAMETERS, assumption_rows

KEYS = {
    "VAT_CONSUMPTION_SHARES",
    "VAT_GAP",
    "VAT_PRICE_ELASTICITY",
    "CIT_SMALL_TAXPAYER_SHARE",
    "PIT_INCOME_DIST_DEFAULT",
    "PIT_BUSINESS_SCALE_SHARE",
    "PIT_BUSINESS_FLAT_SHARE",
    "PIT_BUSINESS_LUMP_SHARE",
    "PIT_LUMP_REVENUE_TO_INCOME",
    "PIT_BUSINESS_INCOME_TO_WAGE_BILL",
    "HOUSEHOLD_MPC",
    "CONSUMPTION_GDP_SHARE",
    "EMPLOYMENT_GDP_ELASTICITY",
}


def test_every_numeric_config_constant_is_registered():
    method = {"CALIBRATION_YEARS", "STRUCTURAL_BREAKS"}
    found = {
        n for n, v in vars(config).items()
        if n.isupper() and isinstance(v, (int, float, dict, tuple)) and n not in method
    }
    assert found == set(PARAMETERS), found ^ set(PARAMETERS)


def test_every_config_constant_has_meta():
    assert set(PARAMETERS) == KEYS
    for key, meta in PARAMETERS.items():
        assert meta.key == key
        assert hasattr(config, key), key


def test_assumption_status_requires_note():
    for meta in PARAMETERS.values():
        assert meta.status in ("from_data", "sourced", "assumption")
        if meta.status == "assumption":
            assert meta.note.strip(), meta.key


def test_value_inside_declared_range():
    for key, meta in PARAMETERS.items():
        value = getattr(config, key)
        if isinstance(value, (int, float)) and meta.low is not None and meta.high is not None:
            assert meta.low <= value <= meta.high, key
    assert sum(config.VAT_CONSUMPTION_SHARES.values()) == pytest.approx(1.0)
    business = config.PIT_BUSINESS_SCALE_SHARE + config.PIT_BUSINESS_FLAT_SHARE + config.PIT_BUSINESS_LUMP_SHARE
    assert business == pytest.approx(1.0)


def test_assumption_rows_have_all_keys():
    rows = assumption_rows()
    assert {r["key"] for r in rows} == KEYS
    for r in rows:
        assert set(r) == {"key", "value", "status", "note", "source", "year", "url", "low", "high", "range_text"}
    by_key = {r["key"]: r for r in rows}
    assert by_key["VAT_GAP"]["value"] == config.VAT_GAP
    assert by_key["PIT_INCOME_DIST_DEFAULT"]["value"][0] == [5_000, 3.0]
    by_key["PIT_INCOME_DIST_DEFAULT"]["value"][0][0] = -1  # copies, not config internals
    by_key["VAT_CONSUMPTION_SHARES"]["value"]["standard"] = -1
    assert config.PIT_INCOME_DIST_DEFAULT[0][0] == 5_000 and config.VAT_CONSUMPTION_SHARES["standard"] == 0.55


MARKER = "PLACEHOLDER-UNVERIFIED"


def _comment_blocks() -> dict[str, list[str]]:
    """Constant name -> comment lines directly above its assignment in config.py."""
    path = Path(config.__file__)
    lines = path.read_text(encoding="utf-8").splitlines()
    blocks: dict[str, list[str]] = {}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name, i, block = node.target.id, node.lineno - 2, []
        elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            name, i, block = node.targets[0].id, node.lineno - 2, []
        else:
            continue
        while i >= 0 and lines[i].lstrip().startswith("#"):
            block.append(lines[i])
            i -= 1
        blocks[name] = block
    return blocks


def test_config_marker_only_on_assumptions():
    blocks = _comment_blocks()
    assert set(PARAMETERS) <= set(blocks)
    for key, meta in PARAMETERS.items():
        text = "\n".join(blocks[key])
        if meta.status == "assumption":
            assert MARKER in text, f"{key} is an assumption but has no {MARKER} comment"
        else:
            assert MARKER not in text, f"{key} is {meta.status} but carries {MARKER}"
            assert "docs/model-parameters.md" in text, f"{key} comment must point to docs/model-parameters.md"
    comment_lines = [ln for ln in Path(config.__file__).read_text(encoding="utf-8").splitlines() if ln.lstrip().startswith("#")]
    markers = sum(MARKER in ln for ln in comment_lines)
    assert markers == sum(m.status == "assumption" for m in PARAMETERS.values())
