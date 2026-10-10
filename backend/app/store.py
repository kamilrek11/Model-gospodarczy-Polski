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

    def _write_series(self, conn: sqlite3.Connection, name: str, source: str, df: pd.DataFrame) -> None:
        rows = [(name, int(y), None if pd.isna(v) else float(v), source) for y, v in df["value"].items()]
        conn.execute("DELETE FROM series WHERE name = ?", (name,))
        conn.executemany("INSERT INTO series (name, year, value, source) VALUES (?, ?, ?, ?)", rows)

    def _write_model(self, conn: sqlite3.Connection, payload: dict) -> None:
        conn.execute("INSERT OR REPLACE INTO model (id, payload) VALUES (1, ?)", (json.dumps(payload),))

    def _write_meta(self, conn: sqlite3.Connection, key: str, value: str) -> None:
        conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))

    def save_series(self, name: str, source: str, df: pd.DataFrame) -> None:
        with self._conn() as c:
            self._write_series(c, name, source, df)

    def save_snapshot(
        self, series: dict[str, tuple[str, pd.DataFrame]], model: dict, meta: dict[str, str]
    ) -> None:
        """Write series (name -> (source, df)), the model and meta in ONE transaction: all or nothing."""
        conn = self._conn()
        try:
            with conn:  # commits on success, rolls back on any exception
                for name, (source, df) in series.items():
                    self._write_series(conn, name, source, df)
                self._write_model(conn, model)
                for key, value in meta.items():
                    self._write_meta(conn, key, value)
        finally:
            conn.close()

    def load_series(self, name: str) -> pd.DataFrame:
        with self._conn() as c:
            rows = c.execute("SELECT year, value FROM series WHERE name = ? ORDER BY year", (name,)).fetchall()
        idx = pd.Index([r[0] for r in rows], dtype="int64", name="year")
        return pd.DataFrame({"value": pd.Series([r[1] for r in rows], dtype="float64").values}, index=idx)

    def save_model(self, payload: dict) -> None:
        with self._conn() as c:
            self._write_model(c, payload)

    def load_model(self) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT payload FROM model WHERE id = 1").fetchone()
        return json.loads(row[0]) if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self._conn() as c:
            self._write_meta(c, key, value)

    def get_meta(self, key: str) -> str | None:
        with self._conn() as c:
            row = c.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None
