"""Data refresh: fetch all sources, check the dataset, estimate the macro block, persist only on full success.

Sources: GUS BDL (macro), Eurostat (consumption, gross operating surplus after BDL's last year), MF
budget execution (rev_vat/rev_cit/rev_pit). A source error or a quality-gate violation (source
"dataset", app.data.dataset) never overwrites the last good state (spec §4). Source warnings (e.g. MF
years that cannot be parsed) do not fail the refresh; they are reported in /refresh/status.

Environment: BDL_CLIENT_ID (optional BDL key), BUDGET_CACHE_DIR (MF cache; empty = off; default
<db dir>/cache), REFRESH_DISABLED=1 (POST /refresh answers 403, e.g. demo/test instances).
"""

import os
import threading
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.data.base import SourceClient, SourceError
from app.data.dataset import assemble, validate_dataset
from app.data.eurostat import EurostatClient
from app.data.gus_bdl import GusBdlClient
from app.data.mf_execution import CACHE_ENV, MfBudgetExecutionClient
from app.model.macro import MACRO_VARS, InsufficientData, fit_macro
from app.store import Store

MODEL_SOURCE = "model"
DATASET_SOURCE = "dataset"
BDL_BASE_URL = "https://bdl.stat.gov.pl/api/v1"
DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "var" / "budget.db"
DISABLED_ENV = "REFRESH_DISABLED"
MSG_DISABLED = "odświeżanie wyłączone w tej instancji"
# per-source HTTP client defaults; the Eurostat and MF clients also pass their own per-request timeouts
HTTP_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


@dataclass
class RefreshResult:
    ok: bool
    errors: dict[str, str] = field(default_factory=dict)
    updated_at: str | None = None
    warnings: list[str] = field(default_factory=list)


def _warnings_of(client) -> list[str]:
    try:
        return [f"{client.name}: {w}" for w in (getattr(client, "warnings", None) or [])]
    except Exception:  # noqa: BLE001 - warnings are informative only
        return []


def refresh(store: Store, clients: Iterable[SourceClient], lags: int = 1) -> RefreshResult:
    fetched: dict[str, pd.DataFrame] = {}
    errors: dict[str, str] = {}
    warnings: list[str] = []
    for client in clients:
        try:
            fetched.update(client.fetch())
        except SourceError as e:
            errors[client.name] = e.message
        except Exception as e:  # a broken client must not crash the job or hide other sources' errors
            errors[client.name] = f"unexpected error: {e!r}"
        warnings += _warnings_of(client)  # e.g. MF years that are not supported: visible, but not a failure

    def failed(errs: dict[str, str]) -> RefreshResult:
        return RefreshResult(False, errs, store.get_meta("updated_at"), warnings)

    if errors:
        return failed(errors)

    # quality gates on everything fetched: any violation stops here, nothing is written
    violations = validate_dataset(fetched)
    if violations:
        return failed({DATASET_SOURCE: " ".join(violations)})
    series = assemble(fetched)

    missing = [v for v in MACRO_VARS if v not in series]
    if missing:  # defensive: gate (a) already reports missing macro series
        return failed({MODEL_SOURCE: f"missing macro series: {', '.join(missing)}"})
    macro = pd.concat({v: series[v][1]["value"] for v in MACRO_VARS}, axis=1)
    try:
        model = fit_macro(macro, lags=lags)
    except InsufficientData as e:
        return failed({MODEL_SOURCE: f"insufficient data: {e.n_obs} complete annual observations, required {e.required}"})
    except (ValueError, np.linalg.LinAlgError) as e:
        return failed({MODEL_SOURCE: f"estimation failed: {e}"})

    updated_at = datetime.now(UTC).isoformat()
    # one transaction: a failure mid-write rolls back and the last good state stays intact.
    # Real source data replaces any seeded data, so the synthetic marker is cleared in the same snapshot.
    store.save_snapshot(series, model.to_dict(), {"updated_at": updated_at, "synthetic": "0"})
    return RefreshResult(True, {}, updated_at, warnings)


