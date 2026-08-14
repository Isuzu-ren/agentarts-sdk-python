# agentarts-memory-code_agent

**Huawei Cloud AgentArts Memory** 作为 **Claude Code / Codex / OpenCode** 三平台 AI 编程助手的长期记忆后端。

一个插件目录同时覆盖三平台，共享同一个本地 HTTP 适配 server + hook 脚本逻辑。

## 关于AgentArts Memory

华为云 AgentArts Memory 是智能体云端记忆解决方案，对智能体记忆数据提供全生命周期管理。

### AgentArts Memory优势

1、开箱即用：
短期记忆 + 长期记忆：支持短期记忆（7~365天）和长期记忆（持久化存储），满足不同时间跨度的记忆需求。

2、多种记忆策略：
支持语义记忆、用户偏好、会话摘要、情景记忆等策略，满足不同场景的记忆需求。

3、多维度隔离：
按策略类型隔离：支持按空间、会话、用户维度进行记忆隔离，确保数据的安全性和独立性。

4、全托管免运维：
云上全托管：无需管理数据库等基础设施和记忆处理引擎，实现业务快速上线，降低运维成本和复杂度。
> 官方文档：[记忆库概述](https://support.huaweicloud.com/highcode-agentarts/agentarts_10_015.html) · [SDK 集成示例](https://support.huaweicloud.com/highcode-agentarts/agentarts_10_016.html) · [创建记忆库](https://support.huaweicloud.com/highcode-agentarts/agentarts_10_017.html)


## 实现方式

| 平台 | 接入方式 | hook 数 | 命令 |
|---|---|---|---|
| Claude Code | `.claude-plugin/plugin.json` + marketplace | 12 | — |
| Codex | `.codex-plugin/plugin.json` + marketplace | 6 | — |
| OpenCode | TypeScript 插件 + opencode.json 配置 | session/message/system 事件 | `/recall` `/remember` |

所有平台共享同一个 `scripts/_shared.mjs`（hook 脚本）和 `opencode/` 下的 TS 插件，只是配置入口不同。所有捕获与注入都调用本地适配 server 的 REST API（`127.0.0.1:8719`），server 再调用云端 AgentArts Memory SDK。

### 数据流

```
Claude Code / Codex / OpenCode agent loop
    │
    ├── hooks / plugin 事件 (生命周期拦截)
    │   ├── session-start → /health (探测 server)
    │   ├── prompt-submit → /add_messages/ (后台记录用户 query) + /search_memory/ + /search_summary/ → stdout 注入
    │   └── pre-compact → /search_memory/ + /search_summary/ → stdout 注入防丢
    │       │
    │       └── 本地适配 server (127.0.0.1:8719, FastAPI)
    │           └── AgentArts MemoryClient → 华为云 AgentArts Memory
    │
    └── OpenCode commands (/recall /remember)
        └── 手动搜索 / 保存记忆
```

## 前置条件

### 1. 安装适配 server

```bash
cd agentarts-memory-plugins/agentarts-memory-code_agent
pip install -e ".[cloud,dev]"   # 需要 agentarts-sdk + fastapi + uvicorn
```

### 2. 启动适配 server

直接运行 server，如缺少必要配置会自动提示输入：

```bash
agentarts-memory-server
```

启动时会检查环境变量：
- ✅ 已配置 → 直接启动
- ❌ 缺少配置 → 交互式提示输入

交互示例：

```
============================================================
AgentArts Memory Server Configuration
============================================================

⚠️  Missing required configuration:

AgentArts Memory Space ID: my-space-id-12345
  ✓ Configured: my-****45

Huawei Cloud Memory API Key: ************************
  ✓ Configured: ************************

ℹ️  Optional: AgentArts Memory Region
  Configure AgentArts Memory Region? [y/N]: y
AgentArts Memory Region (default: cn-southwest-2): cn-north-4
  ✓ Configured: cn-north-4

------------------------------------------------------------
Save configuration to ~/.zshrc for persistence? [y/N]: y
  ✓ Configuration saved to /Users/xxx/.zshrc
  Run 'source ~/.zshrc' or restart terminal to apply.

============================================================
Starting AgentArts Memory Server on 127.0.0.1:8719
============================================================
```

可指定日志级别：

```bash
AGENTARTS_MEMORY_LOG_LEVEL=debug agentarts-memory-server
```

### 3. 验证

```bash
curl http://127.0.0.1:8719/health   # {"status":"healthy","space_id":true,"api_key":true}
```

## 安装插件

### Claude Code

```bash
# 注册 marketplace 后安装
/plugin install agentarts_memory
```

hook 配置由 `hooks/hooks.json` 提供（12 个生命周期 hook），使用 `${CLAUDE_PLUGIN_ROOT}` 变量。

### Codex

```bash
codex plugin marketplace add <repo>
codex plugin add agentarts_memory
```

重启 Codex 后生效。Codex 不自动从 manifest 读 hooks，需手动把 `hooks/hooks.codex.json` 合并到 `~/.codex/hooks.json`（修改路径为绝对路径），并在 `~/.codex/config.toml` 启用：

```toml
[features]
codex_hooks = true
```

hook 配置使用 `${CODEX_PLUGIN_ROOT}` 变量。

### OpenCode

1. 拷贝插件文件和命令到 OpenCode 配置目录：

```bash
mkdir -p ~/.config/opencode/plugins ~/.config/opencode/commands
cp opencode/agentarts-memory-capture.ts ~/.config/opencode/plugins/
cp opencode/commands/recall.md ~/.config/opencode/commands/
cp opencode/commands/remember.md ~/.config/opencode/commands/
```

2. 在 `~/.config/opencode/opencode.json` 启用插件：

```json
{
  "plugin": ["./plugins/agentarts-memory-capture.ts"]
}
```

## user_id 解析优先级

user_id 用于记忆隔离，解析优先级如下：

```
1. payload.user_id / payload.userId  (hook 请求携带)
   ↓ 未提供或为空
2. AGENTARTS_MEMORY_USER_ID 环境变量
   ↓ 未设置
3. 平台默认值（基于环境变量检测）
```

### 平台检测与默认 user_id

| 平台 | 环境变量 | 默认 user_id |
|------|----------|--------------|
| Claude Code | `CLAUDE_PLUGIN_ROOT` | `cc-user` |
| Codex | `CODEX_PLUGIN_ROOT` | `codex-user` |
| OpenCode | `OPENCODE_PLUGIN_ROOT` | `opencode-user` |
| 未知 | — | `__default__` |

当插件通过 marketplace 正确安装时，各平台会自动设置对应的环境变量，无需手动配置。

## hooks → 端点映射

### Claude Code hooks（12 个）

| hook | server 端点 | 写入记忆? | stdout 注入? |
|---|---|---|---|
| SessionStart | `/health` only | ❌ | ❌ |
| UserPromptSubmit | `/add_messages/` + `/search_memory/` + `/search_summary/` | ✅（仅用户 query） | ✅ |
| PreToolUse | no-op placeholder | ❌ | ❌ |
| PostToolUse / PostToolUseFailure | no-op | ❌ | ❌ |
| PreCompact | `/search_memory/` + `/search_summary/` | ❌ | ✅ |
| SubagentStart/Stop, Notification, TaskCompleted, Stop, SessionEnd | no-op | ❌ | ❌ |

### Codex hooks（6 个）

| hook | server 端点 | 写入记忆? | stdout 注入? |
|---|---|---|---|
| SessionStart | `/health` only | ❌ | ❌ |
| UserPromptSubmit | `/add_messages/` + `/search_memory/` + `/search_summary/` | ✅（仅用户 query） | ✅ |
| PreToolUse / PostToolUse | no-op placeholder | ❌ | ❌ |
| PreCompact | `/search_memory/` + `/search_summary/` | ❌ | ✅ |
| Stop | no-op | ❌ | ❌ |

### OpenCode 插件机制

| 钩子 | 作用 | 记忆写入? | 注入? |
|---|---|---|---|
| `session.created` | 探测 `/health`，初始化 per-session 状态，解析 user_id | ❌ | ❌ |
| `session.deleted` | 清理 per-session 缓存 | ❌ | ❌ |
| `message.updated`（assistant） | AI 回复结束后写入暂存的用户 query | ✅（延后写入） | ❌ |
| `chat.message` | 存用户 query、标记 pending、阻塞执行一次 search 并缓存 | ❌（延后写入） | ❌ |
| `experimental.chat.system.transform` | 读取缓存 search 结果注入 `output.system[]` | ❌ | ✅ system prompt |
| `experimental.session.compacting` | 压缩前注入 `output.context[]`（命中缓存，否则 fallback 搜索） | ❌ | ✅ context |

搜索只在 `chat.message` 阻塞执行一次并缓存，`system.transform`/`compacting` 全程只读缓存、不重复搜索。

## 环境变量（可选覆盖）

| 变量 | 默认 | 说明 |
|---|---|---|
| `AGENTARTS_MEMORY_SERVER_URL` | `http://127.0.0.1:8719` | 本地 server 地址（hook/插件端） |
| `AGENTARTS_MEMORY_USER_ID` | 平台默认值 | 记忆隔离 user_id |
| `AGENTARTS_MEMORY_DEBUG` | `0` | 开调试日志 (1=开启) |
| `AGENTARTS_MEMORY_LOG_LEVEL` | `info` | Server 日志级别 (debug/info/warning/error) |
| `AGENTARTS_MEMORY_PROJECT_NAME` | git toplevel basename | scope_id 覆盖 |

## server API

| 端点 | 方法 | 入参 | 说明 |
|---|---|---|---|
| `/health` | GET | — | 配置就绪探测（无网络） |
| `/add_messages/` | POST | `{messages, user_id, scope_id}` | 按 scope 创建/复用 session 写入 |
| `/search_memory/` | POST | `{query, num, user_id, scope_id, threshold}` | 语义搜索 |
| `/list_memories/` | POST | `{limit, offset, user_id, scope_id}` | 列出记忆 |
| `/search_summary/` | POST | `{query, num, user_id, scope_id, threshold}` | 摘要类记忆检索 |

`scope_id` → AgentArts `session_id`（首次自动创建并缓存），`user_id` → `actor_id`。

## 测试

```bash
# Python server 测试
pytest tests/agentarts-memory-code_agent/ -q

# Node hook 脚本测试
node --test tests/agentarts-memory-code_agent/test_scripts.mjs

# 验证平台检测
CLAUDE_PLUGIN_ROOT=/test node -e '
import("./scripts/_shared.mjs").then(m => console.log(m.detectPlatform(), m.resolveUserId({})));
'
# 输出: claude-code cc-user

CODEX_PLUGIN_ROOT=/test node -e '
import("./scripts/_shared.mjs").then(m => console.log(m.detectPlatform(), m.resolveUserId({})));
'
# 输出: codex codex-user

OPENCODE_PLUGIN_ROOT=/test node -e '
import("./scripts/_shared.mjs").then(m => console.log(m.detectPlatform(), m.resolveUserId({})));
'
# 输出: opencode opencode-user
```

## 写入策略

只记录**用户 query**（`UserPromptSubmit` / OpenCode `message.updated`），不写 agent 回答/工具结果。`add_messages` fire-and-forget，不阻塞主循环。

## License

Apache-2.0