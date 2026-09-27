# Anvaya — Delivery Backlog (M0–M6)

> Single source of truth for scope, status and evidence. Update this file in the same commit as the work it describes — a task is not "Done" until this file says so with a link/command that proves it.
> Milestones map onto `../../HomeLab/documentation/anvaya/PLAN.md`'s Phases 0–5 (M0=Phase 0, M1=Phase 1, M2=Phase 2, M3=Phase 3, M4=Phase 4, M5=Phase 5/V2, **M6=Rollout & Operate** — not in PLAN.md, added here because "mount it everywhere and keep it healthy" is its own body of work distinct from building the feature).
> Conventions: **Epic** = milestone-sized outcome · **Story** = a user-visible slice · **Task** = an implementation unit · **Bug** = a defect found after its story shipped · **Issue** = a risk/question/decision, not a defect · **External gate** = something only the owner (or a service outside this repo) can unblock.

Status legend: ✅ Done · 🔄 In progress · ⬜ Not started · ⛔ Blocked · 🟡 Deferred (not blocking)

---

## M0 — Foundations (= PLAN Phase 0) — ✅ **DONE 2026-09-27**

**Epic M0: the platform Anvaya stands on is real** — a local model that loads reliably, a login of its own, and knowledge that survives a restart.

| ID | Type | Title | Status | Depends on | Evidence |
|---|---|---|---|---|---|
| M0-S1 | Story | Local model never fails to answer, cold or warm | ✅ | — | `abstractai/infra/docker-compose.yml` (named volume `abstractai_ollama_models`, `OLLAMA_LOAD_TIMEOUT=10m`); `scripts/bench_local_llm.py` in HomeLab; measured cold 91–160 s (was 284 s / HTTP 500), warm 13–23 tok/s |
| M0-S1-T1 | Task | Move Ollama's model store off the Windows bind mount to a Docker named volume | ✅ | — | `HomeLab/scripts/automation/copy-ollama-models.sh`; volume `abstractai_ollama_models` created, `llama3.2`/`qwen2.5:7b`/`llama3.1:8b` copied (11 GB) |
| M0-S1-T2 | Task | Warm the primary model in the background at API start | ✅ | T1 | `anvaya_api/bootstrap.py::warm_model` (retry ladder 5/20/60/120 s); `/api/status.model.state` — `tests/test_bootstrap.py` |
| M0-B1 | Bug | Cold `llama3.1:8b` load failed with HTTP 500 after 5 min | ✅ Fixed | T1 | root cause: Ollama's own `OLLAMA_LOAD_TIMEOUT` (5 min default); fixed by raising it to 10 m — known-issues **O23** |
| M0-B2 | Bug | A native Windows `ollama.exe` grabs host port 11434 the moment the container releases it | ✅ Worked around | T1 | container no longer publishes 11434; containers use `ollama:11434` on `abstractai-shared` — known-issues **O28** (root cause, the native process, is untouched — External gate) |
| M0-S2 | Story | Anvaya authenticates to AbstractAI as itself, not as admin | ✅ | — | `SERVICE_USERS_JSON_B64` in `AbstractAI/V4/utils/auth.py`; `/api/status.auth == "ok"` |
| M0-S2-T1 | Task | Add per-consumer service logins to AbstractAI's auth module | ✅ | — | AbstractAI commit `7d43175` (`utils/auth.py::_resolve_service_users`), 7 new tests, `utils.auth` 100 % branch |
| M0-S2-T2 | Task | Generate the `anvaya` credential without ever printing it | ✅ | T1 | `compose/.env` (plaintext, gitignored) + AbstractAI `.env` (bcrypt hash, gitignored); generated via a one-shot script, never echoed to chat |
| M0-S2-T3 | Task | Re-seed a hard-reject CostGuard budget for project `anvaya` on every start | ✅ | S2-T1 | `anvaya_api/bootstrap.py::bootstrap` → `PUT /admin/costs/anvaya`; CostGuard is in-memory (no persistence), hence re-seeding — `tests/test_bootstrap.py::test_bootstrap_seeds_budget_prompts_and_warms` |
| M0-S2-T4 | Task | Register/refresh the `anvaya.answer` PromptVault prompt on every start | ✅ | S2-T1 | `AbstractAIClient.ensure_prompt`; PromptVault library moved to a host mount (`AbstractAI/prompts/`) so it survives a gateway recreate |
| M0-S3 | Story | Ingested knowledge survives a gateway restart | ✅ | S2 (Postgres) | `KnowledgeBus` + `PgVectorStore.save_document/load_documents/delete_document`; **verified live**: ingest → restart gateway → search still finds it → delete → gone |
| M0-S3-T1 | Task | Add a persistent document registry to `PgVectorStore` (chunks already persisted; the registry did not) | ✅ | — | AbstractAI `knowledge_bus.py`; `knowledge_documents` table auto-created; 3 new tests (`TestPersistentRegistry`), `knowledge_bus.py` 100 % branch |
| M0-S3-T2 | Task | Wire `KnowledgeBus` selection from env (`KNOWLEDGE_STORE=pgvector` + `POSTGRES_URL`) | ✅ | T1 | `get_knowledge_bus()` in AbstractAI; set on the gateway container |
| M0-B3 | Bug | Compose project-name collision replaced AbstractAI's pgvector Postgres with MobileOTT's dev DB | ✅ Fixed | — | root cause: both `AbstractAI/V4/infra/` and `MobileOTT/infra/` compose files derive project name `infra` from the folder and both declare a `postgres` service; MobileOTT's `docker compose up` silently recreated AbstractAI's container. Fixed: `name: mobileott` in MobileOTT's compose (commit `b1e3c11`), both DBs bound to `127.0.0.1` only, AbstractAI's own container restored with `llm_calls`/`project_budgets` intact — known-issues **O24** |
| M0-B4 | Bug | A live DeepSeek API key was committed as a compose default | ✅ Partly fixed | — | default removed from `AbstractAI/V4/infra/docker-compose.yml` (commit `7d43175`) — known-issues **O25**. **External gate EG-1**: the key is still in git history; only the owner can rotate it at DeepSeek |
| M0-B5 | Bug | `ModelBus._resolve()` lets a known `task_type` override an explicit pinned provider/model | ✅ Worked around | — | `planning` routes to `BUS_PLANNING_MODEL` (`llama3:8b`, not installed → 404 → HTTP 502); `complex`/`frontier` route to Anthropic (cloud) — violates D-04. Fixed in Anvaya: every gateway call sends `task_type: ""` (`abstractai.py`, asserted by `test_stream_tokens_then_done_and_request_body_is_pinned_local`). Known-issues **O27** — **not** fixed in AbstractAI itself (would change CompanionWriter/LearningLens routing; **Issue I-1**, owner decision) |
| M0-I1 | Issue | Model bake-off (PLAN 0.2: `llama3.2` vs `qwen2.5:7b` vs `llama3.1:8b` vs `phi4`) | 🟡 Deferred | — | Not blocking: `llama3.1:8b` chosen provisionally (D-03) because it's AbstractAI's own default and avoids a second model competing for the 6 GB GPU. Revisit once golden-question data exists (M4). |

