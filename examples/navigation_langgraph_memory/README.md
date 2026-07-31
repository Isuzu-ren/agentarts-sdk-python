# Navigation Agent Demo

A local interactive navigation assistant built with LangGraph and the
AgentArts Memory SDK. The agent can search for places, plan routes,
generate map links, and recall long-term user preferences.

## Architecture

```
[User input] -> [LangGraph agent (LLM + tools)]
                    |                 |
              tool_calls?          no tool_calls
                    v                 v
              [ToolNode] <--- loop --  [reply]
                    |
     geocode_address / search_poi / plan_route / generate_map_link / recall_memory
                    |
         [AMap API] / [AgentArts Memory search]
```

- **Short-term memory**: `AgentArtsMemorySessionSaver` checkpointer
  persists conversation state to AgentArts Memory. The backend
  auto-extracts memories using four builtin strategies (semantic,
  episodic, user_preference, summary).
- **Long-term recall**: the `recall_memory` tool performs semantic
  search over extracted memories when the LLM needs historical context.
- **Navigation**: AMap (Gaode) Web Service API for POI search and
  route planning. Falls back to mock data when `AMAP_KEY` is not set.

## Prerequisites

```bash
# Install dependencies (langgraph + tui)
uv sync --extra langgraph --extra tui
# Or: pip install -r examples/navigation_langgraph_memory/requirements.txt

# Copy the env template and fill in your credentials
cp examples/navigation_langgraph_memory/.env.example examples/navigation_langgraph_memory/.env
# Edit examples/navigation_langgraph_memory/.env with your API keys
```

## Quick Start

### 1. Create a memory space (run once)

```bash
uv run python examples/navigation_langgraph_memory/setup_memory.py
```

This creates a memory space and automatically writes `AGENTARTS_MEMORY_SPACE_ID`
and `HUAWEICLOUD_SDK_MEMORY_API_KEY` into `examples/navigation_langgraph_memory/.env`.

### 2. Fill in LLM credentials

Edit `examples/navigation_langgraph_memory/.env` and set your LLM provider keys:

```
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL_NAME=gpt-4o-mini
```

### 3. (Optional) Set AMap key for real navigation data

In `examples/navigation_langgraph_memory/.env`:

```
AMAP_KEY=your-amap-web-service-key
```

Without this key, the agent uses mock POI/route data so the graph
logic can still be exercised.

### 4. Start the agent

```bash
# TUI mode (default)
uv run python examples/navigation_langgraph_memory/nav_agent.py

# Classic CLI mode
uv run python examples/navigation_langgraph_memory/nav_agent.py --cli

# Debug mode (show SDK logs)
uv run python examples/navigation_langgraph_memory/nav_agent.py --debug
```

## Example Session

```
you: 帮我找附近的加油站
agent: [calls search_poi] Found 3 gas stations near you:
  1. 中石化朝阳加油站 - 朝阳路88号
  2. 中石油建国路加油站 - 建国路100号
  3. 壳牌三环加油站 - 南三环西路6号
  Which one would you like to navigate to?

you: 帮我规划到第一个的驾车路线
agent: [calls plan_route] Driving route to 中石化朝阳加油站:
  Distance: 12.5km, Duration: ~28min
  Nav link: https://uri.amap.com/navigation?to=...

you: 我喜欢走高速
agent: Got it - you prefer highway routes. I'll keep that in mind.

you: 我之前说过什么偏好？
agent: [calls recall_memory] You mentioned: you prefer highway routes.
```

## Files

| File | Purpose |
|------|---------|
| `config.py` | Env vars, constants, shared config |
| `setup_memory.py` | One-time: create memory space |
| `amap_tools.py` | AMap API wrappers (geocode_address, search_poi, plan_route, generate_map_link) |
| `memory_tools.py` | recall_memory tool (semantic search) |
| `session_manager.py` | Multi-session management (create/resume/list) |
| `nav_agent.py` | LangGraph agent + interactive CLI/TUI |
| `tui_app.py` | Textual TUI interface |
| `tui_encoding.py` | Windows UTF-8 compatibility |
| `cli_flags.py` | Shared DEBUG flag |
| `.env.example` | Environment variable template |
| `requirements.txt` | Dependencies for pip users |

## Notes

- `VERIFY_SSL` defaults to `true`. Set to `false` in `.env` for internal network environments with self-signed certs.
- Sessions are created on demand at agent startup; metadata is stored locally
  in `sessions.json` so previous conversations can be resumed.
- Backend memory extraction runs on a ~30s idle timer; wait before testing `recall_memory`.
