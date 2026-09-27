import asyncio
import json

import httpx

from anvaya_api import ingest

REAL_URL = "http://example.invalid/api"  # never actually dialled - MockTransport intercepts every request


def run(coro):
    return asyncio.run(coro)


def transport_for(body, status=200):
    return httpx.MockTransport(lambda request: httpx.Response(
        status, content=body if isinstance(body, (bytes, str)) else json.dumps(body)))


# ---------------------------------------------------------------- html_to_text
def test_html_to_text_strips_tags_scripts_styles_and_unescapes():
    raw = "<html><head><style>.x{color:red}</style></head><body><script>evil()</script><h1>Title</h1><p>A &amp; B</p></body></html>"
    text = ingest.html_to_text(raw)
    assert "evil()" not in text and "color:red" not in text
    assert "Title" in text and "A & B" in text


def test_html_to_text_collapses_whitespace_and_blank_lines():
    text = ingest.html_to_text("<p>a</p>\n\n\n\n<p>b</p>   <p>c</p>")
    assert "\n\n\n" not in text and "   " not in text


# ---------------------------------------------------------------- scan_docs
def test_scan_docs_reads_md_and_html_skips_denied_and_binary(tmp_path):
    (tmp_path / "known-issues.md").write_text("# Known issues\nAll good.", encoding="utf-8")
    (tmp_path / "page.html").write_text("<p>Hello <b>World</b></p>", encoding="utf-8")
    (tmp_path / "creds.html").write_text("secret stuff", encoding="utf-8")
    (tmp_path / "network-schematic.html").write_text("<p>LAN map</p>", encoding="utf-8")
    (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "notes.md").write_text("nested note", encoding="utf-8")
    bad = tmp_path / "bad.md"
    bad.write_bytes(b"\xff\xfe not utf8")

    items = ingest.scan_docs(tmp_path)
    sources = {i.source for i in items}
    assert "documentation/known-issues.md" in sources
    assert "documentation/page.html" in sources
    assert "documentation/sub/notes.md" in sources
    assert "documentation/creds.html" not in sources          # deny-listed
    assert "documentation/bad.md" not in sources               # not UTF-8
    schematic = next(i for i in items if i.source == "documentation/network-schematic.html")
    assert schematic.metadata["class"] == "household"
    known = next(i for i in items if "known-issues" in i.source)
    assert known.metadata["class"] == "public" and known.metadata["plugin"] == "homelab.docs"
    page = next(i for i in items if i.source == "documentation/page.html")
    assert "Hello World" in page.text and "<b>" not in page.text


def test_scan_docs_redacts_secrets_and_records_the_count(tmp_path):
    (tmp_path / "leak.md").write_text("password: hunter2xxxx and normal text", encoding="utf-8")
    items = ingest.scan_docs(tmp_path)
    assert items[0].metadata["redacted"] == 1
    assert "hunter2xxxx" not in items[0].text


def test_scan_docs_missing_root_returns_empty(tmp_path):
    assert ingest.scan_docs(tmp_path / "nope") == []


def test_scan_docs_skips_empty_after_redaction(tmp_path):
    (tmp_path / "empty.md").write_text("   \n\n  ", encoding="utf-8")
    assert ingest.scan_docs(tmp_path) == []


def test_stable_id_is_deterministic_and_distinguishes_inputs():
    a = ingest.stable_id_for("docs", "x.md")
    b = ingest.stable_id_for("docs", "x.md")
    c = ingest.stable_id_for("docs", "y.md")
    assert a == b and a != c and a.startswith("anv_")


# ---------------------------------------------------------------- fetch_hub_catalog
def test_fetch_hub_catalog_builds_one_item_per_entry():
    body = {"items": [
        {"id": "app:1", "name": "Jellyfin", "kind": "app", "url": "http://x:8096/", "category": "media",
         "status": "up", "title": "Jellyfin Media Server"},
        {"id": "page:2", "name": "Portal", "kind": "page", "url": "http://x:8099/portal.html"},
    ]}
    items = run(ingest.fetch_hub_catalog(REAL_URL, transport=transport_for(body)))
    assert len(items) == 2
    assert "Jellyfin" in items[0].text and "media" in items[0].text and "up" in items[0].text
    assert "title: Jellyfin Media Server" in items[0].text
    assert items[0].metadata["plugin"] == "homelab.hub" and items[0].metadata["class"] == "public"
    assert items[1].text.count("\n") == 1  # no category/status/title -> just name+URL lines


def test_fetch_hub_catalog_unreachable_returns_empty():
    boom = httpx.MockTransport(lambda r: (_ for _ in ()).throw(httpx.ConnectError("down")))
    assert run(ingest.fetch_hub_catalog(REAL_URL, transport=boom)) == []


