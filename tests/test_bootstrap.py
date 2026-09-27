import asyncio

import httpx

from anvaya_api.abstractai import AbstractAIClient
from anvaya_api.bootstrap import ModelState, PromptCache, WARM_DELAYS_S, bootstrap, warm_model
from anvaya_api.config import Settings

S = Settings(username="a", password="b")
DONE = b'event: done\ndata: {"elapsed": 1}\n\n'


def run(coro):
    return asyncio.run(coro)


def make(handler, settings=S):
    return AbstractAIClient(settings, transport=httpx.MockTransport(handler))


def gw(stream=DONE, prompts=None, budget=200):
    def handler(request):
        p = request.url.path
        if p == "/token":
            return httpx.Response(200, json={"access_token": "t"})
        if p == "/v1/complete/stream":
            return httpx.Response(200, content=stream() if callable(stream) else stream)
        if p.startswith("/admin/costs/"):
            return httpx.Response(budget, json={})
        if p.startswith("/v1/prompts/"):
            return (prompts or (lambda r: httpx.Response(404)))(request)
        return httpx.Response(404)

    return handler


async def no_sleep(_):
    return None


def test_warm_model_success():
    ms = ModelState()
    assert run(warm_model(make(gw()), S, ms, no_sleep)) is True
    assert ms.state == "warm"


def test_warm_model_retries_then_succeeds():
    calls = {"n": 0}

    def stream():
        calls["n"] += 1
        return b'event: error\ndata: {"detail": "loading"}\n\n' if calls["n"] < 3 else DONE

    slept = []

    async def sleep(d):
        slept.append(d)

    ms = ModelState()
    assert run(warm_model(make(gw(stream)), S, ms, sleep)) is True
    assert ms.state == "warm" and slept == list(WARM_DELAYS_S[:2])


def test_warm_model_gives_up_with_error_state():
    ms = ModelState()
    body = b'event: error\ndata: {"detail": "still loading"}\n\n'
    ok = run(warm_model(make(gw(body)), S, ms, no_sleep, delays=(1, 2)))
    assert ok is False and ms.state == "error" and ms.detail == "still loading"


def test_warm_model_error_without_detail_uses_code():
    def rejecting(r):
        return httpx.Response(200, json={"access_token": "t"}) if r.url.path == "/token" else httpx.Response(401)

    ms = ModelState()
    run(warm_model(make(rejecting), S, ms, no_sleep, delays=()))
    assert ms.state == "error" and ms.detail == "AbstractAI rejected the login"


def test_warm_model_item_with_only_a_code():
    class Fake:
        async def complete_stream(self, **kw):
            yield {"error": "gateway_down"}

    ms = ModelState()
    run(warm_model(Fake(), S, ms, no_sleep, delays=()))
    assert ms.detail == "gateway_down"


def test_bootstrap_seeds_budget_prompts_and_warms():
    posted = []

    def prompts(request):
        if request.method == "GET":
            return httpx.Response(404)
        posted.append(request.content)
        return httpx.Response(200, json={"registered": True})

    ms = ModelState()
    run(bootstrap(make(gw(prompts=prompts)), S, ms, "TEMPLATE", no_sleep))
    assert ms.bootstrap == {"budget": True, "prompts": True} and ms.state == "warm"
    assert b"TEMPLATE" in posted[0] and b"production" in posted[0]


def test_helpers_degrade_gracefully():
    def boom(request):
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "t"})
        raise httpx.ConnectError("down")

    async def go():
        no_login = make(lambda r: httpx.Response(500), Settings())
        assert await no_login.ensure_budget("p") is False and await no_login.ensure_prompt("n", "t") is False
        assert await no_login.get_prompt("n") is None

        down = make(boom)
        assert await down.ensure_budget("p") is False and await down.get_prompt("n") is None
        assert await down.ensure_prompt("n", "t") is False

        exists = make(gw(prompts=lambda r: httpx.Response(200, json={"template": "X"})))
        assert await exists.ensure_prompt("n", "t") is True and await exists.get_prompt("n") == "X"
        server_error = make(gw(prompts=lambda r: httpx.Response(500)))
        assert await server_error.ensure_prompt("n", "t") is False and await server_error.get_prompt("n") is None
        post_fails = make(gw(prompts=lambda r: httpx.Response(404 if r.method == "GET" else 500)))
        assert await post_fails.ensure_prompt("n", "t") is False
        assert await make(gw(budget=500)).ensure_budget("p") is False

    run(go())


def test_prompt_cache_ttl_and_fallback():
    now = {"t": 0.0}
    served = {"v": "V1"}

    def prompts(request):
        return httpx.Response(200, json={"template": served["v"]}) if served["v"] else httpx.Response(404)

    cache = PromptCache(make(gw(prompts=prompts)), "FALLBACK", ttl_s=10, clock=lambda: now["t"])

    async def go():
        assert await cache.get() == "V1"
        served["v"] = "V2"
        assert await cache.get() == "V1"          # cached
        now["t"] = 11
        assert await cache.get() == "V2"          # expired -> refetched
        served["v"] = None
        now["t"] = 30
        assert await cache.get() == "FALLBACK"    # vault unavailable -> code constant

    run(go())
