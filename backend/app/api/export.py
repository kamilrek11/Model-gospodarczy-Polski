"""POST /export?format=csv|xlsx: parameters + per-year results of a /simulate response."""

import csv
import io
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Response
from openpyxl import Workbook
from pydantic import BaseModel

from app.model.params import validate
from app.model.simulate import BANDS

HEADER = ["year", "tax", *BANDS, "baseline"]
PARAM_HEADER = ["parametr", "wartość"]
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_FORMULA_PREFIX = ("=", "+", "-", "@", "\t", "\r")


class ExportRequest(BaseModel):
    params: dict[str, Any]
    result: dict[str, Any]
    name: str | None = None


def safe(value: Any) -> Any:
    """Neutralise spreadsheet formula injection in user-supplied text."""
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIX):
        return "'" + value
    return value


def result_rows(result: dict) -> list[list]:
    try:
        years = [int(y) for y in result["years"]]
        taxes, baseline = result["taxes"], result["baseline"]
        names = [*taxes, *(["total"] if "total" in result else [])]
        rows = []
        for tax in names:
            bands = taxes[tax] if tax in taxes else result["total"]
            base = (baseline.get(tax) or {}).get("median")
            for i, year in enumerate(years):
                rows.append([year, tax, *(float(bands[b][i]) for b in BANDS), float(base[i]) if base else None])
        return rows
    except (KeyError, IndexError, TypeError, ValueError, AttributeError) as e:
        raise HTTPException(status_code=422, detail=f"Nieprawidłowy wynik symulacji: {e!r}") from e


def param_rows(req: ExportRequest) -> list[list]:
    try:
        full = validate(req.params)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    rows = [["scenariusz", req.name]] if req.name else []
    return rows + [[k, v] for k, v in full.items()]


def build_csv(params: list[list], rows: list[list]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["# Parametry (mld zł dla wyników)"])
    w.writerow(PARAM_HEADER)
    for r in params:
        w.writerow([safe(c) for c in r])
    w.writerow([])
    w.writerow(["# Wyniki"])
    w.writerow(HEADER)
    for r in rows:
        w.writerow([safe(c) for c in r])
    return ("﻿" + buf.getvalue()).encode("utf-8")


def build_xlsx(params: list[list], rows: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Wyniki"
    ws.append(HEADER)
    for r in rows:
        ws.append([safe(c) for c in r])
    wp = wb.create_sheet("Parametry")
    wp.append(PARAM_HEADER)
    for r in params:
        wp.append([safe(c) for c in r])
    out = io.BytesIO()
    wb.save(out)
    wb.close()
    return out.getvalue()


router = APIRouter(prefix="/export", tags=["export"])


@router.post("")
def post_export(req: ExportRequest, format: Literal["csv", "xlsx"] = Query(...)) -> Response:
    rows = result_rows(req.result)
    params = param_rows(req)
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    if format == "csv":
        content, media = build_csv(params, rows), "text/csv; charset=utf-8"
    else:
        content, media = build_xlsx(params, rows), XLSX_TYPE
    return Response(content, media_type=media, headers={"Content-Disposition": f'attachment; filename="symulacja-{stamp}.{format}"'})
