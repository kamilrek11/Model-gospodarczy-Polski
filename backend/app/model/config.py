"""Non-user model parameters used by the tax modules.

Every value carries either a source note or the marker PLACEHOLDER-UNVERIFIED.
PLACEHOLDER-UNVERIFIED means the number is a rough, order-of-magnitude assumption
that has NOT been checked against a published source and must be replaced
(or confirmed) before results are presented as anything but illustrative.
Tax functions stay pure: callers pass these values in as arguments.
"""

# ---------------------------------------------------------------- VAT

# Share of nominal private consumption (gross of VAT) by VAT rate category.
# Keys map to parameters: standard -> vat_rate_standard, reduced1 -> vat_rate_reduced1,
# reduced2 -> vat_rate_reduced2, zero -> 0% / exempt (no output VAT).
# PLACEHOLDER-UNVERIFIED: rough split; should come from MF/GUS data on consumption by VAT rate.
VAT_CONSUMPTION_SHARES: dict[str, float] = {
    "standard": 0.55,
    "reduced1": 0.15,
    "reduced2": 0.12,
    "zero": 0.18,
}

# VAT compliance gap as a fraction of theoretical revenue.
# PLACEHOLDER-UNVERIFIED: order of magnitude only; replace with the latest
# VAT gap estimate for Poland (e.g. the European Commission VAT Gap report) after verification.
VAT_GAP: float = 0.07

# Price elasticity of real consumption demand w.r.t. the consumer price (gross of VAT).
# Assumes full pass-through of VAT changes to consumer prices.
# PLACEHOLDER-UNVERIFIED: illustrative value, no literature source verified.
VAT_PRICE_ELASTICITY: float = -0.5

# ---------------------------------------------------------------- CIT

# Share of the CIT tax base attributable to small taxpayers (9% rate).
# PLACEHOLDER-UNVERIFIED: should come from MF CIT-8 aggregate statistics.
CIT_SMALL_TAXPAYER_SHARE: float = 0.10

# ---------------------------------------------------------------- PIT

# Default taxable-income distribution of taxpayers on the tax scale (skala podatkowa),
# as (mean annual taxable income in zł, number of taxpayers in millions) per group.
# PLACEHOLDER-UNVERIFIED: synthetic distribution shaped to look plausible; should be
# replaced by MF "Informacja dotycząca rozliczenia podatku dochodowego od osób fizycznych"
# bracket data once loaded.
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
# PLACEHOLDER-UNVERIFIED: rough split.
PIT_BUSINESS_SCALE_SHARE: float = 0.35
PIT_BUSINESS_FLAT_SHARE: float = 0.40
PIT_BUSINESS_LUMP_SHARE: float = 0.25

# Ratio of recorded revenue (ryczałt base) to income for lump-sum taxpayers.
# PLACEHOLDER-UNVERIFIED: illustrative value.
PIT_LUMP_REVENUE_TO_INCOME: float = 2.0

# Non-agricultural business income (PIT base outside wages) as a ratio to the wage bill.
# No business-income series is loaded, so the projection ties it to the wage bill.
# PLACEHOLDER-UNVERIFIED: illustrative ratio; should come from MF PIT statistics.
PIT_BUSINESS_INCOME_TO_WAGE_BILL: float = 0.25

# ---------------------------------------------------------------- second round (macro feedback)

# Marginal propensity to consume out of disposable income: a PIT change of dT (mld zł)
# moves nominal consumption by -HOUSEHOLD_MPC * dT.
# PLACEHOLDER-UNVERIFIED: illustrative value, no literature source verified.
HOUSEHOLD_MPC: float = 0.6

# Share of private consumption in GDP: a relative change of real consumption x moves
# real GDP by CONSUMPTION_GDP_SHARE * x (no import leakage or offsets modelled).
# PLACEHOLDER-UNVERIFIED: order of magnitude only; should come from GUS national accounts.
CONSUMPTION_GDP_SHARE: float = 0.57

# Elasticity of employment w.r.t. real GDP (short-run, Okun-type).
# PLACEHOLDER-UNVERIFIED: illustrative value, no literature source verified.
EMPLOYMENT_GDP_ELASTICITY: float = 0.5

# Number of most recent years used for the per-tax calibration factors (mean ratio of
# recorded revenue to module output at current law). Method choice, not a data value.
CALIBRATION_YEARS: int = 3

# Structural breaks: series -> first year recorded under new rules. Years >= the break are not used
# for calibration or scored by the backtest. rev_pit: from 2025 the state budget keeps a much smaller
# PIT share (local-government financing reform), 2024 97.6 -> 2025 28.75 mld zł (MF reports).
STRUCTURAL_BREAKS: dict[str, int] = {"rev_pit": 2025}
