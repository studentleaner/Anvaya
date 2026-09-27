import asyncio

import httpx

from anvaya_api.abstractai import AbstractAIClient
from anvaya_api.config import Settings
from anvaya_api.retrieval import allowed_classes, has_valid_citation, retrieve

S = Settings(username="a", password="b")


def run(coro):
    return asyncio.run(coro)


def make(handler):
    return AbstractAIClient(S, transport=httpx.MockTransport(handler))


def gw(search_hits, docs):
    def handler(request):
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "t"})
        if request.url.path == "/v1/knowledge/search":
            return httpx.Response(200, json={"results": search_hits})
        if request.url.path == "/v1/knowledge/documents":
            return httpx.Response(200, json={"documents": docs})
        return httpx.Response(404)

    return handler


def doc(doc_id, **meta):
    return {"doc_id": doc_id, "metadata": meta}


def test_allowed_classes_intersects_scope_and_profile():
    assert allowed_classes("this_app", "family") == {"public", "household"}
    assert allowed_classes("my_home", "family") == {"public", "household"}   # family never gets finance/health
    assert allowed_classes("my_home", "system") == {"public", "household", "finance", "health"}
    assert allowed_classes("unknown_scope", "system") == {"public"}


def test_retrieve_filters_by_class_and_caps_top_k():
    hits = [{"doc_id": "a", "text": "T1"}, {"doc_id": "b", "text": "T2"}, {"doc_id": "c", "text": "T3"}]
    docs = [doc("a", plugin="homelab.docs", path="p1", **{"class": "public"}),
            doc("b", plugin="financeos", **{"class": "finance"}),
            doc("c", plugin="homelab.docs", path="p2", **{"class": "public"})]
    result = run(retrieve(make(gw(hits, docs)), "q", scope="this_app", profile="family", top_k=4))
    assert [s.id for s in result.sources] == ["a", "c"]  # b (finance) excluded for family
    assert result.plugins == ["homelab.docs"]


def test_retrieve_respects_top_k_cap():
    hits = [{"doc_id": str(i), "text": f"T{i}"} for i in range(5)]
    docs = [doc(str(i), plugin="homelab.docs", **{"class": "public"}) for i in range(5)]
    result = run(retrieve(make(gw(hits, docs)), "q", scope="this_app", profile="system", top_k=2))
    assert len(result.sources) == 2


def test_retrieve_empty_when_no_hits_or_gateway_down():
    empty = run(retrieve(make(gw([], [])), "q", scope="this_app", profile="family"))
    assert empty.sources == [] and empty.plugins == []
    down = run(retrieve(make(lambda r: httpx.Response(500)), "q", scope="this_app", profile="family"))
    assert down.sources == []


def test_uri_for_prefers_path_then_url_then_entity():
    hits = [{"doc_id": "a", "text": "t"}, {"doc_id": "b", "text": "t"}, {"doc_id": "c", "text": "t"}]
    docs = [doc("a", plugin="homelab.docs", path="x.md", **{"class": "public"}),
            doc("b", plugin="homelab.hub", url="http://y", **{"class": "public"}),
            doc("c", plugin="atlas", entity_id="homelab", **{"class": "public"})]
    result = run(retrieve(make(gw(hits, docs)), "q", scope="this_app", profile="system"))
    assert [s.uri for s in result.sources] == ["/x.md", "http://y", "/atlas/#homelab"]


def test_uri_for_falls_back_to_empty():
    hits = [{"doc_id": "a", "text": "t"}]
    docs = [doc("a", plugin="x", **{"class": "public"})]
    result = run(retrieve(make(gw(hits, docs)), "q", scope="this_app", profile="system"))
    assert result.sources[0].uri == ""


def test_context_block_and_sources_event_shape():
    hits = [{"doc_id": "a", "text": "hello world"}]
    docs = [doc("a", plugin="homelab.docs", path="p.md", anv_doc_id="stable-a", **{"class": "public"})]
    result = run(retrieve(make(gw(hits, docs)), "q", scope="this_app", profile="system"))
    assert result.context_block == "[src_1] hello world"
    assert result.as_sources_event() == [{"id": "src_1", "plugin": "homelab.docs", "title": "p.md", "uri": "/p.md",
                                          "snippet": "hello world"}]


def test_has_valid_citation():
    class R:
        sources = [1, 2]
    assert has_valid_citation("see [src_1] and [src_2]", R()) is True
    assert has_valid_citation("no citation here", R()) is False

    class Empty:
        sources = []
    assert has_valid_citation("I couldn't find that in your home data.", Empty()) is True
    assert has_valid_citation("made up fact", Empty()) is False
