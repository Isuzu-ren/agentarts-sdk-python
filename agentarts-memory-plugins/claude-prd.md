# PRD：AgentArts Memory Agent 插件（Claude Code / Codex / OpenCode）

> 组件名：`agentarts-memory-agent`　|　测试目录：`tests/agentarts-memory-agent/`

## 1. 概述

在 `agentarts-memory-plugins/agentarts-memory-agent/` 下构建一个插件，把华为云 AgentArts Memory
作为 **Claude Code / Codex / OpenCode** 三平台 AI 编程助手的长期记忆后端。架构对齐 Jiuwen
`jiuwen_memory_code_agent`：**各平台 hook/插件 → 本地 Python HTTP 适配 server →
AgentArts MemoryClient（云端 SDK）**。

### 参考实现

- Jiuwen `jiuwen_memory_code_agent`：`scripts/_shared.mjs` + `hooks/*.json` + `opencode/*.ts`
- AgentArts Memory SDK 使用指南：`docs/cn/sdk_user_guide/memory_user_guide.md`
- 已有 Hermes 插件参考：`agentarts-memory-plugins/agentarts-memory-hermes/provider.py`

---

## 2. 环境变量

### server 端（云端 SDK 鉴权，已有）

| 变量 | 用途 |
|---|---|
| `HUAWEICLOUD_SDK_AK` | 华为云 Access Key |
| `HUAWEICLOUD_SDK_SK` | 华为云 Secret Key |
| `HUAWEICLOUD_SDK_MEMORY_API_KEY` | AgentArts Memory 数据面 API Key |
| `HUAWEICLOUD_SDK_REGION` | 华为云区域（默认 `cn-southwest-2`） |
| `AGENTARTS_MEMORY_SPACE_ID` | 记忆空间 ID |

### 脚本/插件端（可选覆盖）

| 变量 | 默认 | 说明 |
|---|---|---|
| `AGENTARTS_MEMORY_SERVER_URL` | `http://127.0.0.1:8719` | 本地 server 地址 |
| `AGENTARTS_MEMORY_USER_ID` | `cc-user` / `codex-user` / `opencode-user` | 记忆隔离 user_id |
| `AGENTARTS_MEMORY_DEBUG` | `0` | 开调试日志 |

---

## 3. 目录结构

```
agentarts-memory-plugins/agentarts-memory-agent/
├── .claude-plugin/plugin.json     # Claude Code 入口（指向 hooks/hooks.json）
├── .codex-plugin/plugin.json      # Codex 入口（指向 hooks/hooks.codex.json）
├── hooks/
│   ├── hooks.json                 # Claude Code hooks（12）
│   └── hooks.codex.json           # Codex hooks（6）
├── opencode/
│   ├── plugin.json
│   ├── agentarts-memory-capture.ts # OpenCode TS 插件
│   └── commands/
│       ├── recall.md              # /recall
│       └── remember.md            # /remember
├── scripts/                        # Node hook 脚本（共享 _shared.mjs）
│   ├── _shared.mjs
│   ├── session-start.mjs          # SessionStart → /health
│   ├── prompt-submit.mjs          # 写用户 query + 搜索注入
│   ├── pre-compact.mjs           # 压缩前注入
│   ├── post-tool-use.mjs          # no-op
│   ├── post-tool-failure.mjs      # no-op
│   ├── pre-tool-use.mjs           # no-op
│   ├── stop.mjs                   # no-op
│   ├── session-end.mjs            # no-op
│   ├── subagent-start.mjs         # no-op
│   ├── subagent-stop.mjs          # no-op
│   ├── notification.mjs          # no-op
│   └── task-completed.mjs         # no-op
├── server/                         # Python 本地 HTTP 适配层
│   ├── __init__.py
│   ├── app.py                     # FastAPI 应用 + 路由
│   ├── agentarts_client.py        # 封装 MemoryClient + scope→session 缓存
│   └── run.py                     # 入口
├── plugin.json                     # 顶层元信息
├── pyproject.toml                 # 子包构建配置
├── README.md
└── AGENTS.md

tests/agentarts-memory-agent/      # 测试用例
├── test_server.py                 # FastAPI TestClient（mock MemoryClient）
├── test_agentarts_client.py       # client 封装/scope→session 缓存单测
└── test_scripts.mjs               # Node hook 脚本单测（mock fetch）
```

