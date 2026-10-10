import itertools
import time
from urllib.parse import urlsplit

import httpx
import pandas as pd

from app.data.base import SourceError, get_capped, to_frame
from app.data.gus_bdl import GusBdlClient

EUROSTAT_BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
DATASET = "nama_10_gdp"
SINCE = 2000
TIMEOUT = httpx.Timeout(20.0)
SOURCE = "eurostat"

# series name -> (na_item, unit); values come as million zl, published as billion zl.
EUROSTAT_SERIES = {
    "consumption_nominal": ("P31_S14", "CP_MNAC"),
    "gross_surplus_eurostat": ("B2A3G", "CP_MNAC"),
}


def decode_jsonstat(doc: object) -> dict[tuple, dict[int, float]]:
    """JSON-stat 2.0 dataset -> {(non-time category codes in `id` order): {year: value}}.

    `value` is a sparse dict keyed by the flat row-major index; an absent/null entry is a
    missing year (dropped, never 0). Flags in `status` ('p', 'e', 'u', 'b', ...) do not
    affect the value. Anything structurally wrong raises SourceError.
    """

    def bad(msg: str) -> SourceError:
        return SourceError(SOURCE, f"malformed JSON-stat: {msg}")

    if not isinstance(doc, dict):
        raise bad("not an object")
    if doc.get("error"):
        raise bad(f"error object {doc['error']!r}")
    try:
        ids, size, values = doc["id"], doc["size"], doc["value"]
        if not isinstance(values, dict):
            raise bad("`value` is not a sparse dict")
        if len(ids) != len(size) or "time" not in ids:
            raise bad("`id`/`size` mismatch or no time dimension")
        if any(not isinstance(n, int) or isinstance(n, bool) or n < 0 for n in size):
            raise bad(f"invalid size {size!r}")
        if 0 in size:
            raise SourceError(SOURCE, f"empty dataset (size {size}), e.g. an unknown unit code")
        cats = []
        for dim, n in zip(ids, size):
            index = doc["dimension"][dim]["category"]["index"]
            ordered = sorted(index.items(), key=lambda kv: kv[1])
            if [p for _, p in ordered] != list(range(n)):
                raise bad(f"category index of {dim!r} does not match size {n}")
            cats.append([code for code, _ in ordered])
        tpos = ids.index("time")
        years = [int(c) for c in cats[tpos]]
        out: dict[tuple, dict[int, float]] = {}
        for combo in itertools.product(*[range(n) for n in size]):
            flat = 0
            for k, n in zip(combo, size):
                flat = flat * n + k
            v = values.get(str(flat))
            if v is None:
                continue
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise bad(f"non-numeric value {v!r}")
            key = tuple(cats[j][combo[j]] for j in range(len(ids)) if j != tpos)
            out.setdefault(key, {})[years[combo[tpos]]] = float(v)
        return out
    except SourceError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, IndexError) as e:
        raise bad(repr(e)) from e


class EurostatClient:
    """Eurostat dissemination API client (nama_10_gdp), verified against the live API on 2026-10-10."""

    name = SOURCE

    def __init__(
        self,
        http: httpx.Client,
        *,
        base_url: str = EUROSTAT_BASE,
        sleep=time.sleep,
        max_retries: int = 3,
    ):
        parts = urlsplit(base_url)
        if parts.scheme != "https" or not parts.hostname:
            raise SourceError(SOURCE, f"base_url must be https, got {base_url!r}")
        self.base_url = base_url.rstrip("/")
        self.host = parts.hostname
        self.http = http
        self.sleep = sleep
        self.max_retries = max_retries

    def _get(self, url: str, params: dict) -> object:
        for attempt in range(self.max_retries + 1):
            try:
                r = get_capped(self.http, url, source=SOURCE, params=params, timeout=TIMEOUT, follow_redirects=False)
            except httpx.HTTPError as e:
                raise SourceError(SOURCE, f"request failed for {url}: {e}") from e
            if r.url.scheme != "https" or r.url.host != self.host:
                raise SourceError(SOURCE, f"response from unexpected location {r.url.host!r}")
            if r.status_code == 429 or r.status_code >= 500:
                if attempt < self.max_retries:
                    self.sleep(GusBdlClient._wait_seconds(r, attempt))
                    continue
                raise SourceError(SOURCE, f"HTTP {r.status_code} for {url} after {attempt + 1} attempts")
            if 300 <= r.status_code < 400:
                raise SourceError(SOURCE, f"HTTP {r.status_code} redirect for {url} (not followed)")
            if r.status_code >= 400:
                raise SourceError(SOURCE, f"HTTP {r.status_code} for {url}")
            try:
                return r.json()
            except ValueError as e:
                raise SourceError(SOURCE, f"invalid JSON from {url}: {e}") from e
        raise SourceError(SOURCE, f"retries exhausted for {url}")  # pragma: no cover

    def _fetch_series(self, series: str, na_item: str, unit: str) -> dict[int, float]:
        params = {
            "format": "JSON",
            "lang": "EN",
            "geo": "PL",
            "na_item": na_item,
            "unit": unit,
            "sinceTimePeriod": SINCE,
        }
        decoded = decode_jsonstat(self._get(f"{self.base_url}/{DATASET}", params))
        if len(decoded) != 1:
            raise SourceError(SOURCE, f"expected a single series for {series}, got {len(decoded)}")
        (key, rows), = decoded.items()
        if key != ("A", unit, na_item, "PL"):
            raise SourceError(SOURCE, f"unexpected series {key!r} for {series}")
        if not rows:
            raise SourceError(SOURCE, f"no data for {series}")
        return rows

    def fetch(self) -> dict[str, pd.DataFrame]:
        out = {}
        for series, (na_item, unit) in EUROSTAT_SERIES.items():
            rows = self._fetch_series(series, na_item, unit)
            out[series] = to_frame([(y, v / 1000.0) for y, v in rows.items()])
        return out
