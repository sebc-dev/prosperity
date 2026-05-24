"""FastAPI application entry point."""

from fastapi import FastAPI

app = FastAPI(title="Prosperity")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
