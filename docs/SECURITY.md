# Anvaya — Security

## Assets

- **Home Knowledge** (documentation, hub catalog, atlas, scheduled tasks) — not secret by design, but should not be exfiltrated wholesale to a third party.
- **The AbstractAI service credential** (`ANVAYA_ABSTRACTAI_USER`/`PASSWORD`) — lives only in gitignored `.env` files (HomeLab `compose/.env` plaintext password; AbstractAI `V4/.env` bcrypt hash), never in this repo, never printed to chat/logs.
- **Household availability** — a bug here should not make other HomeLab pages unusable (the widget degrades to "sign in" or "AI unreachable", never a page crash).

## Trust boundaries

- **The docs nginx login** is the only auth boundary between a LAN client and `anvaya-api` — every mount point (`/anvaya-api/`) is behind it. Anvaya does not implement its own user auth.
- **Retrieved document text** is untrusted input to the model (a document could contain injected instructions). It is wrapped as data in the prompt ("Below are numbered SOURCES..."), and AbstractAI's own guardrail chain runs on the completion call.
- **The AbstractAI gateway's response** is not fully trusted either: `assert_local()` rejects any answer whose `provider` is not `ollama`, closing the one path a compromised or misconfigured gateway could use to route to a cloud model.

## Threats and controls

| Threat | Impact | Control | Verified by |
|---|---|---|---|
| A secret string (password/API key/token) ends up in the knowledge base | Leaked to any Ask Home user who asks the right question | `redact.py` regex-strips secret-shaped strings before ingest; hard path deny-list (`creds.html`, `.env*`, `htpasswd`, `secrets.yaml`, `.storage/**`) skips those files entirely | `tests/test_redact.py` (5 tests), `tests/test_ingest.py::test_scan_docs_reads_md_and_html_skips_denied_and_binary` |
| A cloud model call happens (cost, privacy, or policy violation) | Data leaves the house | `assert_local()` raises on any non-`ollama` provider; `task_type=""` on every call (a set task_type lets AbstractAI's router override the pin — HomeLab known-issues O27); a `$0.0001` hard-reject CostGuard budget for project `anvaya` as defence in depth | `tests/test_abstractai.py::test_assert_local`, `tests/test_bootstrap.py::test_bootstrap_seeds_budget_prompts_and_warms` |
| Kids reach Ask Home | Age-inappropriate answers/actions | Widget never mounts (`profile: "kids"` returns before touching the DOM); API returns `403` | `tests/homechat.test.js`, `tests/test_main.py::test_chat_kids_profile_is_forbidden` |
| Prompt injection via a retrieved document | The model executes an "instruction" hidden in a source | Sources are framed as data in the prompt, not instructions; no action can be taken from model output without a human confirm click (Phase 3 design, not yet exercised at scale) | Manual review; formal injection test set is HomeLab PLAN M4-S2 (not built) |
| An uncited, invented answer about the home | User trusts a wrong fact | Prompt instructs citation; `has_valid_citation()` checks it — **currently telemetry only** (logs a warning), not a hard block (see `OPEN_QUESTIONS.md` Q-01) | `tests/test_retrieval.py::test_has_valid_citation` |

## Secrets handling

Env var **names** only, ever, in this repo or its docs: `ANVAYA_ABSTRACTAI_URL`, `ANVAYA_ABSTRACTAI_USER`, `ANVAYA_ABSTRACTAI_PASSWORD`, `ANVAYA_PROJECT_ID`, `ANVAYA_PRIMARY_MODEL`, `ANVAYA_DATA_DIR`. Real values live in HomeLab's gitignored `compose/.env` and AbstractAI's gitignored `V4/.env` — never here.
