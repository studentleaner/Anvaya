import asyncio

import httpx
import pytest

from anvaya_api import abstractai
from anvaya_api.abstractai import AbstractAIClient, NonLocalProviderError, assert_local
from anvaya_api.config import Settings

CREDS = Settings(username="anvaya", password="pw")


def make(handler, settings=CREDS):
    return AbstractAIClient(settings, transport=httpx.MockTransport(handler))


def run(coro):
    return asyncio.run(coro)


def refuse(request):
    raise httpx.ConnectError("refused")


def test_assert_local():
    assert_local("ollama")
    with pytest.raises(NonLocalProviderError):
        assert_local("openai")


def test_gateway_up_true_false_and_error():
    async def go():
        up = make(lambda r: httpx.Response(200, json={}))
        down = make(lambda r: httpx.Response(503))
        err = make(refuse)
        return await up.gateway_up(), await down.gateway_up(), await err.gateway_up()

    assert run(go()) == (True, False, False)


def test_login_without_credentials_is_none():
    async def go():
        c = make(lambda r: httpx.Response(500), Settings())
        return await c.login()

    assert run(go()) is None


def test_login_caches_then_refreshes(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        assert request.url.path == "/token"
        assert b"username=anvaya" in request.content
        return httpx.Response(200, json={"access_token": f"t{len(calls)}", "token_type": "bearer"})

    async def go():
        c = make(handler)
        first = await c.login()
        second = await c.login()  # cached
        monkeypatch.setattr(abstractai.time, "monotonic", lambda: c._token_at + abstractai.TOKEN_TTL_S + 1)
        third = await c.login()  # expired -> refresh
        await c.aclose()
        return first, second, third

    assert run(go()) == ("t1", "t1", "t2") and len(calls) == 2


def test_login_rejected_and_network_error():
    async def go():
        bad = make(lambda r: httpx.Response(401, json={"detail": "no"}))
        bad._token = "stale"
        rejected = await bad.login()
        err = await make(refuse).login()
        return rejected, err, bad._token

    assert run(go()) == (None, None, None)
