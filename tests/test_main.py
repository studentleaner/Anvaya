import httpx
from fastapi.testclient import TestClient

from anvaya_api.abstractai import AbstractAIClient
from anvaya_api.config import Settings
from anvaya_api.main import create_app


def client_for(settings, handler):
    ai = AbstractAIClient(settings, transport=httpx.MockTransport(handler))
    return TestClient(create_app(settings, ai))


def gateway(request):
    if request.url.path == "/openapi.json":
        return httpx.Response(200, json={})
    if request.url.path == "/token":
        return httpx.Response(200, json={"access_token": "t", "token_type": "bearer"})
    return httpx.Response(404)


def test_healthz():
    assert client_for(Settings(), gateway).get("/healthz").json()["ok"] is True


def test_status_ok():
    body = client_for(Settings(username="a", password="b"), gateway).get("/api/status").json()
    assert body["gateway"] == "up" and body["auth"] == "ok"
    assert body["local_only"] is True and body["provider"] == "ollama"
    assert body["model"] == {"name": "llama3.1:8b", "state": "unknown", "detail": ""} and body["plugins"] == []
    assert body["bootstrap"] == {}


def test_status_not_configured():
    assert client_for(Settings(), gateway).get("/api/status").json()["auth"] == "not_configured"


def test_status_gateway_down_reports_unknown_auth():
    def down(request):
        raise httpx.ConnectError("refused")

    body = client_for(Settings(username="a", password="b"), down).get("/api/status").json()
    assert body["gateway"] == "down" and body["auth"] == "unknown"


def test_status_auth_failed():
    def bad_login(request):
        if request.url.path == "/openapi.json":
            return httpx.Response(200, json={})
        return httpx.Response(401)

    assert client_for(Settings(username="a", password="b"), bad_login).get("/api/status").json()["auth"] == "failed"


def test_module_level_app_exists():
    from anvaya_api.main import app
    assert app.title == "Anvaya API"


# ---------------------------------------------------------------- /api/chat
import json
import re

CHAT = {"message": "What is a solar inverter?", "scope": "this_app", "profile": "family"}


def chat_gateway(stream_body):
    def handler(request):
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "t"})
        if request.url.path == "/v1/complete/stream":
            return httpx.Response(200, content=stream_body.encode())
        return httpx.Response(404)

    return handler


def events(text):
    out = []
    for block in text.strip().split("\n\n"):
        ev, data = block.split("\n", 1)
        out.append((ev[len("event: "):], json.loads(data[len("data: "):])))
    return out


def test_chat_streams_contract_events_in_order():
    body = ('data: {"token": "It converts "}\n\ndata: {"token": "DC to AC."}\n\n'
            'event: done\ndata: {"elapsed": 2.0}\n\n')
    c = client_for(Settings(username="a", password="b"), chat_gateway(body))
    r = c.post("/api/chat", json={**CHAT, "history": [{"role": "user", "text": "hi"}],
                                  "context": {"app": "portal", "page": "system"}})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    ev = events(r.text)
    # Citation enforcement (2026-09-27) buffers the whole answer before showing it, then reveals it word-by-word -
    # the client still sees a token stream, it just isn't literally the model's own token boundaries any more.
    kinds = [e for e, _ in ev]
    assert kinds[:3] == ["status", "context", "status"] and kinds[-2:] == ["sources", "done"]
    assert all(k == "token" for k in kinds[3:-2]) and len(kinds) > 5
    assert ev[1][1] == {"scope": "this_app", "plugins": [], "redacted": 0, "mode": "knowledge"}
    assert "".join(d["t"] for e, d in ev if e == "token") == "It converts DC to AC."
    done = ev[-1][1]
    assert done["local"] is True and done["model"] == "ollama/llama3.1:8b" and done["elapsed_ms"] >= 0
    assert done["cited"] is True  # no sources retrieved -> any answer accepted (general knowledge allowed)
    assert re.fullmatch(r"conv_[0-9A-HJKMNP-TV-Z]{26}", done["conversation_id"])
    assert ev[-2] == ("sources", {"items": []})


def test_chat_keeps_supplied_conversation_id():
    body = 'event: done\ndata: {"elapsed": 1}\n\n'
    c = client_for(Settings(username="a", password="b"), chat_gateway(body))
    cid = "conv_" + "0" * 26
    ev = events(c.post("/api/chat", json={**CHAT, "conversation_id": cid}).text)
    assert ev[-1][1]["conversation_id"] == cid


def test_chat_error_becomes_error_event_with_fallback():
    c = client_for(Settings(), chat_gateway(""))  # no credentials -> gateway_down
    ev = events(c.post("/api/chat", json=CHAT).text)
    assert ev[-1][0] == "error" and ev[-1][1]["code"] == "gateway_down" and ev[-1][1]["fallback"] == "lookup_only"


def test_chat_kids_profile_is_forbidden():
    c = client_for(Settings(username="a", password="b"), chat_gateway(""))
    r = c.post("/api/chat", json={**CHAT, "profile": "kids"})
    assert r.status_code == 403


