"""Client for the AbstractAI gateway - the ONLY door to any model (see HomeLab documentation/anvaya/AGENT-GUIDE.md).

Auth model (verified 2026-09-26): every gateway route uses the admin-style JWT (`POST /token`, OAuth2 password
form, 30-minute tokens). `PROJECT_API_KEYS` / `X-API-Key` exist in api/auth.py but are NOT wired to any route,
so Anvaya logs in as its own service user (SERVICE_USERS_JSON_B64 on the gateway) and refreshes the token
before it expires.
"""

from __future__ import annotations

import json
import time
from typing import AsyncIterator, Optional, Sequence

import httpx

from .config import LOCAL_PROVIDER, Settings

TOKEN_TTL_S = 25 * 60  # gateway tokens live 30 min; refresh early


class NonLocalProviderError(RuntimeError):
    """A response came back from a non-local provider: drop the answer (cloud tripwire, decision D-04)."""


def assert_local(provider: str) -> None:
    if provider != LOCAL_PROVIDER:
        raise NonLocalProviderError(f"provider {provider!r} is not local ({LOCAL_PROVIDER!r} only)")


class AbstractAIClient:
    def __init__(self, settings: Settings, transport: Optional[httpx.AsyncBaseTransport] = None):
        self._s = settings
        self._http = httpx.AsyncClient(base_url=settings.gateway_url, transport=transport,
                                       timeout=settings.request_timeout_s)
        self._token: Optional[str] = None
        self._token_at = 0.0

    async def aclose(self) -> None:
        await self._http.aclose()

    async def gateway_up(self) -> bool:
        """Liveness without spending an LLM call or needing credentials: the OpenAPI document."""
        try:
            r = await self._http.get("/openapi.json", timeout=5.0)
        except httpx.HTTPError:
            return False
        return r.status_code == 200

    async def login(self) -> Optional[str]:
        """Return a bearer token, or None when credentials are missing/rejected. Cached for TOKEN_TTL_S."""
        if not self._s.has_credentials:
            return None
        if self._token and time.monotonic() - self._token_at < TOKEN_TTL_S:
            return self._token
        try:
            r = await self._http.post("/token", data={"username": self._s.username, "password": self._s.password},
                                      timeout=10.0)
        except httpx.HTTPError:
            return None
        if r.status_code != 200:
            self._token = None
            return None
        self._token = r.json()["access_token"]
        self._token_at = time.monotonic()
        return self._token

    async def complete_stream(self, *, prompt: str, system: str, model: str, session_id: str = "",
                              history: Sequence[str] = (), max_tokens: int = 500,
                              temperature: float = 0.3) -> AsyncIterator[dict]:
        """Stream a local completion. Yields exactly one terminal item: {"done": True, ...} or {"error": code, ...};
        before that zero or more {"token": str}. The provider is PINNED to ollama (RouteLLM's default policy points
        at a model that is not installed and one that cannot run on this GPU) and the model is chosen by us."""
        token = await self.login()
        if not token:
            yield {"error": "gateway_down", "detail": "AbstractAI login failed or is not configured"}
            return
        body = {
            "prompt": prompt, "system": system, "provider": LOCAL_PROVIDER, "model": model,
            # task_type MUST stay empty: ModelBus._resolve() lets any known task_type (triage/planning/complex/frontier)
            # OVERRIDE the pinned provider/model - planning -> BUS_PLANNING_MODEL (default "llama3:8b", not installed:
            # HTTP 404) and complex/frontier -> Anthropic (cloud). Empty = our pin is honoured.
            "task_type": "", "quality": "standard", "project_id": self._s.project_id,
            "temperature": temperature, "max_tokens": max_tokens, "session_id": session_id,
            "conversation_history": list(history),
        }
        try:
            async with self._http.stream("POST", "/v1/complete/stream", json=body,
                                         headers={"Authorization": f"Bearer {token}"}) as r:
                if r.status_code == 401:
                    self._token = None
                    yield {"error": "gateway_down", "detail": "AbstractAI rejected the login"}
                    return
                if r.status_code == 400:
                    yield {"error": "bad_request", "detail": (await r.aread()).decode("utf-8", "replace")[:300]}
                    return
                if r.status_code != 200:
                    yield {"error": "gateway_down", "detail": f"gateway HTTP {r.status_code}"}
                    return
                event = "message"
                async for line in r.aiter_lines():
                    if line.startswith("event:"):
                        event = line[6:].strip()
                    elif line.startswith("data:"):
                        data = json.loads(line[5:].strip() or "{}")
                        if event == "error":
                            yield {"error": "model_timeout", "detail": str(data.get("detail", ""))[:300]}
                            return
                        if event == "done":
                            yield {"done": True, "elapsed": data.get("elapsed")}
                            return
                        if data.get("token"):
                            yield {"token": data["token"]}
                    elif not line:
                        event = "message"
        except httpx.ReadTimeout:
            yield {"error": "model_timeout", "detail": "no output within the request timeout"}
            return
        except httpx.HTTPError as exc:
            yield {"error": "gateway_down", "detail": type(exc).__name__}
            return
        yield {"error": "gateway_down", "detail": "stream ended without a done event"}
