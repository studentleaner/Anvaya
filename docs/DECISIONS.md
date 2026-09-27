# Anvaya — Decisions

> Architecture/product decision records for **this repo**. Newest last. Never delete an entry — supersede it (`Status: Superseded by D-nn`).
> The full product decision log (D-01…D-16: model choice, auth, persistence, actions, privacy) lives in HomeLab `documentation/anvaya/DECISIONS.md` — this file only carries decisions specific to *this repository's* structure/tooling, plus a pointer.

## D-01 — Start from project-baseline

- **Date:** 2026-09-27
- **Status:** Accepted
- **Context:** Every ecosystem repo starts from the same foundation so agents and people can work across repos without re-learning structure. Anvaya predates the baseline (it grew its own README/AGENT-GUIDE/PLAN/ARCHITECTURE/CONTRACTS pack, hosted in HomeLab `documentation/anvaya/`, before `project-baseline` existed).
- **Decision:** Adopt the baseline's Tier 0/1 documents in *this* repo as thin summaries that link the existing, more detailed HomeLab pack rather than duplicating it. `Test-ProjectBaseline.ps1` must pass at Tier 1; `CLAUDE.md`/`AGENTS.md` `## Rules` stay byte-identical.
- **Consequences:** Two places describe Anvaya (HomeLab's deep pack, this repo's thin baseline docs). Drift risk — mitigated by the baseline docs linking rather than restating, and by DELIVERY_BACKLOG.md staying the single status source in *both* repos (kept in sync in the same commit whenever possible).

## D-02 — Product decisions live in HomeLab, not duplicated here

- **Date:** 2026-09-27
- **Status:** Accepted
- **Context:** The full product decision log (model choice D-03, no-cloud D-04, widget stack D-05, persistence D-08, auth D-15, model-volume D-16, etc.) already exists at HomeLab `documentation/anvaya/DECISIONS.md`, written before this repo had its own `docs/` folder.
- **Decision:** New *product* decisions are recorded there, not here, to keep one source of truth. This file (`Apps/Anvaya/docs/DECISIONS.md`) is for decisions specific to this repository's own code/tooling/structure (e.g. D-01 above).
- **Consequences:** An agent working only from this repo must follow the link below for the "why" behind Anvaya's actual product choices.

**→ Full product decision log:** `HomeLab/documentation/anvaya/DECISIONS.md` (D-01 through D-16 and counting).
