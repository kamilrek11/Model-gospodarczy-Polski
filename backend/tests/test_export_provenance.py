"""I-3 + C-1: exports carry provenance (data date, model version, synthetic flag, placeholder assumptions)."""

import csv
import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.api.export import PLACEHOLDER_SENTENCE, SYNTHETIC_NOTE
from app.api.refresh import get_store
from app.main import app
from app.model.params import defaults
from app.model.simulate import PLACEHOLDER, simulate
from app.store import Store
from tests.test_simulate import synthetic_history, synthetic_model


@pytest.fixture()
def c(tmp_path):
    app.dependency_overrides[get_store] = lambda: Store(str(tmp_path / "t.db"))
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture(scope="module")
def result():
    hist = synthetic_history()
    res = simulate(synthetic_model(hist), hist, defaults(), horizon=2, n_paths=100, seed=1).to_dict()
    return {**res, "data_updated_at": "2026-01-02T03:04:05+00:00", "model_version": "abcdef123456", "synthetic": True}


def csv_rows(r) -> list[list[str]]:
    assert r.status_code == 200, r.text
    text = r.content.decode("utf-8")
    assert text.startswith("﻿")
    return list(csv.reader(io.StringIO(text[1:])))


def meta_of(rows: list[list[str]]) -> dict[str, str]:
    start = rows.index(["# Metadane"])
    end = rows.index(["# Parametry (mld zł dla wyników)"])
    return {r[0]: r[1] for r in rows[start + 1 : end] if len(r) >= 2}


def test_csv_starts_with_metadata_block(c, result):
    rows = csv_rows(c.post("/export?format=csv", json={"params": {}, "result": result}))
    assert rows[0] == ["# Metadane"]
    meta = meta_of(rows)
    assert meta["dane_z"] == "2026-01-02T03:04:05+00:00"
    assert meta["wersja_modelu"] == "abcdef123456"
    assert meta["dane_syntetyczne"] == "TAK"
    assert meta["uwaga"] == SYNTHETIC_NOTE and "DANE SYNTETYCZNE" in SYNTHETIC_NOTE
    assert meta["wygenerowano"].endswith("+00:00")
    placeholders = [a["key"] for a in result["assumptions"] if a["status"] == PLACEHOLDER]
    assert placeholders and meta["zalozenia_niezweryfikowane"] == ", ".join(placeholders)
    assert meta["zastrzezenie"] == PLACEHOLDER_SENTENCE and "niezweryfikowanych" in PLACEHOLDER_SENTENCE
    # parameters and results blocks follow, unchanged
    assert ["parametr", "wartość"] in rows and ["year", "tax", "median", "p10", "p90", "p2_5", "p97_5", "baseline"] in rows


def test_csv_real_data_has_no_synthetic_note(c, result):
    rows = csv_rows(c.post("/export?format=csv", json={"params": {}, "result": {**result, "synthetic": False}}))
    meta = meta_of(rows)
    assert meta["dane_syntetyczne"] == "NIE" and "uwaga" not in meta


def test_csv_missing_provenance_fields_tolerated(c, result):
    bare = {k: v for k, v in result.items() if k not in {"data_updated_at", "model_version", "synthetic", "assumptions"}}
    meta = meta_of(csv_rows(c.post("/export?format=csv", json={"params": {}, "result": bare})))
    assert meta["dane_z"] == "brak" and meta["wersja_modelu"] == "brak"
    assert meta["dane_syntetyczne"] == "nieznane"
    assert meta["zalozenia_niezweryfikowane"] == "brak informacji"


def test_xlsx_has_metadata_sheet(c, result):
    r = c.post("/export?format=xlsx", json={"params": {}, "result": result})
    assert r.status_code == 200
    wb = load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["Wyniki", "Parametry", "Metadane"]
    meta = {row[0]: row[1] for row in wb["Metadane"].iter_rows(values_only=True)}
    wb.close()
    assert meta["dane_z"] == "2026-01-02T03:04:05+00:00"
    assert meta["dane_syntetyczne"] == "TAK" and meta["uwaga"] == SYNTHETIC_NOTE
    assert meta["zastrzezenie"] == PLACEHOLDER_SENTENCE
    assert "PIT_INCOME_DIST_DEFAULT" in meta["zalozenia_niezweryfikowane"]


def test_provenance_text_is_formula_safe(c, result):
    evil = {**result, "model_version": "=cmd()", "assumptions": [{"key": "@SUM(1)", "status": PLACEHOLDER, "value": 1, "note": ""}]}
    text = c.post("/export?format=csv", json={"params": {}, "result": evil}).content.decode("utf-8-sig")
    assert "'=cmd()" in text and "'@SUM(1)" in text


@pytest.mark.parametrize(
    "bad",
    [
        {"synthetic": "yes"},
        {"data_updated_at": 5},
        {"model_version": "x" * 200},
        {"assumptions": "nope"},
        {"assumptions": [{"key": "A"}] * 500},
        {"assumptions": [{"status": PLACEHOLDER}]},
    ],
)
def test_provenance_fields_validated(c, result, bad):
    r = c.post("/export?format=csv", json={"params": {}, "result": {**result, **bad}})
    assert r.status_code == 422, r.text
