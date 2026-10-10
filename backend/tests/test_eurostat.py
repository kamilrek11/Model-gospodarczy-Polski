"""EurostatClient against RECORDED real Eurostat responses (tests/fixtures/real); no network."""

import json
from pathlib import Path

import httpx
import pytest

from app.data.base import SourceError
from app.data.eurostat import EurostatClient, decode_jsonstat

REAL = Path(__file__).parent / "fixtures" / "real"
BASE = "https://eurostat.test/api/data"
CONS = "eurostat_nama_10_gdp_P31_S14_CP_MNAC.json"
GOS = "eurostat_nama_10_gdp_B2A3G_CP_MNAC.json"
BAD_UNIT = "eurostat_nama_10_gdp_invalid_unit_CP_MIO_NAC.json"
FLAGS = "eurostat_nama_pe_EMP_DC_flags.json"
MULTI = "eurostat_nama_10_gdp_multi_series.json"


def load(name):
    return json.loads((REAL / name).read_text(encoding="utf-8"))


def serving(overrides=None, seen=None):
    overrides = overrides or {}

    def handler(request):
        if seen is not None:
            seen.append(request)
        item = request.url.params["na_item"]
        body = overrides.get(item, load(CONS if item == "P31_S14" else GOS))
        return httpx.Response(200, json=body)

    return handler


def make(handler, base=BASE, **kw):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    kw.setdefault("sleep", lambda s: None)
    return EurostatClient(http, base_url=base, **kw)


def test_decode_jsonstat_sparse_values_and_flags():
    doc = load(FLAGS)
    out = decode_jsonstat(doc)
    assert list(out) == [("A", "THS_PER", "EMP_DC", "PL")]
    s = out[("A", "THS_PER", "EMP_DC", "PL")]
    assert len(s) == 26 and s[2000] == 14516.6
    assert s[2025] == 17432.03  # flag 'p' (provisional) keeps the value
    assert s[2003] == 13606.1  # flag 'b' (break) keeps the value
    del doc["value"]["5"]  # sparse: absent index = missing year, never 0
    doc["value"]["6"] = None
    s = decode_jsonstat(doc)[("A", "THS_PER", "EMP_DC", "PL")]
    assert 2005 not in s and 2006 not in s and len(s) == 24


def test_decode_jsonstat_multi_series_flat_index():
    out = decode_jsonstat(load(MULTI))
    assert len(out) == 6  # CLV20_MNAC exists only for some items: empty series are absent
    assert out[("A", "CP_MNAC", "P31_S14", "PL")][2023] == 1934063.0
    assert out[("A", "CP_MNAC", "B2A3G", "PL")][2022] == 1553042.0
    assert out[("A", "CLV20_MNAC", "B1GQ", "PL")][2025] == 2857985.0


def test_consumption_values():
    df = make(serving()).fetch()["consumption_nominal"]
    assert df.index.name == "year" and str(df.index.dtype) == "int64"
    assert list(df.columns) == ["value"] and str(df["value"].dtype) == "float64"
    assert df.index.min() == 2000 and df.index.max() == 2025 and len(df) == 26
    assert df.loc[2023, "value"] == pytest.approx(1934.063)
    assert df.loc[2024, "value"] == pytest.approx(2056.557)
    assert df.loc[2025, "value"] == pytest.approx(2209.033)


def test_gross_surplus_eurostat_2022_matches_bdl():
    out = make(serving()).fetch()
    assert set(out) == {"consumption_nominal", "gross_surplus_eurostat"}
    df = out["gross_surplus_eurostat"]
    assert df.loc[2022, "value"] == pytest.approx(1553.042)  # == BDL 458419 (1553042 mln)
    assert df.loc[2025, "value"] == pytest.approx(1765.710)


def test_request_uses_cp_mnac_not_cp_mio_nac():
    seen = []
    make(serving(seen=seen)).fetch()
    assert len(seen) == 2
    assert {r.url.params["na_item"] for r in seen} == {"P31_S14", "B2A3G"}
    for r in seen:
        assert r.url.scheme == "https" and r.url.path == "/api/data/nama_10_gdp"
        assert r.url.params["unit"] == "CP_MNAC"
        assert r.url.params["geo"] == "PL"
        assert r.url.params["sinceTimePeriod"] == "2000"


