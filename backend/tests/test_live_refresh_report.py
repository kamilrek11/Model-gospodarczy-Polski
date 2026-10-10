"""Offline tests of scripts/live_refresh_report.py: guards, formatting helpers, and a full run on the
recorded real responses (tests/real_dataset.py, MockTransport). No network."""

import os
import sqlite3
from contextlib import closing

import pandas as pd
import pytest

from app.api.refresh import DEFAULT_DB_PATH
from app.data.base import SourceError
from scripts import live_refresh_report as lr
from tests.real_dataset import real_clients


def frame(d: dict[int, float]) -> pd.DataFrame:
    return pd.DataFrame({"value": list(map(float, d.values()))}, index=pd.Index(list(d), dtype="int64", name="year"))


# ---------------------------------------------------------------- guards


def test_refuses_without_db():
    with pytest.raises(lr.ReportRefused, match="--db"):
        lr.check_target(None, {})


def test_refuses_existing_file(tmp_path):
    db = tmp_path / "x.db"
    db.write_bytes(b"")
    with pytest.raises(lr.ReportRefused, match="exists"):
        lr.check_target(str(db), {})


def test_refuses_app_default_path_even_if_missing(monkeypatch):
    monkeypatch.setattr(lr.os.path, "exists", lambda p: False)
    with pytest.raises(lr.ReportRefused, match="application"):
        lr.check_target(str(DEFAULT_DB_PATH), {})


def test_refuses_budget_db_path_env(tmp_path):
    db = tmp_path / "app.db"
    with pytest.raises(lr.ReportRefused, match="application"):
        lr.check_target(str(tmp_path / "." / "app.db"), {"BUDGET_DB_PATH": str(db)})


def test_accepts_new_file_and_resolves_path(tmp_path):
    target = lr.check_target(str(tmp_path / "sub" / ".." / "new.db"), {})
    assert target == tmp_path / "new.db"
    assert not target.exists()


def test_main_refusal_exits_2_and_creates_nothing(tmp_path, capsys):
    db = tmp_path / "x.db"
    db.write_bytes(b"keep")
    called = []
    assert lr.main(["--db", str(db)], make_clients=lambda cache: called.append(cache) or []) == 2
    assert called == []
    assert db.read_bytes() == b"keep"
    assert "refusing" in capsys.readouterr().err


def test_default_cache_dir_is_next_to_db(tmp_path):
    assert lr.resolve_cache_dir(tmp_path / "r.db", None) == str(tmp_path / "cache")
    assert lr.resolve_cache_dir(tmp_path / "r.db", str(tmp_path / "c")) == str(tmp_path / "c")


def test_default_clients_use_the_api_wiring_with_the_given_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("BUDGET_CACHE_DIR", "/somewhere/else")
    bundle = lr.default_clients(str(tmp_path / "cache"))
    try:
        assert [c.name for c in bundle] == ["gus_bdl", "eurostat", "mf_execution"]
        assert str(bundle[2].cache_dir) == str(tmp_path / "cache")
    finally:
        bundle.close()
    assert os.environ["BUDGET_CACHE_DIR"] == "/somewhere/else"  # environment restored


# ---------------------------------------------------------------- formatting helpers


def test_series_lines_show_source_range_and_last_three_values():
    lines = lr.series_lines({"rev_vat": ("mf_execution", frame({2022: 230.39, 2023: 244.267, 2024: 287.683, 2025: 321.646}))})
    text = "\n".join(lines)
    assert "rev_vat" in text and "mf_execution" in text and "2022–2025" in text
    assert "2023: 244.267" in text and "2025: 321.646" in text and "2022: 230.390" not in text
    assert "rev_cit" in text and "BRAK" in text  # every reported series is listed, missing ones marked


def test_common_macro_years():
    s = {v: ("x", frame({2019: 1, 2020: 1, 2021: 1})) for v in lr.MACRO_VARS}
    s["cpi"] = ("x", frame({2020: 1, 2021: 1, 2022: 1}))
    assert lr.common_macro_years(s) == [2020, 2021]
    assert lr.common_macro_years({}) == []


def test_gate_lines_ok_with_metrics():
    fetched = {
        "consumption_nominal": frame({2023: 1934.063, 2024: 2056.557}),
        "gdp_nominal": frame({2023: 3415.274, 2024: 3653.432}),
        "gross_surplus": frame({2022: 1553.042, 2023: 1676.697}),
        "gross_surplus_eurostat": frame({2022: 1553.042, 2023: 1684.850, 2024: 1689.48}),
    }
    text = "\n".join(lr.gate_lines(True, {}, fetched))
    assert "OK" in text
    assert "0.563" in text and "2024" in text  # consumption / GDP in the last common year
    assert "0.48%" in text and "2023" in text  # largest BDL vs Eurostat surplus difference


