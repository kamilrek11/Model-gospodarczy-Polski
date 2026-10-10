from typing import Protocol

import pandas as pd


class SourceError(Exception):
    def __init__(self, source: str, message: str):
        super().__init__(f"[{source}] {message}")
        self.source = source
        self.message = message


class SourceClient(Protocol):
    name: str

    def fetch(self) -> dict[str, pd.DataFrame]:
        """Series name -> DataFrame indexed by year with a `value` column."""
        ...


def to_frame(rows: list[tuple[int, float]]) -> pd.DataFrame:
    rows = sorted(rows)
    idx = pd.Index([r[0] for r in rows], dtype="int64", name="year")
    return pd.DataFrame({"value": pd.Series([r[1] for r in rows], dtype="float64").values}, index=idx)
