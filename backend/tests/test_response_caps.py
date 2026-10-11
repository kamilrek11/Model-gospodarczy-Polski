"""JSON responses of BDL, Eurostat and the dane.gov.pl resource list are read with a size cap (M6)."""

import httpx
import pytest

import app.data.base as base
import tests.test_eurostat as eurostat_fx
import tests.test_gus_bdl_real as bdl_fx
import tests.test_mf_execution as mf_fx
from app.data.base import SourceError
from app.data.eurostat import EurostatClient
from app.data.gus_bdl import GusBdlClient
from app.data.mf_execution import list_resources

NO_SLEEP = lambda s: None  # noqa: E731


class Endless(httpx.SyncByteStream):
    def __init__(self, pulled: list):
        self.pulled = pulled

    def __iter__(self):
        for _ in range(10_000):
            self.pulled.append(1)
            yield b" " * 10_000


def huge(pulled: list) -> httpx.Response:
    return httpx.Response(200, stream=Endless(pulled), headers={"Content-Type": "application/json"})


def test_default_cap_is_20_mb():
    assert base.MAX_JSON_BYTES == 20_000_000


@pytest.fixture
def small_cap(monkeypatch):
    monkeypatch.setattr(base, "MAX_JSON_BYTES", 50_000)


def test_bdl_response_capped(small_cap):
    pulled = []
    http = httpx.Client(transport=httpx.MockTransport(lambda r: huge(pulled)))
    with pytest.raises(SourceError, match="50000") as e:
        GusBdlClient(bdl_fx.BASE, http, sleep=NO_SLEEP).fetch()
    assert e.value.source == "gus_bdl" and len(pulled) < 10


def test_eurostat_response_capped(small_cap):
    pulled = []
    http = httpx.Client(transport=httpx.MockTransport(lambda r: huge(pulled)))
    with pytest.raises(SourceError, match="50000") as e:
        EurostatClient(http, base_url=eurostat_fx.BASE, sleep=NO_SLEEP).fetch()
    assert e.value.source == "eurostat" and len(pulled) < 10


def test_dane_gov_resource_list_capped(small_cap):
    pulled = []
    http = httpx.Client(transport=httpx.MockTransport(lambda r: huge(pulled)))
    with pytest.raises(SourceError, match="50000") as e:
        list_resources(http, sleep=NO_SLEEP)
    assert e.value.source == "mf_execution" and len(pulled) < 10


def test_declared_content_length_over_cap_rejected(small_cap):
    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"0" * 60_000)))
    with pytest.raises(SourceError, match="60000"):
        list_resources(http, sleep=NO_SLEEP)


def test_capped_reads_still_parse_normal_and_gzip_responses():
    import gzip
    import json

    body = {"data": [], "meta": {"count": 0}}
    raw = gzip.compress(json.dumps(body).encode())
    http = httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, content=raw, headers={"Content-Encoding": "gzip", "Content-Type": "application/json"})))
    assert list_resources(http, sleep=NO_SLEEP) == []
    fake = mf_fx.FakeDaneGov({2024: mf_fx.report_zip(2024)})
    assert len(list_resources(httpx.Client(transport=httpx.MockTransport(fake)), sleep=NO_SLEEP)) == 1
