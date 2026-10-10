from typing import Protocol

import httpx
import pandas as pd

from app.data.base import SourceError, to_frame
from app.data.series_map import EXECUTION_ENDPOINTS, is_unmapped

SOURCE = "execution"


class ExecutionLoader(Protocol):
    def load(self, series: str) -> list[dict]:
        """Return rows [{"year": int, "value": float (mld zl)}]; raise SourceError on failure."""
        ...


class HttpJsonLoader:
    """Fetches {"rows": [{"year","value"}]} JSON from a configured URL per series.
    Response shape is an assumption (no verified endpoints)."""

    def __init__(self, endpoints: dict[str, str] | None = None, http: httpx.Client | None = None):
        self.endpoints = EXECUTION_ENDPOINTS if endpoints is None else endpoints
        self.http = http or httpx.Client(timeout=30)

    def load(self, series: str) -> list[dict]:
        url = self.endpoints.get(series)
        if is_unmapped(url):
            raise SourceError(SOURCE, f"series not mapped: {series}")
        try:
            r = self.http.get(url)
            r.raise_for_status()
            return r.json()["rows"]
        except httpx.HTTPStatusError as e:
            raise SourceError(SOURCE, f"HTTP {e.response.status_code} for {url}") from e
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as e:
            raise SourceError(SOURCE, f"request failed for {url}: {e}") from e


class ExecutionClient:
    name = SOURCE

    def __init__(self, loader: ExecutionLoader, series: tuple[str, ...] = ("rev_pit", "rev_cit", "rev_vat")):
        self.loader = loader
        self.series = series

    def fetch(self) -> dict[str, pd.DataFrame]:
        out = {}
        for s in self.series:
            try:
                rows = self.loader.load(s)
                out[s] = to_frame([(int(r["year"]), float(r["value"])) for r in rows])
            except SourceError:
                raise
            except (KeyError, TypeError, ValueError) as e:
                raise SourceError(SOURCE, f"bad rows for {s}: {e}") from e
        return out
