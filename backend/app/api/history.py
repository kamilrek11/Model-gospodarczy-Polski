"""GET /history: recorded PIT/CIT/VAT revenue series (mld zł)."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.refresh import get_store
from app.api.simulate import NO_DATA
from app.model.simulate import TAXES
from app.store import Store

router = APIRouter(prefix="/history", tags=["history"])


@router.get("")
def get_history(store: Store = Depends(get_store)) -> dict:
    out = {}
    for tax in TAXES:
        df = store.load_series(f"rev_{tax}")
        if not df.empty:
            out[tax] = [{"year": int(y), "value": float(v)} for y, v in df["value"].items()]
    if not out:
        raise HTTPException(status_code=409, detail=NO_DATA)
    return out
