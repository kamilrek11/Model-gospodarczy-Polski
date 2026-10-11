"""Live refresh report: a REAL refresh from GUS BDL, Eurostat and MF into a NEW database, then the default
simulation and the backtest, printed as a plain-text report.

    cd backend && .venv/bin/python -m scripts.live_refresh_report --db /tmp/live.db [--cache-dir DIR]

Network: BDL 6 requests (anonymous limit 1000 / 12 h; set BDL_CLIENT_ID for a higher one), Eurostat 2
requests, dane.gov.pl the resource list plus one ZIP per year not yet in the MF cache (the first run downloads
about 210 MB; the cache keeps parsed values only, default <db dir>/<db stem>-cache).

Guards: --db is required, must not exist yet (an existing file is never touched) and must not be the
application's database (the default path or $BUDGET_DB_PATH, compared after realpath); the MF cache must
not be the application's cache directory (refresh.cache_dir() or <default db dir>/cache). When the refresh
fails, the database file this script created is removed again (a re-run is not refused).

Exit code: 0 when the refresh succeeded (all sources fetched, quality gates passed, snapshot written),
1 when it failed (the report then lists the errors and violations), 2 when the guards refused to run.
"""

import argparse
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from app.api.refresh import DEFAULT_DB_PATH, get_clients, refresh
from app.api.refresh import cache_dir as app_cache_dir
from app.api.simulate import load_history
from app.data.dataset import EUROSTAT_SURPLUS
from app.data.mf_execution import CACHE_ENV
from app.model import config
from app.model.backtest import backtest
from app.model.macro import MACRO_VARS, MacroModel
from app.model.params import defaults
from app.model.simulate import TAXES, simulate
from app.store import Store

HORIZON = 5
N_PATHS = 2000
SEED = 20261010
REPORT_SERIES: tuple[str, ...] = (*MACRO_VARS, "gross_surplus", "gdp_nominal", "rev_vat", "rev_cit", "rev_pit")
TAX_ORDER: tuple[str, ...] = ("vat", "cit", "pit")
PIT_BREAK_YEAR = config.STRUCTURAL_BREAKS["rev_pit"]


class ReportRefused(Exception):
    pass


# ---------------------------------------------------------------- guards and wiring


