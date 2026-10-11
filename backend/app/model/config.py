"""Non-user model parameters used by the tax modules.

Every constant has a status in docs/model-parameters.md (machine-readable copy:
app/model/param_meta.py): from_data, sourced or assumption. Only constants whose status is
`assumption` carry the marker PLACEHOLDER-UNVERIFIED in the comment above them: the number has
NO verified published source and must be replaced (or confirmed) before results are presented
as anything but illustrative. tests/test_param_meta.py keeps the markers and the statuses in step.
Tax functions stay pure: callers pass these values in as arguments.
Status, source, year and uncertainty range of every constant: docs/model-parameters.md
(machine-readable copy: app/model/param_meta.py).
"""

# ---------------------------------------------------------------- VAT

# Share of nominal private consumption (gross of VAT) by VAT rate category.
# Keys map to parameters: standard -> vat_rate_standard, reduced1 -> vat_rate_reduced1,
# reduced2 -> vat_rate_reduced2, zero -> 0% / exempt (no output VAT).
# PLACEHOLDER-UNVERIFIED: rough split; no GUS/MF publication gives consumption by VAT rate.
# Status and range: docs/model-parameters.md.
VAT_CONSUMPTION_SHARES: dict[str, float] = {
    "standard": 0.55,
    "reduced1": 0.15,
    "reduced2": 0.12,
    "zero": 0.18,
}

# VAT compliance gap as a fraction of theoretical revenue (VTTL).
# Source: European Commission, "VAT gap in Europe - report 2025", tables (xlsx), Table 205: Poland 2024
# fast estimate 10.9% (full estimates: 2021 4.8%, 2022 11.2%, 2023 16.0%). See docs/model-parameters.md.
# The term is purely multiplicative and is absorbed by the VAT calibration factor.
VAT_GAP: float = 0.109

# Price elasticity of real consumption demand w.r.t. the consumer price (gross of VAT).
# Assumes full pass-through of VAT changes to consumer prices.
# PLACEHOLDER-UNVERIFIED: illustrative value, no literature source verified. See docs/model-parameters.md.
VAT_PRICE_ELASTICITY: float = -0.5

# ---------------------------------------------------------------- CIT

# Share of the CIT tax base attributable to small taxpayers (9% rate).
# Source: MF "Informacja dotycząca rozliczenia podatku CIT za 2021 r." (dane.gov.pl dataset 162): tax due at 9%
# 2 700 278 tys. zł, at 19% 65 220 084 tys. zł -> base share 30.0 / (30.0 + 343.3) = 8.0%. See docs/model-parameters.md.
CIT_SMALL_TAXPAYER_SHARE: float = 0.08

# ---------------------------------------------------------------- PIT

# Default taxable-income distribution of taxpayers on the tax scale (skala podatkowa),
# as (mean annual taxable income in zł, number of taxpayers in millions) per group.
# PLACEHOLDER-UNVERIFIED: synthetic distribution shaped to look plausible; MF publishes only two
# brackets (see docs/model-parameters.md, section "Rozkład dochodów PIT").
PIT_INCOME_DIST_DEFAULT: tuple[tuple[float, float], ...] = (
    (5_000, 3.0),
    (15_000, 2.5),
    (25_000, 2.5),
    (35_000, 2.5),
    (45_000, 2.5),
    (55_000, 2.2),
    (65_000, 1.9),
    (77_000, 2.2),
    (92_000, 1.5),
    (109_000, 1.2),
    (133_000, 0.8),
    (170_000, 0.5),
    (240_000, 0.25),
    (520_000, 0.15),
)

# Split of non-agricultural business income by taxation form (shares sum to 1).
# scale -> taxed on the scale together with wages, flat -> pit_flat_rate,
# lump -> pit_lump_rate_default applied to revenue (see PIT_LUMP_REVENUE_TO_INCOME).
# Components (2021): MF "Informacja dotycząca rozliczenia PIT za 2021 r." - business income on the scale 43 450 mln zł,
# PIT-36L business income 228 957 mln zł; MF "Informacja dotycząca ryczałtu ... za 2021 r." - business revenue
# 89 466 mln zł converted to income with PIT_LUMP_REVENUE_TO_INCOME (an assumption). See docs/model-parameters.md.
# PLACEHOLDER-UNVERIFIED (assumption derived from MF 2021 data + the assumed PIT_LUMP_REVENUE_TO_INCOME).
PIT_BUSINESS_SCALE_SHARE: float = 0.14
# PLACEHOLDER-UNVERIFIED (as PIT_BUSINESS_SCALE_SHARE; the three shares sum to 1).
PIT_BUSINESS_FLAT_SHARE: float = 0.72
# PLACEHOLDER-UNVERIFIED (as PIT_BUSINESS_SCALE_SHARE; the three shares sum to 1).
PIT_BUSINESS_LUMP_SHARE: float = 0.14

# Ratio of recorded revenue (ryczałt base) to income for lump-sum taxpayers.
# PLACEHOLDER-UNVERIFIED: illustrative value, MF does not publish lump-sum costs. See docs/model-parameters.md.
PIT_LUMP_REVENUE_TO_INCOME: float = 2.0

# Non-agricultural business income (PIT base outside wages) as a ratio to the wage bill.
# No business-income series is loaded, so the projection ties it to the wage bill.
# Components (2021): business income as above (317.1 mld zł) / model wage bill 2021 (GUS BDL wage x employment x 12
# = 783.1 mld zł) = 0.405, rounded to 0.40. See docs/model-parameters.md.
# PLACEHOLDER-UNVERIFIED (assumption derived from MF 2021 data + the assumed PIT_LUMP_REVENUE_TO_INCOME).
PIT_BUSINESS_INCOME_TO_WAGE_BILL: float = 0.40

# ---------------------------------------------------------------- second round (macro feedback)

# Marginal propensity to consume out of disposable income: a PIT change of dT (mld zł)
# moves nominal consumption by -HOUSEHOLD_MPC * dT.
# PLACEHOLDER-UNVERIFIED: illustrative value, no literature source verified. See docs/model-parameters.md.
HOUSEHOLD_MPC: float = 0.6

# Share of private consumption in GDP: a relative change of real consumption x moves
# real GDP by CONSUMPTION_GDP_SHARE * x (no import leakage or offsets modelled).
# Status from_data (docs/model-parameters.md): consumption_nominal / gdp_nominal of the last common year
# (2024: 0.563); this value is only the fallback when those series are missing.
CONSUMPTION_GDP_SHARE: float = 0.57

# Elasticity of employment w.r.t. real GDP (short-run, Okun-type).
# PLACEHOLDER-UNVERIFIED: illustrative value (data check 0.40-0.52, see docs/model-parameters.md).
EMPLOYMENT_GDP_ELASTICITY: float = 0.5

# Log-sd of the lognormal noise on the state's PIT share from 2025 (median 1); see docs/model-parameters.md.
# PLACEHOLDER-UNVERIFIED: no source; scatter of a single calibration point (one year, 2025).
PIT_STATE_SHARE_SIGMA: float = 0.2

# Number of most recent years used for the per-tax calibration factors (mean ratio of
# recorded revenue to module output at current law). Method choice, not a data value.
CALIBRATION_YEARS: int = 3

# Structural breaks: series -> first year recorded under new rules. Years >= the break are not used
# for calibration or scored by the backtest. rev_pit: from 2025 the state budget keeps a much smaller
# PIT share (local-government financing reform), 2024 97.6 -> 2025 28.75 mld zł (MF reports).
STRUCTURAL_BREAKS: dict[str, int] = {"rev_pit": 2025}