**M0 exit evidence:** `curl -u serviceaccount:*** http://192.168.0.113:8099/anvaya-api/status` → `{"gateway":"up","auth":"ok","model":{"state":"warm"},"bootstrap":{"budget":true,"prompts":true},"local_only":true}`; a live chat answered in 9 s once warm.

---

## M1 — Chat core (= PLAN Phase 1) — 🔄 In progress (first slice done)

**Epic M1: `/api/chat` answers correctly, safely, and says when it can't.**

| ID | Type | Title | Status | Depends on | Evidence |
|---|---|---|---|---|---|
| M1-S1 | Story | A question gets a streamed answer from the local model, in the right shape | ✅ | M0 | `POST /api/chat` SSE: `status → context → status → token* → sources → done`, per `documentation/anvaya/CONTRACTS.md` §1.1; `tests/test_main.py` (`test_chat_streams_contract_events_in_order`, 12 chat tests) |
| M1-S1-T1 | Task | `ChatRequest`/event schemas + SSE emitter | ✅ | — | `anvaya_api/chat.py` |
| M1-S1-T2 | Task | Streaming AbstractAI client (`/v1/complete/stream` parser) | ✅ | M0-S2 | `anvaya_api/abstractai.py::complete_stream` |
| M1-S1-T3 | Task | Kids profile refused; local-only enforced | ✅ | — | `main.py` 403 for `profile:"kids"`; `assert_local` raises on any non-ollama provider |
| M1-S1-T4 | Task | Model-state reporting (unknown/loading/warm) in `status` events | ✅ | M0-S1-T2 | `chat.py::wire_state`; `tests/test_main.py::test_chat_announces_model_loading_while_warming` |
| M1-S1-T5 | Task | System prompt served from PromptVault with a code fallback | ✅ | M0-S2-T4 | `anvaya_api/bootstrap.py::PromptCache`; `test_chat_uses_prompt_from_vault` |
| M1-S2 | Story | Retrieval: the answer is grounded in Home Knowledge, not just the model's own head | ✅ **DONE 2026-09-27 (pulled forward with M4-S1)** | M0-S3 | `anvaya_api/retrieval.py`; verified LIVE: "What port does Jenkins run on?" -> cited `[src_3]` -> correct answer, sources returned with plugin/title/uri |
| M1-S2-T1 | Task | Scope resolver: `scope` + `profile` → allowed classes (`allowed_classes()`) | ✅ | — | `retrieval.py::allowed_classes`; kids never reaches this (refused earlier) |
| M1-S2-T2 | Task | Call `GET /v1/knowledge/search` (hybrid) + join `GET /v1/knowledge/documents` for metadata (search alone doesn't return it - known-issues **O31**); build the numbered SOURCES block | ✅ | T1 | `retrieval.py::retrieve` |
| M1-S2-T3 | Task | Citation-required prompting; strip/replace an answer whose `[src_n]` don't exist | ✅ **DONE 2026-09-27** — hard enforcement (Q-01 resolved, HomeLab DECISIONS.md D-17): full answer buffered, checked, one retry with a stronger prompt, deterministic `fallback_answer()` if still uncited; unconditionally accepted when no sources were retrieved | T2 | `anvaya_api/answer.py::generate_from_result`; 100% branch coverage `tests/test_answer.py` |
| M1-S3 | Story | Redaction: secrets and out-of-class data never reach the model | ✅ **DONE 2026-09-27** | M1-S2 | `anvaya_api/redact.py` - regex secret patterns + the project's standard password; runs on every ingested doc |
| M1-S3-T1 | Task | Hard path deny-list (`creds.html`, `.env*`, `htpasswd`, `secrets.yaml`, `.storage/**`) enforced at ingest | ✅ | M4-S1 | `ingest_config.py::DENY_SUBSTRINGS` + `is_denied()`; tested (`test_scan_docs_reads_md_and_html_skips_denied_and_binary`) |
| M1-S3-T2 | Task | Regex redaction of secret-shaped strings before ingest | ✅ | M1-S2-T2 | `redact.py`; 5 tests |
| M1-S4 | Story | Conversations persist across requests | ⬜ | — | Currently: client-supplied `history` (≤ 6 turns), no server-side store — `CONTRACTS.md` §1.1 `history` field |
| M1-S4-T1 | Task | SQLite `conversations`/`messages` tables in `anvaya_api` | ⬜ | — | — |
| M1-S4-T2 | Task | `GET/DELETE /api/conversations[...]` | ⬜ | T1 | — |
| M1-S5 | Story | Guardrails run on every Anvaya prompt | 🔄 | — | AbstractAI's guardrail chain already runs on `/v1/complete*` for every project (verified by AbstractAI's own tests); Anvaya-side untrusted-text wrapper for retrieved content not yet written (depends on M1-S2) |
| M1-I1 | Issue | `max_latency_ms` / session affinity tuning for Anvaya's traffic pattern | ⬜ | — | Not started; low priority until real usage exists |