def test_fetch_hub_catalog_bad_json_returns_empty():
    assert run(ingest.fetch_hub_catalog(REAL_URL, transport=transport_for("not json"))) == []


def test_fetch_hub_catalog_http_error_status_returns_empty():
    assert run(ingest.fetch_hub_catalog(REAL_URL, transport=transport_for({}, status=500))) == []


# ---------------------------------------------------------------- fetch_atlas
def test_fetch_atlas_builds_one_item_per_entity(tmp_path):
    graph = {"entities": [
        {"id": "homelab", "name": "HomeLab", "type": "foundation", "purpose": "the ground",
         "features": ["a", "b"], "links": {"app": "http://x/"}},
    ]}
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(graph), encoding="utf-8")
    items = run(ingest.fetch_atlas(p))
    assert len(items) == 1
    assert "HomeLab (foundation)" in items[0].text and "- a" in items[0].text and "app: http://x/" in items[0].text
    assert items[0].metadata["entity_id"] == "homelab" and items[0].metadata["plugin"] == "atlas"


def test_fetch_atlas_entity_with_minimal_fields(tmp_path):
    p = tmp_path / "graph.json"
    p.write_text(json.dumps({"entities": [{"id": "bare"}]}), encoding="utf-8")
    items = run(ingest.fetch_atlas(p))
    assert items[0].text == "bare (?)"


def test_fetch_atlas_missing_file_returns_empty(tmp_path):
    assert run(ingest.fetch_atlas(tmp_path / "nope.json")) == []


def test_fetch_atlas_bad_json_returns_empty(tmp_path):
    p = tmp_path / "graph.json"
    p.write_text("{not json", encoding="utf-8")
    assert run(ingest.fetch_atlas(p)) == []


# ---------------------------------------------------------------- fetch_scheduled_tasks
def test_fetch_scheduled_tasks_builds_one_item_per_task():
    tasks = [{"name": "HomeLab-Backup", "state": "Ready", "trigger": "Daily 02:00", "principal": "SYSTEM",
             "action": "backup-system.ps1", "last": "2026-09-26 02:00", "result": 0}]
    items = run(ingest.fetch_scheduled_tasks(REAL_URL, transport=transport_for(tasks)))
    assert len(items) == 1 and "HomeLab-Backup" in items[0].text and "Daily 02:00" in items[0].text
    assert items[0].metadata["plugin"] == "homelab.tasks" and items[0].metadata["class"] == "household"


def test_fetch_scheduled_tasks_minimal_task_has_no_action_or_last_lines():
    tasks = [{"name": "X", "state": "Ready", "trigger": "-", "principal": "SYSTEM"}]
    items = run(ingest.fetch_scheduled_tasks(REAL_URL, transport=transport_for(tasks)))
    assert "action:" not in items[0].text and "last run:" not in items[0].text


def test_fetch_scheduled_tasks_unreachable_returns_empty():
    boom = httpx.MockTransport(lambda r: (_ for _ in ()).throw(httpx.ConnectError("down")))
    assert run(ingest.fetch_scheduled_tasks(REAL_URL, transport=boom)) == []


def test_fetch_scheduled_tasks_http_error_status_returns_empty():
    assert run(ingest.fetch_scheduled_tasks(REAL_URL, transport=transport_for([], status=500))) == []


# ---------------------------------------------------------------- all_items / reindex
from anvaya_api.abstractai import AbstractAIClient
from anvaya_api.config import Settings

S = Settings(username="a", password="b")


def make_ai(handler):
    return AbstractAIClient(S, transport=httpx.MockTransport(handler))


def test_all_items_concatenates_every_source(monkeypatch):
    monkeypatch.setattr(ingest, "scan_docs", lambda: [ingest.IngestItem("d1", "t", "s", {})])

    async def fake_hub(*a, **k):
        return [ingest.IngestItem("h1", "t", "s", {})]

    async def fake_atlas(*a, **k):
        return [ingest.IngestItem("a1", "t", "s", {})]

    async def fake_tasks(*a, **k):
        return [ingest.IngestItem("t1", "t", "s", {})]

    monkeypatch.setattr(ingest, "fetch_hub_catalog", fake_hub)
    monkeypatch.setattr(ingest, "fetch_atlas", fake_atlas)
    monkeypatch.setattr(ingest, "fetch_scheduled_tasks", fake_tasks)
    items = run(ingest.all_items())
    assert [i.stable_id for i in items] == ["d1", "h1", "a1", "t1"]


