from fastapi import FastAPI

app = FastAPI(title="Symulator budzetu")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
