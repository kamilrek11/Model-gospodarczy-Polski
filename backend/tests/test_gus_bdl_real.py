"""GusBdlClient against RECORDED real BDL responses (tests/fixtures/real); no network."""

import json
from pathlib import Path

import httpx
import pytest

from app.data.base import SourceError
from app.data.gus_bdl import GusBdlClient

REAL = Path(__file__).parent / "fixtures" / "real"
BASE = "https://bdl.test/api/v1"
FILES = {
    "458431": "bdl_458431_gdp_growth.json",
    "458271": "bdl_458271_gdp_nominal.json",
    "154173": "bdl_154173_employment.json",
    "64428": "bdl_64428_wage.json",
    "217230": "bdl_217230_cpi.json",
    "458419": "bdl_458419_gross_surplus.json",
}


def load(name):
    return json.loads((REAL / name).read_text(encoding="utf-8"))


def var_of(request):
    return request.url.path.rstrip("/").split("/")[-1]


def serving(overrides=None, seen=None):
    overrides = overrides or {}

    def handler(request):
        if seen is not None:
            seen.append(request)
        v = var_of(request)
        body = overrides[v] if v in overrides else load(FILES[v])
        return httpx.Response(200, json=body)

    return handler


def make(handler, **kw):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    kw.setdefault("sleep", lambda s: None)
    return GusBdlClient(BASE, http, **kw)


def test_values_for_poland_only_with_unit_level_0():
    seen = []
    make(serving(seen=seen)).fetch()
    assert {var_of(r) for r in seen} == set(FILES)
    for r in seen:
        assert r.url.params["unit-level"] == "0"
        assert "/data/by-variable/" in r.url.path
    results = load(FILES["458271"])["results"]
    assert [(x["name"], x["id"]) for x in results] == [("POLSKA", "000000000000")]


def test_nominal_gdp_458271_values():
    df = make(serving()).fetch()["gdp_nominal"]
    assert df.index.name == "year"
    assert df.loc[2000, "value"] == pytest.approx(751.669)
    assert df.loc[2024, "value"] == pytest.approx(3653.432)


def test_gross_surplus_converted_to_mld():
    df = make(serving()).fetch()["gross_surplus"]
    assert df.loc[2023, "value"] == pytest.approx(1676.697)


def test_missing_value_attr4_is_dropped():
    out = make(serving({"458431": load("bdl_458272_nominal_dynamics_missing2000.json")})).fetch()
    assert 2000 not in out["pkb_real"].index
    assert 2001 in out["pkb_real"].index
    raw = load("bdl_458272_nominal_dynamics_missing2000.json")["results"][0]["values"][0]
    assert (raw["year"], raw["val"], raw["attrId"]) == ("2000", 0.0, 4)


def test_preliminary_attr9_is_kept():
    out = make(serving()).fetch()
    assert out["gdp_nominal"].loc[2024, "value"] == pytest.approx(3653.432)  # attrId 9
    assert 2024 in out["pkb_real"].index


def test_pkb_real_chained_to_nominal_anchor():
    out = make(serving()).fetch()
    pkb = out["pkb_real"]["value"]
    # base year = latest FINAL (attrId 1) nominal year = 2023
    assert pkb[2023] == pytest.approx(3415.274)
    growth = {int(v["year"]): v["val"] for v in load(FILES["458431"])["results"][0]["values"] if v["attrId"] != 4}
    for y in range(2002, 2025):
        assert pkb[y] / pkb[y - 1] == pytest.approx(growth[y] / 100)
    assert pkb[2024] == pytest.approx(3415.274 * 1.03)
    assert list(pkb.index)[0] == 2001


def test_cpi_level_chained_base_100():
    cpi = make(serving()).fetch()["cpi"]["value"]
    assert cpi[2003] == pytest.approx(100.8)  # base 100 in 2002
    assert cpi[2004] == pytest.approx(100.8 * 1.035)
    assert cpi[2025] / cpi[2024] == pytest.approx(1.036)


