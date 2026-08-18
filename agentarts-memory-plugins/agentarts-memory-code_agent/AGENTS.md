# Repository Guidelines

This sub-package, `agentarts-memory-code_agent`, is part of the AgentArts SDK Python monorepo.
It provides a local HTTP adapter server + multi-agent hook scripts that wire Huawei Cloud
AgentArts Memory into Claude Code / Codex / OpenCode as a long-term memory backend.

## Structure

- `server/` — Python FastAPI adapter over `agentarts.sdk.memory.MemoryClient`
- `scripts/` — Node hook scripts (`.mjs`) shared by Claude Code / Codex
- `hooks/` — `hooks.json` (Claude Code) and `hooks.codex.json` (Codex)
- `opencode/` — TypeScript plugin + slash commands for OpenCode
- `.claude-plugin/`, `.codex-plugin/` — platform plugin manifests

## Commands

```bash
pip install -e ".[dev]"        # install dev deps
pytest tests/agentarts-memory-code_agent/ -q
black . && isort .            # format
ruff check .                  # lint
mypy server                   # type check
```

## Conventions

- black (line-length=100), isort (profile=black), mypy strict, ruff.
- Node scripts are ESM (`.mjs`), shared logic in `scripts/_shared.mjs`.
- Tests live in `tests/agentarts-memory-code_agent/` and mock `MemoryClient` (no cloud calls).
