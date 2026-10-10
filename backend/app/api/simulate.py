"""POST /simulate: Monte Carlo revenue paths for a parameter scenario (spec §6)."""

import hashlib
import json
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.refresh import get_store
from app.model.macro import MACRO_VARS, MacroModel
from app.model.simulate import REQUIRED_SERIES, simulate
from app.store import Store

NO_DATA = "brak danych – uruchom odświeżenie"
HISTORY_SERIES: tuple[str, ...] = tuple(dict.fromkeys([*MACRO_VARS, *(s for req in REQUIRED_SERIES.values() for s in req)]))


class SimulateRequest(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)
    horizon: int = Field(5, ge=1, le=5)
    n_paths: int = Field(2000, ge=100, le=10_000)
    seed: int | None = None


def model_version(model: dict) -> str:
    """Short stable hash of the stored model dict."""
    return hashlib.sha256(json.dumps(model, sort_keys=True).encode()).hexdigest()[:12]


def load_history(store: Store) -> dict[str, pd.DataFrame]:
    out = {}
    for name in HISTORY_SERIES:
        df = store.load_series(name)
        if not df.empty:
            out[name] = df
    return out


router = APIRouter(prefix="/simulate", tags=["simulate"])


@router.post("")
def post_simulate(req: SimulateRequest, store: Store = Depends(get_store)) -> dict:
    stored = store.load_model()
    if stored is None:
        raise HTTPException(status_code=409, detail=NO_DATA)
    history = load_history(store)
    if not any(v in history for v in MACRO_VARS):
        raise HTTPException(status_code=409, detail=NO_DATA)
    try:
        res = simulate(MacroModel.from_dict(stored), history, req.params, req.horizon, req.n_paths, req.seed)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return {
        **res.to_dict(),
        "model_version": model_version(stored),
        "data_updated_at": store.get_meta("updated_at"),
        "synthetic": store.is_synthetic(),
    }
