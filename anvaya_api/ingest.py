"""Home Knowledge ingest pipeline (PLAN Phase 4, pulled forward 2026-09-27).

Sources (see ingest_config.py for why these and not a raw drive scan):
  - HomeLab documentation/*.md + *.html   -> class "household" (network-schematic.html) or "public" (everything else)
  - homelab-hub /api/catalog              -> every live app/page/project/link URL, one document
  - Ecosystem Atlas graph.json            -> every entity's purpose/features/links, one document per entity
  - service-control-api /api/tasks        -> every HomeLab-* scheduled task, one document

Idempotent: each source document gets a stable `doc_id` derived from its identity (path / item id), and existing
documents are diffed by content hash so an unchanged file costs zero AbstractAI calls on a re-run.
"""

from __future__ import annotations

import hashlib
import html
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Optional

import httpx

from .abstractai import AbstractAIClient
from .ingest_config import ATLAS_GRAPH_PATH, DOCS_DIR, HUB_CATALOG_URL, TASKS_URL, TEXT_SUFFIXES, is_denied
from .redact import redact

log = logging.getLogger("anvaya.ingest")

_TAG_RE = re.compile(r"<script.*?</script>|<style.*?</style>|<[^>]+>", re.I | re.S)
_WS_RE = re.compile(r"[ \t]+")
_BLANKLINES_RE = re.compile(r"\n{3,}")


def html_to_text(raw: str) -> str:
    """Rough tag stripping for ingestion purposes - Anvaya reads for meaning, not layout."""
    text = _TAG_RE.sub(" ", raw)
    text = html.unescape(text)
    text = _WS_RE.sub(" ", text)
    return _BLANKLINES_RE.sub("\n\n", text).strip()


@dataclass
class IngestItem:
    stable_id: str  # OUR identity for this source item - the real KnowledgeBus doc_id is assigned per ingest call
    text: str
    source: str
    metadata: dict


def stable_id_for(*parts: str) -> str:
    return "anv_" + hashlib.sha256("|".join(parts).encode()).hexdigest()[:24]


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def scan_docs(root: Path = DOCS_DIR) -> list[IngestItem]:
    """Every non-denied .md/.html under `root`, redacted, as one IngestItem each."""
    items: list[IngestItem] = []
    if not root.exists():
        log.warning("docs root %s does not exist - skipping", root)
        return items
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        rel = str(path.relative_to(root)).replace("\\", "/")
        if is_denied(rel):
            continue
        try:
            raw = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as e:
            log.warning("skip %s: %s", rel, e)
            continue
        text = html_to_text(raw) if path.suffix.lower() == ".html" else raw
        text, redacted_count = redact(text)
        if not text.strip():
            continue
        klass = "household" if rel == "network-schematic.html" else "public"
        items.append(IngestItem(
            stable_id=stable_id_for("docs", rel),
            text=text,
            source=f"documentation/{rel}",
            metadata={"plugin": "homelab.docs", "class": klass, "path": rel,
                     "content_hash": content_hash(text), "redacted": redacted_count},
        ))
    return items


async def fetch_hub_catalog(url: str = HUB_CATALOG_URL, timeout: float = 10.0,
                            transport: Optional[httpx.AsyncBaseTransport] = None) -> list[IngestItem]:
    """One document per catalog item (URL + kind + category + status) - lets Anvaya answer "what's at :NNNN"
    and "what pages/apps do we have" without needing per-page prose."""
    try:
        async with httpx.AsyncClient(timeout=timeout, transport=transport) as c:
            r = await c.get(url)
            r.raise_for_status()
            body = r.json()
    except (httpx.HTTPError, ValueError) as e:
        log.warning("hub catalog unreachable: %s", e)
        return []
    items = []
    for it in body.get("items", []):
        parts = [f"{it.get('name', '?')} - {it.get('kind', '?')}", f"URL: {it.get('url', '')}"]
        if it.get("category"):
            parts.append(f"category: {it['category']}")
        if it.get("status"):
            parts.append(f"status: {it['status']}")
        if it.get("title"):
            parts.append(f"title: {it['title']}")
        text = "\n".join(parts)
        items.append(IngestItem(
            stable_id=stable_id_for("hub", it.get("id", it.get("url", ""))),
            text=text, source="homelab-hub/api/catalog",
            metadata={"plugin": "homelab.hub", "class": "public", "url": it.get("url", ""),
                     "content_hash": content_hash(text)},
        ))
    return items


