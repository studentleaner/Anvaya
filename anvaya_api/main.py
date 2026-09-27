"""Anvaya API. Behind the HomeLab docs nginx: /anvaya-api/x -> /api/x (login enforced there)."""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from . import __version__
from .abstractai import AbstractAIClient
from .bootstrap import ANSWER_PROMPT, ModelState, PromptCache, bootstrap
from .chat import SYSTEM_PROMPT, ChatRequest, chat_events, wire_state
from .config import LOCAL_PROVIDER, Settings


def create_app(settings: Optional[Settings] = None, client: Optional[AbstractAIClient] = None,
               run_bootstrap: bool = True) -> FastAPI:
    s = settings or Settings.from_env()
    ai = client or AbstractAIClient(s)
    ms = ModelState()
    prompts = PromptCache(ai, SYSTEM_PROMPT)

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI):
        task = asyncio.create_task(bootstrap(ai, s, ms, SYSTEM_PROMPT)) if run_bootstrap else None
        try:
            yield
        finally:
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(title="Anvaya API", version=__version__, lifespan=lifespan)

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
            "model": {"name": s.primary_model, "state": wire_state(ms), "detail": ms.detail},
            "bootstrap": ms.bootstrap,
            "plugins": [],
            "mode": "model_only",  # TEST MODE: no Home Knowledge / plugins yet (PLAN Phase 1-4)
            "local_only": True,
            "project_id": s.project_id,
            "version": __version__,
        }

    @app.post("/api/chat")
    async def chat(req: ChatRequest) -> StreamingResponse:
        if req.profile == "kids":  # decision D-11: no Ask Home on the Kids profile in V1
            raise HTTPException(status_code=403, detail="Ask Home is not available on the Kids profile")
        started = time.monotonic()
        return StreamingResponse(
            chat_events(req, ai, s, lambda: int((time.monotonic() - started) * 1000),
                        await prompts.get(), ms),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


app = create_app()
