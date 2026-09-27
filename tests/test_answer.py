import asyncio

import httpx

from anvaya_api.abstractai import AbstractAIClient
from anvaya_api.answer import collect_answer, generate_from_result, generate_grounded_answer
from anvaya_api.config import Settings
from anvaya_api.retrieval import RetrievalResult, Source

S = Settings(username="a", password="b")
DONE = 'event: done\ndata: {"elapsed": 1}\n\n'


def run(coro):
    return asyncio.run(coro)


def make(handler):
    return AbstractAIClient(S, transport=httpx.MockTransport(handler))


def stream_gw(bodies):
    """bodies: list of response bodies, consumed in order across successive /v1/complete/stream calls."""
    calls = {"n": 0}

    def handler(request):
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "t"})
        if request.url.path == "/v1/complete/stream":
            body = bodies[min(calls["n"], len(bodies) - 1)]
            calls["n"] += 1
            return httpx.Response(200, content=body.encode())
        return httpx.Response(404)

    handler.calls = calls
    return handler


NO_SOURCES = RetrievalResult()
WITH_SOURCE = RetrievalResult(sources=[Source("id1", "homelab.docs", "solar.md", "/solar.md", "snip", "The inverter is a Deye.")])


def test_collect_answer_success():
    text, error = run(collect_answer(make(stream_gw(['data: {"token": "Hi"}\n\n' + DONE])),
                                     prompt="p", system="s", model="m"))
    assert text == "Hi" and error is None


def test_collect_answer_error_event():
    text, error = run(collect_answer(make(stream_gw(['event: error\ndata: {"detail": "boom"}\n\n'])),
                                     prompt="p", system="s", model="m"))
    assert text == "" and error == {"code": "model_timeout", "message": "boom"}


def test_collect_answer_no_credentials():
    text, error = run(collect_answer(AbstractAIClient(Settings(), transport=httpx.MockTransport(lambda r: httpx.Response(500))),
                                     prompt="p", system="s", model="m"))
    assert text == "" and error == {"code": "gateway_down", "message": "AbstractAI login failed or is not configured"}


def test_generate_from_result_no_sources_accepts_any_answer_no_retry():
    h = stream_gw(['data: {"token": "General knowledge answer."}\n\n' + DONE])
    ans = run(generate_from_result(make(h), "what is the sun", NO_SOURCES, model="m", base_system_prompt="BASE"))
    assert ans.text == "General knowledge answer." and ans.cited is True and ans.error is None
    assert h.calls["n"] == 1  # one call, no retry needed


def test_generate_from_result_cited_on_first_try_no_retry():
    h = stream_gw(['data: {"token": "It is a Deye [src_1]."}\n\n' + DONE])
    ans = run(generate_from_result(make(h), "which inverter", WITH_SOURCE, model="m", base_system_prompt="BASE"))
    assert ans.text == "It is a Deye [src_1]." and ans.cited is True
    assert h.calls["n"] == 1


def test_generate_from_result_retries_once_then_succeeds():
    h = stream_gw(['data: {"token": "It is a Deye."}\n\n' + DONE,          # uncited
                  'data: {"token": "It is a Deye [src_1]."}\n\n' + DONE])  # retry, cited
    ans = run(generate_from_result(make(h), "which inverter", WITH_SOURCE, model="m", base_system_prompt="BASE"))
    assert ans.text == "It is a Deye [src_1]." and ans.cited is True and h.calls["n"] == 2


def test_generate_from_result_falls_back_after_failed_retry(caplog):
    h = stream_gw(['data: {"token": "It is a Deye."}\n\n' + DONE,   # uncited
                  'data: {"token": "Still uncited."}\n\n' + DONE])  # retry also uncited
    with caplog.at_level("WARNING"):
        ans = run(generate_from_result(make(h), "which inverter", WITH_SOURCE, model="m", base_system_prompt="BASE"))
    assert ans.cited is False and "solar.md" in ans.text and h.calls["n"] == 2
    assert any("stayed uncited" in rec.message for rec in caplog.records)


def test_generate_from_result_falls_back_when_retry_errors():
    h = stream_gw(['data: {"token": "It is a Deye."}\n\n' + DONE,               # uncited
                  'event: error\ndata: {"detail": "gateway hiccup"}\n\n'])       # retry fails outright
    ans = run(generate_from_result(make(h), "which inverter", WITH_SOURCE, model="m", base_system_prompt="BASE"))
    assert ans.cited is False and "solar.md" in ans.text


def test_generate_from_result_propagates_first_attempt_error():
    h = stream_gw(['event: error\ndata: {"detail": "down"}\n\n'])
    ans = run(generate_from_result(make(h), "q", WITH_SOURCE, model="m", base_system_prompt="BASE"))
    assert ans.error == {"code": "model_timeout", "message": "down"} and ans.text == ""


def test_generate_grounded_answer_retrieves_then_delegates():
    def handler(request):
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "t"})
        if request.url.path == "/v1/knowledge/search":
            return httpx.Response(200, json={"results": [{"doc_id": "a", "text": "The inverter is a Deye."}]})
        if request.url.path == "/v1/knowledge/documents":
            return httpx.Response(200, json={"documents": [{"doc_id": "a", "metadata": {"plugin": "homelab.docs", "class": "public", "path": "solar.md"}}]})
        if request.url.path == "/v1/complete/stream":
            return httpx.Response(200, content=('data: {"token": "It is a Deye [src_1]."}\n\n' + DONE).encode())
        return httpx.Response(404)

    ans = run(generate_grounded_answer(make(handler), "which inverter", scope="my_home", profile="system",
                                       model="m", base_system_prompt="BASE"))
    assert ans.text == "It is a Deye [src_1]." and ans.cited is True and len(ans.result.sources) == 1