---

## M2 — HomeChat widget (= PLAN Phase 2) — 🔄 In progress (pulled forward)

**Epic M2: Ask Home is usable, in place, on every page it's asked for — never a separate page, never on Kids.**

| ID | Type | Title | Status | Depends on | Evidence |
|---|---|---|---|---|---|
| M2-S1 | Story | Desktop drawer + mobile bottom sheet, one shared component | ✅ | M1-S1 | `HomeLab/documentation/js/homechat.js`; CSS breakpoint < 768 px → bottom sheet; `tests/homechat.test.js` (Node unit test: SSE parser, kids-never-mounts) |
| M2-S1-T1 | Task | `HomeChat.mount({app,page,profile,entity_type,entity_id})` — zero-build, one `<script>` line | ✅ | — | `homechat.js` |
| M2-S1-T2 | Task | Scope picker (This App / Current Page / My Home / All Apps) | ✅ | — | `homechat.js` `SCOPES` |
| M2-S1-T3 | Task | `● Local AI` status chip with tooltip (mode/model/privacy) | ✅ | M0-S1-T2 | `refreshStatus()` in `homechat.js` |
| M2-S1-T4 | Task | Streaming render via `fetch` + `ReadableStream` (not `EventSource`, which can't POST) | ✅ | M1-S1 | `homechat.js::sendMessage` |
| M2-S1-T5 | Task | **In-drawer sign-in** — a 401 shows a small form inside the drawer (same `hl_auth` cookie as `login.html`), never a page navigation; the pending question is re-sent after sign-in | ✅ | — | `homechat.js::showLogin`; verified live in-browser (screenshot: sign-in form renders inside the open drawer, URL unchanged) |
| M2-S1-T6 | Task | JS syntax regression guard | ✅ | — | `tests/Test-Launchers.ps1` syntax-checks every inline `<script>` on dashboard + documentation pages (added after an apostrophe bug once broke `vpn.html` silently) |
| M2-S2 | Story | Mounted everywhere it should be, nowhere it shouldn't | ✅ **8/9 pages done 2026-09-27** | S1 | `portal.html`, `home.html`, `alerts.html`, `index.html`, `arrivals.html`, `solar.html`, `news.html`, `containers.html`, Finance OS SPA |
| M2-S2-T1 | Task | Mount on `portal.html` (Family + System profiles via `MODE`, never Kids) | ✅ | — | `documentation/portal.html` |
| M2-S2-T2 | Task | Mount on `home.html` (profile `family`) | ✅ | — | `documentation/home.html` |
| M2-S2-T3 | Task | Mount on `alerts.html` (profile `family`) | ✅ | — | `documentation/alerts.html` |
| M2-S2-T4 | Task | Mount on `index.html` (profile `system`, behind the docs login) | ✅ | — | `documentation/index.html` |
| M2-S2-T5 | Task | Mount on `arrivals.html`/`solar.html`/`news.html` (family) + `containers.html` (system) | ✅ **DONE 2026-09-27** | — | 4 launcher tests, live syntax scan |
| M2-S2-T6 | Task | Mount on the Finance OS SPA (separate repo) | ✅ **DONE 2026-09-27** | cross-repo | `Apps/Finance OS/web/index.html` - absolute `/js/homechat.js` path (page is served under `/finance/`, script lives on homelab-docs root) |
| M2-S2-T7 | Task | `tv.html` | ⛔ **Deliberately deferred** | — | LG webOS has severe memory constraints (`tv-launcher-dev.md`: canvas GPU memory, `navigateClean()` rules) - a blind widget mount risks the exact OOM class of bug that page already works around. Needs its own design pass (e.g. remote-control-only, no drawer), not a copy-paste of the desktop widget |
| M2-S3 | Story | Sources are visible and clickable | 🔄 | M1-S2 (done) | Backend emits real `sources` events now (verified live); the widget's UI chips to render them are not built yet - `homechat.js` currently ignores the `sources` event payload |
| M2-S4 | Story | Action buttons (propose → preview → confirm) | ⬜ | M3 | — |
| M2-B1 | Bug | An apostrophe inside a single-quoted JS string once left `vpn.html` on "Loading…" forever while every API test passed | ✅ Fixed (prior incident, guard added) | — | Root-caused the class of bug; `homechat.js` was written and syntax-checked against exactly this regression (M2-S1-T6) before first mount |

---

## M3 — Plugins + actions (= PLAN Phase 3) — ⬜ Not started

**Epic M3: Ask Home can read real Home data through per-app plugins, and propose (never silently execute) safe actions.**

| ID | Type | Title | Status | Depends on | Evidence |
|---|---|---|---|---|---|
| M3-S1 | Story | Plugin registry validates and health-checks manifests | ⬜ | M1-S2 | Contract defined: `documentation/anvaya/CONTRACTS.md` §3 + `schemas/plugin-manifest.schema.json` |
| M3-S1-T1 | Task | Load `config/anvaya/plugins.yaml`, validate against the schema | ⬜ | — | — |
| M3-S1-T2 | Task | Per-plugin 3 s timeout + circuit breaker | ⬜ | T1 | — |
| M3-S2 | Story | First-party read plugins: `homelab.docs`, `homelab.hub`, `homelab.ha`, `financeos` | ⬜ | S1 | — |
| M3-S2-T1 | Task | `homelab.ha` — allowlisted entity domains (sensor/climate/media_player/vacuum/binary_sensor) | ⬜ | — | — |
| M3-S2-T2 | Task | `financeos` — read-only (ledger never writable from Anvaya, per Finance OS's own rule "AI never becomes the accounting system") | ⬜ | — | — |
| M3-S3 | Story | Action engine: propose → confirm → execute → audit, with idempotency | ⬜ | S2 | Contract defined: `CONTRACTS.md` §2 + `schemas/action-proposal.schema.json` |
| M3-S3-T1 | Task | `json_mode` structured proposal, validated against the plugin's `params_schema` before it's ever shown | ⬜ | — | — |
| M3-S3-T2 | Task | `POST /api/actions/{id}/confirm` — single-use, expiring, append-only audit log | ⬜ | T1 | — |
| M3-S4 | Story | Two safe-write actions ship: `create_reminder`, `announce` | ⬜ | S3 | `homelab.reminders` (bp-proxy), `script.announce` already exist as HomeLab APIs — just need the plugin wrapper |
| M3-I1 | Issue | Sensitive-tier actions (payments, locks, deletes) | ⬜ (out of scope for V1) | — | Deliberately deferred past V1 per D-10; needs owner sign-off before any code is written |

---

## M4 — Home Knowledge + quality (= PLAN Phase 4) — ⬜ Not started

**Epic M4: Home Knowledge is actually populated, and Anvaya's answers are measured, not just believed.**

| ID | Type | Title | Status | Depends on | Evidence |
|---|---|---|---|---|---|
| M4-S1 | Story | Documentation and plugin data get ingested automatically | ✅ **DONE 2026-09-27, pulled forward** (scope: catalogued sources, not a raw drive scan - see ARCHITECTURE.md) | M0-S3 | `anvaya_api/ingest.py`; live run: 696 documents (419 atlas + 157 hub + 92 docs + 28 tasks), idempotent (stable ids + content-hash diff), 26 tests / 100% branch |
| M4-S1-T1 | Task | Ingest pipeline: docs (redacted/deny-listed) + hub catalog + atlas + scheduled tasks; content-hash skip, orphan delete | ✅ | — | `ingest.py::reindex` |
| M4-S1-T2 | Task | Scheduled reindex — **hidden, user-level task, every 6h, catch-up ON** (Q-03 resolved, HomeLab DECISIONS.md D-18: this call is a pure idempotent HTTP request with no service disruption, unlike the disruptive tasks O20 was about, so catch-up is safe here) | ✅ **DONE 2026-09-27** | T1 | HomeLab `scripts/scheduler/Register-AnvayaReindexTask.ps1` + `wrappers/Invoke-AnvayaReindex.ps1`; task `HomeLab-AnvayaReindex` registered + verified live (696 scanned, 14 ingested, 0 failed) |
| M4-S1-T3 | Task | Channel-agnostic answer endpoint (`POST /api/ask`) for adapters that can't consume SSE (Telegram/WhatsApp/voice) | ✅ **DONE 2026-09-27** | M1-S2 | `anvaya_api/main.py::ask`; same citation enforcement as `/api/chat` via `answer.generate_grounded_answer` |
| M4-S1-T4 | Task | Telegram wired to Ask Home via `/api/ask` | ✅ **DONE 2026-09-27** | M4-S1-T3 | Aegis `runtime/iron-dome/telegram_gateway.py::_cmd_ask` — direct call over the shared `abstractai-shared` Docker network; verified live |
| M4-S1-T5 | Task | WhatsApp wired to Ask Home | ⬜ **Not started** | M4-S1-T3 | Aegis's `whatsapp_gateway.py` is outbound-only (Twilio) with no Twilio credentials configured and no inbound listener; needs a Twilio account + inbound webhook receiver before a two-way `/ask` is possible |
| M4-S1-T6 | Task | Voice: Echo "announce" via Ask Home | ✅ Trivial, already possible | M4-S1-T3 | Existing `script.announce` funnel can call `/api/ask` and speak the answer; no new work needed |
| M4-S1-T7 | Task | Voice: Echo "hear" a spoken question | ⬜ **Not started, materially bigger** | M4-S1-T3 | Needs a custom Alexa skill (intent model + account linking), not just an HA automation; scoped but not built |
| M4-S2 | Story | A golden question set exists and Anvaya is graded against it | ⬜ | M1-S2 | — |
| M4-S2-T1 | Task | ≥ 50 questions in `tests/golden/questions.yaml`, sourced from real docs + synthetic finance data only | ⬜ | — | — |
| M4-S2-T2 | Task | Eval gate via AbstractAI's EvaluationBus (local judge): citation validity ≥ 95 %, no-answer-when-absent ≥ 90 %, injection resistance 100 % | ⬜ | T1 | — |
| M4-S3 | Story | 👍/👎 feedback becomes a triage queue | ⬜ | M1-S4 | — |
| M4-I1 | Issue | Multilingual (Malayalam) retrieval quality | ⬜ | — | Decision D-06: default English-first for V1; revisit here with real recall numbers |
| M4-EG1 | External gate | Family profile access to Ask Home | ⛔ Gated | M4-S2-T2 | Default per D-13/DECISIONS: **System only until the eval gate passes**, then Family. Owner can override this gate at any time. |

---

## M5 — V2 (= PLAN Phase 5) — ⬜ Not started (by design — no work begins here before V1 has run for two weeks)

**Epic M5: cross-app actions, voice, memory, proactive suggestions.**

| ID | Type | Title | Status | Depends on | Evidence |
|---|---|---|---|---|---|
| M5-S1 | Story | Cross-app multi-step action proposals | ⬜ | M3 stable in production | — |
| M5-S2 | Story | Voice in/out via existing Wyoming Whisper/Piper | ⬜ | — | Whisper/Piper already run in HomeLab; integration not started |
| M5-S3 | Story | Explicit "remember this" long-term memory | ⬜ | M1-S4 | — |
| M5-S4 | Story | Knowledge graph (entity relationships, e.g. `Car → insurance, service, EMI`) | ⬜ | M4 | — |
| M5-S5 | Story | Proactive suggestions via `script.announce` (category `system`) | ⬜ | M3 | — |
| M5-S6 | Story | SutraMesh-routed model selection | ⬜ | SutraMesh exists (currently spec-only, no code) | External dependency on another unbuilt project |
| M5-S7 | Story | TV surface | ⬜ | — | Explicitly out of scope until V1 is proven; LG webOS constraints documented in HomeLab `tv-launcher-dev.md` |

---

## M6 — Rollout & Operate (not a PLAN phase — cross-cutting) — 🔄 In progress

**Epic M6: Anvaya stays healthy, documented, and doesn't quietly break something else.**

| ID | Type | Title | Status | Depends on | Evidence |
|---|---|---|---|---|---|
| M6-S1 | Story | Every change is tested, documented and pushed in the same session | ✅ ongoing | — | This file + `documentation/anvaya/*` in HomeLab kept in lock-step with every commit; HomeLab `Test-Launchers.ps1` carries Anvaya-specific checks (served docs, schema validity, 401/200, live status) |
| M6-S2 | Story | HomeLab's own test suite stays green alongside Anvaya's rollout | 🔄 | — | 278 checks, 2 pre-existing failures **unrelated to Anvaya** (OnlyOffice `/example/` 500s — O29; 4 untracked container ports — O30). Not caused by this work; flagged for the owner, not silently ignored. |
| M6-S3 | Story | Atlas and the requirements tracker reflect reality | ✅ ongoing | — | `EcosystemAnalysis/atlas/graph.json` entity `personal-suite.anvaya`; HomeLab `requirements-tracker.md` R17.1–R17.9 |
| M6-I1 | Issue | Two near-duplicate project docs (`CLAUDE.md` / `AGENTS.md` in HomeLab) must be edited together | 🔄 ongoing | — | Known drift risk, called out in HomeLab tracker R16.7; both edited in every round so far |
| M6-EG1 | External gate | Rotate the DeepSeek API key | ⛔ | — | Key default removed from code (M0-B4) but the value is in AbstractAI's git history. **Only the owner can rotate it at the DeepSeek dashboard.** |
| M6-EG2 | External gate | Confirm/clean up 4 untracked container ports (`ngx-test`, `vaultwarden`, `acid2-acid2_run1`, `capstone-url-shortener`) | ⛔ | — | Not Anvaya's — found while running the HomeLab suite. known-issues **O30**. Needs the owner to say whether they're intentional. |
| M6-EG3 | External gate | OnlyOffice `/example/` returning 500 | ⛔ | — | Pre-existing, unrelated to this work (`docker logs onlyoffice`: `meta/config timed out`). known-issues **O29**. Owner action: `docker restart onlyoffice` (untested here). |
| M6-EG4 | External gate | Fix `ModelBus._resolve()`'s `task_type` override in AbstractAI itself (vs. Anvaya's `task_type:""` workaround) | ⛔ | — | Would change routing behaviour for CompanionWriter/LearningLens too — needs the AbstractAI owner's sign-off, not just Anvaya's. known-issues **O27**. |
| M6-EG5 | External gate | Disable or reconcile the native Windows `ollama.exe` competing for host port 11434 / GPU | ⛔ | — | known-issues **O28**; root cause (a Startup shortcut) untouched by this work. |

---

## Cross-cutting non-negotiables (apply to every milestone)

1. **AbstractAI only, local models only.** No milestone ever adds a call that bypasses the gateway or reaches a cloud provider. Enforced by `assert_local` + `task_type:""` + the CostGuard tripwire (M0-S2-T3).
2. **Nothing executes because a model said so.** Every action is `proposed` until a human clicks confirm (M3-S3).
3. **Finance is read-only.** No milestone gives Anvaya a finance write path.
4. **Kids profile never gets Ask Home.** Enforced at the widget (never mounts) and the API (403) — tested at both layers.
5. **100% branch coverage** on every new `anvaya_api` module, before it merges.
6. **This file is updated in the same commit** as any status change it describes.

## How to read "Done" here

A row is ✅ only if there is a command, a test name, or a live-verification note in its Evidence column that someone else could re-run and get the same result. A row without evidence is 🔄 or ⬜ regardless of how it feels.
