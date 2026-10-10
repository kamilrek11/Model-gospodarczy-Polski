from fastapi import FastAPI

from app.api.backtest import router as backtest_router
from app.api.export import router as export_router
from app.api.history import router as history_router
from app.api.parameters import router as parameters_router
from app.api.refresh import router as refresh_router
from app.api.simulate import router as simulate_router

app = FastAPI(title="Symulator budzetu")
app.include_router(parameters_router)
app.include_router(refresh_router)
app.include_router(simulate_router)
app.include_router(history_router)
app.include_router(backtest_router)
app.include_router(export_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
