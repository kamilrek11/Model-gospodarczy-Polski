"""Monte Carlo simulation of PIT, CIT and VAT revenue (mld zł) over 1-5 years (spec §5-§6).

Macro paths
    The fitted VAR on log differences is iterated forward per path, with residual rows
    bootstrapped jointly (cross-equation correlation kept) from the estimation residuals:
        d_t = const + sum_l d_{t-l} A_l + e*_t,   level_t = last_level * exp(cumsum d).
    One pass per year, vectorised over paths. Baseline (current law, params.defaults())
    and scenario use THE SAME macro draws (common random numbers), so with default
    parameters the scenario equals the baseline exactly.

Second round (one step, closed within each simulated year; nothing is counted twice)
    1. Household disposable income (PIT): computed first, from the first-round PIT
       (PIT on the unadjusted wage bill):
         f_pit = -HOUSEHOLD_MPC * (PIT_first_round - PIT_first_round_baseline) / C
    2. VAT: vat_revenue gets C * (1 + f_pit), i.e. consumption at BASELINE prices, moved
       only by the PIT income channel and NOT by the VAT price response. vat_revenue itself
       owns the volume response to VAT rates (vat.py contract), so f_vat below never
       enters the VAT base (that would be a double count). With unchanged PIT, f_pit = 0
       and VAT gets the pre-feedback path exactly.
    3. Macro variables:
         f_vat = consumption_feedback(eff_vat_base, eff_vat_new, elasticity)
                 (the same response vat_revenue applies, used here ONLY for other variables)
         real consumption factor  c = (1 + f_vat) * (1 + f_pit)
         consumer prices (CPI)    x (1 + eff_vat_new) / (1 + eff_vat_base)   (full pass-through)
         real GDP                 x 1 + CONSUMPTION_GDP_SHARE * (c - 1)
         employment               x 1 + EMPLOYMENT_GDP_ELASTICITY * (gdp factor - 1)
         nominal wage             unchanged (no wage-price feedback in v1)
    4. Bases of the other taxes are rebuilt from the adjusted macro variables:
         PIT: wage bill = wage_nominal * adjusted employment (+ business income tied to it)
         CIT: gross surplus x real GDP factor (VAT price effect does not raise surplus)
       PIT and CIT are computed once on these bases (no further iteration); the second-round
       PIT change does not loop back into consumption or VAT.
    Every factor is floored at 0, so extreme parameters cannot produce negative bases.

Calibration
    Per tax, factor = mean over the last CALIBRATION_YEARS years (with both the base series
    and rev_<tax> recorded) of rev_<tax> / module output at current law. vat_revenue has no
    calib argument, so its factor multiplies the output; PIT and CIT take it as `calib`.
    Years at or after a structural break of rev_<tax> (config.STRUCTURAL_BREAKS, e.g. the 2025
    state-budget PIT share) are never used (calibration_years).
    Note: historical years are evaluated at CURRENT law, not the law in force then.

A module whose required series is missing (or not usable) is disabled with a message;
no data is ever invented. All non-user constants come from app.model.config and those
marked PLACEHOLDER-UNVERIFIED there are listed in `assumptions` automatically.
"""

import inspect
import re
from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

from app.model import config
from app.model.macro import MacroModel
from app.model.params import defaults, validate
from app.model.taxes.cit import cit_revenue
from app.model.taxes.pit import IncomeDist, default_income_dist, pit_revenue
from app.model.taxes.vat import consumption_feedback, effective_vat_rate, vat_revenue

TAXES: tuple[str, ...] = ("pit", "cit", "vat")
BANDS: dict[str, float] = {"median": 0.5, "p10": 0.1, "p90": 0.9, "p2_5": 0.025, "p97_5": 0.975}
PLACEHOLDER = "PLACEHOLDER-UNVERIFIED"

