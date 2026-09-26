# Anvaya - instructions for any coding agent

1. **Read the canonical docs first**: HomeLab `documentation/anvaya/README.md` and `AGENT-GUIDE.md` (`D:\Code\Projects\HomeLab\documentation\anvaya\`, or `http://192.168.0.113:8099/anvaya/`). Pick the next unchecked task in `PLAN.md`.
2. **Non-negotiables**: all AI via the AbstractAI gateway only; local Ollama models only (never call Ollama directly, never a cloud provider); nothing executes because a model said so (actions are proposals a user confirms); secrets never enter prompts/indexes/logs/git; finance data is read-only; no Ask Home on the Kids profile.
3. **Quality bar**: `python -X utf8 -m pytest --cov --cov-branch` must stay at 100 % branch coverage; tests use fakes (no network, no real LLM).
4. **Git**: branch `main`; push as `studentleaner` through Git Credential Manager (`git -c credential.helper= -c credential.helper=manager push`). Never commit `.env`, data, or anything from the HomeLab `compose/.env`.
5. Update the HomeLab docs (PLAN status board, tracker, known-issues, CLAUDE.md + AGENTS.md, atlas) in the same working session.
