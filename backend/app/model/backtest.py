"""Rolling-origin backtest of the simulator (spec §5-§6).

For each origin year T with at least `min_train` macro observations up to T, the macro VAR is
refitted on data up to T, `simulate` (the same machinery as POST /simulate, default params,
calibration included) projects T+1..T+horizon, and the median/bands are compared with realised
rev_<tax>. Metrics are pooled over all (origin, horizon) pairs with a realised value.

Caveat: calibration (and the whole tax chain) uses TODAY's tax law for past years, so the
backtest measures the model + macro uncertainty, not a replay of historical law.

Structural breaks (config.STRUCTURAL_BREAKS, e.g. rev_pit from 2025): realised values at or after
the break year are never scored, and `simulate` never calibrates on them (calibration_years), so a
training window that reaches the break cannot leak the new regime into the factor either.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.model import config
from app.model.macro import MACRO_VARS, MIN_OBS, InsufficientData, fit_macro
from app.model.params import defaults
from app.model.simulate import BREAK_NOTES, simulate

BACKTEST_PATHS = 500
BACKTEST_SEED = 12345

NOTE_CURRENT_LAW = "Backtest liczy lata historyczne przy obecnym prawie podatkowym (domyślne parametry), nie przy prawie obowiązującym w danym roku."
NOTE_METRICS = "MAPE w procentach; pokrycie jako ułamek realizacji w przedziałach 80% (p10-p90) i 95% (p2,5-p97,5)."
NOTE_PIT_BREAK = BREAK_NOTES["rev_pit"]
MSG_NO_ORIGIN = "Za mało danych do backtestu: brak roku startowego z wystarczającą liczbą obserwacji i realizacji."


@dataclass
class BacktestResult:
    mape: dict[str, float] = field(default_factory=dict)
    coverage80: dict[str, float] = field(default_factory=dict)
    coverage95: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=lambda: [NOTE_CURRENT_LAW, NOTE_METRICS])
    message: str | None = None
    n_origins: int = 0
    n_skipped: int = 0

    def to_dict(self) -> dict:
        return {
            "mape": self.mape,
            "coverage80": self.coverage80,
            "coverage95": self.coverage95,
            "notes": self.notes,
            "message": self.message,
            "n_origins": self.n_origins,
            "n_skipped": self.n_skipped,
        }


def _before_break(name: str, df: pd.DataFrame) -> pd.DataFrame:
    brk = config.STRUCTURAL_BREAKS.get(name)
    return df if brk is None else df[df.index < brk]


def _notes(n_skipped: int, broken: set[str] = frozenset()) -> list[str]:
    notes = [NOTE_CURRENT_LAW, NOTE_METRICS]
    if n_skipped:
        notes.append(f"Pominięto {n_skipped} lat startowych (brak dopasowania modelu) - wyniki opierają się na pozostałych latach.")
    for name in sorted(broken):
        year = config.STRUCTURAL_BREAKS[name]
        notes.append(BREAK_NOTES.get(name, f"Załamanie strukturalne serii {name} od {year} r."))
        notes.append(f"Realizacje {name} od {year} r. nie są oceniane w backteście (załamanie strukturalne).")
        if name == "rev_pit":
            notes.append(f"W backteście PIT liczony jest według zasad sprzed {year} r. (bez udziału budżetu państwa); backtest nie ocenia prognoz udziału.")
    return notes


def backtest(data: dict[str, pd.DataFrame], horizon: int = 3, min_train: int = MIN_OBS) -> BacktestResult:
    # an origin needs at least MIN_OBS macro years to be fitted at all; below that it would only be
    # counted as "skipped", so n_skipped is reserved for real fit failures
    min_train = max(min_train, MIN_OBS)
    if not all(v in data and not data[v].empty for v in MACRO_VARS):
        return BacktestResult(message=MSG_NO_ORIGIN)
    macro = pd.concat({v: data[v]["value"].astype(float) for v in MACRO_VARS}, axis=1).dropna().sort_index()
    years = [int(y) for y in macro.index]
    params = defaults()

    errors: dict[str, list[float]] = {}
    hit80: dict[str, list[float]] = {}
    hit95: dict[str, list[float]] = {}
    n_origins = 0
    n_skipped = 0
    broken: set[str] = set()  # series whose realised values past a structural break were left out
    for pos, origin in enumerate(years[:-1]):
        if pos + 1 < min_train:
            continue
        # series past a structural break are cut before it: neither the module calibration nor the PIT state
        # share (s0 = 1 here) may learn from the new regime, so the backtest never sees the 2025 PIT split
        train = {k: _before_break(k, df[df.index <= origin]) for k, df in data.items()}
        try:
            model = fit_macro(macro[macro.index <= origin], lags=1)
            res = simulate(model, train, params, horizon, BACKTEST_PATHS, BACKTEST_SEED)
        except (InsufficientData, ValueError, np.linalg.LinAlgError):
            n_skipped += 1
            continue
        used = False
        for tax, bands in res.taxes.items():  # only enabled taxes
            realised = data.get(f"rev_{tax}")
            if realised is None or realised.empty:
                continue
            for i, year in enumerate(res.years):
                if year not in realised.index or not np.isfinite(realised.loc[year, "value"]):
                    continue
                brk = config.STRUCTURAL_BREAKS.get(f"rev_{tax}")
                if brk is not None and year >= brk:
                    broken.add(f"rev_{tax}")
                    continue
                actual = float(realised.loc[year, "value"])
                used = True
                if actual != 0:
                    errors.setdefault(tax, []).append(abs(bands["median"][i] - actual) / abs(actual) * 100.0)
                hit80.setdefault(tax, []).append(float(bands["p10"][i] <= actual <= bands["p90"][i]))
                hit95.setdefault(tax, []).append(float(bands["p2_5"][i] <= actual <= bands["p97_5"][i]))
        n_origins += used
    if not n_origins:
        return BacktestResult(message=MSG_NO_ORIGIN, n_skipped=n_skipped, notes=_notes(n_skipped, broken))
    return BacktestResult(
        mape={t: float(np.mean(v)) for t, v in errors.items()},
        coverage80={t: float(np.mean(v)) for t, v in hit80.items()},
        coverage95={t: float(np.mean(v)) for t, v in hit95.items()},
        n_origins=n_origins,
        n_skipped=n_skipped,
        notes=_notes(n_skipped, broken),
    )
