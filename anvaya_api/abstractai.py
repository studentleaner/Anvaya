"""Client for the AbstractAI gateway - the ONLY door to any model (see HomeLab documentation/anvaya/AGENT-GUIDE.md).

Auth model (verified 2026-09-26): every gateway route uses the admin-style JWT (`POST /token`, OAuth2 password
form, 30-minute tokens). `PROJECT_API_KEYS` / `X-API-Key` exist in api/auth.py but are NOT wired to any route,
so Anvaya logs in as its own service user and refreshes the token before it expires.
"""

from __future__ import annotations

import time
from typing import Optional

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
