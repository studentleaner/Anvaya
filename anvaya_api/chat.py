"""Chat endpoint logic (PLAN Phase 1, first slice = "model only" test mode).

TEST MODE (2026-09-27): no plugins and no Home Knowledge yet - the model answers from its own knowledge only and is
told it cannot see the home's data. Sources are always empty and no actions are ever proposed. Everything else
follows CONTRACTS.md: SSE events status / context / token / sources / done|error, profile rules, local-only.
"""

from __future__ import annotations

import json
from typing import AsyncIterator, Literal, Optional

from pydantic import BaseModel, Field

from .abstractai import AbstractAIClient
from .config import LOCAL_PROVIDER, Settings
from .ids import new_id

SYSTEM_PROMPT = (
    "You are Ask Home, the assistant inside the Prayag Home apps of one family's home lab. "
    "This is a TEST build: you cannot see the home's data yet (no documents, devices, finance or reminders). "
    "Never invent facts about this home; if asked about them, say you cannot see that yet and suggest where the "
    "user might look. For general questions, answer briefly (at most 6 sentences). Reply in the language of the "
    "question. You cannot perform actions."
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


async def chat_events(req: ChatRequest, ai: AbstractAIClient, s: Settings, elapsed_ms) -> AsyncIterator[str]:
    conversation_id = req.conversation_id or new_id("conv")
    message_id = new_id("msg")
    yield sse("status", {"stage": "routing", "model_state": "unknown"})
    yield sse("context", {"scope": req.scope, "plugins": [], "redacted": 0, "mode": "model_only"})
    yield sse("status", {"stage": "generating", "model_state": "unknown"})
    # complete_stream ALWAYS ends with a terminal item (done/error), so this loop never falls through.
    async for item in ai.complete_stream(prompt=req.message, system=SYSTEM_PROMPT, model=s.primary_model,
                                         session_id=conversation_id, history=history_lines(req.history)):  # pragma: no branch
        if "token" in item:
            yield sse("token", {"t": item["token"]})
        elif "error" in item:
            yield sse("error", {"code": item["error"], "message": item.get("detail", ""), "fallback": "lookup_only"})
            return
        else:
            yield sse("sources", {"items": []})
            yield sse("done", {"conversation_id": conversation_id, "message_id": message_id,
                               "elapsed_ms": elapsed_ms(), "model": f"{LOCAL_PROVIDER}/{s.primary_model}",
                               "local": True})
            return
