"""Anvaya API (Phase 0 skeleton). Behind the HomeLab docs nginx: /anvaya-api/x -> /api/x (login enforced there)."""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI

from . import __version__
from .abstractai import AbstractAIClient
from .config import LOCAL_PROVIDER, Settings


def create_app(settings: Optional[Settings] = None, client: Optional[AbstractAIClient] = None) -> FastAPI:
    s = settings or Settings.from_env()
    ai = client or AbstractAIClient(s)
    app = FastAPI(title="Anvaya API", version=__version__)

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"ok": True, "version": __version__}

    @app.get("/api/status")
    async def status() -> dict:
        up = await ai.gateway_up()
        if not s.has_credentials:
            auth = "not_configured"
        elif not up:
            auth = "unknown"
        else:
            auth = "ok" if await ai.login() else "failed"
        return {
            "gateway": "up" if up else "down",
            "auth": auth,
            "provider": LOCAL_PROVIDER,
            "model": {"name": s.primary_model, "state": "unknown"},  # real warm/cold state arrives with PLAN 1.6
            "plugins": [],
            "local_only": True,
            "project_id": s.project_id,
            "version": __version__,
        }

    return app


app = create_app()
