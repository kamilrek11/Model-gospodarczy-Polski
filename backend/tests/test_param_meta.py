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
        assert set(r) == {"key", "value", "status", "note", "source", "year", "url", "low", "high"}
    by_key = {r["key"]: r for r in rows}
    assert by_key["VAT_GAP"]["value"] == config.VAT_GAP
    assert by_key["PIT_INCOME_DIST_DEFAULT"]["value"][0] == [5_000, 3.0]
    by_key["PIT_INCOME_DIST_DEFAULT"]["value"][0][0] = -1  # copies, not config internals
    by_key["VAT_CONSUMPTION_SHARES"]["value"]["standard"] = -1
    assert config.PIT_INCOME_DIST_DEFAULT[0][0] == 5_000 and config.VAT_CONSUMPTION_SHARES["standard"] == 0.55