# series each module needs: macro bases (store names) + recorded revenue for calibration
REQUIRED_SERIES: dict[str, tuple[str, ...]] = {
    "pit": ("wage_nominal", "employment", "rev_pit"),
    "cit": ("gross_surplus", "rev_cit"),
    "vat": ("consumption_nominal", "rev_vat"),
}

STRUCTURAL_ASSUMPTIONS: tuple[tuple[str, str], ...] = (
    ("structure.vat_base", "VAT liczony od konsumpcji w cenach bazowych skorygowanej tylko o zmianę dochodu rozporządzalnego z PIT; reakcję wolumenu na stawki VAT liczy wyłącznie moduł VAT (bez podwójnego liczenia)."),
    ("structure.second_round", "Druga runda w jednym kroku: zmiana VAT/PIT -> ceny i dochód rozporządzalny -> konsumpcja (i baza VAT), PKB, zatrudnienie -> bazy PIT i CIT."),
    ("structure.wages_fixed", "Nominalne wynagrodzenie nie reaguje na zmiany podatków (brak sprzężenia płacowo-cenowego w v1)."),
    ("structure.gross_surplus_projection", "Nadwyżka operacyjna brutto rośnie jak realny PKB x CPI od ostatniego roku danych."),
    ("structure.calibration_current_law", "Kalibracja liczy lata historyczne przy obecnym prawie (domyślne parametry), nie przy prawie obowiązującym w danym roku."),
)

# Polish notes for the structural breaks declared in config.STRUCTURAL_BREAKS (also used by the backtest)
BREAK_NOTES: dict[str, str] = {
    "rev_pit": "PIT w budżecie państwa: zmiana zasad podziału od 2025 r. (reforma finansowania JST); kalibracja do 2024; "
    "wykonanie 2025 nie jest porównywalne z prognozą przy dotychczasowych zasadach.",
}


def calibration_years(series_name: str, years) -> list[int]:
    """Years usable for calibration of `series_name`: those before its structural break (if any)."""
    brk = config.STRUCTURAL_BREAKS.get(series_name)
    return [int(y) for y in years if brk is None or int(y) < brk]


@dataclass
class SimResult:
    years: list[int]
    taxes: dict[str, dict[str, list[float]]]  # tax -> band -> horizon values
    baseline: dict[str, dict[str, list[float]]]  # tax | "total" -> {"median": [...]}
    total: dict[str, list[float]]  # band -> horizon values
    macro: dict[str, dict[str, list[float]]]  # variable -> {"median","p10","p90","baseline"}
    calibration: dict[str, dict] = field(default_factory=dict)
    assumptions: list[dict] = field(default_factory=list)
    disabled_modules: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "years": self.years,
            "taxes": self.taxes,
            "baseline": self.baseline,
            "total": self.total,
            "macro": self.macro,
            "calibration": self.calibration,
            "assumptions": self.assumptions,
            "disabled_modules": self.disabled_modules,
        }


@dataclass
class _Context:
    enabled: list[str]
    calib: dict[str, float]
    dist: IncomeDist
    gs_anchor: float | None  # gross surplus in the model's last year
    nominal_gdp_anchor: float  # pkb_real * cpi in the model's last year


# ---------------------------------------------------------------- assumptions


def placeholder_assumptions() -> list[dict]:
    """Constants of app.model.config with their comment; status read from the markers.

    A constant without its own comment inherits the comment of the constant directly
    above it (same block, no blank line), e.g. PIT_BUSINESS_FLAT_SHARE.
    """
    out: list[dict] = []
    comments: list[str] = []
    last_note: str | None = None
    for line in inspect.getsource(config).splitlines():
        stripped = line.strip()
        if not stripped:
            comments, last_note = [], None
        elif stripped.startswith("#"):
            text = stripped.lstrip("#").strip()
            if text and not text.startswith("---"):
                comments.append(text)
        elif m := re.match(r"^([A-Z][A-Z0-9_]*)\s*(?::[^=]*)?=", line):
            note = " ".join(comments) if comments else last_note
            comments, last_note = [], note
            name = m.group(1)
            value = getattr(config, name)
            out.append({
                "key": name,
                "value": [list(r) for r in value] if isinstance(value, tuple) else value,
                "status": PLACEHOLDER if note and PLACEHOLDER in note else "documented",
                "note": (note or "").replace(f"{PLACEHOLDER}:", "").replace(PLACEHOLDER, "").strip() or name,
            })
    return out


