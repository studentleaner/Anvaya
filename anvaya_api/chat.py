"""Chat endpoint logic (PLAN Phase 1).

Retrieval-grounded and citation-enforced (2026-09-27): the model's full answer is validated before anything is
shown - see answer.py for why and the trade-off that makes (buffered generation instead of live token-by-token
reveal). The client still gets a `token` stream (CONTRACTS.md's event shape is unchanged), it is just built from
the already-validated final text, split into words, rather than forwarded live from the model.
"""

from __future__ import annotations

import json
from typing import AsyncIterator, Literal, Optional

from pydantic import BaseModel, Field

from .abstractai import AbstractAIClient
from .answer import generate_from_result
from .bootstrap import ModelState
from .chat_prompt import SYSTEM_PROMPT
from .config import LOCAL_PROVIDER, Settings
from .ids import new_id
from .retrieval import retrieve

MAX_HISTORY = 6


class HistoryItem(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(max_length=2000)


class ChatContext(BaseModel):
    app: str = Field(default="", max_length=64)
    page: str = Field(default="", max_length=128)
    entity_type: str = Field(default="", max_length=64)
    entity_id: str = Field(default="", max_length=128)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    scope: Literal["this_app", "current_page", "my_home", "all_apps"]
    profile: Literal["family", "kids", "system"]
    conversation_id: Optional[str] = Field(default=None, pattern=r"^conv_[0-9A-HJKMNP-TV-Z]{26}$")
    context: Optional[ChatContext] = None
    client: Optional[dict] = None
    history: list[HistoryItem] = Field(default_factory=list, max_length=MAX_HISTORY)


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def history_lines(items: list[HistoryItem]) -> list[str]:
    return [f"{h.role}: {h.text}" for h in items[-MAX_HISTORY:]]


def wire_state(ms: ModelState) -> str:
    return {"warm": "warm", "warming": "loading"}.get(ms.state, "unknown")


def _words(text: str) -> list[str]:
    """Split into reveal chunks for the SSE `token` stream. Not the model's real token boundaries (the answer was
    already fully generated) - just something that reads as a natural typing reveal client-side."""
    parts = text.split(" ")
    return [(p + " ") for p in parts[:-1]] + ([parts[-1]] if parts and parts[-1] else [])


async def chat_events(req: ChatRequest, ai: AbstractAIClient, s: Settings, elapsed_ms,
                      system_prompt: str, ms: ModelState) -> AsyncIterator[str]:
    conversation_id = req.conversation_id or new_id("conv")
    message_id = new_id("msg")
    yield sse("status", {"stage": "routing", "model_state": wire_state(ms)})
    result = await retrieve(ai, req.message, scope=req.scope, profile=req.profile, settings=s)
    yield sse("context", {"scope": req.scope, "plugins": result.plugins, "redacted": result.redacted,
                          "mode": "knowledge"})
    yield sse("status", {"stage": "model_loading" if ms.state == "warming" else "generating",
                         "model_state": wire_state(ms)})
    answer = await generate_from_result(ai, req.message, result, model=s.primary_model,
                                        base_system_prompt=system_prompt, session_id=conversation_id,
                                        history=history_lines(req.history))
    if answer.error:
        yield sse("error", {"code": answer.error["code"], "message": answer.error.get("message", ""),
                            "fallback": "lookup_only"})
        return
    if answer.text:
        ms.set("warm")  # a completed answer proves the model is loaded and answering
    for chunk in _words(answer.text):
        yield sse("token", {"t": chunk})
    yield sse("sources", {"items": result.as_sources_event()})
    yield sse("done", {"conversation_id": conversation_id, "message_id": message_id,
                       "elapsed_ms": elapsed_ms(), "model": f"{LOCAL_PROVIDER}/{s.primary_model}",
                       "local": True, "cited": answer.cited})