def test_chat_validation():
    c = client_for(Settings(username="a", password="b"), chat_gateway(""))
    assert c.post("/api/chat", json={**CHAT, "message": ""}).status_code == 422
    assert c.post("/api/chat", json={**CHAT, "scope": "everything"}).status_code == 422
    assert c.post("/api/chat", json={**CHAT, "conversation_id": "nope"}).status_code == 422
    too_long = [{"role": "user", "text": "x"}] * 7
    assert c.post("/api/chat", json={**CHAT, "history": too_long}).status_code == 422


def test_history_lines_and_status_mode():
    from anvaya_api.chat import HistoryItem, history_lines
    items = [HistoryItem(role="user", text="a"), HistoryItem(role="assistant", text="b")]
    assert history_lines(items) == ["user: a", "assistant: b"]
    body = client_for(Settings(), gateway).get("/api/status").json()
    assert body["mode"] == "knowledge"


def test_chat_marks_model_warm_and_status_reports_it():
    body = 'data: {"token": "x"}\n\nevent: done\ndata: {"elapsed": 1}\n\n'
    c = client_for(Settings(username="a", password="b"), chat_gateway(body))
    assert c.get("/api/status").json()["model"]["state"] == "unknown"
    ev = events(c.post("/api/chat", json=CHAT).text)
    assert ev[0][1]["model_state"] == "unknown"       # first request: nothing known yet
    assert c.get("/api/status").json()["model"]["state"] == "warm"
    ev2 = events(c.post("/api/chat", json=CHAT).text)
    assert ev2[0][1]["model_state"] == "warm" and ev2[2][1] == {"stage": "generating", "model_state": "warm"}


def test_wire_state_mapping():
    from anvaya_api.bootstrap import ModelState
    from anvaya_api.chat import wire_state
    ms = ModelState()
    ms.set("warming")
    assert wire_state(ms) == "loading"
    ms.set("error", "x")
    assert wire_state(ms) == "unknown"


def test_chat_announces_model_loading_while_warming():
    from anvaya_api.bootstrap import ModelState
    from anvaya_api.chat import ChatRequest, chat_events

    async def collect_first_events():
        ai = AbstractAIClient(Settings(username="a", password="b"),
                              transport=httpx.MockTransport(chat_gateway('event: done\ndata: {"elapsed": 1}\n\n')))
        ms = ModelState()
        ms.set("warming")
        out = []
        async for frame in chat_events(ChatRequest(**CHAT), ai, Settings(username="a", password="b"), lambda: 1, "SYS", ms):
            out.append(frame)
        return out

    import asyncio
    frames = asyncio.run(collect_first_events())
    assert '"stage": "model_loading"' in frames[2] and '"model_state": "loading"' in frames[2]


def test_lifespan_runs_bootstrap_in_background_and_cancels_cleanly():
    seen = []

    def handler(request):
        seen.append(request.url.path)
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "t"})
        if request.url.path.startswith("/admin/costs"):
            return httpx.Response(200, json={})
        if request.url.path.startswith("/v1/prompts"):
            return httpx.Response(200, json={"template": "T"})
        if request.url.path == "/v1/complete/stream":
            return httpx.Response(200, content=b'event: done\ndata: {"elapsed": 1}\n\n')
        return httpx.Response(404)

    s = Settings(username="a", password="b")
    ai = AbstractAIClient(s, transport=httpx.MockTransport(handler))
    import time as _t
    with TestClient(create_app(s, ai)) as c:
        for _ in range(100):
            body = c.get("/api/status").json()
            if body["model"]["state"] == "warm":
                break
            _t.sleep(0.05)
        assert body["model"]["state"] == "warm" and body["bootstrap"] == {"budget": True, "prompts": True}
    assert "/v1/complete/stream" in seen


def test_lifespan_cancels_a_slow_bootstrap():
    def slow(request):
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "t"})
        return httpx.Response(200, json={})

    s = Settings(username="a", password="b")
    ai = AbstractAIClient(s, transport=httpx.MockTransport(slow))
    with TestClient(create_app(s, ai)) as c:      # exits immediately: the still-running warm-up task is cancelled
        assert c.get("/healthz").status_code == 200


def test_lifespan_without_bootstrap():
    s = Settings()
    with TestClient(create_app(s, AbstractAIClient(s, transport=httpx.MockTransport(gateway)), run_bootstrap=False)) as c:
        assert c.get("/healthz").status_code == 200


def test_chat_uses_prompt_from_vault():
    captured = {}

    def handler(request):
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "t"})
        if request.url.path == "/v1/prompts/anvaya.answer":
            return httpx.Response(200, json={"template": "VAULT PROMPT"})
        if request.url.path == "/v1/complete/stream":
            captured.update(json.loads(request.content))
            return httpx.Response(200, content=b'event: done\ndata: {"elapsed": 1}\n\n')
        return httpx.Response(404)

    c = client_for(Settings(username="a", password="b"), handler)
    c.post("/api/chat", json=CHAT)
    assert captured["system"].startswith("VAULT PROMPT")