def test_levels_as_published():
    out = make(serving()).fetch()
    assert out["employment"].loc[2024, "value"] == 11038780
    assert out["wage_nominal"].loc[2023, "value"] == pytest.approx(7595.30)


def test_retry_after_non_numeric_header():
    sleeps, calls = [], []

    def h(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "3 sek"}, json={"errorResult": "x"})
        return serving()(request)

    make(h, sleep=sleeps.append).fetch()
    assert sleeps == [3]


def test_retry_after_numeric_default_and_cap():
    for header, expected in (("5", [5]), ("100 sek", [30]), (None, [1])):
        sleeps, calls = [], []

        def h(request, header=header, calls=calls):
            calls.append(1)
            if len(calls) == 1:
                return httpx.Response(429, headers={"Retry-After": header} if header else {})
            return serving()(request)

        make(h, sleep=sleeps.append).fetch()
        assert sleeps == expected


def test_429_after_max_retries_raises_source_error():
    sleeps, calls = [], []

    def h(request):
        calls.append(1)
        return httpx.Response(429, headers={"Retry-After": "3 sek"})

    with pytest.raises(SourceError) as e:
        make(h, sleep=sleeps.append, max_retries=3).fetch()
    assert e.value.source == "gus_bdl"
    assert len(calls) == 4 and sleeps == [3, 3, 3]


def test_5xx_backoff_default_then_error_and_4xx_not_retried():
    sleeps, calls = [], []

    def h500(request):
        calls.append(1)
        return httpx.Response(503)

    with pytest.raises(SourceError) as e:
        make(h500, sleep=sleeps.append).fetch()
    assert e.value.source == "gus_bdl" and sleeps == [1, 2, 4]
    calls.clear()

    def h404(request):
        calls.append(1)
        return httpx.Response(404)

    with pytest.raises(SourceError):
        make(h404).fetch()
    assert len(calls) == 1


def test_timeout_is_source_error():
    def boom(request):
        raise httpx.ConnectTimeout("t")

    with pytest.raises(SourceError) as e:
        make(boom).fetch()
    assert e.value.source == "gus_bdl"


def test_page_size_never_above_100():
    seen = []
    make(serving(seen=seen)).fetch()
    assert all(int(r.url.params["page-size"]) <= 100 for r in seen)


def test_x_client_id_header_sent():
    seen = []
    make(serving(seen=seen), client_id="abc-123").fetch()
    assert all(r.headers["X-ClientId"] == "abc-123" for r in seen)
    seen.clear()
    make(serving(seen=seen)).fetch()
    assert all("X-ClientId" not in r.headers for r in seen)


def _mut(fn):
    b = json.loads(json.dumps(load(FILES["154173"])))
    fn(b)
    return b


def test_parse_errors_are_source_errors():
    def bad_val(b): b["results"][0]["values"][0]["val"] = "abc"
    def no_year(b): del b["results"][0]["values"][0]["year"]
    def bad_year(b): b["results"][0]["values"][0]["year"] = "x"
    def bad_results(b): b["results"] = "nope"
    def no_attr(b): del b["results"][0]["values"][0]["attrId"]

    bodies = [_mut(f) for f in (bad_val, no_year, bad_year, bad_results, no_attr)] + [[1, 2], "str"]
    for body in bodies:
        with pytest.raises(SourceError) as e:
            make(serving({"154173": body})).fetch()
        assert e.value.source == "gus_bdl"


def test_empty_series_raises_no_data():
    def empty(b): b["results"][0]["values"] = [{"year": "2022", "val": 0.0, "attrId": 4}]
    with pytest.raises(SourceError, match="no data"):
        make(serving({"154173": _mut(empty)})).fetch()


def test_non_national_unit_raises():
    def wrong(b): b["results"][0]["id"] = "011200000000"
    with pytest.raises(SourceError):
        make(serving({"154173": _mut(wrong)})).fetch()
    with pytest.raises(SourceError):
        make(serving({"154173": {"results": []}})).fetch()
