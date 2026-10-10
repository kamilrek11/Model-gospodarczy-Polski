"""Live smoke tests against the REAL public sources (network). Skipped unless RUN_LIVE=1 (tests/conftest.py).

Run explicitly:  cd backend && RUN_LIVE=1 .venv/bin/python -m pytest -m live -q

Each test makes only small requests through the production client classes:
- GUS BDL: one request (nominal GDP, variable 458271, national unit only);
- Eurostat: two requests (nama_10_gdp P31_S14 and B2A3G, as the client always fetches both);
- MF (dane.gov.pl dataset 163): the resource list plus ONE yearly ZIP (2024, about 6.4 MB). The client
  supports restricting years (`years=range(2024, 2025)`), so no other year is downloaded; the cache is a
  per-test temporary directory, so the test always exercises the real download.

Reference values were recorded on 2026-10-10 (docs/data-sources-discovery.md). The tolerance (±3%) allows
for routine statistical revisions; a failure message says how far the live value drifted, so a revision
can be told apart from a unit or parsing error (those are off by orders of magnitude).
"""

import os

import httpx
import pytest

from app.api.refresh import BDL_BASE_URL, HTTP_TIMEOUT
from app.data.eurostat import EurostatClient
from app.data.gus_bdl import GusBdlClient
from app.data.mf_execution import MfBudgetExecutionClient
from app.data.series_map import BDL_SERIES

pytestmark = pytest.mark.live

TOLERANCE = 0.03


def _check(series: str, year: int, live: float, recorded: float, unit: str = "mld zł") -> None:
    drift = live / recorded - 1.0
    assert abs(drift) <= TOLERANCE, (
        f"{series} {year}: live value {live:.3f} {unit} differs from the value recorded on 2026-10-10 "
        f"({recorded:.3f} {unit}) by {drift:+.1%} (allowed ±{TOLERANCE:.0%}). A drift of a few percent is "
        f"probably a data revision (update the reference after checking the source); a factor near 1000 "
        f"points to a unit error (mln vs mld zł), anything else to a changed response shape or row/column."
    )


@pytest.fixture
def http():
    with httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=False) as client:
        yield client


def test_live_bdl_gdp_nominal_2024(http):
    client = GusBdlClient(BDL_BASE_URL, http, client_id=os.environ.get("BDL_CLIENT_ID") or None)
    rows = client._fetch_var("gdp_nominal", BDL_SERIES["gdp_nominal"])  # one request, mln zł
    assert 2024 in rows, f"BDL 458271 has no 2024 value any more (years: {sorted(rows)})"
    _check("gdp_nominal (BDL 458271)", 2024, rows[2024][0] / 1000.0, 3653.432)


def test_live_eurostat_consumption_2024(http):
    out = EurostatClient(http).fetch()
    cons = out["consumption_nominal"]["value"]
    assert 2024 in cons.index, f"Eurostat P31_S14 has no 2024 value (years: {list(cons.index)})"
    _check("consumption_nominal (Eurostat nama_10_gdp P31_S14)", 2024, float(cons.loc[2024]), 2056.557)


def test_live_mf_vat_2024(http, tmp_path):
    client = MfBudgetExecutionClient(http, str(tmp_path / "cache"), years=range(2024, 2025))
    out = client.fetch()
    vat = out["rev_vat"]["value"]
    assert list(vat.index) == [2024], f"expected only 2024, got {list(vat.index)}; warnings: {client.warnings}"
    _check("rev_vat (MF dataset 163, 007 row 1.1)", 2024, float(vat.loc[2024]), 287.68336891)
