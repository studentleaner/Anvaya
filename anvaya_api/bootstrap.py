"""Start-up work for anvaya-api (PLAN Phase 0): seed AbstractAI policy/prompts and warm the local model.

Runs in the background so the API answers immediately; every step is best-effort and reported by /api/status.
Why it exists (measured 2026-09-26/27): a cold local-model load takes 90-160 s, and the gateway keeps PromptVault
and CostGuard state in memory / the container filesystem, so they are re-seeded here on every start.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

from .abstractai import AbstractAIClient
from .config import Settings

ANSWER_PROMPT = "anvaya.answer"
WARM_DELAYS_S = (5, 20, 60, 120)  # retry ladder while the gateway / Ollama come up


@dataclass
class ModelState:
    """What we honestly know about the primary model: unknown | warming | warm | error."""
    state: str = "unknown"
    detail: str = ""
    since: float = field(default_factory=time.time)
    bootstrap: dict = field(default_factory=dict)

    def set(self, state: str, detail: str = "") -> None:
        self.state, self.detail, self.since = state, detail, time.time()


async def warm_model(ai: AbstractAIClient, s: Settings, ms: ModelState,
                     sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
                     delays: tuple = WARM_DELAYS_S) -> bool:
    """One-token completion to make the gateway/Ollama load the primary model; retried while dependencies come up."""
    ms.set("warming")
    for attempt in range(len(delays) + 1):
        error = ""
        async for item in ai.complete_stream(prompt="ok", system="Reply with one word.", model=s.primary_model,
                                             max_tokens=1, temperature=0.0):
            if "error" in item:
                error = item.get("detail") or item["error"]
        if not error:
            ms.set("warm")
            return True
        ms.set("warming", error)
        if attempt < len(delays):
            await sleep(delays[attempt])
    ms.set("error", ms.detail)
    return False


async def bootstrap(ai: AbstractAIClient, s: Settings, ms: ModelState, answer_template: str,
                    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None:
    """Policy + prompts first (cheap, fail fast), then the slow model warm-up."""
    ms.bootstrap["budget"] = await ai.ensure_budget(s.project_id)
    ms.bootstrap["prompts"] = await ai.ensure_prompt(ANSWER_PROMPT, answer_template)
    await warm_model(ai, s, ms, sleep)


class PromptCache:
    """System prompt = latest PromptVault template (owner-editable without a redeploy), cached, with the code
    constant as the fallback so a gateway hiccup never blocks a chat."""

    def __init__(self, ai: AbstractAIClient, fallback: str, ttl_s: float = 300.0,
                 clock: Callable[[], float] = time.monotonic):
        self._ai, self._fallback, self._ttl, self._clock = ai, fallback, ttl_s, clock
        self._value: Optional[str] = None
        self._at = float("-inf")

    async def get(self) -> str:
        if self._value is not None and self._clock() - self._at < self._ttl:
            return self._value
        fetched = await self._ai.get_prompt(ANSWER_PROMPT)
        self._value = fetched or self._fallback
        self._at = self._clock()
        return self._value
