"""Assembly of the fetched source series into the stored dataset, and its quality gates.

refresh() calls validate_dataset() on everything the clients returned (series name -> frame, values in
the model units: amounts in mld zł) and, only when it returns no violations, assemble() to build what
is written to the store (series name -> (source label, frame)). A violation stops the refresh before
anything is written; the messages are Polish and meant for the user.
"""

import pandas as pd

from app.model.macro import MACRO_VARS

# series -> source that delivers it (the label stored with each series)
SERIES_SOURCES: dict[str, str] = {
    "pkb_real": "gus_bdl",
    "employment": "gus_bdl",
    "wage_nominal": "gus_bdl",
    "cpi": "gus_bdl",
    "gdp_nominal": "gus_bdl",  # auxiliary: used by the consumption/GDP gate
    "gross_surplus": "gus_bdl",
    "consumption_nominal": "eurostat",
    "rev_vat": "mf_execution",
    "rev_cit": "mf_execution",
    "rev_pit": "mf_execution",
}
EUROSTAT_SURPLUS = "gross_surplus_eurostat"
EXTENDED_SURPLUS_SOURCE = "gus_bdl+eurostat"

MIN_CONTIGUOUS_MACRO_YEARS = 15
CONSUMPTION_GDP_RANGE = (0.4, 0.7)
REVENUE_RANGES_MLD: dict[str, tuple[float, float]] = {
    "rev_vat": (100.0, 500.0),
    "rev_cit": (20.0, 150.0),
    "rev_pit": (10.0, 200.0),  # the 2025 state-budget PIT (28.75 after the JST reform) stays inside
}
SURPLUS_MAX_REL_DIFF = 0.02


def _values(series: dict[str, pd.DataFrame], name: str) -> pd.Series | None:
    df = series.get(name)
    if df is None or "value" not in getattr(df, "columns", ()) or df.empty:
        return None
    return df["value"].astype(float).sort_index()


def _num(x: float, digits: int = 1) -> str:
    return f"{x:,.{digits}f}".replace(",", " ").replace(".", ",")


def _years(years) -> str:
    years = [int(y) for y in years]
    shown = ", ".join(str(y) for y in years[:10])
    return shown + (f" i {len(years) - 10} innych" if len(years) > 10 else "")


def _longest_run(years: list[int]) -> tuple[int, int, int]:
    """(length, first, last) of the longest run of consecutive years."""
    best = (0, 0, 0)
    start = prev = None
    for y in sorted(years):
        if prev is None or y != prev + 1:
            start = y
        prev = y
        if y - start + 1 > best[0]:
            best = (y - start + 1, start, y)
    return best


