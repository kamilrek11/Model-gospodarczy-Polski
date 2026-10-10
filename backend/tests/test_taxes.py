import itertools

import numpy as np
import pytest

from app.model import config
from app.model.params import defaults
from app.model.taxes.cit import cit_revenue
from app.model.taxes.pit import IncomeDist, default_income_dist, pit_revenue, scale_tax
from app.model.taxes.vat import consumption_feedback, effective_vat_rate, vat_revenue

YEARS = 3


def _cons():
    return np.full(YEARS, 1230.0)  # mld zł, gross of VAT


def _single_person_dist(income=100_000.0):
    return IncomeDist(incomes=np.array([income]), taxpayers=np.array([1.0]))


# ---------------------------------------------------------------- VAT

def test_vat_standard_rate_up_increases_revenue():
    base = defaults()
    shares = {"standard": 1.0}
    r0 = vat_revenue(_cons(), shares, base, gap=0.0, elasticity=0.0, base_p=base)
    # net base = 1230 / 1.23 = 1000; 23% of it
    np.testing.assert_allclose(r0, 230.0)
    p = dict(base, vat_rate_standard=0.46)
    r1 = vat_revenue(_cons(), shares, p, gap=0.0, elasticity=0.0, base_p=base)
    # elasticity 0 -> revenue proportional to the rate
    np.testing.assert_allclose(r1, 2 * r0)


def test_vat_gap_scales_revenue():
    base = defaults()
    r = vat_revenue(_cons(), {"standard": 1.0}, base, gap=0.1, elasticity=0.0, base_p=base)
    np.testing.assert_allclose(r, 207.0)


def test_vat_elasticity_dampens_increase():
    base = defaults()
    shares = {"standard": 1.0}
    p = dict(base, vat_rate_standard=0.25)
    r0 = vat_revenue(_cons(), shares, base, gap=0.0, elasticity=-0.5, base_p=base)
    r_lin = vat_revenue(_cons(), shares, p, gap=0.0, elasticity=0.0, base_p=base)
    r_el = vat_revenue(_cons(), shares, p, gap=0.0, elasticity=-0.5, base_p=base)
    assert np.all(r_el > r0)
    assert np.all(r_el < r_lin)
    # exact: 0.25 * 1000 * (1.25/1.23)^-0.5
    np.testing.assert_allclose(r_el, 250.0 * (1.25 / 1.23) ** -0.5)


def test_vat_zero_share_contributes_nothing_and_default_shares_sum_to_one():
    base = defaults()
    r = vat_revenue(_cons(), {"zero": 1.0}, base, gap=0.0, elasticity=-0.5, base_p=base)
    np.testing.assert_allclose(r, 0.0)
    assert sum(config.VAT_CONSUMPTION_SHARES.values()) == pytest.approx(1.0)


def test_vat_unknown_share_key_rejected():
    base = defaults()
    with pytest.raises(ValueError):
        vat_revenue(_cons(), {"23": 1.0}, base, gap=0.0, elasticity=0.0, base_p=base)


def test_consumption_feedback():
    assert consumption_feedback(0.2, 0.2, -0.5) == pytest.approx(0.0)
    up = consumption_feedback(0.2, 0.22, -0.5)
    assert up == pytest.approx((1.22 / 1.2) ** -0.5 - 1)
    assert up < 0
    assert consumption_feedback(0.2, 0.18, -0.5) > 0
    assert consumption_feedback(0.2, 0.3, 0.0) == pytest.approx(0.0)


def test_vat_volume_response_equals_feedback_contract():
    # Contract: vat_revenue owns the volume response. Its elasticity effect is exactly
    # the consumption_feedback factor, so feeding feedback-adjusted consumption back
    # into vat_revenue would apply the response twice.
    base = defaults()
    shares = {"standard": 1.0}
    p = dict(base, vat_rate_standard=0.27)
    e = -0.5
    r_lin = vat_revenue(_cons(), shares, p, gap=0.0, elasticity=0.0, base_p=base)
    r_el = vat_revenue(_cons(), shares, p, gap=0.0, elasticity=e, base_p=base)
    fb = consumption_feedback(0.23, 0.27, e)
    np.testing.assert_allclose(r_el, r_lin * (1 + fb))
    double = vat_revenue(_cons() * (1 + fb), shares, p, gap=0.0, elasticity=e, base_p=base)
    assert np.all(double < r_el)  # the double-counted path the docstring forbids


def test_vat_docstrings_state_contract():
    assert "pre-feedback" in vat_revenue.__doc__
    assert "must not" in consumption_feedback.__doc__


def test_effective_vat_rate_default():
    base = defaults()
    shares = {"standard": 0.5, "reduced1": 0.5}
    assert effective_vat_rate(shares, base) == pytest.approx(0.155)


# ---------------------------------------------------------------- CIT

def test_cit_zero_rate_zero_revenue():
    p = dict(defaults(), cit_rate=0.0, cit_rate_small=0.0)
    r = cit_revenue(np.full(YEARS, 500.0), small_share=0.1, p=p, calib=0.2)
    np.testing.assert_allclose(r, 0.0)


def test_cit_blended_rate():
    r = cit_revenue(np.full(YEARS, 500.0), small_share=0.1, p=defaults(), calib=0.2)
    # 500 * 0.2 * (0.9*0.19 + 0.1*0.09) = 100 * 0.18
    np.testing.assert_allclose(r, 18.0)


# ---------------------------------------------------------------- PIT

def test_scale_tax_default_values():
    p = defaults()
    # 50 000: 0.12*50000 - 3600 = 2400
    assert scale_tax(np.array([50_000.0]), p)[0] == pytest.approx(2400.0)
    # 200 000: 0.12*120000 - 3600 + 0.32*80000 = 36400
    assert scale_tax(np.array([200_000.0]), p)[0] == pytest.approx(36400.0)
    # below tax-free amount -> 0
    assert scale_tax(np.array([20_000.0]), p)[0] == 0.0