def test_status_reports_last_reindex_and_gains_no_new_fields_before_reindex_runs():
    body = client_for(Settings(), gateway).get("/api/status").json()
    assert body["last_reindex"] == {}


def test_admin_reindex_endpoint_returns_a_report_and_status_reflects_it():
    def handler(request):
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "t"})
        if request.url.path == "/v1/knowledge/documents":
            return httpx.Response(200, json={"documents": []})
        if request.url.path == "/v1/knowledge/ingest":
            return httpx.Response(200, json={"doc_id": "d1", "status": "ready"})
        return httpx.Response(404)

    c = client_for(Settings(username="a", password="b"), handler)
    r = c.post("/api/admin/reindex")
    assert r.status_code == 200
    body = r.json()
    assert body["scanned"] >= 0 and "at" in body
    assert c.get("/api/status").json()["last_reindex"]["scanned"] == body["scanned"]


# ----------------------------------------------------------------- /api/ask
def test_ask_returns_a_cited_answer():
    def handler(request):
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "t"})
        if request.url.path == "/v1/knowledge/search":
            return httpx.Response(200, json={"results": [{"doc_id": "a", "text": "The inverter is a Deye."}]})
        if request.url.path == "/v1/knowledge/documents":
            return httpx.Response(200, json={"documents": [{"doc_id": "a", "metadata": {"plugin": "homelab.docs", "class": "public", "path": "solar.md"}}]})
        if request.url.path == "/v1/complete/stream":
            return httpx.Response(200, content=b'data: {"token": "It is a Deye [src_1]."}\n\nevent: done\ndata: {"elapsed": 1}\n\n')
        return httpx.Response(404)

    c = client_for(Settings(username="a", password="b"), handler)
    r = c.post("/api/ask", json={"message": "which inverter"})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "It is a Deye [src_1]." and body["cited"] is True and body["local"] is True
    assert body["model"] == "ollama/llama3.1:8b"
    assert body["sources"] == [{"id": "src_1", "plugin": "homelab.docs", "title": "solar.md", "uri": "/solar.md",
                               "snippet": "The inverter is a Deye."}]


def test_ask_defaults_scope_and_profile():
    c = client_for(Settings(username="a", password="b"), chat_gateway('event: done\ndata: {"elapsed": 1}\n\n'))
    r = c.post("/api/ask", json={"message": "hello"})
    assert r.status_code == 200 and r.json()["cited"] is True  # no sources -> accepted


def test_ask_rejects_kids_profile_at_schema_level():
    c = client_for(Settings(username="a", password="b"), chat_gateway(""))
    r = c.post("/api/ask", json={"message": "hello", "profile": "kids"})
    assert r.status_code == 422


def test_ask_validation():
    c = client_for(Settings(username="a", password="b"), chat_gateway(""))
    assert c.post("/api/ask", json={"message": ""}).status_code == 422
    assert c.post("/api/ask", json={"message": "x", "scope": "everything"}).status_code == 422


def test_ask_gateway_error_becomes_502():
    c = client_for(Settings(), chat_gateway(""))  # no credentials -> gateway_down
    r = c.post("/api/ask", json={"message": "hello"})
    assert r.status_code == 502
    assert "AbstractAI" in r.json()["detail"]


def test_build_system_prompt_with_and_without_sources():
    from anvaya_api.chat_prompt import build_system_prompt
    from anvaya_api.retrieval import RetrievalResult, Source
    empty = build_system_prompt("BASE", RetrievalResult())
    assert empty.startswith("BASE") and "No information about this home" in empty
    with_src = build_system_prompt("BASE", RetrievalResult(sources=[Source("id1", "homelab.docs", "t", "u", "s", "full text")]))
    assert "SOURCES:" in with_src and "[src_1] full text" in with_src


def test_chat_cites_a_real_source_no_warning_logged(caplog):
    def handler(request):
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "t"})
        if request.url.path == "/v1/knowledge/search":
            return httpx.Response(200, json={"results": [{"doc_id": "a", "text": "The inverter is a Deye."}]})
        if request.url.path == "/v1/knowledge/documents":
            return httpx.Response(200, json={"documents": [{"doc_id": "a", "metadata": {"plugin": "homelab.docs", "class": "public", "path": "solar.md"}}]})
        if request.url.path == "/v1/complete/stream":
            return httpx.Response(200, content=b'data: {"token": "It is a Deye [src_1]."}\n\nevent: done\ndata: {"elapsed": 1}\n\n')
        return httpx.Response(404)

    c = client_for(Settings(username="a", password="b"), handler)
    with caplog.at_level("WARNING"):
        r = c.post("/api/chat", json=CHAT)
    ev = events(r.text)
    ctx = ev[1][1]
    assert ctx["plugins"] == ["homelab.docs"]
    sources_ev = next(d for e, d in ev if e == "sources")
    assert sources_ev["items"] == [{"id": "src_1", "plugin": "homelab.docs", "title": "solar.md", "uri": "/solar.md", "snippet": "The inverter is a Deye."}]
    assert not any("cited no source" in rec.message for rec in caplog.records)
