from fastapi import FastAPI

from app.api.parameters import router as parameters_router

app = FastAPI(title="Symulator budzetu")
app.include_router(parameters_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
