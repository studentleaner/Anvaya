# Anvaya — Roadmap

> Owns **scope and exit criteria** per milestone. Work items and status live in `DELIVERY_BACKLOG.md` (same M-numbers). Full detail per phase: HomeLab `documentation/anvaya/PLAN.md`. Any agent starts cold from here.

## Milestone map

| Milestone | Outcome (one sentence a user would recognise) | Depends on | Status |
|---|---|---|---|
| M0 | The platform underneath works: local model loads reliably, Anvaya has its own AbstractAI login, knowledge survives a restart | — | ✅ Done |
| M1 | A question gets a streamed, cited answer grounded in real Home Knowledge, or an honest "I don't know" | M0 | 🔄 First slice done (retrieval + redaction); persisted conversations + hard citation enforcement open |
| M2 | The Ask Home drawer works in place on the app's own pages, mobile and desktop, signs in without navigating away | M1 | 🔄 8 of 9 target pages mounted; source chips in the UI not built |
| M3 | Ask Home can read real per-app data through plugins and propose (never silently run) safe actions | M1 | ⬜ Not started |
| M4 | Home Knowledge is populated automatically and answers are measured against a golden set | M0, M3 | 🔄 Ingest pipeline done and run live (696 documents); scheduled reindex and the eval gate not built |
| M5 (V2) | Cross-app actions, voice, memory, proactive suggestions | M3, M4 | ⬜ Deliberately not started until V1 has run for two weeks |
| M6 | Rollout stays healthy: every mount tested, docs and atlas kept truthful, nothing else on the host silently breaks | — | 🔄 Ongoing |

## Exit criteria per milestone

**M0** — `/api/status` reports `auth: ok`, model `state: warm` after startup, and knowledge survives a gateway restart (ingest → restart → search still finds it). *Met.*

**M1** — Every chat answer either cites an existing `[src_n]` or explicitly says it doesn't know; secrets never reach the model or the knowledge store. *Partially met: citation is enforced by prompt + logged as telemetry, not yet hard-blocked (a live-streaming vs. buffer-then-validate trade-off, see DECISIONS).*

**M2** — Ask Home is mounted, JS-syntax-checked, and functionally tested (login gate, kids-never-mounts) on every HomeLab page it makes sense on; `tv.html` gets an explicit decision, not a silent skip. *8/9 done; `tv.html` decision recorded (deferred, webOS memory risk).*

**M3** — At least one safe-write action (e.g. `create_reminder`) works end-to-end: propose → preview → confirm → executed → audited. *Not started.*

**M4** — A scheduled (hidden, no-catch-up) reindex keeps Home Knowledge current without manual intervention; a golden-question eval gate exists before Ask Home reaches the Family profile for `my_home`/`all_apps` scopes. *Ingest pipeline built and proven live; scheduling and the eval gate remain.*

**M6** — HomeLab's own test suite (`Test-Launchers.ps1`) stays green through every Anvaya change; anything found along the way that isn't Anvaya's to fix is recorded, not silently left. *Ongoing discipline, not a one-time gate.*

## Non-goals across all milestones

Cloud models of any kind, in any milestone. Full detail: `DECISIONS.md` D-04.
