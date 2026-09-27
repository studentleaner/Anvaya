# Anvaya — Project Intelligence for Claude

Ask Home: one connected intelligence layer across every Home app - a drawer, mounted in place on the app's own pages, backed by shared Home Knowledge and per-app plugins, answering only through AbstractAI's local models.

This is the entry point for all AI-assisted work in this repo. `AGENTS.md` carries the same rules for other agents - **edit both in the same commit**; the `## Rules` sections must stay byte-identical (`Test-ProjectBaseline.ps1` checks).

## Reading order (cold start)

1. `README.md` - what it is, how to build/test/run.
2. `docs/VISION_AND_SCOPE.md` - why, for whom, and what it is **not**.
3. `docs/DELIVERY_BACKLOG.md` - what is done (with evidence), what is next, what is blocked.
4. `docs/ROADMAP.md` - the milestones and their exit criteria.
5. `docs/DECISIONS.md` + `docs/OPEN_QUESTIONS.md` - settled vs undecided.
6. `docs/ARCHITECTURE.md`, `docs/SECURITY.md`, `docs/QA_ACCEPTANCE.md` - before touching code.
7. The full spec pack lives in the HomeLab repo, `documentation/anvaya/` (`AGENT-GUIDE.md`, `PLAN.md`, `ARCHITECTURE.md`, `CONTRACTS.md` + `schemas/`, `LOCAL-LLM.md`, `DECISIONS.md`) - the docs in *this* repo summarise and link it, they don't repeat it.

## Rules

1. **All model calls go through AbstractAI** (`/v1/complete`, prompts from `/v1/prompts`) - never a provider SDK directly.
2. **Import the kit, never copy** - shared code comes from a versioned package/feed.
3. **Creds from Vaultwarden** - no secrets in the repo or in docs (env var *names* only).
4. **Idempotent + config-driven** - no manual steps; re-running is safe.
5. **Verify-then-commit** - build/test green -> commit on a branch -> push.
6. **Docker/data on D:, never C:.**
7. **Status lives in `docs/DELIVERY_BACKLOG.md` only** - update it in the same commit as the work; ✅ needs evidence (command, test name, commit, or dated live check).
8. **Decisions are recorded, not remembered** - a new or reversed decision gets a `D-nn` entry in `docs/DECISIONS.md` in the same commit.
9. **Never edit `docs/SPEC.md` in place** - it is the owner's source text; supersede it through `DECISIONS.md`.

### Anvaya-specific (on top of the 9 above)

10. **Local models only, no cloud, ever** - every completion call is pinned `provider="ollama"` and `task_type=""` (a known-task_type would let AbstractAI's router silently swap in a cloud model - see HomeLab known-issues O27). `assert_local()` in `anvaya_api/abstractai.py` is the enforcement point.
11. **Nothing executes because a model said so** - actions are `proposed`, never run, until a human clicks confirm (Phase 3, not built yet).
12. **Finance is read-only** - Anvaya never writes to the financial ledger.
13. **The Kids profile never gets Ask Home** - refused at both the widget (never mounts) and the API (`403`).
14. **100% branch coverage** on every `anvaya_api` module before it merges (`python -X utf8 -m pytest --cov --cov-branch`).

## Project specifics

- Slug: `anvaya` · Stack: Python 3.12 / FastAPI / httpx, vanilla-JS widget (`documentation/js/homechat.js` in HomeLab) · Owner: Pradeep
- Deployed as container `anvaya-api` in the HomeLab compose stack (`compose/infrastructure/compose.yml`), behind the HomeLab docs login, no host port.
- No Kanboard/Wiki.js SDLC provisioning yet - tracked directly in this repo's `docs/DELIVERY_BACKLOG.md`.

## Verify

```text
build:  pip install -r requirements.txt
test:   python -X utf8 -m pytest --cov --cov-branch   # must stay at 100%
run:    ANVAYA_ABSTRACTAI_URL=http://192.168.0.113:8001 python -m uvicorn anvaya_api.main:app --port 8300
live:   curl -u serviceaccount:*** http://192.168.0.113:8099/anvaya-api/status
```
