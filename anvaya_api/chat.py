"""Chat endpoint logic (PLAN Phase 1).

Retrieval-grounded (2026-09-27): every question is checked against Home Knowledge first. When sources are found
they are numbered and cited ([src_n]); home-specific questions with no match get an honest "I don't have that"
instead of an invented answer. General-knowledge questions (not about this home) may still be answered normally.
Everything else follows CONTRACTS.md: SSE events status / context / token / sources / done|error, profile rules,
local-only.
"""

from __future__ import annotations

import json
import logging
from typing import AsyncIterator, Literal, Optional

from pydantic import BaseModel, Field

from .abstractai import AbstractAIClient
from .bootstrap import ModelState
from .config import LOCAL_PROVIDER, Settings
from .ids import new_id
from .retrieval import RetrievalResult, has_valid_citation, retrieve

log = logging.getLogger("anvaya.chat")

SYSTEM_PROMPT = (
    "You are Ask Home, the assistant inside the Prayag Home apps of one family's home lab. "
    "Answer briefly (at most 6 sentences unless asked for more). Reply in the language of the question. "
    "You cannot perform actions - you can only look things up and answer."
)
WITH_SOURCES_SUFFIX = (
    "\n\nBelow are numbered SOURCES retrieved from this home's own data. If the question is about this home "
    "or its setup, answer USING ONLY these sources and cite each fact as [src_n]. If the sources don't actually "
    "cover the question, say you don't have that information yet rather than guessing. If the question is general "
    "knowledge unrelated to this home, you may answer normally without citing.\n\nSOURCES:\n{context}"
)
WITHOUT_SOURCES_SUFFIX = (
    "\n\nNo information about this home was found for this question. If it is about this home or its setup, say "
    "you don't have that information yet rather than guessing. For general-knowledge questions you may still "
    "answer normally."
)
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


def build_system_prompt(base: str, result: RetrievalResult) -> str:
    if result.sources:
        return base + WITH_SOURCES_SUFFIX.format(context=result.context_block)
    return base + WITHOUT_SOURCES_SUFFIX


async def chat_events(req: ChatRequest, ai: AbstractAIClient, s: Settings, elapsed_ms,
                      system_prompt: str, ms: ModelState) -> AsyncIterator[str]:
    conversation_id = req.conversation_id or new_id("conv")
    message_id = new_id("msg")
    yield sse("status", {"stage": "routing", "model_state": wire_state(ms)})
    result = await retrieve(ai, req.message, scope=req.scope, profile=req.profile)
    yield sse("context", {"scope": req.scope, "plugins": result.plugins, "redacted": result.redacted,
                          "mode": "knowledge"})
    yield sse("status", {"stage": "model_loading" if ms.state == "warming" else "generating",
                         "model_state": wire_state(ms)})
    prompt_system = build_system_prompt(system_prompt, result)
    answer = ""
    # complete_stream ALWAYS ends with a terminal item (done/error), so this loop never falls through.
    async for item in ai.complete_stream(prompt=req.message, system=prompt_system, model=s.primary_model,
                                         session_id=conversation_id, history=history_lines(req.history)):  # pragma: no branch
        if "token" in item:
            if ms.state != "warm":
                ms.set("warm")          # a token proves the model is loaded and answering
            answer += item["token"]
            yield sse("token", {"t": item["token"]})
        elif "error" in item:
            yield sse("error", {"code": item["error"], "message": item.get("detail", ""), "fallback": "lookup_only"})
            return
        else:
            if not has_valid_citation(answer, result):  # telemetry only for now - see PLAN M1-S2-T3 / known-issues
                log.warning("answer for conv=%s cited no source although %d were retrieved",
                           conversation_id, len(result.sources))
            yield sse("sources", {"items": result.as_sources_event()})
            yield sse("done", {"conversation_id": conversation_id, "message_id": message_id,
                               "elapsed_ms": elapsed_ms(), "model": f"{LOCAL_PROVIDER}/{s.primary_model}",
                               "local": True})
            return