def test_empty_dataset_raises_source_error():
    bad = load(BAD_UNIT)
    assert 0 in bad["size"] and not bad["value"]
    with pytest.raises(SourceError) as e:
        make(serving({"P31_S14": bad})).fetch()
    assert e.value.source == "eurostat"
    with pytest.raises(SourceError):
        decode_jsonstat(bad)


def test_missing_values_dropped_not_zero():
    doc = load(CONS)
    del doc["value"]["25"]
    df = make(serving({"P31_S14": doc})).fetch()["consumption_nominal"]
    assert 2025 not in df.index and df.index.max() == 2024
    assert (df["value"] > 0).all()


def test_all_values_missing_raises():
    doc = load(CONS)
    doc["value"] = {}
    with pytest.raises(SourceError):
        make(serving({"P31_S14": doc})).fetch()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(error={"status": 400, "label": "bad"}),
        lambda d: d.pop("size"),
        lambda d: d.update(id=["freq", "unit", "na_item", "geo"]),  # no time dimension
        lambda d: d.update(value=[1, 2, 3]),
        lambda d: d["value"].update({"3": "n/a"}),
        lambda d: d["dimension"]["time"]["category"]["index"].update({"2000": "x"}),
    ],
)
def test_malformed_documents_are_source_errors(mutate):
    doc = load(CONS)
    mutate(doc)
    with pytest.raises(SourceError) as e:
        make(serving({"P31_S14": doc})).fetch()
    assert e.value.source == "eurostat"


def test_non_object_json_is_source_error():
    with pytest.raises(SourceError):
        make(lambda r: httpx.Response(200, json=[1, 2])).fetch()


def test_more_than_one_series_is_source_error():
    with pytest.raises(SourceError, match="single series"):
        make(serving({"P31_S14": load(MULTI)})).fetch()


def test_wrong_series_returned_is_source_error():
    with pytest.raises(SourceError, match="unexpected series"):
        make(serving({"P31_S14": load(GOS)})).fetch()  # B2A3G answer to a P31_S14 query


def test_http_errors_and_malformed_json_are_source_errors():
    calls = []

    def h500(r):
        calls.append(1)
        return httpx.Response(503)

    with pytest.raises(SourceError, match="503"):
        make(h500, max_retries=2).fetch()
    assert len(calls) == 3  # transient: retried, then error

    calls.clear()

    def h404(r):
        calls.append(1)
        return httpx.Response(404)

    with pytest.raises(SourceError, match="404"):
        make(h404).fetch()
    assert len(calls) == 1  # 4xx not retried

    with pytest.raises(SourceError, match="invalid JSON"):
        make(lambda r: httpx.Response(200, content=b"<html>not json")).fetch()


def test_transient_429_then_success_and_retry_after_used():
    sleeps, state = [], {"n": 0}

    def handler(request):
        state["n"] += 1
        if state["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "3"})
        return serving()(request)

    out = make(handler, sleep=sleeps.append).fetch()
    assert sleeps == [3.0] and len(out) == 2


def test_timeout_is_source_error_and_explicit_timeout_sent():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(SourceError, match="request failed"):
        make(handler).fetch()
    seen = []
    make(serving(seen=seen)).fetch()
    assert all("timeout" in r.extensions and r.extensions["timeout"]["read"] for r in seen)


def test_redirect_is_not_followed_and_is_source_error():
    def handler(request):
        return httpx.Response(302, headers={"Location": "https://evil.test/x"})

    seen = []

    def spy(request):
        seen.append(request.url.host)
        return handler(request)

    http = httpx.Client(transport=httpx.MockTransport(spy), follow_redirects=True)
    with pytest.raises(SourceError, match="redirect"):
        EurostatClient(http, base_url=BASE).fetch()
    assert seen == ["eurostat.test"]  # never requested the other host


def test_plain_http_base_url_rejected():
    with pytest.raises(SourceError, match="https"):
        EurostatClient(httpx.Client(), base_url="http://ec.europa.eu/x")


def test_default_base_url_is_eurostat_https():
    from app.data.eurostat import EUROSTAT_BASE

    assert EUROSTAT_BASE.startswith("https://ec.europa.eu/eurostat/")
