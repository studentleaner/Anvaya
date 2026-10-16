# Anvaya — Operations runbook

> Day-2 operations: health, logs, the startup sequence, backup/restore, and a runbook per failure mode.
> Companion to `docs/DEPLOYMENT.md`. Env var **names** only (rule 3). Deep product context: HomeLab `documentation/anvaya/`.

## 1. Health and status

| Signal | Where | Healthy looks like |
|---|---|---|
| Liveness | `GET /healthz` (internal :8300; via docs login `…:8099/anvaya-api/healthz`) | `{"ok":true,"version":"0.0.1"}` |
| Readiness / detail | `GET /api/status` | `gateway: "up"`, `auth: "ok"`, `model.state: "warm"`, `local_only: true` |
| Container health | `docker inspect --format '{{.State.Health.Status}}' anvaya-api` | `healthy` (HomeLab healthcheck hits `/healthz` every 30s) |
| Startup bootstrap | `/api/status.bootstrap` | `{"budget": true, "prompts": true}` |

`/api/status` fields: `gateway` (up/down — an `/openapi.json` probe, no LLM spend), `auth` (`ok` / `failed` / `not_configured` / `unknown`), `model.state` (`unknown`→`warming`→`warm`, or `error`), `bootstrap.budget`/`bootstrap.prompts`, `last_reindex`, `mode: "knowledge"`, `local_only: true`.

## 2. Logs

- Container: `docker logs -f anvaya-api` (uvicorn access + app logs; `PYTHONUNBUFFERED=1`).
- The app logs errors through uvicorn's standard logger; there is no separate log file inside the container (state lives in `/data`).
- Watch for: `assert_local` / `NonLocalProviderError` (a cloud provider answered — a rule-10 breach), `AbstractAI login failed`, `gateway HTTP …`, `model_timeout`.

## 3. Startup behaviour (why an empty status right after deploy is normal)

On start, a background task (`bootstrap.py`) runs, best-effort, and reports via `/api/status`:

1. **Seed CostGuard budget** — `PUT /admin/costs/anvaya` (`monthly_usd=0.0001`, mode `reject`). CostGuard is in-memory on the gateway, so this re-runs every start. `bootstrap.budget=true` when it succeeded.
2. **Seed the `anvaya.answer` PromptVault prompt** — registered once; an owner edit in PromptVault wins (never overwritten). `bootstrap.prompts=true`.
3. **Warm the primary model** — a 1-token completion, retried on the ladder **5s / 20s / 60s / 120s** while the gateway + Ollama come up. `/api/status.model.state` moves `warming`→`warm`; a cold local load takes ~90–160s. `model.detail` carries the last error while warming.

The API answers immediately while this runs; a cold model means the first chat may take minutes (the request timeout is `ANVAYA_REQUEST_TIMEOUT_S`, default 240s).

## 4. Backup and restore

