"""Anvaya API. Behind the HomeLab docs nginx: /anvaya-api/x -> /api/x (login enforced there)."""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from . import __version__
from .abstractai import AbstractAIClient
from .answer import generate_grounded_answer
from .bootstrap import ModelState, PromptCache, bootstrap
from .chat import ChatRequest, chat_events, wire_state
from .chat_prompt import SYSTEM_PROMPT
from .config import LOCAL_PROVIDER, Settings
from .ingest import IngestReport, reindex


class AskRequest(BaseModel):
    """Channel-agnostic Q&A - Telegram/WhatsApp/voice adapters call this instead of /api/chat's SSE stream.
    `profile` deliberately excludes "kids" at the schema level: channel adapters are owner-only by construction
    (allowlisted chat ids etc.), there is no path that should ever reach Ask Home as a kid."""
    message: str = Field(min_length=1, max_length=4000)
    scope: Literal["this_app", "current_page", "my_home", "all_apps"] = "my_home"
    profile: Literal["family", "system"] = "system"


class AskResponse(BaseModel):
    answer: str
    sources: list[dict]
    model: str
    local: bool
    cited: bool


def create_app(settings: Optional[Settings] = None, client: Optional[AbstractAIClient] = None,
               run_bootstrap: bool = True) -> FastAPI:
    s = settings or Settings.from_env()
    ai = client or AbstractAIClient(s)
    ms = ModelState()
    prompts = PromptCache(ai, SYSTEM_PROMPT)
    last_reindex: dict = {}

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
            "mode": "knowledge",  # retrieval-grounded since 2026-09-27 (PLAN Phase 1.2/1.3)
            "last_reindex": last_reindex,
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

    @app.post("/api/ask", response_model=AskResponse)
    async def ask(req: AskRequest) -> AskResponse:
        """One request, one citation-enforced answer - for channel adapters (Telegram/WhatsApp/voice) that can't
        consume an SSE stream. See documentation/anvaya/CHANNELS.md (HomeLab) for how each channel calls this."""
        answer = await generate_grounded_answer(ai, req.message, scope=req.scope, profile=req.profile,
                                                model=s.primary_model, base_system_prompt=await prompts.get())
        if answer.error:
            raise HTTPException(status_code=502, detail=answer.error.get("message") or answer.error["code"])
        return AskResponse(answer=answer.text, sources=answer.result.as_sources_event(),
                           model=f"{LOCAL_PROVIDER}/{s.primary_model}", local=True, cited=answer.cited)

    @app.post("/api/admin/reindex")
    async def admin_reindex() -> dict:
        """Re-sync Home Knowledge from docs/hub/atlas/tasks. Not profile-gated here - the docs nginx already puts
        every mount of this API behind the login; a dedicated System-only check can be added once Anvaya has its
        own per-request caller identity (PLAN Phase 3)."""
        report: IngestReport = await reindex(ai)
        last_reindex.clear()
        last_reindex.update(scanned=report.scanned, ingested=report.ingested, unchanged=report.unchanged,
                            deleted=report.deleted, failed=report.failed, at=time.time())
        return last_reindex

    return app


app = create_app()