def test_gate_lines_failure_lists_violations_and_source_errors():
    text = "\n".join(lr.gate_lines(False, {"dataset": "Brak serii rev_pit.", "gus_bdl": "HTTP 429"}, {}))
    assert "NIE PRZESZŁO" in text and "Brak serii rev_pit." in text and "gus_bdl: HTTP 429" in text


def test_warning_lines():
    assert "brak" in lr.warning_lines([])[0]
    assert "mf_execution: 2015: legacy .xls" in "\n".join(lr.warning_lines(["mf_execution: 2015: legacy .xls"]))


def test_calibration_lines():
    text = "\n".join(lr.calibration_lines({"pit": {"factor": 1.2345678, "years": [2022, 2023, 2024], "method": "m"}}))
    assert "PIT" in text and "1.23457" in text and "2022, 2023, 2024" in text
    assert "VAT" in text and "wyłączony" in text  # a tax without calibration is reported, not silently omitted


def test_forecast_lines_medians_next_to_realised():
    sim = {
        "years": [2025, 2026],
        "taxes": {"vat": {"median": [300.0, 320.5], "p10": [280.0, 290.0], "p90": [320.0, 350.0]}},
    }
    hist = {"rev_vat": frame({2022: 230.0, 2023: 244.0, 2024: 287.7, 2025: 321.6})}
    text = "\n".join(lr.forecast_lines(sim, hist))
    assert "VAT" in text
    assert "2022: 230.000" in text and "2024: 287.700" in text  # last 3 realised up to the model's last year
    assert "2025: 300.000 (p10–p90 280.000–320.000; wykonanie 321.600)" in text
    assert "2026: 320.500" in text


def test_backtest_lines():
    bt = {"mape": {"vat": 4.25}, "coverage80": {"vat": 0.8}, "coverage95": {"vat": 1.0}, "n_origins": 7, "n_skipped": 0,
          "notes": ["n1"], "message": None}
    text = "\n".join(lr.backtest_lines(bt))
    assert "VAT" in text and "4.25%" in text and "80%" in text and "100%" in text and "7" in text
    assert "PIT" in text and "brak" in text
    assert "message" not in text
    assert "Za mało" in "\n".join(lr.backtest_lines({"mape": {}, "message": "Za mało danych", "notes": []}))


def test_pit_break_lines():
    hist = {"rev_pit": frame({2023: 91.666, 2024: 97.600, 2025: 28.752})}
    text = "\n".join(lr.pit_break_lines(hist, {"pit": {"factor": 1.0, "years": [2022, 2023, 2024]}}))
    assert "2025" in text and "28.752" in text and "97.600" in text and "-70.5%" in text
    assert "2022, 2023, 2024" in text
    assert "nieporównywaln" in text


# ---------------------------------------------------------------- full run, offline


def test_full_run_on_recorded_real_responses(tmp_path, capsys):
    db = tmp_path / "live.db"
    https = []
    code = lr.main(["--db", str(db)], make_clients=lambda cache: real_clients(https))
    for h in https:
        h.close()
    out = capsys.readouterr().out
    assert code == 0
    assert "Bramki jakości: OK" in out
    for name in ("pkb_real", "consumption_nominal", "rev_vat", "rev_cit", "rev_pit"):
        assert name in out
    assert "eurostat" in out and "mf_execution" in out
    assert "Kalibracja" in out and "Prognoza" in out and "Backtest" in out and "Załamanie PIT 2025" in out
    with closing(sqlite3.connect(db)) as c:
        assert c.execute("SELECT value FROM meta WHERE key='synthetic'").fetchone()[0] == "0"


def test_failed_refresh_exits_1_and_reports_errors(tmp_path, capsys):
    class Failing:
        name = "gus_bdl"
        warnings: list[str] = []

        def fetch(self):
            raise SourceError("gus_bdl", "HTTP 429 after 4 attempts")

    code = lr.main(["--db", str(tmp_path / "f.db")], make_clients=lambda cache: [Failing()])
    out = capsys.readouterr().out
    assert code == 1
    assert "NIE PRZESZŁO" in out and "gus_bdl: HTTP 429 after 4 attempts" in out
    assert "Prognoza" not in out
