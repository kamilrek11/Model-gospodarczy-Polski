import re
import time

import httpx
import pandas as pd

from app.data.base import SourceError, to_frame
from app.data.series_map import BDL_NATIONAL_UNIT_ID, BDL_SERIES
from app.data.transform import chain_growth

# attrId values that carry a usable number (1 final, 3/11/13/20/21 flagged, 9 preliminary, 97 other).
# Everything else (e.g. 4 = "no data", val 0.0) is a missing value.
VALUE_ATTRS = frozenset({1, 3, 9, 11, 13, 20, 21, 97})
FINAL_ATTR = 1
PAGE_SIZE = 100  # API maximum
MAX_WAIT_S = 30.0
DEFAULT_BACKOFF_S = (1.0, 2.0, 4.0)
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


class GusBdlClient:
    """BDL API v1 client (verified against the live API on 2026-10-10)."""

    name = "gus_bdl"

    def __init__(
        self,
        base_url: str,
        http: httpx.Client,
        *,
        client_id: str | None = None,
        sleep=time.sleep,
        max_retries: int = 3,
    ):
        self.base_url = base_url.rstrip("/")
        self.http = http
        self.client_id = client_id
        self.sleep = sleep
        self.max_retries = max_retries

    @staticmethod
    def _wait_seconds(response: httpx.Response, attempt: int) -> float:
        m = _NUMBER.match(response.headers.get("Retry-After", "").strip())
        if m:
            wait = float(m.group().replace(",", "."))
        else:
            wait = DEFAULT_BACKOFF_S[min(attempt, len(DEFAULT_BACKOFF_S) - 1)]
        return min(wait, MAX_WAIT_S)

    def _get(self, url: str, params: dict) -> object:
        headers = {"X-ClientId": self.client_id} if self.client_id else {}
        for attempt in range(self.max_retries + 1):
            try:
                r = self.http.get(url, params=params, headers=headers)
            except httpx.HTTPError as e:
                raise SourceError(self.name, f"request failed for {url}: {e}") from e
            if r.status_code == 429 or r.status_code >= 500:
                if attempt < self.max_retries:
                    self.sleep(self._wait_seconds(r, attempt))
                    continue
                raise SourceError(self.name, f"HTTP {r.status_code} for {url} after {attempt + 1} attempts")
            if r.status_code >= 400:
                raise SourceError(self.name, f"HTTP {r.status_code} for {url}")
            try:
                return r.json()
            except ValueError as e:
                raise SourceError(self.name, f"invalid JSON from {url}: {e}") from e
        raise SourceError(self.name, f"retries exhausted for {url}")  # pragma: no cover

    def _fetch_var(self, series: str, var_id: str) -> dict[int, tuple[float, int]]:
        """year -> (value, attrId) for the national unit, missing values dropped."""
        url = f"{self.base_url}/data/by-variable/{var_id}"
        params = {"format": "json", "lang": "pl", "unit-level": 0, "page-size": PAGE_SIZE}
        body = self._get(url, params)
        rows: dict[int, tuple[float, int]] = {}
        try:
            results = body["results"]
            if len(results) != 1 or str(results[0]["id"]) != BDL_NATIONAL_UNIT_ID:
                raise SourceError(self.name, f"national unit {BDL_NATIONAL_UNIT_ID} not found for {series}")
            for v in results[0]["values"]:
                year, attr = int(v["year"]), int(v["attrId"])
                if attr not in VALUE_ATTRS or v.get("val") is None:
                    continue
                rows[year] = (float(v["val"]), attr)
        except SourceError:
            raise
        except (KeyError, TypeError, ValueError, AttributeError, IndexError) as e:
            raise SourceError(self.name, f"malformed response for {series}: {e!r}") from e
        if not rows:
            raise SourceError(self.name, f"no data for {series}")
        return rows

    def fetch(self) -> dict[str, pd.DataFrame]:
        raw = {s: self._fetch_var(s, vid) for s, vid in BDL_SERIES.items()}

        def values(s: str, scale: float = 1.0) -> list[tuple[int, float]]:
            return [(y, v * scale) for y, (v, _) in raw[s].items()]

        def growth(s: str) -> pd.Series:
            return pd.Series({y: v for y, (v, _) in raw[s].items()}, dtype="float64")

        final_years = [y for y, (_, a) in raw["gdp_nominal"].items() if a == FINAL_ATTR]
        if not final_years:
            raise SourceError(self.name, "no final nominal GDP year to anchor pkb_real")
        base_year = max(final_years)
        anchor = raw["gdp_nominal"][base_year][0] / 1000.0
        cpi_growth = growth("cpi_growth")
        try:
            pkb = chain_growth(growth("pkb_growth"), base_year, anchor)
            cpi = chain_growth(cpi_growth, int(cpi_growth.index.min()) - 1, 100.0)
        except ValueError as e:
            raise SourceError(self.name, f"cannot chain index series: {e}") from e
        return {
            "pkb_real": to_frame(list(pkb.items())),
            "employment": to_frame(values("employment")),
            "wage_nominal": to_frame(values("wage_nominal")),
            "cpi": to_frame(list(cpi.items())),
            "gross_surplus": to_frame(values("gross_surplus", 1 / 1000.0)),
            "gdp_nominal": to_frame(values("gdp_nominal", 1 / 1000.0)),
        }
