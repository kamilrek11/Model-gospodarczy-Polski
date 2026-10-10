import json
from pathlib import Path

import httpx
import pandas as pd
import pytest

from app.data.base import SourceError
from app.data.execution import ExecutionClient, HttpJsonLoader

FIX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


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


def test_execution_client_empty_series_raises():
    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"rows": []})))
    with pytest.raises(SourceError, match="no data") as e:
        ExecutionClient(HttpJsonLoader({"rev_pit": "https://x.test/pit"}, http), series=("rev_pit",)).fetch()
    assert e.value.source == "execution"
