import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.model.params import PARAMETER_SCHEMA, defaults, validate

EXPECTED = {
    "pit_rate_low": 0.12,
    "pit_rate_high": 0.32,
    "pit_threshold": 120000,
    "pit_tax_free": 30000,
    "pit_flat_rate": 0.19,
    "pit_lump_rate_default": 0.12,
    "vat_rate_standard": 0.23,
    "vat_rate_reduced1": 0.08,
    "vat_rate_reduced2": 0.05,
    "cit_rate": 0.19,
    "cit_rate_small": 0.09,
}


def test_defaults_match_current_law():
    assert defaults() == EXPECTED


def test_validate_fills_missing_with_defaults():
    out = validate({"vat_rate_standard": 0.25})
    assert out["vat_rate_standard"] == 0.25
    assert out["cit_rate"] == 0.19


def test_validate_rejects_unknown_key():
    with pytest.raises(ValueError):
        validate({"nope": 1})


def test_validate_rejects_out_of_range():
    with pytest.raises(ValueError):
        validate({"vat_rate_standard": 1.5})
    with pytest.raises(ValueError):
        validate({"pit_threshold": -1})


def test_get_parameters_endpoint_lists_all_keys():
    r = TestClient(app).get("/parameters")
    assert r.status_code == 200
    assert {p["key"] for p in r.json()} == set(EXPECTED)
    assert len(PARAMETER_SCHEMA) == len(EXPECTED)