class ClientBundle(list):
    """The source clients of one refresh run plus the HTTP clients they use; close() releases them."""

    def __init__(self, clients: Iterable[SourceClient], http_clients: Iterable[httpx.Client] = ()):
        super().__init__(clients)
        self.http_clients = list(http_clients)

    def close(self) -> None:
        for h in self.http_clients:
            h.close()


def close_clients(clients) -> None:
    """Release a bundle's resources; plain lists (e.g. test overrides) have nothing to close."""
    close = getattr(clients, "close", None)
    if callable(close):
        close()


class RefreshJob:
    """In-process background job state: idle | running | done | failed."""

    def __init__(self) -> None:
        self.state = "idle"
        self.errors: dict[str, str] = {}
        self.warnings: list[str] = []
        self._lock = threading.Lock()

    def try_start(self) -> bool:
        with self._lock:
            if self.state == "running":
                return False
            self.state, self.errors, self.warnings = "running", {}, []
            return True

    def run(self, store: Store, clients) -> None:
        warnings: list[str] = []
        try:
            res = refresh(store, clients)
            state, errors, warnings = ("done" if res.ok else "failed"), res.errors, res.warnings
        except Exception as e:  # e.g. store failure; report instead of leaving the job "running"
            state, errors = "failed", {"refresh": f"unexpected error: {e!r}"}
        finally:
            try:
                close_clients(clients)
            except Exception:  # noqa: BLE001 - closing must never leave the job "running"
                pass
        with self._lock:
            self.state, self.errors, self.warnings = state, errors, warnings


_job = RefreshJob()


def get_job() -> RefreshJob:
    return _job


def _db_path() -> Path:
    return Path(os.environ.get("BUDGET_DB_PATH") or DEFAULT_DB_PATH)


def get_store() -> Store:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return Store(str(path))


def cache_dir() -> str | None:
    """BUDGET_CACHE_DIR if set (empty = cache off), else <directory of the db>/cache."""
    env = os.environ.get(CACHE_ENV)
    if env is not None:
        return env or None
    return str(_db_path().parent / "cache")


def refresh_disabled() -> bool:
    return os.environ.get(DISABLED_ENV, "").strip() == "1"


def get_clients() -> ClientBundle:
    """One HTTP client per source; the bundle is closed by RefreshJob.run (or by a rejected POST)."""
    bdl_http, eu_http, mf_http = (httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=False) for _ in range(3))
    return ClientBundle(
        [
            GusBdlClient(BDL_BASE_URL, bdl_http, client_id=os.environ.get("BDL_CLIENT_ID") or None),
            EurostatClient(eu_http),
            MfBudgetExecutionClient(mf_http, cache_dir()),
        ],
        [bdl_http, eu_http, mf_http],
    )


router = APIRouter(prefix="/refresh", tags=["refresh"])


@router.post("", status_code=202)
def start_refresh(
    background: BackgroundTasks,
    store: Store = Depends(get_store),
    clients: ClientBundle = Depends(get_clients),
    job: RefreshJob = Depends(get_job),
) -> dict:
    if refresh_disabled():
        close_clients(clients)
        raise HTTPException(status_code=403, detail=MSG_DISABLED)
    if not job.try_start():
        close_clients(clients)
        raise HTTPException(status_code=409, detail="refresh already running")
    background.add_task(job.run, store, clients)
    return {"state": job.state}


@router.get("/status")
def refresh_status(store: Store = Depends(get_store), job: RefreshJob = Depends(get_job)) -> dict:
    return {
        "state": job.state,
        "errors": dict(job.errors),
        "warnings": list(job.warnings),
        "updated_at": store.get_meta("updated_at"),
        "synthetic": store.is_synthetic(),
        "disabled": refresh_disabled(),
    }
