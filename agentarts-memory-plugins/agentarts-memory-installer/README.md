# agentarts-memory-installer

Unified Python installer for AgentArts Memory plugins. Deploys memory plugins to supported AI agent platforms via **direct file writing** (no marketplace).

## 安装

```bash
cd agentarts-memory-plugins/agentarts-memory-installer
pip install -e .
```

## 用法

```
agentarts-memory install   [hermes|claude|codex|opencode|openclaw] [--global] [--yes]
agentarts-memory uninstall [hermes|claude|codex|opencode|openclaw] [--global] [--yes]
```

- 不带 target 时：自动检测已安装的平台，交互式选择。
- `--global`：安装到用户级配置（默认项目级；hermes 固定用户级）。
- `--yes`：跳过所有交互提示（CI 友好）。
- `openclaw`：暂未实现，执行时提示并正常退出。

### 示例

```bash
# 交互式安装（自动检测平台）
agentarts-memory install

# 安装 hermes（用户级，自动确认）
agentarts-memory install hermes --global --yes

# 卸载 claude（用户级，自动确认）
agentarts-memory uninstall claude --global --yes
```

## 各平台落点速查

| 平台 | 项目级 | 用户级 | 部署内容 | 注册方式 |
|---|---|---|---|---|
| hermes | —（固定用户级） | `~/.hermes/hermes-agent/plugins/memory/agentarts/` | `provider.py` + `plugin.yaml` + `__init__.py` | `.env` 写 API Key；`agentarts.json` 写 space_id/region |
| claude | `.claude/` | `~/.claude/` | 13 个 `.mjs` 脚本 → `agentarts-memory/scripts/` | `settings.json` 的 `hooks`（绝对路径，12 个 hook） |
| codex | `.codex/` | `~/.codex/` | 同上 13 个 `.mjs` 脚本 | `hooks.json` 合并（6 个 hook）+ `config.toml` 的 `[features] codex_hooks = true` |
| opencode | `.opencode/` | `~/.config/opencode/` | TS 插件 → `plugins/`、命令 → `commands/` | `opencode.json` 的 `plugin` 数组 |
| openclaw | — | — | 无（占位） | 无 |

> claude/codex/opencode 三平台共享 hook 脚本，运行时都调用本地适配 server（`127.0.0.1:8719`）。

## 凭证 / 环境变量

| 变量 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `AGENTARTS_MEMORY_SPACE_ID` | 是 | — | AgentArts 记忆库 ID |
| `HUAWEICLOUD_SDK_MEMORY_API_KEY` | 是 | — | AgentArts 记忆库 API Key |
| `HUAWEICLOUD_SDK_REGION` | 否 | `cn-southwest-2` | 区域 |

安装时检测这些环境变量，缺失则交互式提示输入（带校验）。

## 安装记录

安装记录保存在 `~/.agentarts-memory/installed.json`，支撑干净卸载：按清单精确移除我们部署的文件和注入的 hook 条目，不误删用户自有配置。

## 包结构

```
agentarts-memory-installer/
├── pyproject.toml                    # 入口 agentarts-memory = "cli:main"
├── __init__.py
├── cli.py                           # argparse 主入口（install/uninstall）
├── config.py                        # 凭证检测/交互补全
├── manifest.py                      # installed.json 读写
├── assets.py                        # 定位素材源目录
├── utils.py                         # 路径/JSON 合并摘除/TOML 合并/.env/状态输出/交互
└── platforms/
    ├── __init__.py                  # PLATFORMS 注册表
    ├── base.py                      # Platform 抽象基类 + InstallResult
    ├── hermes.py
    ├── claude.py
    ├── codex.py
    ├── opencode.py
    └── openclaw.py                  # 占位
```

## 测试

```bash
pytest tests/agentarts-memory-installer/ -v
```

测试使用 tmp HOME 隔离，不碰真实 `~`。核心场景：各平台 install→uninstall 往返、幂等性（连续安装不重复）、JSON/TOML 合并摘除往返。
