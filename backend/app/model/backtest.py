"""Rolling-origin backtest of the simulator (spec §5-§6).

For each origin year T with at least `min_train` macro observations up to T, the macro VAR is
refitted on data up to T, `simulate` (the same machinery as POST /simulate, default params,
calibration included) projects T+1..T+horizon, and the median/bands are compared with realised
rev_<tax>. Metrics are pooled over all (origin, horizon) pairs with a realised value.

Caveat: calibration (and the whole tax chain) uses TODAY's tax law for past years, so the
backtest measures the model + macro uncertainty, not a replay of historical law.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.model.macro import MACRO_VARS, InsufficientData, fit_macro
from app.model.params import defaults
from app.model.simulate import simulate

BACKTEST_PATHS = 500
BACKTEST_SEED = 12345

NOTE_CURRENT_LAW = "Backtest liczy lata historyczne przy obecnym prawie podatkowym (domyślne parametry), nie przy prawie obowiązującym w danym roku."
NOTE_METRICS = "MAPE w procentach; pokrycie jako ułamek realizacji w przedziałach 80% (p10-p90) i 95% (p2,5-p97,5)."
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


def _notes(n_skipped: int) -> list[str]:
    notes = [NOTE_CURRENT_LAW, NOTE_METRICS]
    if n_skipped:
        notes.append(f"Pominięto {n_skipped} lat startowych (brak dopasowania modelu) - wyniki opierają się na pozostałych latach.")
    return notes


def backtest(data: dict[str, pd.DataFrame], horizon: int = 3, min_train: int = 12) -> BacktestResult:
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
    for pos, origin in enumerate(years[:-1]):
        if pos + 1 < min_train:
            continue
        train = {k: df[df.index <= origin] for k, df in data.items()}
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
                actual = float(realised.loc[year, "value"])
                used = True
                if actual != 0:
                    errors.setdefault(tax, []).append(abs(bands["median"][i] - actual) / abs(actual) * 100.0)
                hit80.setdefault(tax, []).append(float(bands["p10"][i] <= actual <= bands["p90"][i]))
                hit95.setdefault(tax, []).append(float(bands["p2_5"][i] <= actual <= bands["p97_5"][i]))
        n_origins += used
    if not n_origins:
        return BacktestResult(message=MSG_NO_ORIGIN, n_skipped=n_skipped, notes=_notes(n_skipped))
    return BacktestResult(
        mape={t: float(np.mean(v)) for t, v in errors.items()},
        coverage80={t: float(np.mean(v)) for t, v in hit80.items()},
        coverage95={t: float(np.mean(v)) for t, v in hit95.items()},
        n_origins=n_origins,
        n_skipped=n_skipped,
        notes=_notes(n_skipped),
    )
