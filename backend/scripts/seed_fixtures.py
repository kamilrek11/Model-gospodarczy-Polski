"""Seed a store with SYNTHETIC data so the app and the e2e tests run offline.

!!! The seeded numbers are INVENTED (random walk with fixed seed). They are NOT real
!!! GUS / MF / ZUS / Eurostat data and must NEVER be presented as real.

Guards: refuses to run unless env SEED_FIXTURES=1 AND an explicit --db path is given.
The path is resolved (realpath) and refused if it is the application's default database
or the current $BUDGET_DB_PATH, and refused if the file already exists but is not
marked synthetic (meta synthetic == "1"): an existing unmarked store is treated as possibly real.
"""

import argparse
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from app.api.refresh import DEFAULT_DB_PATH
from app.model.macro import MACRO_VARS, fit_macro
from app.store import Store

SOURCE = "synthetic"
N_YEARS = 24
FIRST_YEAR = 2002
WARNING = (
    "WARNING: SYNTHETIC DATA. The seeded series are invented (seed-deterministic) and are NOT real "
    "GUS/MF/ZUS/Eurostat figures. Never present them as real."
)

# Stable VAR(1) on log differences (rows = equation, cols = lagged variable).
_A = np.array(
    [
        [0.40, 0.10, 0.00, -0.10, 0.05],
        [0.20, 0.30, 0.00, 0.00, 0.00],
        [0.10, 0.10, 0.30, 0.20, 0.00],
        [0.00, 0.00, 0.10, 0.50, 0.00],
        [0.10, 0.00, 0.20, 0.10, 0.30],
    ]
)
_C = np.array([0.02, 0.005, 0.03, 0.01, 0.02])


class SeedRefused(Exception):
    pass


def check_guards(db: str | None, env: dict[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    if env.get("SEED_FIXTURES") != "1":
        raise SeedRefused("refusing to seed: set SEED_FIXTURES=1 (data is synthetic, never real)")
    if not db:
        raise SeedRefused("refusing to seed: an explicit --db path is required")
    target = os.path.realpath(db)
    protected = {os.path.realpath(DEFAULT_DB_PATH)}
    if env.get("BUDGET_DB_PATH"):
        protected.add(os.path.realpath(env["BUDGET_DB_PATH"]))
    if target in protected:
        raise SeedRefused(f"refusing to seed: {target} is the application's database (default or $BUDGET_DB_PATH)")
    if os.path.exists(target) and not _is_synthetic(target):
        raise SeedRefused(f"refusing to seed: {target} exists and is not marked synthetic (possibly real data)")
    return Path(target)


def _is_synthetic(path: str) -> bool:
    import sqlite3
    from contextlib import closing

    try:
        with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as c:
            row = c.execute("SELECT value FROM meta WHERE key = 'synthetic'").fetchone()
    except sqlite3.Error:
        return False
    return bool(row) and row[0] == "1"


def synthetic_panel(n_years: int = N_YEARS, seed: int = 20260101) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    k = len(MACRO_VARS)
    burn = 50
    d = np.zeros((n_years - 1 + burn, k))
    d[0] = np.linalg.solve(np.eye(k) - _A, _C)
    for t in range(1, len(d)):
        d[t] = _C + _A @ d[t - 1] + rng.normal(0, 0.01, k)
    d = d[burn:]
    levels = 100 * np.exp(np.vstack([np.zeros(k), np.cumsum(d, axis=0)]))
    idx = pd.Index(range(FIRST_YEAR, FIRST_YEAR + n_years), dtype="int64", name="year")
    lv = pd.DataFrame(levels, index=idx, columns=list(MACRO_VARS))
    noise = lambda: 1.0 + rng.normal(0, 0.01, n_years)  # noqa: E731
    nominal_gdp = lv["pkb_real"] * lv["cpi"] / 100.0
    gross_surplus = 0.4 * nominal_gdp * noise()
    wage_bill = lv["wage_nominal"] * lv["employment"] / 100.0
    panel = {v: lv[[v]].rename(columns={v: "value"}) for v in MACRO_VARS}
    panel["gross_surplus"] = pd.DataFrame({"value": gross_surplus}, index=idx)
    panel["rev_pit"] = pd.DataFrame({"value": 0.08 * wage_bill * noise()}, index=idx)
    panel["rev_cit"] = pd.DataFrame({"value": 0.03 * gross_surplus * noise()}, index=idx)
    panel["rev_vat"] = pd.DataFrame({"value": 0.12 * lv["consumption_nominal"] * noise()}, index=idx)
    return panel


def seed(db: Path) -> None:
    db.parent.mkdir(parents=True, exist_ok=True)
    panel = synthetic_panel()
    macro = pd.concat({v: panel[v]["value"] for v in MACRO_VARS}, axis=1)
    model = fit_macro(macro, lags=1)
    store = Store(str(db))
    store.save_snapshot(
        {name: (SOURCE, df) for name, df in panel.items()},
        model.to_dict(),
        {"updated_at": pd.Timestamp.now(tz="UTC").isoformat(), "synthetic": "1"},
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", help="explicit path of the SQLite file to seed (required)")
    args = ap.parse_args(argv)
    try:
        db = check_guards(args.db)
    except SeedRefused as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(WARNING, file=sys.stderr)
    seed(db)
    print(f"seeded synthetic data into {db}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
