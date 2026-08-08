# 开发计划：AgentArts Memory Agent 插件

> 依据：`claude-prd.md` + Jiuwen `jiuwen_memory_code_agent` 源码 + AgentArts Memory SDK

## 总体信息

- 插件根目录：`agentarts-memory-plugins/agentarts-memory-agent/`
- 组件名：`agentarts-memory-agent`
- 测试目录：`tests/agentarts-memory-agent/`
- Python 版本：3.10+（monorepo `requires-python = ">=3.10"`）
- 代码风格：black(line-length=100)、isort(profile=black)、mypy strict、ruff
- 架构：Node/TS hooks → 本地 Python FastAPI server(`127.0.0.1:8719`) → AgentArts MemoryClient

## 目标产物清单

| 文件 | 内容 |
|---|---|
| `server/__init__.py` | 包入口 |
| `server/agentarts_client.py` | 封装 MemoryClient + scope→session 缓存 |
| `server/app.py` | FastAPI 应用 + 5 个路由 |
| `server/run.py` | 启动入口 |
| `scripts/_shared.mjs` | 项目解析/HTTP/输出格式 |
| `scripts/*.mjs` (12) | 各 hook 脚本 |
| `hooks/hooks.json` | Claude Code hooks |
| `hooks/hooks.codex.json` | Codex hooks |
| `.claude-plugin/plugin.json` | Claude Code 入口 |
| `.codex-plugin/plugin.json` | Codex 入口 |
| `opencode/plugin.json` + `agentarts-memory-capture.ts` + `commands/*.md` | OpenCode |
| `plugin.json` | 顶层元信息 |
| `pyproject.toml` | 子包构建 |
| `README.md` / `AGENTS.md` | 文档 |
| `tests/agentarts-memory-agent/test_server.py` | server 路由单测 |
| `tests/agentarts-memory-agent/test_agentarts_client.py` | client 单测 |
| `tests/agentarts-memory-agent/test_scripts.mjs` | hook 脚本单测 |

---

## 阶段 1：项目骨架（预计 0.5h）

1.1 创建目录结构（`agentarts-memory-agent/` 下全部子目录）
1.2 创建 `pyproject.toml`（fastapi/uvicorn/agentarts-sdk 依赖 + console_script）
1.3 创建 `plugin.json` / `.claude-plugin/plugin.json` / `.codex-plugin/plugin.json` / `opencode/plugin.json`
1.4 创建 `AGENTS.md` 子包指引
1.5 验证骨架可 import

## 阶段 2：Python 适配 server（预计 1.5h）

2.1 `server/agentarts_client.py`：封装 MemoryClient，scope_id→session_id 缓存（create_memory_session），
    user_id→actor_id 映射；方法：add_messages / search_memories / list_memories / health
2.2 `server/app.py`：FastAPI + 5 路由（/health GET, /add_messages/ /search_memory/
    /list_memories/ /search_summary/ POST），CORS，错误处理
2.3 `server/run.py`：uvicorn 启动入口，端口 8719
2.4 编写 `tests/agentarts-memory-agent/test_agentarts_client.py`（scope→session 缓存、actor_id 映射、
    各方法入参映射，monkeypatch MemoryClient）
2.5 编写 `tests/agentarts-memory-agent/test_server.py`（TestClient 验证各路由）
2.6 跑测试，失败则修复

## 阶段 3：Node hook 脚本（预计 1h）

3.1 `scripts/_shared.mjs`：REST_URL/auth/resolveProject(detect CLAUDE_PLUGIN_ROOT|PLUGIN_ROOT)/
    post/postJson/addMessages/searchAndFormat/healthCheck/formatOutput(coerceText/isSdkChildContext)
3.2 `scripts/session-start.mjs` → /health
3.3 `scripts/prompt-submit.mjs` → add_messages(fire-and-forget) + searchAndFormat → stdout
3.4 `scripts/pre-compact.mjs` → searchAndFormat → stdout
3.5 其余 no-op 脚本（post-tool-use/stop/session-end/subagent-*/notification/task-completed/pre-tool-use/post-tool-failure）
3.6 编写 `tests/agentarts-memory-agent/test_scripts.mjs`（mock fetch，验证 stdin→stdout）
3.7 跑测试

## 阶段 4：Hooks 配置（预计 0.3h）

4.1 `hooks/hooks.json`（Claude Code 12 hooks，用 `${CLAUDE_PLUGIN_ROOT}`）
4.2 `hooks/hooks.codex.json`（Codex 6 hooks，用 `${PLUGIN_ROOT}`）
4.3 校验 JSON 合法

## 阶段 5：OpenCode TS 插件（预计 0.5h）

5.1 `opencode/agentarts-memory-capture.ts`：Plugin 导出，event(session.created/deleted/
    message.updated) + chat.message + system.transform + session.compacting；scope 从 ctx.worktree；
    search 在 chat.message 阻塞缓存
5.2 `opencode/commands/recall.md` + `remember.md`
5.3 README 说明 OpenCode 安装

## 阶段 6：文档与收尾（预计 0.3h）

6.1 `README.md`（三平台安装 + server 启动 + 环境变量）
6.2 全量测试 + lint/black/mypy
6.3 修复残留问题

## 验收标准

- 所有测试通过（不允许删/跳/降标准让测试通过）
- server 5 路由行为正确，scope→session 缓存命中
- hook 脚本 stdin→stdout 行为符合预期，no-op 正确排空 stdin
- 三平台入口文件齐全且 JSON 合法
