"""Data refresh: fetch all sources, estimate the macro block, persist only on full success.

Partial success never overwrites the last good state (spec §4).
"""

import os
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.data.base import SourceClient, SourceError
from app.data.execution import ExecutionClient, HttpJsonLoader
from app.data.gus_bdl import GusBdlClient
from app.model.macro import MACRO_VARS, InsufficientData, fit_macro
from app.store import Store

MODEL_SOURCE = "model"
BDL_BASE_URL = "https://bdl.stat.gov.pl/api/v1"
DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "var" / "budget.db"


@dataclass
class RefreshResult:
    ok: bool
    errors: dict[str, str] = field(default_factory=dict)
    updated_at: str | None = None


def refresh(store: Store, clients: list[SourceClient], lags: int = 1) -> RefreshResult:
    fetched: dict[str, tuple[str, pd.DataFrame]] = {}
    errors: dict[str, str] = {}
    for client in clients:
        try:
            for series, df in client.fetch().items():
                fetched[series] = (client.name, df)
        except SourceError as e:
            errors[client.name] = e.message
        except Exception as e:  # a broken client must not crash the job or hide other sources' errors
            errors[client.name] = f"unexpected error: {e!r}"
    if errors:
        return RefreshResult(False, errors, store.get_meta("updated_at"))

    missing = [v for v in MACRO_VARS if v not in fetched]
    if missing:
        return RefreshResult(False, {MODEL_SOURCE: f"missing macro series: {', '.join(missing)}"}, store.get_meta("updated_at"))
    macro = pd.concat({v: fetched[v][1]["value"] for v in MACRO_VARS}, axis=1)
    try:
        model = fit_macro(macro, lags=lags)
    except InsufficientData as e:
        msg = f"insufficient data: {e.n_obs} complete annual observations, required {e.required}"
        return RefreshResult(False, {MODEL_SOURCE: msg}, store.get_meta("updated_at"))
    except (ValueError, np.linalg.LinAlgError) as e:
        return RefreshResult(False, {MODEL_SOURCE: f"estimation failed: {e}"}, store.get_meta("updated_at"))

    updated_at = datetime.now(UTC).isoformat()
    # one transaction: a failure mid-write rolls back and the last good state stays intact.
    # Real source data replaces any seeded data, so the synthetic marker is cleared in the same snapshot.
    store.save_snapshot(fetched, model.to_dict(), {"updated_at": updated_at, "synthetic": "0"})
    return RefreshResult(True, {}, updated_at)


class RefreshJob:
    """In-process background job state: idle | running | done | failed."""

    def __init__(self) -> None:
        self.state = "idle"
        self.errors: dict[str, str] = {}
        self._lock = threading.Lock()

    def try_start(self) -> bool:
        with self._lock:
            if self.state == "running":
                return False
            self.state, self.errors = "running", {}
            return True

    def run(self, store: Store, clients: list[SourceClient]) -> None:
        try:
            res = refresh(store, clients)
            state, errors = ("done" if res.ok else "failed"), res.errors
        except Exception as e:  # e.g. store failure; report instead of leaving the job "running"
            state, errors = "failed", {"refresh": f"unexpected error: {e!r}"}
        with self._lock:
            self.state, self.errors = state, errors


_job = RefreshJob()


def get_job() -> RefreshJob:
    return _job


def get_store() -> Store:
    path = Path(os.environ.get("BUDGET_DB_PATH", DEFAULT_DB_PATH))
    path.parent.mkdir(parents=True, exist_ok=True)
    return Store(str(path))


def get_clients() -> list[SourceClient]:
    # With the unverified series map both clients raise SourceError("series not mapped") before any request.
    return [
        GusBdlClient(BDL_BASE_URL, httpx.Client(timeout=30)),
        ExecutionClient(HttpJsonLoader()),
    ]


router = APIRouter(prefix="/refresh", tags=["refresh"])


@router.post("", status_code=202)
def start_refresh(
    background: BackgroundTasks,
    store: Store = Depends(get_store),
    clients: list[SourceClient] = Depends(get_clients),
    job: RefreshJob = Depends(get_job),
) -> dict:
    if not job.try_start():
        raise HTTPException(status_code=409, detail="refresh already running")
    background.add_task(job.run, store, clients)
    return {"state": job.state}


@router.get("/status")
def refresh_status(store: Store = Depends(get_store), job: RefreshJob = Depends(get_job)) -> dict:
    return {
        "state": job.state,
        "errors": dict(job.errors),
        "updated_at": store.get_meta("updated_at"),
        "synthetic": store.is_synthetic(),
    }
