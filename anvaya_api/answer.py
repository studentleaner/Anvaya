"""Citation-enforced answer generation - the core both /api/chat (SSE) and /api/ask (JSON, for channel adapters:
Telegram/WhatsApp/voice) build on.

Trade-off this makes (PLAN M1-S2-T3 / DECISIONS Q-01, resolved 2026-09-27 - hard enforcement chosen): the model's
full answer is collected BEFORE anything is shown, so it can be validated. This costs live token-by-token reveal
(the caller only gets the finished text) in exchange for never showing an answer that had sources available but
ignored them. When retrieval finds nothing, any answer is accepted (general-knowledge questions stay unrestricted -
see retrieval.has_valid_citation).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Sequence

from .abstractai import AbstractAIClient
from .chat_prompt import build_system_prompt
from .retrieval import RetrievalResult, fallback_answer, has_valid_citation, retrieve

log = logging.getLogger("anvaya.answer")

RETRY_SUFFIX = (
    "\n\nYour previous answer did not cite any of the numbered sources above. If you used information from them, "
    "you MUST cite it as [src_n]. If none of them actually answer the question, say so explicitly instead of "
    "guessing."
)


@dataclass
class Answer:
    text: str
    result: RetrievalResult
    model: str
    cited: bool = True
    error: Optional[dict] = None


async def collect_answer(ai: AbstractAIClient, *, prompt: str, system: str, model: str, session_id: str = "",
                         history: Sequence[str] = (), max_tokens: int = 500,
                         temperature: float = 0.3) -> tuple[str, Optional[dict]]:
    """Fully consume complete_stream. Returns (text, None) on success, ("", {code, message}) on failure."""
    text = ""
    async for item in ai.complete_stream(prompt=prompt, system=system, model=model, session_id=session_id,
                                         history=history, max_tokens=max_tokens,
                                         temperature=temperature):  # pragma: no branch
        if "token" in item:
            text += item["token"]
        elif "error" in item:
            return "", {"code": item["error"], "message": item.get("detail", "")}
        else:
            return text, None
    return text, None  # pragma: no cover - complete_stream always ends with a terminal item (see its own contract)


async def generate_from_result(ai: AbstractAIClient, message: str, result: RetrievalResult, *, model: str,
                               base_system_prompt: str, session_id: str = "",
                               history: Sequence[str] = ()) -> Answer:
    """The shared core: build the grounded prompt, generate, enforce citation (one retry), fall back if still
    uncited. Takes an already-retrieved RetrievalResult so callers that need it earlier (e.g. to emit an SSE
    `context` event before generation starts) don't retrieve twice."""
    system_prompt = build_system_prompt(base_system_prompt, result)
    text, error = await collect_answer(ai, prompt=message, system=system_prompt, model=model,
                                       session_id=session_id, history=history)
    if error:
        return Answer(text="", result=result, model=model, error=error)
    if has_valid_citation(text, result):
        return Answer(text=text, result=result, model=model, cited=True)

    retry_text, retry_error = await collect_answer(ai, prompt=message, system=system_prompt + RETRY_SUFFIX,
                                                   model=model, session_id=session_id, history=history)
    if not retry_error and has_valid_citation(retry_text, result):
        return Answer(text=retry_text, result=result, model=model, cited=True)

    log.warning("grounded answer stayed uncited after one retry (session=%s, sources=%d)",
               session_id, len(result.sources))
    return Answer(text=fallback_answer(result), result=result, model=model, cited=False)


async def generate_grounded_answer(ai: AbstractAIClient, message: str, *, scope: str, profile: str, model: str,
                                   base_system_prompt: str, session_id: str = "",
                                   history: Sequence[str] = ()) -> Answer:
    """Convenience wrapper for callers (e.g. /api/ask) that don't need the intermediate RetrievalResult for
    anything of their own - retrieves, then delegates to generate_from_result."""
    result = await retrieve(ai, message, scope=scope, profile=profile)
    return await generate_from_result(ai, message, result, model=model, base_system_prompt=base_system_prompt,
                                      session_id=session_id, history=history)
