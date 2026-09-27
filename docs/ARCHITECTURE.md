# Anvaya — Architecture

> Full architecture (verified against the running stack, port numbers, network names, mount paths, failure modes): HomeLab `documentation/anvaya/ARCHITECTURE.md`. This page is the map, not the territory.

## Context

```
HomeChat widget (documentation/js/homechat.js, in every mounted page)
        │  fetch/SSE  /anvaya-api/...  (docs nginx, login, same origin)
        ▼
anvaya-api  (this repo — FastAPI, container, no host port)
        │  X-API-Key-free: logs in as its own AbstractAI user
        ▼
AbstractAI gateway  (ModelBus · RouteLLM · KnowledgeBus · PromptVault · Guardrails · CostGuard)
        ▼
abstractai-ollama  (local model, GTX 1660 SUPER, 6 GB)
```

Anvaya never talks to Ollama, another model provider, or a cloud API directly — only through AbstractAI (see `CLAUDE.md`/`AGENTS.md` Rule 10).

## Components

| Component | Responsibility | Tech | Lives in |
|---|---|---|---|
| `homechat.js` | Drawer + mobile sheet UI, SSE streaming, in-drawer sign-in | Vanilla JS, no build step | HomeLab `documentation/js/homechat.js` |
| `anvaya_api.main` | HTTP surface: `/healthz`, `/api/status`, `/api/chat`, `/api/admin/reindex` | FastAPI | `anvaya_api/main.py` |
| `anvaya_api.chat` | Request/response contract, retrieval-grounded prompt building, SSE event emission | Pydantic + async generators | `anvaya_api/chat.py` |
| `anvaya_api.abstractai` | The only door to AbstractAI: login/refresh, streaming completion, knowledge ops | httpx | `anvaya_api/abstractai.py` |
| `anvaya_api.retrieval` | Scope/profile → allowed classes → search + metadata join → numbered sources | — | `anvaya_api/retrieval.py` |
| `anvaya_api.ingest` | Home Knowledge sync from docs/hub-catalog/atlas/scheduled-tasks | httpx, pathlib | `anvaya_api/ingest.py` |
| `anvaya_api.redact` | Secret-shaped strings stripped before anything is ingested | regex | `anvaya_api/redact.py` |
| `anvaya_api.bootstrap` | Model warm-up, CostGuard/PromptVault re-seed on every start | asyncio | `anvaya_api/bootstrap.py` |

## Data flow (a chat turn)

1. Widget POSTs `{message, scope, profile, context, history}` to `/api/chat`.
2. `retrieval.retrieve()` resolves allowed classes (scope ∩ profile), searches KnowledgeBus, joins document metadata (search alone doesn't return it — HomeLab known-issues O31), builds a numbered SOURCES block.
3. `chat.build_system_prompt()` appends the sources (or a "nothing found" note) to the PromptVault-cached system prompt.
4. `abstractai.complete_stream()` streams tokens from the pinned local model (`provider="ollama"`, `task_type=""`).
5. `main.py` streams SSE events back: `status → context → status → token* → sources → done | error`.

## Key boundaries

- **Anvaya ↔ AbstractAI**: HTTP + its own service login (`SERVICE_USERS_JSON_B64`, D-15). Anvaya never bypasses this even for "just an embedding" or "just a search".
- **Anvaya ↔ Home Knowledge sources**: read-only bind mounts (`documentation/`, atlas `graph.json`) + read-only HTTP (`homelab-hub`, `service-control-api`). No source is ever written back to.
- **Anvaya ↔ plugins** (Phase 3, not built): will be its own HTTP contract, not a shared database.

## Tech choices (→ DECISIONS)

- FastAPI + httpx, no ORM (SQLite planned for conversations, Phase 1.4 — not built yet).
- No build step for the widget — matches the rest of the HomeLab static-page pattern (`live.js`).
- 100% branch coverage as a structural choice, not just a target — see `QA_ACCEPTANCE.md`.