async def fetch_atlas(path: Path = ATLAS_GRAPH_PATH) -> list[IngestItem]:
    """One document per entity: name, type, purpose, features, links - the atlas is already the curated summary,
    so no extra prose synthesis is needed."""
    if not path.exists():
        log.warning("atlas graph %s does not exist - skipping", path)
        return []
    import json
    try:
        graph = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        log.warning("could not read atlas graph: %s", e)
        return []
    items = []
    for e in graph.get("entities", []):
        parts = [f"{e.get('name', e['id'])} ({e.get('type', '?')})"]
        if e.get("purpose"):
            parts.append(e["purpose"])
        for feat in e.get("features", []) or []:
            parts.append(f"- {feat}")
        for k, v in (e.get("links") or {}).items():
            parts.append(f"{k}: {v}")
        text = "\n".join(parts)
        items.append(IngestItem(
            stable_id=stable_id_for("atlas", e["id"]),
            text=text, source=f"atlas/{e['id']}",
            metadata={"plugin": "atlas", "class": "public", "entity_type": e.get("type", ""),
                     "entity_id": e["id"], "content_hash": content_hash(text)},
        ))
    return items


async def fetch_scheduled_tasks(url: str = TASKS_URL, timeout: float = 10.0,
                                transport: Optional[httpx.AsyncBaseTransport] = None) -> list[IngestItem]:
    """One document per HomeLab-* scheduled task (name, schedule, action, last result) - so "what runs at night"
    or "is the backup task registered" can be answered directly."""
    try:
        async with httpx.AsyncClient(timeout=timeout, transport=transport) as c:
            r = await c.get(url)
            r.raise_for_status()
            tasks = r.json()
    except (httpx.HTTPError, ValueError) as e:
        log.warning("scheduled-tasks API unreachable: %s", e)
        return []
    items = []
    for t in tasks:
        parts = [f"Scheduled task: {t.get('name', '?')}", f"state: {t.get('state', '?')}",
                 f"trigger: {t.get('trigger', '?')}", f"principal: {t.get('principal', '?')}"]
        if t.get("action"):
            parts.append(f"action: {t['action']}")
        if t.get("last"):
            parts.append(f"last run: {t['last']} (result {t.get('result', '?')})")
        text = "\n".join(parts)
        items.append(IngestItem(
            stable_id=stable_id_for("task", t.get("name", "")),
            text=text, source="service-control-api/api/tasks",
            metadata={"plugin": "homelab.tasks", "class": "household",
                     "content_hash": content_hash(text)},
        ))
    return items


async def all_items() -> list[IngestItem]:
    docs = scan_docs()
    hub = await fetch_hub_catalog()
    atlas = await fetch_atlas()
    tasks = await fetch_scheduled_tasks()
    return docs + hub + atlas + tasks


@dataclass
class IngestReport:
    scanned: int = 0
    ingested: int = 0
    unchanged: int = 0
    deleted: int = 0
    failed: int = 0


_OUR_PLUGINS = {"homelab.docs", "homelab.hub", "homelab.tasks", "atlas"}


async def reindex(ai: AbstractAIClient, items: Optional[list[IngestItem]] = None) -> IngestReport:
    """Full sync: ingest new/changed items, delete documents whose source no longer exists. Idempotent - an
    unchanged item costs one `list_documents` comparison and zero ingest calls.

    KnowledgeBus mints a fresh (random) doc_id on every ingest call - there is no "update in place" - so we track
    OUR OWN stable identity in metadata.anv_doc_id and look documents up by that, not by the KnowledgeBus doc_id."""
    items = items if items is not None else await all_items()
    report = IngestReport(scanned=len(items))
    existing_docs = await ai.list_documents()
    by_stable_id = {(d.get("metadata") or {}).get("anv_doc_id"): d for d in existing_docs
                    if (d.get("metadata") or {}).get("anv_doc_id")}
    wanted = set()
    for item in items:
        wanted.add(item.stable_id)
        prior = by_stable_id.get(item.stable_id)
        if prior and (prior.get("metadata") or {}).get("content_hash") == item.metadata.get("content_hash"):
            report.unchanged += 1
            continue
        if prior:
            await ai.delete_document(prior["doc_id"])  # stale version - a new one replaces it below
        doc = await ai.ingest_text(item.text, source=item.source,
                                   metadata={**item.metadata, "anv_doc_id": item.stable_id})
        if doc is None or doc.get("status") == "failed":
            report.failed += 1
        else:
            report.ingested += 1
    for stable_id, d in by_stable_id.items():
        if stable_id not in wanted and (d.get("metadata") or {}).get("plugin") in _OUR_PLUGINS:
            await ai.delete_document(d["doc_id"])
            report.deleted += 1
    return report
