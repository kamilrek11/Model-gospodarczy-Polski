"""Realistic datasets for dataset/refresh/model tests, without network.

The REAL client classes (GusBdlClient, EurostatClient, MfBudgetExecutionClient) are run on the recorded
public responses in tests/fixtures/real through httpx.MockTransport. MF covers the reconstructed report
years 2016, 2018, 2023, 2024 and 2025 (incl. the real 2025 PIT structural break, 28.75 mld zł).
No synthetic generator is involved.
"""

from functools import lru_cache

import httpx
import pandas as pd

import tests.test_eurostat as eurostat_fx
import tests.test_gus_bdl_real as bdl_fx
import tests.test_mf_execution as mf_fx
from app.data.eurostat import EurostatClient
from app.data.gus_bdl import GusBdlClient
from app.data.mf_execution import MfBudgetExecutionClient

MF_YEARS = (2016, 2018, 2023, 2024, 2025)


class StubClient:
    def __init__(self, name: str, series: dict[str, pd.DataFrame], warnings: list[str] | None = None):
        self.name = name
        self.series = series
        self.warnings = list(warnings or [])

    def fetch(self) -> dict[str, pd.DataFrame]:
        return {k: v.copy() for k, v in self.series.items()}


def real_clients(http_clients: list[httpx.Client] | None = None) -> list:
    """The three real client classes wired to MockTransports serving the recorded fixtures."""
    bdl_http = httpx.Client(transport=httpx.MockTransport(bdl_fx.serving()))
    eu_http = httpx.Client(transport=httpx.MockTransport(eurostat_fx.serving()))
    mf_http = httpx.Client(transport=httpx.MockTransport(mf_fx.FakeDaneGov({y: mf_fx.report_zip(y) for y in MF_YEARS})))
    if http_clients is not None:
        http_clients.extend([bdl_http, eu_http, mf_http])
    no_sleep = lambda s: None  # noqa: E731
    return [
        GusBdlClient(bdl_fx.BASE, bdl_http, sleep=no_sleep),
        EurostatClient(eu_http, base_url=eurostat_fx.BASE, sleep=no_sleep),
        MfBudgetExecutionClient(mf_http, None, sleep=no_sleep),
    ]


@lru_cache(maxsize=1)
def _real_by_source() -> tuple[tuple[str, tuple[tuple[str, pd.DataFrame], ...]], ...]:
    https: list[httpx.Client] = []
    try:
        out = tuple((c.name, tuple(c.fetch().items())) for c in real_clients(https))
    finally:
        for h in https:
            h.close()
    return out


def real_by_source() -> dict[str, dict[str, pd.DataFrame]]:
    """client name -> fetched series (fresh copies)."""
    return {name: {s: df.copy() for s, df in series} for name, series in _real_by_source()}


def real_results() -> dict[str, pd.DataFrame]:
    """All fetched series merged (series name -> frame), as refresh() collects them."""
    return {s: df for series in real_by_source().values() for s, df in series.items()}


def real_stub_clients(transform=None) -> list[StubClient]:
    """Stub clients returning the real fetched series; `transform(series_name, df) -> df` alters them."""
    out = []
    for name, series in real_by_source().items():
        if transform is not None:
            series = {s: transform(s, df) for s, df in series.items()}
        out.append(StubClient(name, series))
    return out
