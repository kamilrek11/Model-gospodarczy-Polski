import pandas as pd
import pytest

from app.data.transform import chain_growth


def s(d):
    return pd.Series(d, dtype="float64")


def test_chain_growth_forward_and_backward():
    out = chain_growth(s({2022: 105.3, 2023: 100.2, 2024: 103.0}), 2023, 200.0)
    assert out[2023] == pytest.approx(200.0)
    assert out[2024] == pytest.approx(206.0)
    assert out[2022] == pytest.approx(200.0 * 100 / 100.2)
    assert out.index.dtype == "int64"


def test_chain_growth_base_before_first_year():
    out = chain_growth(s({2003: 101.0, 2004: 102.0}), 2002, 100.0)
    assert list(out.index) == [2003, 2004]
    assert out[2003] == pytest.approx(101.0)
    assert out[2004] == pytest.approx(103.02)


def test_chain_growth_rejects_missing_year_gap():
    with pytest.raises(ValueError):
        chain_growth(s({2003: 101.0, 2005: 102.0}), 2002, 100.0)


def test_chain_growth_rejects_base_year_outside_range():
    with pytest.raises(ValueError):
        chain_growth(s({2003: 101.0, 2004: 102.0}), 2010, 100.0)
    with pytest.raises(ValueError):
        chain_growth(s({2003: 101.0, 2004: 102.0}), 2000, 100.0)