---

## 4. 平台接入差异（对齐 Jiuwen）

| 平台 | 接入方式 | hook 数 | 注入方式 | scope_id 来源 |
|---|---|---|---|---|
| Claude Code | `.claude-plugin/plugin.json` + marketplace | 12 | stdout 纯文本 | stdin `cwd` → git toplevel basename |
| Codex | `.codex-plugin/plugin.json` + marketplace | 6 | stdout 纯文本 | stdin `cwd` → git toplevel basename |
| OpenCode | TS 插件 `agentarts-memory-capture.ts` + opencode.json | session/message/system 事件 | `output.system[]` / `output.context[]` | `ctx.worktree` basename |

- Claude Code/Codex 共享同一套 `.mjs` 脚本，经 `CLAUDE_PLUGIN_ROOT` / `PLUGIN_ROOT` 区分平台。
- OpenCode 不走 stdout，TS 插件直接操作 output 数组；搜索在 `chat.message` 阻塞执行一次并
  缓存到 `sessionSearchResult`，`system.transform`/`compacting` 只读缓存。
- OpenCode 额外暴露 `/recall`、`/remember` 两个 slash 命令（调 server REST）。

---

## 5. 本地 HTTP 适配 server（三平台共用）

- 框架：Python + FastAPI + uvicorn，命令 `agentarts-memory-server`，默认 `127.0.0.1:8719`。
- 内部用 `agentarts.sdk.memory.MemoryClient`，鉴权走环境变量。
- 端点（尾斜杠）：

| 端点 | 方法 | 入参 | 映射到 SDK |
|---|---|---|---|
| `/health` | GET | — | 探测 server 与 SDK 配置就绪 |
| `/add_messages/` | POST | `{messages:[{role,content}], user_id, scope_id}` | 按 scope 创建/复用 session → `add_messages` |
| `/search_memory/` | POST | `{query, num, user_id, scope_id, threshold}` | `search_memories(MemorySearchFilter(query, top_k=num, min_score=threshold))` |
| `/list_memories/` | POST | `{limit, offset, user_id, scope_id}` | `list_memories(space_id, limit, offset)` |
| `/search_summary/` | POST | `{query, num, user_id, scope_id, threshold}` | 复用 `list_memories` 过滤摘要类记忆返回（无独立摘要端点则复用 list） |

- 会话映射：`scope_id` → AgentArts `session_id`（首次 `create_memory_session` 并缓存），
  `user_id` → `actor_id`。Node/TS 脚本只需传 `scope_id`/`user_id`。

---

## 6. 写入策略（对齐 Jiuwen）

- 只记录**用户 query**（`UserPromptSubmit` / OpenCode `message.updated`），不写 agent 回答/工具结果。
- `add_messages` fire-and-forget（不阻塞主循环）。

---

## 7. 测试（`tests/agentarts-memory-agent/`）

- `test_server.py`：FastAPI `TestClient`，monkeypatch `MemoryClient`，验证各端点入参映射、
  scope→session 缓存、错误处理、`/health`。
- `test_agentarts_client.py`：client 封装与 scope→session 缓存逻辑单测。
- `test_scripts.mjs`：mock `fetch`，验证 `prompt-submit`/`pre-compact`/`session-start` 的
  stdin→stdout 与 no-op 行为。
- 不做真实云调用（集成测试需凭证，本地默认跳过）。

---

## 8. 范围边界

- 不做 MCP server / 检索工具暴露（三平台均靠 hooks/插件自动注入；OpenCode slash 命令调 REST）。
- 不自动写 agent 回答（只写用户 query，与 Jiuwen 一致）。
- 不改动仓库内已有的 `agentarts-memory-hermes`。
- Cursor 支持不在本期范围。