def check_target(db: str | None, env: dict[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    if not db:
        raise ReportRefused("refusing to run: an explicit --db path (a new file) is required")
    target = os.path.realpath(db)
    protected = {os.path.realpath(DEFAULT_DB_PATH)}
    if env.get("BUDGET_DB_PATH"):
        protected.add(os.path.realpath(env["BUDGET_DB_PATH"]))
    if target in protected:
        raise ReportRefused(f"refusing to run: {target} is the application's database (default or $BUDGET_DB_PATH)")
    if os.path.exists(target):
        raise ReportRefused(f"refusing to run: {target} exists (the report writes only to a new database)")
    return Path(target)


def resolve_cache_dir(db: Path, cache_dir: str | None) -> str:
    """--cache-dir, else <db dir>/<db stem>-cache; never the application's own MF cache."""
    chosen = cache_dir if cache_dir else str(db.parent / f"{db.stem}-cache")
    protected = {os.path.realpath(DEFAULT_DB_PATH.parent / "cache")}
    app_cache = app_cache_dir()
    if app_cache:
        protected.add(os.path.realpath(app_cache))
    if os.path.realpath(chosen) in protected:
        raise ReportRefused(f"refusing to run: {os.path.realpath(chosen)} is the application's MF cache directory")
    return chosen


def default_clients(cache_dir: str):
    """The API's own client wiring (refresh.get_clients), with the MF cache directory set for this call only."""
    old = os.environ.get(CACHE_ENV)
    os.environ[CACHE_ENV] = cache_dir
    try:
        return get_clients()
    finally:
        if old is None:
            del os.environ[CACHE_ENV]
        else:
            os.environ[CACHE_ENV] = old


class RecordingClient:
    """Delegates to a source client and keeps what it returned (for the gate metrics in the report)."""

    def __init__(self, client):
        self.client = client
        self.name = client.name
        self.result: dict[str, pd.DataFrame] = {}

    @property
    def warnings(self) -> list[str]:
        return list(getattr(self.client, "warnings", None) or [])

    def fetch(self) -> dict[str, pd.DataFrame]:
        self.result = self.client.fetch()
        return self.result


# ---------------------------------------------------------------- formatting helpers (pure)


def fmt(x, digits: int = 3) -> str:
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "–"
    return f"{float(x):.{digits}f}"


def _values(df: pd.DataFrame | None) -> pd.Series:
    if df is None or df.empty:
        return pd.Series(dtype=float)
    return df["value"].astype(float).dropna().sort_index()


def _last(values: pd.Series, n: int = 3, upto: int | None = None) -> str:
    if upto is not None:
        values = values[values.index <= upto]
    return ", ".join(f"{int(y)}: {fmt(v)}" for y, v in values.iloc[-n:].items()) or "–"


def series_lines(series: dict[str, tuple[str, pd.DataFrame]]) -> list[str]:
    out = []
    for name in REPORT_SERIES:
        if name not in series:
            out.append(f"  {name:<20} BRAK")
            continue
        source, df = series[name]
        v = _values(df)
        if v.empty:
            out.append(f"  {name:<20} {source:<17} BRAK WARTOŚCI")
            continue
        years = [int(y) for y in v.index]
        gaps = sorted(set(range(years[0], years[-1] + 1)) - set(years))
        span = f"{years[0]}–{years[-1]} ({len(years)} lat{', luki: ' + ', '.join(map(str, gaps)) if gaps else ''})"
        out.append(f"  {name:<20} {source:<17} {span:<22} ostatnie: {_last(v)}")
    return out


def common_macro_years(series: dict[str, tuple[str, pd.DataFrame]]) -> list[int]:
    if not all(v in series for v in MACRO_VARS):
        return []
    sets = [set(int(y) for y in _values(series[v][1]).index) for v in MACRO_VARS]
    return sorted(set.intersection(*sets))


def gate_lines(ok: bool, errors: dict[str, str], fetched: dict[str, pd.DataFrame]) -> list[str]:
    out = []
    if ok:
        out.append("Bramki jakości: OK (wszystkie źródła pobrane, 0 naruszeń; zapisano synthetic=0)")
    else:
        out.append("Bramki jakości / odświeżenie: NIE PRZESZŁO – nic nie zapisano")
        for source, message in errors.items():
            out.append(f"  {source}: {message}")
    cons, gdp = _values(fetched.get("consumption_nominal")), _values(fetched.get("gdp_nominal"))
    both = pd.concat([cons, gdp], axis=1, join="inner").dropna()
    if not both.empty:
        y = int(both.index[-1])
        out.append(f"  (b) konsumpcja / PKB nominalny w {y} r.: {fmt(both.iloc[-1, 0] / both.iloc[-1, 1])} (zakres 0.4–0.7)")
    bdl, eu = _values(fetched.get("gross_surplus")), _values(fetched.get(EUROSTAT_SURPLUS))
    both = pd.concat([bdl.rename("b"), eu.rename("e")], axis=1, join="inner").dropna()
    if not both.empty:
        diff = (both["b"] / both["e"] - 1.0).abs()
        y = int(diff.idxmax())
        out.append(
            f"  (d) nadwyżka operacyjna GUS BDL vs Eurostat: {len(both)} wspólnych lat "
            f"({int(both.index[0])}–{int(both.index[-1])}), największa różnica {float(diff.max()) * 100:.2f}% w {y} r. (limit 2%)"
        )
    return out


def warning_lines(warnings: list[str]) -> list[str]:
    if not warnings:
        return ["Ostrzeżenia źródeł: brak"]
    return ["Ostrzeżenia źródeł (nie przerywają odświeżenia):", *(f"  - {w}" for w in warnings)]


def calibration_lines(calibration: dict) -> list[str]:
    out = ["Kalibracja (średnia relacja wykonania do wyniku modułu przy obecnym prawie):"]
    for tax in TAX_ORDER:
        c = calibration.get(tax)
        if not c:
            out.append(f"  {tax.upper()}: moduł wyłączony (brak kalibracji)")
            continue
        out.append(f"  {tax.upper()}: współczynnik {c['factor']:.6g}, lata {', '.join(map(str, c['years']))}")
    return out


def forecast_lines(sim: dict, history: dict[str, pd.DataFrame]) -> list[str]:
    years = sim["years"]
    last_model_year = years[0] - 1
    out = [f"Prognoza (mediana, mld zł; parametry domyślne = obecne prawo; horyzont {len(years)} lat od {years[0]}):"]
    for tax in TAX_ORDER:
        bands = sim["taxes"].get(tax)
        realised = _values(history.get(f"rev_{tax}"))
        if not bands:
            out.append(f"  {tax.upper()}: moduł wyłączony")
            continue
        out.append(f"  {tax.upper()}: wykonanie {_last(realised, 3, last_model_year)}")
        for i, y in enumerate(years):
            real = f"; wykonanie {fmt(realised.loc[y])}" if y in realised.index else ""
            out.append(
                f"    {y}: {fmt(bands['median'][i])} (p10–p90 {fmt(bands['p10'][i])}–{fmt(bands['p90'][i])}{real})"
            )
    return out


def backtest_lines(bt: dict) -> list[str]:
    if bt.get("message"):
        return [f"Backtest: {bt['message']}"]
    out = [
        f"Backtest (origins: {bt.get('n_origins', 0)}, pominięte: {bt.get('n_skipped', 0)}; horyzont 3 lata, mediana vs wykonanie):"
    ]
    for tax in TAX_ORDER:
        if tax not in bt.get("mape", {}):
            out.append(f"  {tax.upper()}: brak ocenionych lat")
            continue
        out.append(
            f"  {tax.upper()}: MAPE {bt['mape'][tax]:.2f}%, pokrycie 80% {bt['coverage80'][tax]:.0%}, "
            f"pokrycie 95% {bt['coverage95'][tax]:.0%}"
        )
    out += [f"  uwaga: {n}" for n in bt.get("notes", [])]
    return out


def pit_break_lines(history: dict[str, pd.DataFrame], calibration: dict) -> list[str]:
    pit = _values(history.get("rev_pit"))
    out = [f"Załamanie PIT {PIT_BREAK_YEAR}:"]
    if PIT_BREAK_YEAR in pit.index and PIT_BREAK_YEAR - 1 in pit.index:
        before, after = float(pit.loc[PIT_BREAK_YEAR - 1]), float(pit.loc[PIT_BREAK_YEAR])
        out.append(
            f"  wykonanie PIT w budżecie państwa {PIT_BREAK_YEAR - 1}: {fmt(before)}, {PIT_BREAK_YEAR}: {fmt(after)} mld zł "
            f"({(after / before - 1) * 100:+.1f}%) – reforma finansowania JST (większy udział JST w PIT)"
        )
    else:
        out.append(f"  brak pary lat {PIT_BREAK_YEAR - 1}/{PIT_BREAK_YEAR} w rev_pit")
    years = calibration.get("pit", {}).get("years")
    out.append(f"  kalibracja PIT używa tylko lat < {PIT_BREAK_YEAR}: {', '.join(map(str, years)) if years else '–'}")
    out.append(f"  backtest nie ocenia realizacji rev_pit od {PIT_BREAK_YEAR} r.")
    out.append(
        f"  prognoza PIT jest liczona według zasad podziału sprzed reformy – nieporównywalna z wykonaniem od {PIT_BREAK_YEAR} r."
    )
    return out


def format_report(
    meta: dict[str, str],
    result,
    fetched: dict[str, pd.DataFrame],
    series: dict[str, tuple[str, pd.DataFrame]] | None = None,
    sim: dict | None = None,
    bt: dict | None = None,
    history: dict[str, pd.DataFrame] | None = None,
) -> str:
    lines = [f"Raport odświeżenia na żywo – {meta.get('date', '')}"]
    lines += [f"  {k}: {v}" for k, v in meta.items() if k != "date"]
    lines.append("")
    lines += gate_lines(result.ok, result.errors, fetched)
    lines += warning_lines(result.warnings)
    if not result.ok or series is None:
        return "\n".join(lines) + "\n"
    lines += ["", "Serie w magazynie (mld zł; indeksy jako poziomy; zatrudnienie w etatach; płaca w zł/mies.):"]
    lines += series_lines(series)
    common = common_macro_years(series)
    if common:
        lines.append(f"  wspólne lata makro ({', '.join(MACRO_VARS)}): {len(common)} ({common[0]}–{common[-1]})")
    lines.append("")
    lines += calibration_lines(sim["calibration"])
    if sim.get("disabled_modules"):
        lines += [f"  {d['message']}" for d in sim["disabled_modules"]]
    lines.append("")
    lines += forecast_lines(sim, history)
    lines.append("")
    lines += backtest_lines(bt)
    lines.append("")
    lines += pit_break_lines(history, sim["calibration"])
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- run


def _git_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=10,
                             cwd=Path(__file__).resolve().parent)
        return out.stdout.strip() or "?"
    except (OSError, subprocess.SubprocessError):
        return "?"


def stored_series(store: Store) -> dict[str, tuple[str, pd.DataFrame]]:
    import sqlite3
    from contextlib import closing

    with closing(sqlite3.connect(store.path)) as c:
        sources = dict(c.execute("SELECT name, MIN(source) FROM series GROUP BY name").fetchall())
    return {name: (src, store.load_series(name)) for name, src in sources.items()}


def _remove_db(db: Path) -> None:
    """Remove the database this run created (check_target guaranteed it did not exist before)."""
    for path in (db, db.with_name(db.name + "-journal")):
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def run(db: Path, cache_dir: str, make_clients) -> tuple[int, str]:
    meta = {
        "date": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "commit": _git_commit(),
        "baza": str(db),
        "cache MF": cache_dir,
        "BDL_CLIENT_ID": "ustawiony" if os.environ.get("BDL_CLIENT_ID") else "brak (limit anonimowy)",
    }
    db.parent.mkdir(parents=True, exist_ok=True)
    store = Store(str(db))
    clients = make_clients(cache_dir)
    recorders = [RecordingClient(c) for c in clients]
    try:
        result = refresh(store, recorders)
    finally:
        close = getattr(clients, "close", None)
        if callable(close):
            close()
    fetched: dict[str, pd.DataFrame] = {}
    for r in recorders:
        fetched.update(r.result)
    if not result.ok:
        _remove_db(db)
        return 1, format_report(meta, result, fetched)

    model = MacroModel.from_dict(store.load_model())
    history = load_history(store)
    meta["symulacja"] = f"parametry domyślne, horyzont {HORIZON}, {N_PATHS} ścieżek, seed {SEED}"
    sim = simulate(model, history, defaults(), HORIZON, N_PATHS, SEED).to_dict()
    bt = backtest(history).to_dict()
    return 0, format_report(meta, result, fetched, stored_series(store), sim, bt, history)


def main(argv: list[str] | None = None, make_clients=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", help="path of a NEW SQLite file for the refreshed data (must not exist)")
    ap.add_argument("--cache-dir", help="MF cache directory (default: <db dir>/<db stem>-cache)")
    args = ap.parse_args(argv)
    try:
        db = check_target(args.db)
        cache = resolve_cache_dir(db, args.cache_dir)
    except ReportRefused as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    try:
        code, report = run(db, cache, make_clients or default_clients)
    except BaseException:
        _remove_db(db)
        raise
    print(report, end="")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