def _item(stable_id, text="text", plugin="homelab.docs", **extra):
    return ingest.IngestItem(stable_id, text, "src", {"plugin": plugin, "class": "public", "content_hash": ingest.content_hash(text), **extra})


def test_reindex_ingests_new_items():
    ingested = []

    def handler(request):
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "t"})
        if request.url.path == "/v1/knowledge/documents":
            return httpx.Response(200, json={"documents": []})
        if request.url.path == "/v1/knowledge/ingest":
            ingested.append(request.content)
            return httpx.Response(200, json={"doc_id": "new1", "status": "ready"})
        return httpx.Response(404)

    report = run(ingest.reindex(make_ai(handler), [_item("d1")]))
    assert report.scanned == 1 and report.ingested == 1 and report.unchanged == 0 and report.failed == 0
    assert len(ingested) == 1


def test_reindex_skips_unchanged_by_content_hash():
    item = _item("d1")
    existing = [{"doc_id": "old1", "metadata": {"anv_doc_id": "d1", "content_hash": item.metadata["content_hash"]}}]
    calls = {"ingest": 0}

    def handler(request):
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "t"})
        if request.url.path == "/v1/knowledge/documents":
            return httpx.Response(200, json={"documents": existing})
        if request.url.path == "/v1/knowledge/ingest":
            calls["ingest"] += 1
            return httpx.Response(200, json={"doc_id": "new1", "status": "ready"})
        return httpx.Response(404)

    report = run(ingest.reindex(make_ai(handler), [item]))
    assert report.unchanged == 1 and calls["ingest"] == 0


def test_reindex_replaces_changed_item_deleting_the_stale_doc():
    old_hash = "deadbeef00000000"
    existing = [{"doc_id": "old1", "metadata": {"anv_doc_id": "d1", "content_hash": old_hash}}]
    deleted, ingested = [], []

    def handler(request):
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "t"})
        if request.url.path == "/v1/knowledge/documents":
            return httpx.Response(200, json={"documents": existing})
        if request.url.path == "/v1/knowledge/documents/old1" and request.method == "DELETE":
            deleted.append("old1")
            return httpx.Response(200, json={"deleted": "old1"})
        if request.url.path == "/v1/knowledge/ingest":
            ingested.append(request.content)
            return httpx.Response(200, json={"doc_id": "new1", "status": "ready"})
        return httpx.Response(404)

    report = run(ingest.reindex(make_ai(handler), [_item("d1", text="new content")]))
    assert deleted == ["old1"] and report.ingested == 1 and report.unchanged == 0


def test_reindex_deletes_orphans_from_our_own_plugins_only():
    existing = [
        {"doc_id": "orphan1", "metadata": {"anv_doc_id": "gone", "plugin": "homelab.docs"}},
        {"doc_id": "other1", "metadata": {"anv_doc_id": "not-ours", "plugin": "financeos"}},
    ]
    deleted = []

    def handler(request):
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "t"})
        if request.url.path == "/v1/knowledge/documents":
            return httpx.Response(200, json={"documents": existing})
        if request.method == "DELETE":
            deleted.append(request.url.path)
            return httpx.Response(200, json={})
        return httpx.Response(404)

    report = run(ingest.reindex(make_ai(handler), []))
    assert deleted == ["/v1/knowledge/documents/orphan1"] and report.deleted == 1


def test_reindex_counts_failed_ingest():
    def handler(request):
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "t"})
        if request.url.path == "/v1/knowledge/documents":
            return httpx.Response(200, json={"documents": []})
        if request.url.path == "/v1/knowledge/ingest":
            return httpx.Response(422, json={"detail": "bad"})
        return httpx.Response(404)

    report = run(ingest.reindex(make_ai(handler), [_item("d1")]))
    assert report.failed == 1 and report.ingested == 0


def test_reindex_uses_all_items_when_none_given(monkeypatch):
    async def fake_all_items():
        return [_item("d1")]

    monkeypatch.setattr(ingest, "all_items", fake_all_items)

    def handler(request):
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "t"})
        if request.url.path == "/v1/knowledge/documents":
            return httpx.Response(200, json={"documents": []})
        if request.url.path == "/v1/knowledge/ingest":
            return httpx.Response(200, json={"doc_id": "n1", "status": "ready"})
        return httpx.Response(404)

    report = run(ingest.reindex(make_ai(handler)))
    assert report.scanned == 1 and report.ingested == 1


def test_fetch_hub_catalog_item_without_title():
    body = {"items": [{"id": "x", "name": "N", "kind": "app", "url": "http://y/"}]}
    items = run(ingest.fetch_hub_catalog(REAL_URL, transport=transport_for(body)))
    assert "title:" not in items[0].text
