import json
from pathlib import Path

import httpx
import pandas as pd
import pytest

from app.data.base import SourceError
from app.data.execution import ExecutionClient, HttpJsonLoader
from app.data.gus_bdl import GusBdlClient

FIX = Path(__file__).parent / "fixtures"
BASE = "https://bdl.test/api/v1"
# test-only mapping with fake ids matching the synthetic fixtures
TEST_MAP = {"pkb_real": {"var_id": "9001", "unit": "Polska"}}


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def client(handler, series_map=TEST_MAP):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return GusBdlClient(BASE, http, series_map=series_map)


def paged(request):
    page = request.url.params.get("page", "0")
    return httpx.Response(200, json=load("synthetic_bdl_page1.json" if page == "0" else "synthetic_bdl_page2.json"))


def test_gus_client_parses_series():
    seen = []
    def h(req):
        seen.append(req)
        return httpx.Response(200, json=load("synthetic_bdl_page2.json"))
    out = client(h).fetch()
    df = out["pkb_real"]
    assert list(df.index) == [2022] and df.index.name == "year"
    assert df["value"].iloc[0] == 125.0
    assert "/data/by-variable/9001" in str(seen[0].url)


def test_gus_client_raises_source_error_on_http_500():
    with pytest.raises(SourceError) as e:
        client(lambda r: httpx.Response(500)).fetch()
    assert e.value.source == "gus_bdl"


def test_gus_client_raises_on_429_and_timeout():
    with pytest.raises(SourceError):
        client(lambda r: httpx.Response(429)).fetch()
    def boom(r):
        raise httpx.ConnectTimeout("t")
    with pytest.raises(SourceError) as e:
        client(boom).fetch()
    assert e.value.source == "gus_bdl"


def test_gus_client_paginates():
    df = client(paged).fetch()["pkb_real"]
    assert list(df.index) == [2020, 2021, 2022]
    assert list(df["value"]) == [100.0, 110.0, 125.0]  # national unit only


def test_gus_client_unmapped_series_raises():
    c = client(paged, series_map=None)  # default placeholder map
    with pytest.raises(SourceError, match="series not mapped"):
        c.fetch()


def test_gus_client_missing_national_unit_raises():
    body = load("synthetic_bdl_page2.json")
    body["results"][0]["name"] = "MAZOWIECKIE"
    with pytest.raises(SourceError):
        client(lambda r: httpx.Response(200, json=body)).fetch()


def test_execution_client_parses():
    def h(req):
        return httpx.Response(200, json=load("synthetic_execution.json"))
    http = httpx.Client(transport=httpx.MockTransport(h))
    loader = HttpJsonLoader({"rev_pit": "https://x.test/pit"}, http)
    out = ExecutionClient(loader, series=("rev_pit",)).fetch()
    assert out["rev_pit"]["value"].tolist() == [70.5, 75.25]
    assert isinstance(out["rev_pit"], pd.DataFrame)


def test_execution_client_errors_and_unmapped():
    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    with pytest.raises(SourceError) as e:
        ExecutionClient(HttpJsonLoader({"rev_pit": "https://x.test/pit"}, http), series=("rev_pit",)).fetch()
    assert e.value.source == "execution"
    with pytest.raises(SourceError, match="series not mapped"):
        ExecutionClient(HttpJsonLoader({}, http), series=("rev_pit",)).fetch()
    with pytest.raises(SourceError, match="series not mapped"):
        ExecutionClient(HttpJsonLoader({"rev_pit": "TODO_VERIFY_URL"}, http), series=("rev_pit",)).fetch()
