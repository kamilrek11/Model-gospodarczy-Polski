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

State-budget PIT share (spec 2026-10-11-udzial-pit-design.md)
    From the rev_pit break year b (2025 reform of local-government financing) the reported PIT is
        PIT_state = PIT (current law, pre-reform calibration) * s0 * m * eps
    s0 = rev_pit[b] / PIT module output for b (estimate_state_share: from the stored wage bill of b when
    available, else the median baseline forecast for b from a fixed-seed run of _SHARE_PATHS paths, so s0 does
    not depend on the caller's seed or n_paths); m = pit_state_share_mult (the baseline uses m = 1);
    eps = exp(PIT_STATE_SHARE_SIGMA * z), z ~ N(0, 1) per path from a separate generator, the same eps for the
    baseline and the scenario. The share only scales the REPORTED PIT after _scenario: the disposable-income
    channel and the second round still use total PIT. Without rev_pit[b] (or a module value for b): s0 = 1,
    no eps, and the PIT_STATE_SHARE assumption row says so; years before b are never scaled.

A module whose required series is missing (or not usable) is disabled with a message;
no data is ever invented. All non-user constants come from app.model.config and those
registered in app.model.param_meta are listed in `assumptions` with their status.
"""

from copy import deepcopy
from dataclasses import dataclass, field, replace
from typing import Literal

import numpy as np
import pandas as pd

from app.model import config, param_meta
from app.model.macro import MacroModel
from app.model.params import defaults, validate
from app.model.taxes.cit import cit_revenue
from app.model.taxes.pit import IncomeDist, default_income_dist, pit_revenue
from app.model.taxes.vat import consumption_feedback, effective_vat_rate, vat_revenue

TAXES: tuple[str, ...] = ("pit", "cit", "vat")
BANDS: dict[str, float] = {"median": 0.5, "p10": 0.1, "p90": 0.9, "p2_5": 0.025, "p97_5": 0.975}

# method-choice constants (not parameters of the registry) still listed for transparency
METHOD_CHOICES: tuple[tuple[str, str], ...] = (
    ("CALIBRATION_YEARS", "Liczba ostatnich lat użytych do współczynników kalibracji każdego podatku (średnia relacji wykonania do wyniku modułu przy obecnym prawie). Wybór metody, nie wartość z danych."),
    ("STRUCTURAL_BREAKS", "Załamania strukturalne: seria -> pierwszy rok zapisany według nowych zasad. Lata od załamania nie służą do kalibracji ani oceny backtestu. rev_pit: od 2025 r. budżet państwa zatrzymuje znacznie mniejszą część PIT (reforma finansowania samorządów), 2024: 97,6 -> 2025: 28,75 mld zł (sprawozdania MF). Prognoza PIT mnoży wynik modułu przez udział budżetu państwa s₀ (PIT_STATE_SHARE), skalibrowany na wykonaniu z jednego roku załamania; ten rok służy do kalibracji udziału, a nie do kalibracji modułu ani oceny backtestu."),
)

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
    "rev_pit": "PIT w budżecie państwa: zmiana zasad podziału od 2025 r. (reforma finansowania JST); prognoza uwzględnia "
    "udział budżetu państwa po reformie, oszacowany z jednego roku (2025); wykonanie 2025 służy do kalibracji udziału, "
    "nie do oceny backtestu.",
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
    state_share: "StateShare | None" = None  # not serialised; the PIT_STATE_SHARE assumption row carries it

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
    consumption_gdp_share: float  # from_data constant (resolve_constants)


# ---------------------------------------------------------------- assumptions


SERIES_FROM_DATA: tuple[str, ...] = ("consumption_nominal", "gdp_nominal")  # inputs of resolve_constants
CONSUMPTION_SHARE_RANGE = (0.4, 0.7)  # plausibility gate for the computed consumption / GDP ratio


def _resolve_details(history: dict[str, pd.DataFrame]) -> dict[str, dict]:
    """from_data constants: key -> {value, status, year, note}. Never raises; falls back to config."""
    key = "CONSUMPTION_GDP_SHARE"
    pl = lambda x: f"{x:.3f}".replace(".", ",")  # noqa: E731
    fallback = float(getattr(config, key))
    cons, gdp = _series(history, "consumption_nominal"), _series(history, "gdp_nominal")
    missing = [n for n, s in (("consumption_nominal", cons), ("gdp_nominal", gdp)) if s.empty]
    if missing:
        why = f"brak serii {', '.join(missing)} w danych"
    else:
        both = pd.concat([cons.rename("c"), gdp.rename("g")], axis=1, join="inner").dropna()
        both = both[both["g"] > 0]
        if both.empty:
            why = "brak wspólnego roku obu serii"
        else:
            year, row = int(both.index[-1]), both.iloc[-1]
            ratio = float(row["c"] / row["g"])
            lo, hi = CONSUMPTION_SHARE_RANGE
            if np.isfinite(ratio) and lo <= ratio <= hi:
                ratios = both["c"] / both["g"]
                note = f"Obliczono z danych: {pl(ratio)} w {year} r. (zakres {int(both.index[0])}-{year}: {pl(ratios.min())}-{pl(ratios.max())})."
                meta = param_meta.PARAMETERS[key]
                if meta.low is not None and meta.high is not None and not meta.low <= ratio <= meta.high:
                    note += f" Wartość poza zakresem rejestru ({pl(meta.low)}–{pl(meta.high)})."
                return {key: {"value": ratio, "status": "from_data", "year": year, "note": note}}
            why = f"obliczony udział {pl(ratio)} ({year} r.) poza dopuszczalnym zakresem {pl(lo)}–{pl(hi)}"
    note = f"Użyto wartości zapasowej {pl(fallback)}: {why}."
    return {key: {"value": fallback, "status": "assumption", "year": None, "note": note}}


def resolve_constants(history: dict[str, pd.DataFrame]) -> dict[str, float]:
    """Values of the `from_data` constants: computed from the stored series, else the config fallback."""
    return {k: d["value"] for k, d in _resolve_details(history).items()}


def parameter_assumptions(history: dict[str, pd.DataFrame] | None = None) -> list[dict]:
    """Registered config constants (param_meta) with status/source, plus the method-choice constants.

    from_data constants report the value actually used (resolve_constants) and the last year used; when they could
    not be computed the row says `assumption` and why. param_meta.PARAMETERS itself is never changed.
    """
    rows = param_meta.assumption_rows()
    if history is not None:
        details = _resolve_details(history)
        for r in rows:
            d = details.get(r["key"])
            if d is None:
                continue
            r["value"], r["status"] = d["value"], d["status"]
            r["year"] = d["year"]
            r["note"] = f"{r['note']} {d['note']}"
    return rows + [
        {"key": k, "value": deepcopy(getattr(config, k)), "status": "model-structure", "note": n, "source": "", "year": None, "url": "", "low": None, "high": None, "range_text": ""}
        for k, n in METHOD_CHOICES
    ]


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
        consumption_gdp_share=resolve_constants(history)["CONSUMPTION_GDP_SHARE"],
    )
    return ctx, calibration, disabled


# ---------------------------------------------------------------- state-budget PIT share


@dataclass(frozen=True)
class StateShare:
    s0: float
    year: int | None  # break year of rev_pit (first year under the new rules)
    source: Literal["data", "forecast", "none"]
    note: str  # Polish: how s0 was obtained, or why the pre-reform rules are used


def _pl(x: float, digits: int = 3) -> str:
    return f"{x:.{digits}f}".replace(".", ",")


def estimate_state_share(
    model: MacroModel, history: dict[str, pd.DataFrame], ctx: _Context, years: list[int], pit_base: np.ndarray
) -> StateShare:
    """s0 = recorded rev_pit in the break year / PIT module output for that year (current law, pre-reform calibration).

    Module output: from the stored wage_nominal * employment of the break year when both are recorded ('data'),
    else the median of `pit_base` (baseline PIT paths, shape (n_paths, len(years))) in that year ('forecast').
    Anything missing or a non-positive / non-finite ratio gives s0 = 1 ('none'). Never raises.
    """
    b = config.STRUCTURAL_BREAKS.get("rev_pit")

    def none(why: str) -> StateShare:
        rules = f"PIT liczony według zasad sprzed {b} r." if b is not None else "PIT liczony bez udziału budżetu państwa."
        return StateShare(1.0, b, "none", f"{rules} Nie oszacowano udziału budżetu państwa: {why}.")

    if b is None:
        return none("brak zadeklarowanego załamania strukturalnego serii rev_pit")
    if "pit" not in ctx.enabled:
        return none("moduł PIT jest wyłączony")
    rev = _series(history, "rev_pit")
    if b not in rev.index:
        return none(f"brak wykonania rev_pit za {b} r. w danych")
    rev_b = float(rev.loc[b])
    wage, emp = _series(history, "wage_nominal"), _series(history, "employment")
    if b in wage.index and b in emp.index:
        bill = np.array([float(wage.loc[b]) * float(emp.loc[b])])
        module = float(_pit(bill, ctx.dist, defaults(), ctx.calib["pit"])[0])
        source, how = "data", f"wynik modułu PIT z danych makro za {b} r."
    elif b in years and pit_base.ndim == 2 and pit_base.shape[1] == len(years) and pit_base.shape[0] > 0:
        module = float(np.median(pit_base[:, years.index(b)]))
        source, how = "forecast", f"mediana prognozy modułu PIT na {b} r.; brak pełnych danych makro za {b} r."
    else:
        return none(f"brak danych makro za {b} r. i rok {b} poza horyzontem prognozy")
    s0 = rev_b / module if module != 0 else float("nan")
    if not np.isfinite(s0) or s0 <= 0:
        return none(f"nieprawidłowa relacja wykonania do wyniku modułu za {b} r.")
    note = (
        f"s₀ = {_pl(s0)}: wykonanie rev_pit {b} r. {_pl(rev_b, 2)} mld zł ÷ {_pl(module, 2)} mld zł "
        f"({how}, obecne prawo i kalibracja sprzed załamania)."
    )
    return StateShare(float(s0), int(b), source, note)


# The 'forecast' source of s0 uses its own fixed Monte Carlo run, so s0 does not depend on the
# caller's seed (incl. the API default None) or n_paths. Method choice, not a data value.
_SHARE_SEED: int = 2025
_SHARE_PATHS: int = 2000


def _share_pit_base(model: MacroModel, history: dict[str, pd.DataFrame], ctx: _Context, years: list[int], law: dict) -> np.ndarray:
    """Baseline PIT paths (_SHARE_PATHS, len(years)) from a fixed-seed run, only when s0 needs the forecast.

    Empty (0, len(years)) when the break year is not in `years`, PIT is disabled, or the stored wage bill of the
    break year is available (the 'data' source does not use the forecast).
    """
    b = config.STRUCTURAL_BREAKS.get("rev_pit")
    empty = np.empty((0, len(years)))
    if b is None or b not in years or "pit" not in ctx.enabled:
        return empty
    if b in _series(history, "wage_nominal").index and b in _series(history, "employment").index:
        return empty
    k = years.index(b) + 1  # only the years up to the break are needed
    lv = simulate_levels(model, k, _SHARE_PATHS, np.random.default_rng(_SHARE_SEED))
    first = _pit(lv["wage_nominal"] * lv["employment"], ctx.dist, law, ctx.calib["pit"])
    pit = _scenario(lv, law, law, ctx, first)[0]["pit"]
    out = np.full((_SHARE_PATHS, len(years)), np.nan)
    out[:, :k] = pit
    return out


def _state_share_row(share: StateShare, m: float) -> dict:
    sigma = float(config.PIT_STATE_SHARE_SIGMA)
    if share.source == "none":
        note = share.note + (f" Mnożnik użytkownika {_pl(m, 2)} działa od {share.year} r. bez rozrzutu Monte Carlo." if share.year is not None else "")
        return {"key": "PIT_STATE_SHARE", "value": share.s0, "status": "assumption", "year": share.year, "note": note}
    note = (
        f"Udział budżetu państwa w PIT od {share.year} r. (reforma finansowania JST). {share.note} "
        f"Mnożnik użytkownika m = {_pl(m, 2)}, efektywny udział s₀×m = {_pl(share.s0 * m)}. "
        f"Oszacowane z jednego roku ({share.year}): s₀ zawiera też błąd prognozy modelu dla tego roku. "
        f"Rozrzut Monte Carlo: czynnik lognormalny o medianie 1 i odchyleniu logarytmu σ = {_pl(sigma, 2)} "
        "(PIT_STATE_SHARE_SIGMA), wspólny dla bazy i scenariusza na każdej ścieżce."
    )
    return {
        "key": "PIT_STATE_SHARE",
        "value": share.s0,
        "status": "calibrated",
        "year": share.year,
        "note": note,
        "source": f"obliczono: wykonanie MF (rev_pit {share.year}) ÷ moduł PIT",
        "low": share.s0 * float(np.exp(-sigma)),
        "high": share.s0 * float(np.exp(sigma)),
        "range_text": f"s₀·exp(∓σ), σ = {_pl(sigma, 2)}",
    }


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
    gdp_factor = np.maximum(1.0 + ctx.consumption_gdp_share * (c_factor - 1.0), 0.0)
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

    # state-budget PIT share: only the reported PIT, after the feedback channels (see module docstring)
    years = list(range(model.last_year + 1, model.last_year + 1 + horizon))
    share = estimate_state_share(model, history, ctx, years, _share_pit_base(model, history, ctx, years, law))
    if "pit" in taxes and share.year is not None:
        after = (np.array(years) >= share.year)[None, :]
        eps = 1.0
        if share.source != "none":
            eps_rng = np.random.default_rng([seed, 7]) if seed is not None else np.random.default_rng()
            eps = np.exp(config.PIT_STATE_SHARE_SIGMA * eps_rng.standard_normal((n_paths, 1)))
        base_taxes["pit"] = base_taxes["pit"] * np.where(after, share.s0 * eps, 1.0)
        taxes["pit"] = taxes["pit"] * np.where(after, share.s0 * p["pit_state_share_mult"] * eps, 1.0)

    zeros = np.zeros((n_paths, horizon))
    total = sum(taxes.values(), zeros)
    base_total = sum(base_taxes.values(), zeros)

    baseline = {t: _bands(v, ("median",)) for t, v in base_taxes.items()}
    baseline["total"] = _bands(base_total, ("median",))
    macro_out = {
        v: {**_bands(macro[v], ("median", "p10", "p90")), "baseline": _bands(base_macro[v], ("median",))["median"]}
        for v in macro
    }

    assumptions = parameter_assumptions(history)
    assumptions += [{"key": k, "value": None, "status": "model-structure", "note": n} for k, n in STRUCTURAL_ASSUMPTIONS]
    assumptions += [
        {"key": f"structure.break.{name}", "value": year, "status": "model-structure", "note": BREAK_NOTES.get(name, f"Załamanie strukturalne serii {name} od {year} r.")}
        for name, year in config.STRUCTURAL_BREAKS.items()
    ]
    assumptions += [
        {"key": f"calibration.{t}", "value": c["factor"], "status": "calibrated", "note": c["method"] + f" ({c['years'][0]}-{c['years'][-1]})"}
        for t, c in calibration.items()
    ]
    assumptions.append(_state_share_row(share, float(p["pit_state_share_mult"])))

    for a in assumptions:  # uniform row shape
        for k, v in (("source", ""), ("year", None), ("url", ""), ("low", None), ("high", None), ("range_text", "")):
            a.setdefault(k, v)

    return SimResult(
        years=years,
        taxes={t: _bands(v) for t, v in taxes.items()},
        baseline=baseline,
        total=_bands(total),
        macro=macro_out,
        calibration=calibration,
        assumptions=assumptions,
        disabled_modules=disabled,
        state_share=share,
    )