- All persistent state is the Docker volume **`anvaya_data`** (mounted at `/data`): ingest/knowledge index, local state. Conversations/knowledge are otherwise held by AbstractAI's KnowledgeBus (pgvector Postgres), backed up by HomeLab's own DB backup.
- **Backup** (HomeLab host):
  ```bash
  docker run --rm -v anvaya_data:/data -v /mnt/host/o/Backups:/b alpine \
    tar czf /b/anvaya_data-$(date +%Y%m%d).tgz -C /data .
  ```
  (HomeLab's `backup-system.ps1` already covers named volumes on its schedule — prefer that.)
- **Restore**: stop `anvaya-api`, untar back into the volume, recreate:
  ```bash
  docker run --rm -v anvaya_data:/data -v /mnt/host/o/Backups:/b alpine \
    sh -c "rm -rf /data/* && tar xzf /b/anvaya_data-<date>.tgz -C /data"
  docker compose -f compose/infrastructure/compose.yml up -d --force-recreate anvaya-api
  ```
- **Knowledge re-sync** (self-healing, no restore needed): `POST /api/admin/reindex` (through the docs login) re-pulls Home Knowledge from docs/hub/atlas/tasks; it is idempotent (content-hash skip). A hidden scheduled task runs it every 6h.

## 5. Alerts

There is no dedicated alert rule yet; rely on the container healthcheck + HomeLab's Uptime Kuma/Jenkins heal. If Anvaya starts answering with `gateway: down`, HomeLab's `script.announce` category `system` already carries infra notices. A Kuma monitor is an open owner item (see `docs/DELIVERY_BACKLOG.md` "Waiting on owner").

## 6. Runbook — failure modes

| Symptom | Likely cause | Do |
|---|---|---|
| `/api/status` `gateway: "down"`; `/api/ask` → `502`; chat streams `error: gateway_down` | AbstractAI gateway down or unreachable | `docker ps | grep abstractai-gateway`; bring the gateway group up in HomeLab; verify `curl http://abstractai-gateway:8000/openapi.json` from a container on `abstractai-shared`. Anvaya itself stays healthy. |
| `/api/status` `auth: "not_configured"` | `ANVAYA_ABSTRACTAI_USER`/`_PASSWORD` unset | Set them in HomeLab `compose/.env` and recreate the container. |
| `/api/status` `auth: "failed"` | Wrong credentials, or the gateway has no `anvaya` service user | Re-check the secret in Vaultwarden; confirm `SERVICE_USERS_JSON_B64` on the gateway includes `anvaya` (AbstractAI). |
| `/api/status` `model.state: "warming"` for minutes, or `error` | Cold local model load; or the model isn't installed | Wait (up to ~160s). If it stays `error`, confirm `ANVAYA_PRIMARY_MODEL` is present in Ollama (`ollama list` in the gateway's Ollama). Do not switch to a cloud model (rule 10). |
| `/api/ask` → `502` with `detail` mentioning a timeout | Model slower than `ANVAYA_REQUEST_TIMEOUT_S` | Raise the timeout or check GPU contention; see HomeLab `documentation/anvaya/LOCAL-LLM.md`. |
| Log shows `NonLocalProviderError` | A cloud provider answered (a rule-10 breach) | Stop and report to the owner immediately. Verify every completion call pins `provider="ollama"` and `task_type=""` (a known `task_type` lets AbstractAI's router swap in a cloud model — see `docs/DECISIONS.md` / HomeLab O27). |
| `/api/status.bootstrap.prompts: false` | Prompt registration failed (auth/gateway) | Once `auth: ok`, it re-seeds on the next restart; `PromptCache` falls back to the code constant meanwhile, so chat keeps working. |
| `POST /api/admin/reindex` returns a non-zero `failed` | A knowledge source (docs/hub/atlas/tasks) unreachable or a doc rejected | Inspect the response (`scanned/ingested/unchanged/deleted/failed`); a partial failure is self-healing on the next 6h run. |
| `curl … /anvaya-api/status` returns `401` | You hit the docs login, not the app | Provide the docs login (`-u serviceaccount`) — the API is intentionally not publicly reachable. |

## 7. Escalation / owner gates

These need the owner (see `docs/DELIVERY_BACKLOG.md` "Waiting on owner"): adding an Uptime Kuma monitor for `anvaya-api` (no host port, login-protected), and the ecosystem-wide DeepSeek key rotation (`M0-B4`/`M6-EG1`).

## 8. Golden commands

```bash
docker compose -f compose/infrastructure/compose.yml up -d --force-recreate anvaya-api   # redeploy
docker logs --tail 100 anvaya-api                                                         # recent logs
docker inspect --format '{{.State.Health.Status}}' anvaya-api                              # health
curl -s http://192.168.0.113:8099/anvaya-api/status -u serviceaccount                      # status
python -X utf8 -m pytest --cov --cov-branch                                                # tests + 100% branch floor
```
