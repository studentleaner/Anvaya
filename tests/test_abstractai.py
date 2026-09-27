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


# ---------------------------------------------------------------- complete_stream
def sse_body(*frames):
    return "".join(frames).encode()


def frame(event, data):
    import json
    return (f"event: {event}\n" if event else "") + f"data: {json.dumps(data)}\n\n"


def stream_handler(status=200, body=b"", raises=None):
    def handler(request):
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "tok", "token_type": "bearer"})
        assert request.url.path == "/v1/complete/stream"
        assert request.headers["authorization"] == "Bearer tok"
        if raises:
            raise raises
        return httpx.Response(status, content=body)

    return handler


def collect(client, **kw):
    async def go():
        out = []
        async for item in client.complete_stream(prompt="hi", system="s", model="llama3.1:8b", **kw):
            out.append(item)
        await client.aclose()
        return out

    return run(go())


def test_stream_tokens_then_done_and_request_body_is_pinned_local():
    seen = {}

    def handler(request):
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "tok"})
        import json
        seen.update(json.loads(request.content))
        return httpx.Response(200, content=sse_body(
            frame(None, {"token": "Hel"}), ": comment ignored\n", "\n", frame(None, {"token": "lo"}),
            frame(None, {"other": 1}), "data:\n\n", frame("done", {"elapsed": 1.5})))

    out = collect(make(handler), session_id="conv_x", history=["user: a"])
    assert out == [{"token": "Hel"}, {"token": "lo"}, {"done": True, "elapsed": 1.5}]
    assert seen["provider"] == "ollama" and seen["model"] == "llama3.1:8b" and seen["project_id"] == "anvaya"
    assert seen["quality"] == "standard" and seen["conversation_history"] == ["user: a"]
    assert seen["task_type"] == ""  # a known task_type would override the pinned local model (ModelBus._resolve)
    assert seen["session_id"] == "conv_x"


def test_stream_without_credentials():
    out = collect(make(lambda r: httpx.Response(500), Settings()))
    assert out[0]["error"] == "gateway_down"


def test_stream_error_event():
    out = collect(make(stream_handler(body=sse_body(frame("error", {"detail": "boom"})))))
    assert out == [{"error": "model_timeout", "detail": "boom"}]


def test_stream_http_statuses():
    assert collect(make(stream_handler(status=401)))[0]["error"] == "gateway_down"
    bad = collect(make(stream_handler(status=400, body=b'{"detail":"Content rejected"}')))
    assert bad[0]["error"] == "bad_request" and "rejected" in bad[0]["detail"]
    assert collect(make(stream_handler(status=502)))[0] == {"error": "gateway_down", "detail": "gateway HTTP 502"}


def test_stream_401_clears_cached_token():
    async def go():
        c = make(stream_handler(status=401))
        async for _ in c.complete_stream(prompt="p", system="s", model="m"):
            pass
        return c._token

    assert run(go()) is None


def test_stream_timeout_network_and_truncated():
    assert collect(make(stream_handler(raises=httpx.ReadTimeout("slow"))))[0]["error"] == "model_timeout"
    assert collect(make(stream_handler(raises=httpx.ConnectError("refused"))))[0]["error"] == "gateway_down"
    cut = collect(make(stream_handler(body=sse_body(frame(None, {"token": "a"})))))
    assert cut[0] == {"token": "a"} and cut[1]["error"] == "gateway_down"


# ---------------------------------------------------------------- knowledge ops
def kb_gw(handler_map):
    def handler(request):
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "tok"})
        h = handler_map.get(request.url.path)
        return h(request) if h else httpx.Response(404)

    return handler


def test_ingest_text_success_and_metadata_serialized():
    seen = {}

    def ingest(request):
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={"doc_id": "d1", "status": "ready"})

    doc = run(make(kb_gw({"/v1/knowledge/ingest": ingest})).ingest_text("hi", source="s", metadata={"class": "public"}))
    assert doc == {"doc_id": "d1", "status": "ready"}
    assert 'metadata=%7B%22class%22%3A+%22public%22%7D' in seen["body"] or '"class"' in seen["body"]


def test_ingest_text_no_metadata_and_failure_paths():
    ok_no_meta = run(make(kb_gw({"/v1/knowledge/ingest": lambda r: httpx.Response(200, json={"doc_id": "d1"})})).ingest_text("hi", source="s"))
    assert ok_no_meta == {"doc_id": "d1"}
    assert run(make(kb_gw({"/v1/knowledge/ingest": lambda r: httpx.Response(422)})).ingest_text("hi", source="s")) is None
    assert run(make(lambda r: httpx.Response(500), Settings()).ingest_text("hi", source="s")) is None


def test_list_documents_shapes_and_failure():
    assert run(make(kb_gw({"/v1/knowledge/documents": lambda r: httpx.Response(200, json={"documents": [{"doc_id": "a"}]})})).list_documents()) == [{"doc_id": "a"}]
    assert run(make(kb_gw({"/v1/knowledge/documents": lambda r: httpx.Response(200, json=[{"doc_id": "b"}])})).list_documents()) == [{"doc_id": "b"}]
    assert run(make(kb_gw({"/v1/knowledge/documents": lambda r: httpx.Response(500)})).list_documents()) == []
    assert run(make(lambda r: httpx.Response(500), Settings()).list_documents()) == []


def test_delete_document():
    assert run(make(kb_gw({"/v1/knowledge/documents/x": lambda r: httpx.Response(200, json={"deleted": "x"})})).delete_document("x")) is True
    assert run(make(kb_gw({"/v1/knowledge/documents/x": lambda r: httpx.Response(404)})).delete_document("x")) is False


def test_search_filters_by_doc_ids_and_handles_failure():
    def search(request):
        return httpx.Response(200, json={"results": [{"doc_id": "a", "text": "x"}, {"doc_id": "b", "text": "y"}]})

    c = make(kb_gw({"/v1/knowledge/search": search}))
    assert run(c.search("q")) == [{"doc_id": "a", "text": "x"}, {"doc_id": "b", "text": "y"}]
    assert run(c.search("q", doc_ids=["b"])) == [{"doc_id": "b", "text": "y"}]
    assert run(make(kb_gw({"/v1/knowledge/search": lambda r: httpx.Response(500)})).search("q")) == []
