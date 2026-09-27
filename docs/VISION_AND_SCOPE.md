# Anvaya — Vision and Scope

One connected intelligence layer across every Home app: a **✦ Ask Home** drawer, mounted in place on the app's own pages (never a separate destination), backed by shared Home Knowledge and per-app plugins, answering only through **AbstractAI's local models — no cloud, ever.**

> Full spec: HomeLab `documentation/anvaya/anvaya.md` (owner's original) + `ARCHITECTURE.md` (verified against the real stack). This page is the short version.

## Problem

Every Home app (portal, home devices, alerts, finance, docs, arrivals…) is its own island. Getting an answer means knowing which app has it, then reading it yourself. There is no single place to ask "what port is Jenkins on" or "is the backup task registered" and get a cited, correct answer.

## Users

| User | Need | How they use it |
|---|---|---|
| The owner (family admin) | Answer home/setup questions without hunting through docs | Ask Home drawer on any System-profile page (`index.html`, `containers.html`, Finance OS) |
| Family members | General questions, home-adjacent (not finance/health) | Ask Home drawer on Family-profile pages (`portal.html`, `home.html`, `alerts.html`, …) |
| Kids | — | **Never** — Ask Home does not mount on the Kids profile, by design (D-11) |
| A cold-start agent | Extend Anvaya without re-deriving the whole design | This doc pack + `documentation/anvaya/` in HomeLab |

## Goals

- Grounded answers with visible sources, or an honest "I don't have that" — never an invented fact about the home.
- Works in place on whatever page it's mounted on; no separate chat app, no page navigation to sign in.
- Everything stays on this machine: AbstractAI + a local Ollama model, nothing sent to a cloud provider.

## Non-goals (V1)

- Autonomous or multi-agent behaviour — every action is a human-confirmed proposal, not built yet.
- Any write path into Finance OS's ledger.
- Voice, cross-app multi-step actions, a knowledge graph, TV surface — all V2 (PLAN Phase 5).
- A raw scan of every drive/file on the machine — Home Knowledge is the *catalogued* sources (HomeLab docs, the container/page catalog, the Ecosystem Atlas, scheduled tasks), not literal disk imaging. See `ARCHITECTURE.md` and HomeLab known-issues for why.

## Success measures

- A real, previously-untested question about the home returns a correct, cited answer (verified live 2026-09-27: "what port is Jenkins on" → correct, cited).
- Ask Home is mounted on every page it makes sense on, without breaking that page (JS-syntax-checked, launcher-suite-tested).
- Zero calls to a non-local model provider, ever (enforced by `assert_local()`, tested).

## Constraints

- Single 6 GB GPU (GTX 1660 SUPER) shared with other AbstractAI consumers — only one 7–8B model resident at a time.
- AbstractAI is a shared platform owned elsewhere; Anvaya extends it (service login, metadata passthrough, persistence) rather than forking it.
