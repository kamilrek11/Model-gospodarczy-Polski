import json
import sqlite3

import pandas as pd


class Store:
    def __init__(self, path: str):
        self.path = path
        with self._conn() as c:
            c.execute(
                "CREATE TABLE IF NOT EXISTS series ("
                "name TEXT NOT NULL, year INTEGER NOT NULL, value REAL, source TEXT, "
                "PRIMARY KEY (name, year))"
            )
            c.execute("CREATE TABLE IF NOT EXISTS model (id INTEGER PRIMARY KEY CHECK (id = 1), payload TEXT NOT NULL)")
            c.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        return conn

    def save_series(self, name: str, source: str, df: pd.DataFrame) -> None:
        rows = [(name, int(y), None if pd.isna(v) else float(v), source) for y, v in df["value"].items()]
        with self._conn() as c:
            c.execute("DELETE FROM series WHERE name = ?", (name,))
            c.executemany("INSERT INTO series (name, year, value, source) VALUES (?, ?, ?, ?)", rows)

    def load_series(self, name: str) -> pd.DataFrame:
        with self._conn() as c:
            rows = c.execute("SELECT year, value FROM series WHERE name = ? ORDER BY year", (name,)).fetchall()
        idx = pd.Index([r[0] for r in rows], dtype="int64", name="year")
        return pd.DataFrame({"value": pd.Series([r[1] for r in rows], dtype="float64").values}, index=idx)

    def save_model(self, payload: dict) -> None:
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO model (id, payload) VALUES (1, ?)", (json.dumps(payload),))

    def load_model(self) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT payload FROM model WHERE id = 1").fetchone()
        return json.loads(row[0]) if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))

    def get_meta(self, key: str) -> str | None:
        with self._conn() as c:
            row = c.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None
