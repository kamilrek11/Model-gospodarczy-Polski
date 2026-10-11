from typing import Protocol

import httpx
import pandas as pd

# cap for JSON API responses (BDL, Eurostat, the dane.gov.pl resource list); real ones are < 1 MB
MAX_JSON_BYTES = 20_000_000
_DROPPED_HEADERS = ("content-encoding", "content-length", "transfer-encoding")


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


def get_capped(http: httpx.Client, url: str, *, source: str, max_bytes: int | None = None, **kwargs) -> httpx.Response:
    """GET streamed with a size cap on the (decoded) body; returns a fully read response.

    A larger body (or a larger declared Content-Length) raises SourceError before it is held in memory.
    httpx.HTTPError propagates to the caller, like http.get().
    """
    limit = MAX_JSON_BYTES if max_bytes is None else max_bytes
    with http.stream("GET", url, **kwargs) as r:
        declared = r.headers.get("Content-Length", "")
        if declared.isdigit() and int(declared) > limit:
            raise SourceError(source, f"response from {url} declares {declared} bytes (limit {limit})")
        buf = bytearray()
        for chunk in r.iter_bytes():
            buf += chunk
            if len(buf) > limit:
                raise SourceError(source, f"response from {url} exceeds {limit} bytes")
        # the body is already decoded: drop the encoding headers so the copy is not decoded twice
        headers = [(k, v) for k, v in r.headers.multi_items() if k.lower() not in _DROPPED_HEADERS]
        return httpx.Response(r.status_code, headers=headers, content=bytes(buf), request=r.request)
