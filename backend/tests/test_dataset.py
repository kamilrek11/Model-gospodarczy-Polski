"""Dataset assembly and quality gates on REAL recorded data (tests/real_dataset.py); no network."""

import numpy as np
import pandas as pd
import pytest

from app.data.dataset import assemble, validate_dataset
from tests.real_dataset import real_results


def scaled(results: dict, name: str, factor: float) -> dict:
    out = dict(results)
    out[name] = results[name] * factor
    return out


def test_real_dataset_passes_all_gates():
    assert validate_dataset(real_results()) == []


def test_assemble_extends_gross_surplus_from_eurostat_after_bdl_last_year():
    res = real_results()
    bdl, eu = res["gross_surplus"]["value"], res["gross_surplus_eurostat"]["value"]
    assert bdl.index.max() == 2023 and eu.index.max() == 2025  # recorded data

    out = assemble(res)

    source, gs = out["gross_surplus"]
    assert source == "gus_bdl+eurostat"
    assert list(gs.index) == list(range(int(bdl.index.min()), 2026))
    assert gs.index.name == "year" and gs.index.dtype == np.int64 and gs["value"].dtype == np.float64
    # years up to BDL's last year come from BDL, later years from Eurostat
    pd.testing.assert_series_equal(gs["value"].loc[:2023], bdl, check_names=False)
    assert gs.loc[2023, "value"] == pytest.approx(1676.697)
    assert gs.loc[2024, "value"] == eu.loc[2024] and gs.loc[2025, "value"] == eu.loc[2025]
    assert "gross_surplus_eurostat" not in out


def test_assemble_labels_each_series_with_its_source():
    out = assemble(real_results())
    assert {k: s for k, (s, _) in out.items()} == {
        "pkb_real": "gus_bdl",
        "employment": "gus_bdl",
        "wage_nominal": "gus_bdl",
        "cpi": "gus_bdl",
        "gdp_nominal": "gus_bdl",
        "gross_surplus": "gus_bdl+eurostat",
        "consumption_nominal": "eurostat",
        "rev_vat": "mf_execution",
        "rev_cit": "mf_execution",
        "rev_pit": "mf_execution",
    }
    assert out["rev_vat"][1].loc[2024, "value"] == pytest.approx(287.68336891)
    assert out["consumption_nominal"][1].loc[2024, "value"] == pytest.approx(2056.557)


def test_assemble_without_eurostat_surplus_keeps_bdl():
    res = real_results()
    del res["gross_surplus_eurostat"]
    source, gs = assemble(res)["gross_surplus"]
    assert source == "gus_bdl" and gs.index.max() == 2023


def test_validate_flags_thousand_fold_unit_error():
    violations = validate_dataset(scaled(real_results(), "consumption_nominal", 1000.0))
    assert len(violations) == 1
    assert "konsumpcj" in violations[0] and "PKB" in violations[0] and "[0,4; 0,7]" in violations[0]
    assert "2024" in violations[0]  # last common year
    # the other direction (mld read as tys.) too
    assert validate_dataset(scaled(real_results(), "gdp_nominal", 1000.0))


def test_validate_flags_wrong_vat_scale():
    for factor in (1000.0, 0.001):
        violations = validate_dataset(scaled(real_results(), "rev_vat", factor))
        assert len(violations) == 1, violations
        assert "rev_vat" in violations[0] and "[100; 500]" in violations[0] and "2025" in violations[0]
    assert any("rev_cit" in v for v in validate_dataset(scaled(real_results(), "rev_cit", 1000.0)))
    assert any("rev_pit" in v for v in validate_dataset(scaled(real_results(), "rev_pit", 0.001)))


def test_validate_rev_pit_2025_break_value_is_within_bounds():
    # the real 2025 state-budget PIT (28.75 mld zł, JST reform) is a structural break, not a unit error
    res = real_results()
    assert res["rev_pit"]["value"].iloc[-1] == pytest.approx(28.75211501)
    assert not any("rev_pit" in v for v in validate_dataset(res))


def test_validate_requires_15_contiguous_macro_years():
    res = real_results()
    emp = res["employment"]
    res["employment"] = emp.drop(index=2014)  # 2005-2013 (9) and 2015-2024 (10)
    violations = validate_dataset(res)
    assert len(violations) == 1
    assert "15" in violations[0] and "10" in violations[0] and "2015–2024" in violations[0]

    res = real_results()
    res["employment"] = res["employment"].loc[2011:]  # 14 years
    assert any("14" in v and "15" in v for v in validate_dataset(res))

    res = real_results()
    res["employment"] = res["employment"].loc[2010:]  # exactly 15
    assert validate_dataset(res) == []


def test_validate_names_missing_series():
    res = real_results()
    del res["cpi"], res["rev_cit"]
    violations = validate_dataset(res)
    assert any("cpi" in v for v in violations)
    assert any("rev_cit" in v for v in violations)


def test_validate_gross_surplus_sources_disagree():
    res = real_results()
    eu = res["gross_surplus_eurostat"].copy()
    eu.loc[2020, "value"] *= 1.05
    res["gross_surplus_eurostat"] = eu
    violations = validate_dataset(res)
    assert len(violations) == 1
    assert "nadwyżk" in violations[0].lower() and "2020" in violations[0] and "2%" in violations[0]
    # the real difference (2023: 1676.697 vs 1684.850 = 0.5%) is accepted
    assert validate_dataset(real_results()) == []


def test_validate_flags_nan_and_negative_amounts():
    res = real_results()
    vat = res["rev_vat"].copy()
    vat.loc[2018, "value"] = np.nan
    res["rev_vat"] = vat
    gs = res["gross_surplus"].copy()
    gs.loc[2010, "value"] = -5.0
    res["gross_surplus"] = gs
    violations = validate_dataset(res)
    assert any("rev_vat" in v and "2018" in v and "brak wartości" in v for v in violations)
    assert any("gross_surplus" in v and "2010" in v and "ujemn" in v for v in violations)
