import httpx
import pandas as pd

from app.data.base import SourceError, to_frame
from app.data.series_map import BDL_SERIES, is_unmapped

MAX_PAGES = 100


class GusBdlClient:
    """BDL API v1 client (shape assumed from public docs; see task-4 report)."""

    name = "gus_bdl"

    def __init__(self, base_url: str, http: httpx.Client, series_map: dict | None = None, page_size: int = 100):
        self.base_url = base_url.rstrip("/")
        self.http = http
        self.series_map = BDL_SERIES if series_map is None else series_map
        self.page_size = page_size

    def _get(self, url: str, params: dict | None) -> dict:
        try:
            r = self.http.get(url, params=params)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            raise SourceError(self.name, f"HTTP {e.response.status_code} for {url}") from e
        except (httpx.HTTPError, ValueError) as e:
            raise SourceError(self.name, f"request failed for {url}: {e}") from e

    def _fetch_one(self, series: str, spec: dict) -> pd.DataFrame:
        var_id = spec.get("var_id")
        if is_unmapped(var_id):
            raise SourceError(self.name, f"series not mapped: {series}")
        unit = spec.get("unit", "Polska")
        url = f"{self.base_url}/data/by-variable/{var_id}"
        params: dict | None = {"format": "json", "lang": "pl", "page-size": self.page_size, "page": 0}
        rows: dict[int, float] = {}
        found_unit = False
        for _ in range(MAX_PAGES):
            body = self._get(url, params)
            for res in body.get("results", []):
                if res.get("name") != unit:
                    continue
                found_unit = True
                for v in res.get("values", []):
                    if v.get("val") is None:
                        continue
                    rows[int(v["year"])] = float(v["val"])
            nxt = (body.get("links") or {}).get("next")
            if not nxt:
                break
            url, params = nxt, None  # next link is absolute and carries its own query
        else:
            raise SourceError(self.name, f"too many pages for {series}")
        if not found_unit:
            raise SourceError(self.name, f"unit {unit!r} not found for {series}")
        return to_frame(list(rows.items()))

    def fetch(self) -> dict[str, pd.DataFrame]:
        return {s: self._fetch_one(s, spec) for s, spec in self.series_map.items()}
