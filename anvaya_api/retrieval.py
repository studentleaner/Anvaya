"""Scope -> retrieval (PLAN Phase 1.2/1.3). Maps a chat request's scope + context to a KnowledgeBus search, then
formats the numbered SOURCES block the answer prompt cites from. No plugin layer yet (PLAN Phase 3) - retrieval
reads whatever was ingested by ingest.py, filtered by the classes each profile is allowed to see (CONTRACTS.md §4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .abstractai import AbstractAIClient

MAX_SNIPPET_CHARS = 400
MAX_SOURCES = 4

# scope -> which document classes it may draw from (kids never calls this at all - refused earlier in main.py)
_SCOPE_CLASSES: dict[str, set[str]] = {
    "this_app": {"public", "household"},
    "current_page": {"public", "household"},
    "my_home": {"public", "household", "finance", "health"},
    "all_apps": {"public", "household", "finance", "health"},
}
# profile -> classes it may ever see, regardless of scope (CONTRACTS.md §4: finance/health never for kids - kids
# never reaches here at all; family gets household+public only until the Phase 4 eval gate passes, per DECISIONS D-13)
_PROFILE_CLASSES: dict[str, set[str]] = {
    "family": {"public", "household"},
    "system": {"public", "household", "finance", "health"},
}


@dataclass
class Source:
    id: str
    plugin: str
    title: str
    uri: str
    snippet: str
    text: str


@dataclass
class RetrievalResult:
    sources: list[Source] = field(default_factory=list)
    plugins: list[str] = field(default_factory=list)
    redacted: int = 0

    @property
    def context_block(self) -> str:
        return "\n\n".join(f"[src_{i + 1}] {s.text}" for i, s in enumerate(self.sources))

    def as_sources_event(self) -> list[dict]:
        return [{"id": f"src_{i + 1}", "plugin": s.plugin, "title": s.title, "uri": s.uri, "snippet": s.snippet}
                for i, s in enumerate(self.sources)]


def allowed_classes(scope: str, profile: Literal["family", "system"]) -> set[str]:
    return _SCOPE_CLASSES.get(scope, {"public"}) & _PROFILE_CLASSES.get(profile, {"public"})


async def retrieve(ai: AbstractAIClient, query: str, *, scope: str, profile: str, top_k: int = MAX_SOURCES) -> RetrievalResult:
    classes = allowed_classes(scope, profile)
    # /v1/knowledge/search returns {doc_id, text, score} - no metadata (chunks aren't tied to their document's
    # metadata in the gateway's search response). Join against /v1/knowledge/documents by doc_id instead of
    # changing AbstractAI's response schema for this.
    hits, docs = await ai.search(query, top_k=top_k * 3), await ai.list_documents()  # over-fetch, filter by class below
    meta_by_doc_id = {d["doc_id"]: (d.get("metadata") or {}) for d in docs}
    result = RetrievalResult()
    plugins: set[str] = set()
    for h in hits:
        meta = meta_by_doc_id.get(h.get("doc_id", ""), {})
        klass = meta.get("class", "public")
        if klass not in classes:
            continue
        text = h.get("text", "")
        plugin = meta.get("plugin", "unknown")
        plugins.add(plugin)
        result.sources.append(Source(
            id=meta.get("anv_doc_id", h.get("doc_id", "")),
            plugin=plugin,
            title=meta.get("path") or meta.get("entity_id") or h.get("source", "source"),
            uri=_uri_for(meta),
            snippet=text[:MAX_SNIPPET_CHARS],
            text=text,
        ))
        if len(result.sources) >= top_k:
            break
    result.plugins = sorted(plugins)
    return result


def _uri_for(meta: dict) -> str:
    if meta.get("path"):
        return "/" + meta["path"]
    if meta.get("url"):
        return meta["url"]
    if meta.get("entity_id"):
        return f"/atlas/#{meta['entity_id']}"
    return ""


NO_MATCH_REPLY = "I couldn't find that in your home data."


def has_valid_citation(answer: str, result: RetrievalResult) -> bool:
    """Whether `answer` is safe to show as-is. When sources exist, at least one must actually be cited - a model
    that had grounding material but ignored it is exactly the case worth catching. When there is nothing to cite,
    ANY answer is accepted: the system prompt explicitly allows unsourced general-knowledge answers in that case
    (see chat.py WITHOUT_SOURCES_SUFFIX) - there is nothing to enforce."""
    if not result.sources:
        return True
    return any(f"[src_{i + 1}]" in answer for i in range(len(result.sources)))


def fallback_answer(result: RetrievalResult) -> str:
    """Deterministic, un-hallucinated answer used when the model twice fails to cite its sources (chat.py's
    enforcement retry). Lists what was found without claiming the model's synthesis is trustworthy."""
    if not result.sources:
        return NO_MATCH_REPLY
    titles = ", ".join(s.title for s in result.sources)
    return f"I found information that may be relevant but couldn't produce a properly cited answer. Sources: {titles}."
