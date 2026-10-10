"""GET /backtest: rolling-origin accuracy of the simulator on stored history."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.refresh import get_store
from app.api.simulate import NO_DATA, load_history
from app.model.backtest import backtest
from app.model.macro import MACRO_VARS
from app.store import Store

router = APIRouter(prefix="/backtest", tags=["backtest"])


@router.get("")
def get_backtest(store: Store = Depends(get_store)) -> dict:
    history = load_history(store)
    if not any(v in history for v in MACRO_VARS):
        raise HTTPException(status_code=409, detail=NO_DATA)
    return backtest(history).to_dict()