def test_pit_threshold_zero_all_taxed_high():
    p = dict(defaults(), pit_threshold=0)
    wage = np.full(YEARS, 100.0)
    r = pit_revenue(wage, np.zeros(YEARS), _single_person_dist(100_000.0), p, calib=1.0)
    # whole base at 32% minus reducing amount 0.12*30000: (32000-3600)/100000 = 0.284
    np.testing.assert_allclose(r, 28.4)


def test_pit_tax_free_above_threshold_nonnegative():
    p = dict(defaults(), pit_tax_free=200_000, pit_threshold=50_000)
    r = pit_revenue(np.full(YEARS, 900.0), np.full(YEARS, 300.0), default_income_dist(), p, calib=1.0)
    assert np.all(np.isfinite(r))
    assert np.all(r >= 0)


def test_pit_threshold_acts_on_distribution():
    dist = default_income_dist()
    wage, bus = np.full(YEARS, 900.0), np.zeros(YEARS)
    base = defaults()
    r0 = pit_revenue(wage, bus, dist, base, calib=1.0)
    r_lower = pit_revenue(wage, bus, dist, dict(base, pit_threshold=60_000), calib=1.0)
    r_higher_free = pit_revenue(wage, bus, dist, dict(base, pit_tax_free=40_000), calib=1.0)
    assert np.all(r_lower > r0)
    assert np.all(r_higher_free < r0)


def test_pit_business_income_channels():
    base = dict(defaults(), pit_rate_low=0.0, pit_rate_high=0.0)
    dist = _single_person_dist()
    bus = np.full(YEARS, 100.0)
    r = pit_revenue(np.zeros(YEARS), bus, dist, base, calib=1.0)
    expected = 100.0 * (
        config.PIT_BUSINESS_FLAT_SHARE * base["pit_flat_rate"]
        + config.PIT_BUSINESS_LUMP_SHARE * config.PIT_LUMP_REVENUE_TO_INCOME * base["pit_lump_rate_default"]
    )
    np.testing.assert_allclose(r, expected)


def test_pit_bracket_creep_with_wage_growth():
    dist = default_income_dist()
    p = defaults()
    wage = np.array([900.0, 1800.0])
    r = pit_revenue(wage, np.zeros(2), dist, p, calib=1.0)
    # doubling nominal incomes raises the effective rate (fixed thresholds)
    assert r[1] / wage[1] > r[0] / wage[0]


def test_pit_level_shift_changes_effective_rate():
    # a level cut in year 0 must lower the effective rate (no re-anchoring to year 0)
    dist = default_income_dist()
    p = defaults()
    zero = np.zeros(1)
    r_base = pit_revenue(np.array([900.0]), zero, dist, p, calib=1.0)
    r_cut = pit_revenue(np.array([810.0]), zero, dist, p, calib=1.0)
    assert r_cut[0] / 810.0 < r_base[0] / 900.0 - 1e-4


def test_pit_anchor_independent_of_other_paths():
    # result for a year must not depend on the first element of the array (path 0 draw)
    dist = default_income_dist()
    p = defaults()
    a = pit_revenue(np.array([500.0, 900.0]), np.zeros(2), dist, p, calib=1.0)
    b = pit_revenue(np.array([1500.0, 900.0]), np.zeros(2), dist, p, calib=1.0)
    assert a[1] == pytest.approx(b[1])


def test_income_dist_default_reference_base_is_distribution_total():
    dist = default_income_dist()
    rows = np.array(config.PIT_INCOME_DIST_DEFAULT)
    # taxpayers in millions, incomes in zł -> mld zł
    assert dist.reference_base == pytest.approx(float(np.sum(rows[:, 0] * rows[:, 1])) / 1000.0)
    assert IncomeDist(incomes=np.array([1.0]), taxpayers=np.array([1.0]), reference_base=5.0).reference_base == 5.0


def test_income_dist_validation():
    with pytest.raises(ValueError):
        IncomeDist(incomes=np.array([1.0, 2.0]), taxpayers=np.array([1.0]))
    with pytest.raises(ValueError):
        IncomeDist(incomes=np.array([-1.0]), taxpayers=np.array([1.0]))


# ---------------------------------------------------------------- extremes

def test_modules_finite_for_extreme_params():
    keys = list(defaults())
    cons = _cons()
    gos = np.full(YEARS, 800.0)
    wage, bus = np.full(YEARS, 900.0), np.full(YEARS, 300.0)
    dist = default_income_dist()
    base = defaults()
    for combo in itertools.product([0.0, 1.0], repeat=len(keys)):
        p = dict(base)
        for k, flag in zip(keys, combo):
            if k == "pit_threshold":
                p[k] = 1_000_000 if flag else 0
            elif k == "pit_tax_free":
                p[k] = 200_000 if flag else 0
            else:
                p[k] = flag
        for res in (
            vat_revenue(cons, config.VAT_CONSUMPTION_SHARES, p, config.VAT_GAP, config.VAT_PRICE_ELASTICITY, base),
            cit_revenue(gos, config.CIT_SMALL_TAXPAYER_SHARE, p, calib=0.2),
            pit_revenue(wage, bus, dist, p, calib=1.0),
        ):
            assert res.shape == (YEARS,)
            assert np.all(np.isfinite(res)), (p, res)
            assert np.all(res >= 0), (p, res)
    # extreme effective rates in feedback
    for a, b in itertools.product([0.0, 1.0], repeat=2):
        assert np.isfinite(consumption_feedback(a, b, config.VAT_PRICE_ELASTICITY))
