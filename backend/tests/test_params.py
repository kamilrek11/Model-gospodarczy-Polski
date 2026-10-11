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
    "pit_state_share_mult": 1.0,
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


def test_contract_tax_values_lowercase_and_prefix_matches():
    from app.model.params import schema_as_dicts

    rows = TestClient(app).get("/parameters").json()
    assert rows == schema_as_dicts()
    assert {r["tax"] for r in rows} <= {"pit", "cit", "vat"}
    for r in rows:
        assert r["key"].startswith(r["tax"] + "_"), r


def test_frontend_parameters_fixture_matches_backend_schema():
    import json
    from pathlib import Path

    from app.model.params import schema_as_dicts

    path = Path(__file__).resolve().parents[2] / "frontend" / "src" / "testdata" / "parameters.json"
    assert json.loads(path.read_text(encoding="utf-8")) == schema_as_dicts(), "regenerate frontend/src/testdata/parameters.json from schema_as_dicts()"


def test_old_requests_without_the_multiplier_validate_to_default():
    assert validate({})["pit_state_share_mult"] == 1.0
    assert validate({"vat_rate_standard": 0.25, "pit_rate_low": 0.1})["pit_state_share_mult"] == 1.0


def test_multiplier_out_of_range_rejected():
    for bad in (0.4, 2.1):
        with pytest.raises(ValueError, match="poza zakresem"):
            validate({"pit_state_share_mult": bad})
    assert validate({"pit_state_share_mult": 0.5})["pit_state_share_mult"] == 0.5
    assert validate({"pit_state_share_mult": 2.0})["pit_state_share_mult"] == 2.0