def validate_dataset(series: dict[str, pd.DataFrame]) -> list[str]:
    """Quality gates (a)-(e) on the fetched series; returns the violations (empty list = OK)."""
    out: list[str] = []

    # (e) no missing (NaN) and no negative values in any series
    for name in sorted(series):
        v = _values(series, name)
        if v is None:
            continue
        if v.isna().any():
            out.append(f"Seria {name}: brak wartości (NaN) w latach {_years(v.index[v.isna()])}.")
        neg = v[v < 0]
        if not neg.empty:
            out.append(f"Seria {name}: ujemne wartości w latach {_years(neg.index)}.")

    # (a) at least 15 contiguous years common to the macro variables
    macro = {name: _values(series, name) for name in MACRO_VARS}
    missing = [name for name, v in macro.items() if v is None]
    if missing:
        out.append(f"Brak serii makro: {', '.join(missing)}.")
    else:
        common = set.intersection(*(set(int(y) for y in v.dropna().index) for v in macro.values()))
        n, first, last = _longest_run(list(common))
        if n < MIN_CONTIGUOUS_MACRO_YEARS:
            span = f" ({first}–{last})" if n else ""
            out.append(
                f"Za mało ciągłych lat wspólnych dla zmiennych makro ({', '.join(MACRO_VARS)}): "
                f"najdłuższy ciąg ma {n} lat{span}, wymagane co najmniej {MIN_CONTIGUOUS_MACRO_YEARS}."
            )

    # (b) consumption / nominal GDP in the last common year (catches mln vs mld)
    cons, gdp = _values(series, "consumption_nominal"), _values(series, "gdp_nominal")
    if cons is None or gdp is None:
        absent = [n for n, v in (("consumption_nominal", cons), ("gdp_nominal", gdp)) if v is None]
        out.append(f"Brak serii do kontroli jednostek: {', '.join(absent)}.")
    else:
        both = pd.concat([cons, gdp], axis=1, join="inner").dropna()
        both = both[both.iloc[:, 1] > 0]
        if both.empty:
            out.append("Brak wspólnego roku konsumpcji (consumption_nominal) i nominalnego PKB (gdp_nominal) do kontroli jednostek.")
        else:
            year = int(both.index[-1])
            ratio = float(both.iloc[-1, 0] / both.iloc[-1, 1])
            lo, hi = CONSUMPTION_GDP_RANGE
            if not lo <= ratio <= hi:
                out.append(
                    f"Relacja konsumpcji (consumption_nominal) do nominalnego PKB (gdp_nominal) w {year} r. wynosi "
                    f"{_num(ratio, 3)}, poza zakresem [0,4; 0,7] – prawdopodobny błąd jednostek (np. mln zamiast mld zł)."
                )

    # (c) last value of each budget revenue series in a plausible mld zł range
    for name, (lo, hi) in REVENUE_RANGES_MLD.items():
        v = _values(series, name)
        if v is None or v.dropna().empty:
            out.append(f"Brak serii {name}.")
            continue
        v = v.dropna()
        year, last = int(v.index[-1]), float(v.iloc[-1])
        if not lo <= last <= hi:
            out.append(
                f"Ostatnia wartość {name} ({year} r.) wynosi {_num(last, 3)} mld zł, poza zakresem "
                f"[{lo:g}; {hi:g}] mld zł – prawdopodobny błąd jednostek."
            )

    # (d) BDL vs Eurostat gross operating surplus agree on overlapping years; the BDL series is required
    # and the Eurostat years appended after it (assemble) must continue it without a gap
    bdl, eu = _values(series, "gross_surplus"), _values(series, EUROSTAT_SURPLUS)
    if bdl is None:
        out.append("Brak serii gross_surplus (nadwyżka operacyjna brutto, GUS BDL) – wymagana do modułu CIT.")
    if bdl is not None and eu is not None:
        later = [int(y) for y in eu.index if y > bdl.index.max()]
        if later:
            gaps = sorted(set(range(int(bdl.index.max()) + 1, later[-1] + 1)) - set(later))
            if gaps:
                out.append(
                    f"Nadwyżka operacyjna brutto (gross_surplus): po ostatnim roku GUS BDL ({int(bdl.index.max())}) "
                    f"brakuje w Eurostacie lat {_years(gaps)} – przedłużona seria miałaby lukę."
                )
        both = pd.concat([bdl.rename("bdl"), eu.rename("eu")], axis=1, join="inner").dropna()
        both = both[both["eu"] > 0]
        if both.empty:
            out.append("Nadwyżka operacyjna brutto: brak wspólnych lat GUS BDL i Eurostatu – nie można sprawdzić zgodności źródeł.")
        else:
            diff = (both["bdl"] / both["eu"] - 1.0).abs()
            bad = diff[diff > SURPLUS_MAX_REL_DIFF]
            if not bad.empty:
                worst = int(bad.idxmax())
                out.append(
                    f"Nadwyżka operacyjna brutto: GUS BDL i Eurostat różnią się o więcej niż 2% w latach "
                    f"{_years(bad.index)} (największa różnica {_num(float(bad.max()) * 100, 1)}% w {worst} r.)."
                )
    return out


def validate_against_stored(series: dict[str, pd.DataFrame], stored_last_years: dict[str, int | None]) -> list[str]:
    """Gate (f): no budget revenue series may end before the last year already stored (a source that
    lost its latest years must not shorten the last good state). `stored_last_years`: name -> last
    stored year (None = nothing stored; seeded synthetic data is not passed in)."""
    out: list[str] = []
    for name in REVENUE_RANGES_MLD:
        prev = stored_last_years.get(name)
        v = _values(series, name)
        if prev is None or v is None or v.dropna().empty:
            continue  # nothing stored yet, or already reported by gate (c)
        last = int(v.dropna().index[-1])
        if last < prev:
            out.append(
                f"Seria {name} kończy się na {last} r., a zapisane dane sięgają {prev} r. – brak najnowszych lat "
                f"w źródle; zapisane dane pozostają bez zmian."
            )
    return out


def _frame(values: pd.Series) -> pd.DataFrame:
    idx = pd.Index([int(y) for y in values.index], dtype="int64", name="year")
    return pd.DataFrame({"value": values.to_numpy(dtype="float64")}, index=idx)


def assemble(results: dict[str, pd.DataFrame]) -> dict[str, tuple[str, pd.DataFrame]]:
    """Series to store: name -> (source label, frame). gross_surplus = BDL, extended with the
    Eurostat years after BDL's last year (label "gus_bdl+eurostat"). Unknown series are dropped."""
    out: dict[str, tuple[str, pd.DataFrame]] = {}
    for name, source in SERIES_SOURCES.items():
        v = _values(results, name)
        if v is not None:
            out[name] = (source, _frame(v))
    bdl, eu = _values(results, "gross_surplus"), _values(results, EUROSTAT_SURPLUS)
    if eu is not None:
        if bdl is None:
            # not stored after a refresh (gate (d) rejects a missing BDL series); for direct callers the
            # Eurostat-only series is still labelled with its real source
            out["gross_surplus"] = ("eurostat", _frame(eu))
        else:
            later = eu[eu.index > bdl.index.max()]
            if not later.empty:
                out["gross_surplus"] = (EXTENDED_SURPLUS_SOURCE, _frame(pd.concat([bdl, later])))
    return out
