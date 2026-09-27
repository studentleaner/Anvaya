# Anvaya — Open Questions

> Undecided things that affect scope or design. Each has a **default** so work is never blocked on silence — if nobody answers, the default applies and becomes a `DECISIONS.md` entry.
> The fuller owner-question set (multilingual retrieval, pgvector location, retention, etc.) lives in HomeLab `documentation/anvaya/DECISIONS.md` under "Open questions for the owner" — this file tracks questions specific to *this repo's* remaining build work.

| ID | Question | Options | Default if unanswered | Decides | Blocks | Status |
|---|---|---|---|---|---|---|
| Q-01 | Hard-block an uncited answer, or keep it as telemetry-only? | (a) buffer the full stream, validate citations, replace if invalid — costs live-streaming UX; (b) keep today's telemetry-only warning log | (b) keep telemetry-only; revisit once real usage shows how often it happens | owner | M1 exit criterion ("fully met" vs "partially met") | Open |
| Q-02 | Should `tv.html` get its own, lighter Ask Home surface, or stay excluded entirely? | (a) a minimal remote-control-only surface designed for webOS memory limits; (b) never on TV | (b) never, until someone designs (a) | owner | M2-S2-T7 | Open |
| Q-03 | Scheduled reindex cadence and catch-up policy | Nightly, hidden, user-level, **no catch-up** (per HomeLab's scheduler rules — a missed-night catch-up burst already broke other tasks once) vs. on-demand only | On-demand only until scheduled (current state) | owner | M4-S1-T2 | Open |
| Q-04 | Fix AbstractAI's `ModelBus._resolve()` task_type override for real, or keep Anvaya's `task_type=""` workaround forever? | (a) AbstractAI-side fix, changes routing for CompanionWriter/LearningLens too; (b) keep the workaround | (b) keep the workaround | AbstractAI owner | HomeLab known-issues O27 | Open |

<!-- When answered: Status → Answered (D-nn), and add the decision to DECISIONS.md. -->
