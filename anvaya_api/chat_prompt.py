"""The system prompt and how retrieved sources get folded into it. Split out from chat.py so both chat.py (SSE)
and answer.py (the shared generation core used by /api/chat and /api/ask) can use it without a circular import."""

from __future__ import annotations

from .retrieval import RetrievalResult

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


def build_system_prompt(base: str, result: RetrievalResult) -> str:
    if result.sources:
        return base + WITH_SOURCES_SUFFIX.format(context=result.context_block)
    return base + WITHOUT_SOURCES_SUFFIX
