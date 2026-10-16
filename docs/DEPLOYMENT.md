# Anvaya — Deployment

> How Anvaya is built, configured, deployed and rolled back. Env var **names** only — no secret values (rule 3).
> The full product/ops context is in HomeLab `documentation/anvaya/` (`PLAN.md`, `ARCHITECTURE.md`, `LOCAL-LLM.md`).

## 1. Environments

| Environment | What runs | How it is started |
|---|---|---|
| **Local dev** | `anvaya_api` via `uvicorn`, no Docker needed | `ANVAYA_ABSTRACTAI_URL=http://192.168.0.113:8001 python -m uvicorn anvaya_api.main:app --port 8300` |
| **Standalone container** | The `Dockerfile` in this repo (`anvaya-api` image) | `docker build -t anvaya-api .` then `docker run --env-file .env -p 8300:8300 anvaya-api` (used by CI / a fresh host) |
| **HomeLab (production)** | Container `anvaya-api` defined in HomeLab `compose/infrastructure/compose.yml` | `docker compose` group deploy in HomeLab (see §4). **No host port** — reached only through the docs nginx at `/anvaya-api/` behind the login. |

There is one production target today (the HomeLab host `192.168.0.113`). Everything Anvaya does is local-only by rule (D-04 / rule 10).

## 2. Configuration (env var names)

Read once from the environment in `anvaya_api/config.py` (`Settings.from_env`). Defaults in the table are the built-in fallbacks.

| Var | Default | Purpose |
|---|---|---|
| `ANVAYA_ABSTRACTAI_URL` | `http://abstractai-gateway:8000` | AbstractAI gateway base URL. Local dev uses `http://192.168.0.113:8001`. |
| `ANVAYA_ABSTRACTAI_USER` | `anvaya` | Anvaya's own AbstractAI service login. |
| `ANVAYA_ABSTRACTAI_PASSWORD` | *(empty)* | Service login password. **Secret** — HomeLab `compose/.env` / Vaultwarden only. Blank ⇒ `/api/status` reports `auth: not_configured`. |
| `ANVAYA_PROJECT_ID` | `anvaya` | CostGuard budget key (re-seeded at start). |
| `ANVAYA_PRIMARY_MODEL` | `llama3.1:8b` | The pinned local Ollama model. |
| `ANVAYA_DATA_DIR` | `/data` | Ingest/knowledge store + local state. |
| `ANVAYA_REQUEST_TIMEOUT_S` | `240.0` | Upstream timeout (a cold model load can take minutes). |
| `ANVAYA_HA_URL` / `ANVAYA_HA_TOKEN` | `http://homeassistant:8123` / *(empty)* | Live facts (Home Assistant). Token **secret**; blank ⇒ that provider contributes nothing. |
| `ANVAYA_RADARR_URL` / `ANVAYA_RADARR_API_KEY` | `http://host.docker.internal:7878` / *(empty)* | Live facts (Radarr). Key **secret**; blank ⇒ silent. |
| `ANVAYA_SONARR_URL` / `ANVAYA_SONARR_API_KEY` | `http://host.docker.internal:8989` / *(empty)* | Live facts (Sonarr). Key **secret**; blank ⇒ silent. |
| `ANVAYA_FINANCE_API_URL` | `http://finance-api:8200` | Read-only finance facts (Finance OS). |

HomeLab-only extras set on the container (not read by `Settings`): `HOMELAB_DOCS_DIR`, `ATLAS_GRAPH_PATH`, `HUB_CATALOG_URL`, `TASKS_URL`, `PYTHONPATH=/app`, `TZ=Asia/Kolkata`.

`.env.example` lists the `ANVAYA_*` names with placeholder values. Real values live in the HomeLab `compose/.env` (gitignored), never in this repo.

## 3. Build

- **No build step** for the Python app itself.
- Standalone image: `docker build -t anvaya-api:0.0.1 .` (reads `requirements.txt`, copies `anvaya_api/`, `EXPOSE 8300`, `CMD uvicorn …`).
- The HomeLab container does **not** build — it runs `python:3.12-slim`, bind-mounts `D:/Code/HomeAutomation/Apps/Anvaya/anvaya_api` **read-only**, and `pip install`s `requirements.txt` at start (same pattern as `finance-api`).

## 4. Deploy (HomeLab — the real path)

1. Ensure the AbstractAI gateway + the local Ollama model are up and the `anvaya` service login exists (`ANVAYA_ABSTRACTAI_USER`/`_PASSWORD` in `compose/.env`).
2. From the HomeLab repo (never `--remove-orphans` on a single group — all 8 compose files share `name: homelab`):
   ```bash
   docker compose --env-file compose/.env -f compose/infrastructure/compose.yml up -d anvaya-api
   ```
3. Verify from the host (health is on `/healthz`; status is on `/api/status` through the docs login):
   ```bash
   docker compose -f compose/infrastructure/compose.yml ps anvaya-api     # State: running (healthy)
   curl -s http://192.168.0.113:8099/anvaya-api/status -u serviceaccount   # {"gateway":"up","auth":"ok",...}
   ```
4. The docs nginx rewrites `/anvaya-api/x` → the container's `/api/x`; `homechat.js` (HomeLab) calls `/anvaya-api/chat`.

## 5. Rollback

- **Image/deploy rollback:** nothing to roll back image-wise (source is bind-mounted). To revert behaviour, restore the previous `anvaya_api` files or check out the prior commit and recreate:
  ```bash
  # in D:/Code/HomeAutomation/Apps/Anvaya
  git checkout <previous-good-commit> -- anvaya_api
  docker compose -f compose/infrastructure/compose.yml up -d --force-recreate anvaya-api
  ```
- **Data:** conversations/knowledge index live in the named volume `anvaya_data` (`/data`). It survives a container recreate; only delete it deliberately (it is a restore point).
- **Config rollback:** revert `compose/.env` values and recreate the container.
- **Keep the app up on failure:** `restart: unless-stopped` is set; if the gateway is down the API still serves `/healthz` and `/api/status` reports `gateway: down` (degraded, not crashed).

## 6. Post-deploy checklist

- [ ] `docker compose … ps anvaya-api` → `healthy` (healthcheck hits `http://127.0.0.1:8300/healthz`).
- [ ] `/anvaya-api/status` → `gateway: up`, `auth: ok`, `model.state` eventually `warm`, `local_only: true`.
- [ ] A chat/ask request returns a cited answer (see `docs/QA_ACCEPTANCE.md`).
- [ ] Logs show no `assert_local` violations (rule 10).

## 7. Monitoring

The HomeLab compose already defines a container `healthcheck` on `/healthz` (interval 30s). The portable `Dockerfile` carries the same `HEALTHCHECK` so any orchestrator that builds the image inherits it. An Uptime Kuma HTTP monitor is **not yet added**: `anvaya-api` has no host port and the docs path is behind the login, so a plain Kuma monitor cannot reach `/healthz` without credentials — see `docs/DELIVERY_BACKLOG.md` "Waiting on owner".