# ---------------------------------------------------------------- history helpers


def _series(history: dict[str, pd.DataFrame], name: str) -> pd.Series:
    df = history.get(name)
    if df is None or df.empty:
        return pd.Series(dtype=float)
    return df["value"].astype(float).dropna()


def _calib_window(*series: pd.Series) -> pd.DataFrame:
    joined = pd.concat(series, axis=1, join="inner").dropna().sort_index()
    return joined.iloc[-config.CALIBRATION_YEARS:]


def _wage_bill_to_scale_base(wage_bill):
    return wage_bill * (1.0 + config.PIT_BUSINESS_SCALE_SHARE * config.PIT_BUSINESS_INCOME_TO_WAGE_BILL)


def _pit(wage_bill: np.ndarray, dist: IncomeDist, p: dict, calib: float) -> np.ndarray:
    return pit_revenue(wage_bill, config.PIT_BUSINESS_INCOME_TO_WAGE_BILL * wage_bill, dist, p, calib)


def _vat(consumption: np.ndarray, p: dict, base_p: dict) -> np.ndarray:
    return vat_revenue(consumption, config.VAT_CONSUMPTION_SHARES, p, config.VAT_GAP, config.VAT_PRICE_ELASTICITY, base_p)


def _cit(gross_surplus: np.ndarray, p: dict, calib: float) -> np.ndarray:
    return cit_revenue(gross_surplus, config.CIT_SMALL_TAXPAYER_SHARE, p, calib)


def _prepare(model: MacroModel, history: dict[str, pd.DataFrame]) -> tuple[_Context, dict, list[dict]]:
    """Calibration factors per tax (at current law) and disabled modules."""
    law = defaults()
    lv = dict(zip(model.variables, model.last_levels))
    # PIT income distribution is anchored to the scale base of the model's last data year
    dist = replace(default_income_dist(), reference_base=float(_wage_bill_to_scale_base(lv["wage_nominal"] * lv["employment"])))
    calib: dict[str, float] = {}
    calibration: dict[str, dict] = {}
    disabled: list[dict] = []
    gs_anchor = None

    for tax in TAXES:
        missing = [s for s in REQUIRED_SERIES[tax] if _series(history, s).empty]
        if missing:
            disabled.append({"module": tax, "message": f"Moduł {tax.upper()} wyłączony: brak serii {', '.join(missing)} w danych."})
            continue
        rev = _series(history, f"rev_{tax}").rename("rev")
        rev = rev[rev.index.isin(calibration_years(f"rev_{tax}", rev.index))]
        if tax == "pit":
            w = _calib_window(rev, _series(history, "wage_nominal").rename("w"), _series(history, "employment").rename("e"))
            module = _pit(w["w"].to_numpy() * w["e"].to_numpy(), dist, law, 1.0) if len(w) else np.array([])
        elif tax == "cit":
            gs = _series(history, "gross_surplus")
            if model.last_year not in gs.index:
                disabled.append({"module": tax, "message": f"Moduł CIT wyłączony: brak gross_surplus za rok {model.last_year} (ostatni rok modelu)."})
                continue
            gs_anchor = float(gs.loc[model.last_year])
            w = _calib_window(rev, gs.rename("gs"))
            module = _cit(w["gs"].to_numpy(), law, 1.0) if len(w) else np.array([])
        else:
            w = _calib_window(rev, _series(history, "consumption_nominal").rename("c"))
            module = _vat(w["c"].to_numpy(), law, law) if len(w) else np.array([])
        if len(w) == 0 or np.any(module <= 0) or np.any(w["rev"].to_numpy() < 0):
            disabled.append({"module": tax, "message": f"Moduł {tax.upper()} wyłączony: brak lat do kalibracji (wspólnych dla bazy i rev_{tax})."})
            continue
        factor = float(np.mean(w["rev"].to_numpy() / module))
        if not np.isfinite(factor) or factor <= 0:
            disabled.append({"module": tax, "message": f"Moduł {tax.upper()} wyłączony: nieprawidłowy współczynnik kalibracji."})
            continue
        calib[tax] = factor
        calibration[tax] = {
            "factor": factor,
            "years": [int(y) for y in w.index],
            "method": f"średnia relacja wykonania rev_{tax} do wyniku modułu przy obecnym prawie z ostatnich {config.CALIBRATION_YEARS} lat"
            + (f" przed załamaniem strukturalnym w {brk} r." if (brk := config.STRUCTURAL_BREAKS.get(f"rev_{tax}")) else ""),
        }

    ctx = _Context(
        enabled=[t for t in TAXES if t in calib],
        calib=calib,
        dist=dist,
        gs_anchor=gs_anchor,
        nominal_gdp_anchor=float(lv["pkb_real"] * lv["cpi"]),
    )
    return ctx, calibration, disabled


