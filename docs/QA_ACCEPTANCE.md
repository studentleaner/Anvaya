# Anvaya — QA and Acceptance

## Definition of done (every story)

- [ ] Behaviour covered by automated tests (unit; the relevant integration level for anything that talks to AbstractAI is a mocked-transport test, per `tests/`)
- [ ] `python -X utf8 -m pytest --cov --cov-branch` green at **100%** — the `pyproject.toml` gate (`fail_under = 100`) enforces this; there is no lower bar
- [ ] `DELIVERY_BACKLOG.md` row updated with evidence in the same commit (both this repo's and, when the change is visible from HomeLab, the tracker row there)
- [ ] Docs touched by the change updated (this file set + HomeLab `documentation/anvaya/` if the change affects the wider design)
- [ ] No secrets, no TODO-without-backlog-ID
- [ ] For anything touching a mounted page: HomeLab's `tests/Test-Launchers.ps1` still passes (JS syntax check, mount presence, login gate)

## Test pyramid

| Level | What | Where | How run |
|---|---|---|---|
| Unit | Every `anvaya_api` module in isolation, `httpx.MockTransport` for any AbstractAI call | `tests/test_*.py` | `python -X utf8 -m pytest --cov --cov-branch` |
| Widget unit | SSE parser, kids-never-mounts | `tests/homechat.test.js` (Node, no DOM) | `node tests/homechat.test.js` |
| Live integration | Real gateway, real local model, real chat turn | Manual, this session's own verification runs | `curl -u serviceaccount:*** .../anvaya-api/chat` with a real question; check the answer cites a real `[src_n]` |
| Cross-repo (HomeLab) | Widget mounted correctly, login-gated, doesn't break the host page | `HomeLab/tests/Test-Launchers.ps1` | `pwsh tests/Test-Launchers.ps1` from the HomeLab repo |

## Coverage policy

**100% branch coverage, no exceptions, enforced by the build itself** (`pyproject.toml` → `fail_under = 100`). This has held since the first commit (14 tests at Phase 0.5) through 108 tests today. A change that can't reach 100% branch coverage cleanly is usually a sign the code path is untestable as written (e.g. dead code, or a branch that should be `# pragma: no cover` with a one-line reason) — not a reason to lower the bar.

## Acceptance per milestone

See `ROADMAP.md`'s "Exit criteria per milestone" — each milestone's bar is stated there, not repeated here (one question, one document).
