"""FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI

from backend.modules.accounts.transports.http import router as accounts_router
from backend.modules.auth.transports.http import router as auth_router
from backend.shared.db import lifespan

app = FastAPI(title="Prosperity", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(accounts_router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