# ---------------------------------------------------------------- simulation


def simulate_levels(model: MacroModel, horizon: int, n_paths: int, rng: np.random.Generator) -> dict[str, np.ndarray]:
    """Bootstrap VAR paths of levels: variable -> (n_paths, horizon)."""
    k, lags = len(model.variables), model.lags
    const = model.coefs[0]
    blocks = [model.coefs[1 + l * k : 1 + (l + 1) * k] for l in range(lags)]
    draws = rng.integers(0, model.resid.shape[0], size=(n_paths, horizon))
    state = np.broadcast_to(model.last_obs, (n_paths, lags, k)).copy()  # oldest first
    d = np.empty((n_paths, horizon, k))
    for h in range(horizon):
        step = const + model.resid[draws[:, h]]
        for l in range(lags):
            step = step + state[:, lags - 1 - l] @ blocks[l]
        d[:, h] = step
        state = np.concatenate([state[:, 1:], step[:, None, :]], axis=1)
    levels = model.last_levels * np.exp(np.cumsum(d, axis=1))
    return {v: levels[:, :, i] for i, v in enumerate(model.variables)}


def _scenario(lv: dict[str, np.ndarray], p: dict, law: dict, ctx: _Context, pit_first_law: np.ndarray | None):
    cons, cpi, gdp = lv["consumption_nominal"], lv["cpi"], lv["pkb_real"]
    emp, wage = lv["employment"], lv["wage_nominal"]
    taxes: dict[str, np.ndarray] = {}

    # 1. PIT disposable-income channel (first round)
    f_pit = 0.0
    if pit_first_law is not None:
        d_pit = _pit(wage * emp, ctx.dist, p, ctx.calib["pit"]) - pit_first_law
        f_pit = -config.HOUSEHOLD_MPC * d_pit / cons  # both in mld zł (units enforced by the dataset gates)
    pit_factor = np.maximum(1.0 + f_pit, 0.0)

    # 2. VAT on consumption at baseline prices moved only by the PIT channel (owns its volume response)
    if "vat" in ctx.enabled:
        taxes["vat"] = ctx.calib["vat"] * _vat(cons * pit_factor, p, law)

    # 3. macro variables
    eff_law = effective_vat_rate(config.VAT_CONSUMPTION_SHARES, law)
    eff_new = effective_vat_rate(config.VAT_CONSUMPTION_SHARES, p)
    f_vat = consumption_feedback(eff_law, eff_new, config.VAT_PRICE_ELASTICITY)
    price = (1.0 + eff_new) / (1.0 + eff_law)
    c_factor = np.maximum((1.0 + f_vat) * pit_factor, 0.0)
    gdp_factor = np.maximum(1.0 + config.CONSUMPTION_GDP_SHARE * (c_factor - 1.0), 0.0)
    emp_factor = np.maximum(1.0 + config.EMPLOYMENT_GDP_ELASTICITY * (gdp_factor - 1.0), 0.0)
    macro = {
        "pkb_real": gdp * gdp_factor,
        "employment": emp * emp_factor,
        "wage_nominal": wage,
        "cpi": cpi * price,
        "consumption_nominal": cons * price * c_factor,
        "consumption_real": cons / cpi * c_factor,
    }

    # 4. second-round bases for PIT and CIT, computed once
    if "pit" in ctx.enabled:
        taxes["pit"] = _pit(wage * macro["employment"], ctx.dist, p, ctx.calib["pit"])
    if "cit" in ctx.enabled:
        gs = ctx.gs_anchor * (gdp * cpi) / ctx.nominal_gdp_anchor * gdp_factor
        taxes["cit"] = _cit(gs, p, ctx.calib["cit"])
    return taxes, macro


