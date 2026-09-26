# Anvaya

**One conversation. Your whole home.** The shared "✦ Ask Home" intelligence layer for the HomeLab / Prayag Home app suite: a drawer in every page, backed by shared Home Knowledge and per-app plugins.

**Hard constraints (owner, 2026-09-26):** every model/RAG call goes through the **AbstractAI gateway**, and only **local Ollama models** are used - no cloud, ever. See `anvaya_api/abstractai.py` (`assert_local`) and the plan below.

## Status
**Phase 0 (foundations) in progress.** This repo currently contains the service skeleton only: `GET /healthz`, `GET /api/status`, the AbstractAI client (login + liveness + local-only assertion), 100 % branch-covered tests. Chat, plugins, the widget and knowledge ingestion are Phases 1-4.

## Read this first (canonical docs live in the HomeLab repo)
`documentation/anvaya/` in [USI-Projects/HomeLab](https://github.com/USI-Projects/HomeLab/tree/feature/incident-recovery-ops-b-backup/documentation/anvaya) - start with `README.md` -> `AGENT-GUIDE.md` -> `PLAN.md` (task list + status board), then `ARCHITECTURE.md`, `CONTRACTS.md` (+ JSON schemas), `LOCAL-LLM.md`, `DECISIONS.md`. (Also served at `http://192.168.0.113:8099/anvaya/`.) Those docs are the source of truth; do not copy them here.

## Run / test
```bash
pip install -r requirements.txt pytest pytest-cov
python -X utf8 -m pytest --cov --cov-branch        # 100 % branch coverage is enforced (pyproject fail_under)
ANVAYA_ABSTRACTAI_URL=http://192.168.0.113:8001 python -m uvicorn anvaya_api.main:app --port 8300
```
In the HomeLab it runs as container `anvaya-api` (no host port), reached only through the docs nginx at `/anvaya-api/` behind the login. Configuration is by environment (`.env.example`); real values are in the HomeLab `compose/.env`, never in git.

## Layout
```
anvaya_api/   config.py (env settings) - abstractai.py (gateway client: login/liveness/local-only) - main.py (FastAPI app)
tests/        pytest, httpx MockTransport fakes (no network)
```
