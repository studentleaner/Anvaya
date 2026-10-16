# Anvaya — API contract

> Summary of the HTTP surface the app exposes. The **authoritative** contract (full field semantics, JSON schemas,
> channel adapters) is HomeLab `documentation/anvaya/CONTRACTS.md` + `documentation/anvaya/schemas/` — this file
> summarises and links it, it does not replace it.

## Base path and auth

- Container listens on `:8300`. There is **no host port**: outside the HomeLab Docker networks it is reachable only
  through the docs nginx, which rewrites `/anvaya-api/<x>` → `/api/<x>` (and `/anvaya-api/status`, `/healthz`) and
  enforces the docs login. Callers pass their own identity at the nginx layer; the app itself does not authenticate
  end users in V1.
- Content type: `application/json` (JSON endpoints) or `text/event-stream` (`/api/chat`).
- The **Kids profile is refused** at this layer: `/api/chat` returns `403` before any work (decision D-11; enforced
  at the widget too).

## Versioning

- The app version is `anvaya_api.__version__` (currently `0.0.1`), surfaced in `/healthz` and `/api/status`.
- The HomeLab `schemas/` carry explicit `$id` versions (e.g. `.../anvaya/schemas/chat-request/v1`). Breaking changes
  to a request/response shape bump that schema version and are recorded as a `D-nn` in `docs/DECISIONS.md`.
- Additive fields are safe; clients must ignore unknown fields.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/healthz` | Liveness. `{"ok": true, "version": "0.0.1"}`. No auth, no model spend. |
| `GET` | `/api/status` | Readiness + detail (gateway/auth/model/bootstrap). See `docs/OPERATIONS.md`. |
| `POST` | `/api/chat` | Streaming chat (`text/event-stream`) for the HomeChat widget. |
| `POST` | `/api/ask` | One-shot JSON Q&A for channel adapters (Telegram/WhatsApp/voice) that can't consume SSE. |
| `POST` | `/api/admin/reindex` | Re-sync Home Knowledge (idempotent). Returns the reindex report. |

### `GET /healthz`

```json
{ "ok": true, "version": "0.0.1" }
```

### `GET /api/status`

```json
{
  "gateway": "up",            // "up" | "down"  (an /openapi.json probe, no model spend)
  "auth": "ok",               // "ok" | "failed" | "not_configured" | "unknown"
  "provider": "ollama",
  "model": { "name": "llama3.1:8b", "state": "warm", "detail": "" },  // state: unknown|warming|warm|error
  "bootstrap": { "budget": true, "prompts": true },
  "plugins": [],
  "mode": "knowledge",
  "last_reindex": { "scanned": 696, "ingested": 14, "unchanged": 682, "deleted": 0, "failed": 0, "at": 0.0 },
  "local_only": true,
  "project_id": "anvaya",
  "version": "0.0.1"
}
```

### `POST /api/chat` (SSE)

Request body = `schemas/chat-request.schema.json`:

```json
{
  "message": "why is the solar battery low?",
  "scope": "my_home",                 // this_app | current_page | my_home | all_apps
  "profile": "family",                // family | kids | system   (kids → 403)
  "conversation_id": "conv_01J...",   // optional; ULID, validated if present
  "context": { "app": "", "page": "", "entity_type": "", "entity_id": "" },
  "client": {},
  "history": [ { "role": "user", "text": "…" } ]   // max 6 items, each ≤2000 chars
}
```

Response: `text/event-stream` (`Cache-Control: no-cache`, `X-Accel-Buffering: no`), events in order:
`status`→`context`→`status`→(`token`×N)→`sources`→`done`, or `error` instead of the token/sources/done tail
(= `schemas/chat-event.schema.json`):

```
event: status
data: {"stage":"routing","model_state":"unknown"}      // model_state: warm|loading|unknown

event: context
data: {"scope":"my_home","plugins":[],"redacted":0,"mode":"knowledge"}

event: status
data: {"stage":"generating","model_state":"unknown"}   // stage: generating | model_loading

event: token
data: {"t":"the "}                                      // many; word-level reveal of the validated answer

event: sources
data: {"items":[{"n":1,"source":"…","title":"…"}]}      // [src_n] the answer may cite

event: done
data: {"conversation_id":"conv_…","message_id":"msg_…","elapsed_ms":1234,
       "model":"ollama/llama3.1:8b","local":true,"cited":true}
```

On failure the stream ends with:

```
event: error
data: {"code":"gateway_down","message":"…","fallback":"lookup_only"}
```

**Note:** the answer is fully generated and citation-checked *before* the `token` stream is emitted, so the reveal
is a choreographed word-split of the final text, not live model tokens (see `anvaya_api/answer.py` for why —
citation enforcement is chosen over live streaming).

### `POST /api/ask` (JSON)

Request body: `message` (1–4000), `scope` (same enum, default `my_home`), `profile` (`family` | `system` — **`kids`
is not in the schema**; channel adapters are owner-only by construction).

```json
{
  "answer": "…[src_1]…",
  "sources": [ { "n": 1, "source": "…", "title": "…" } ],
  "model": "ollama/llama3.1:8b",
  "local": true,
  "cited": true
}
```

### `POST /api/admin/reindex`

No request body. Response = the reindex report:

```json
{ "scanned": 696, "ingested": 14, "unchanged": 682, "deleted": 0, "failed": 0, "at": 1750000000.0 }
```

## Error model

| Condition | Surface | Code / status |
|---|---|---|
| Kids profile | `/api/chat` | HTTP `403`, detail `Ask Home is not available on the Kids profile` |
| Gateway unreachable / login failed / 401 | `/api/chat` SSE `error`; `/api/ask` HTTP | code `gateway_down`; `/api/ask` → `502` with detail |
| Model returned no output in time | same | code `model_timeout` |
| Gateway rejected the request (400) | same | code `bad_request` |
| Answer had sources but cited none (after one retry) | returned answer | `cited: false`, text = `fallback_answer(result)` (not an HTTP error) |
| Validation (bad `scope`/`profile`, long message, bad ULID) | FastAPI | HTTP `422` |

`/api/ask` maps any model/gateway error to HTTP `502` with the error's message (or code) as `detail`.

## Related contracts

- Authority: HomeLab `documentation/anvaya/CONTRACTS.md`.
- Schemas: `documentation/anvaya/schemas/{chat-request,chat-event,plugin-manifest,action-proposal}.schema.json`.
- Channel adapters (how Telegram/WhatsApp/voice call `/api/ask`): HomeLab `documentation/anvaya/CHANNELS.md`.
- Acceptance tests: `docs/QA_ACCEPTANCE.md`.