def _bands(x: np.ndarray, keys=tuple(BANDS)) -> dict[str, list[float]]:
    q = np.quantile(x, [BANDS[k] for k in keys], axis=0)
    return {k: q[i].tolist() for i, k in enumerate(keys)}


def simulate(
    model: MacroModel,
    history: dict[str, pd.DataFrame],
    params: dict,
    horizon: int = 5,
    n_paths: int = 2000,
    seed: int | None = None,
) -> SimResult:
    p = validate(params)  # raises ValueError with a Polish message
    if not 1 <= horizon <= 5:
        raise ValueError(f"Horyzont musi być w zakresie 1-5 lat, podano {horizon}")
    if n_paths < 1:
        raise ValueError("Liczba ścieżek musi być dodatnia")
    law = defaults()
    ctx, calibration, disabled = _prepare(model, history)
    lv = simulate_levels(model, horizon, n_paths, np.random.default_rng(seed))

    pit_first_law = _pit(lv["wage_nominal"] * lv["employment"], ctx.dist, law, ctx.calib["pit"]) if "pit" in ctx.enabled else None
    base_taxes, base_macro = _scenario(lv, law, law, ctx, pit_first_law)
    taxes, macro = _scenario(lv, p, law, ctx, pit_first_law)

    zeros = np.zeros((n_paths, horizon))
    total = sum(taxes.values(), zeros)
    base_total = sum(base_taxes.values(), zeros)

    baseline = {t: _bands(v, ("median",)) for t, v in base_taxes.items()}
    baseline["total"] = _bands(base_total, ("median",))
    macro_out = {
        v: {**_bands(macro[v], ("median", "p10", "p90")), "baseline": _bands(base_macro[v], ("median",))["median"]}
        for v in macro
    }

    assumptions = placeholder_assumptions()
    assumptions += [{"key": k, "value": None, "status": "model-structure", "note": n} for k, n in STRUCTURAL_ASSUMPTIONS]
    assumptions += [
        {"key": f"structure.break.{name}", "value": year, "status": "model-structure", "note": BREAK_NOTES.get(name, f"Załamanie strukturalne serii {name} od {year} r.")}
        for name, year in config.STRUCTURAL_BREAKS.items()
    ]
    assumptions += [
        {"key": f"calibration.{t}", "value": c["factor"], "status": "calibrated", "note": c["method"] + f" ({c['years'][0]}-{c['years'][-1]})"}
        for t, c in calibration.items()
    ]

    return SimResult(
        years=list(range(model.last_year + 1, model.last_year + 1 + horizon)),
        taxes={t: _bands(v) for t, v in taxes.items()},
        baseline=baseline,
        total=_bands(total),
        macro=macro_out,
        calibration=calibration,
        assumptions=assumptions,
        disabled_modules=disabled,
    )
