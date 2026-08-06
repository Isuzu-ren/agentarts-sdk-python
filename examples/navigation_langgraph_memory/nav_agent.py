"""
Navigation Agent Demo - LangGraph Agent with AgentArts Memory

A local interactive navigation assistant that can:
  - Search for POIs (gas stations, restaurants, parking, etc.)
  - Plan routes (driving/walking/riding/transit)
  - Generate map visualization links
  - Recall long-term user preferences and history via AgentArts Memory

Conversation state is persisted through AgentArtsMemorySessionSaver
(native SDK LangGraph checkpointer). The backend auto-extracts
memories using the four builtin strategies. Long-term recall uses a
hybrid approach: an auto_recall node searches AgentArtsMemoryStore
(SDK LangGraph Store) before each LLM call to inject relevant memories,
and the recall_memory tool provides on-demand deep search for specific
queries beyond the auto-injected context.

Prerequisites:
  1. Install dependencies:
       uv sync --extra langgraph --extra tui
     Or: pip install -r examples/navigation_langgraph_memory/requirements.txt
  2. Copy env template and fill in credentials:
       cp examples/navigation_langgraph_memory/.env.example examples/navigation_langgraph_memory/.env
  3. Create memory space (writes SPACE_ID + API_KEY to .env):
       uv run python examples/navigation_langgraph_memory/setup_memory.py
  4. Fill in LLM credentials in .env (OPENAI_API_KEY, etc.)
  5. (Optional) Set AMAP_KEY in .env for real AMap API calls

Usage:
  uv run python examples/navigation_langgraph_memory/nav_agent.py          # TUI mode (default)
  uv run python examples/navigation_langgraph_memory/nav_agent.py --cli    # Classic CLI mode
  uv run python examples/navigation_langgraph_memory/nav_agent.py --debug  # Show SDK logs
"""

import os
import sys

import config  # noqa: F401  (sets env vars as side effect)
from config import (
    ACTOR_ID,
    API_KEY,
    ASSISTANT_ID,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MODEL_NAME,
    SPACE_ID,
    VERIFY_SSL,
)


def _check_env():
    """Validate that required env vars are set before building the agent."""
    missing = []
    if not SPACE_ID:
        missing.append("AGENTARTS_MEMORY_SPACE_ID")
    if not API_KEY:
        missing.append("HUAWEICLOUD_SDK_MEMORY_API_KEY")
    if not OPENAI_API_KEY:
        missing.append("OPENAI_API_KEY")

    if missing:
        print("[ERR] Missing required environment variables:")
        for v in missing:
            print(f"    - {v}")
        print("\nRun setup first:  uv run python examples/navigation_langgraph_memory/setup_memory.py")
        print("Then export the printed variables and your OPENAI_API_KEY.")
        sys.exit(1)


def build_agent():
    """Build and compile the LangGraph navigation agent."""
    # Imports are deferred so _check_env() runs first and fails fast
    # without importing heavy modules.
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI
    from langgraph.graph import END, MessagesState, START, StateGraph
    from langgraph.prebuilt import ToolNode
    from langgraph.store.base import BaseStore

    from agentarts.sdk.integration.langgraph import (
        AgentArtsMemorySessionSaver,
        AgentArtsMemoryStore,
    )

    from amap_tools import generate_map_link, geocode_address, plan_route, search_poi
    from memory_tools import recall_memory

    class NavAgentState(MessagesState):
        """State with memory_context for auto-injected long-term memories.

        memory_context holds formatted memory text from the auto_recall
        node. It uses the default (replace) reducer: each auto_recall
        invocation overwrites the previous value.
        """

        memory_context: str

    SYSTEM_PROMPT = """\
You are a navigation assistant that helps users find places and plan routes.

Available tools:
- geocode_address: Convert a place name (e.g. "中关村") to coordinates.
  Call this FIRST when the user gives a place name and you need coordinates
  for plan_route or nearby search_poi.
- search_poi: Search for POIs (gas stations, restaurants, parking, etc.).
  Supports nearby search when location coordinates are provided.
- plan_route: Plan a route (driving/walking/riding/transit). Supports
  waypoints for driving and requires city for transit.
- generate_map_link: Generate a map visualization URL for locations
- recall_memory: Deep recall tool for specific historical queries.
  Relevant memories are auto-injected each turn (see [Memory Context]).
  Only call this tool when you need details BEYOND the auto-injected context.

Rules:
- Coordinates use "longitude,latitude" format, e.g. "116.481181,39.990021"
- When the user gives a place name (e.g. "中关村"), call geocode_address
  to get coordinates before planning routes or doing nearby search
- If the user's location is unknown, ask which city or area they are in
- When the user expresses a preference (e.g. "I like highways"), respond
  naturally - the memory system saves it automatically
- Use recall_memory only for deep queries beyond the auto-injected
  [Memory Context]; do NOT call it every turn
- Present POI options clearly with names and addresses before planning routes
"""

    all_tools = [geocode_address, search_poi, plan_route, generate_map_link, recall_memory]

    llm = ChatOpenAI(
        model=OPENAI_MODEL_NAME,
        api_key=OPENAI_API_KEY,
        base_url=OPENAI_BASE_URL or None,
        temperature=0,
    )
    llm_with_tools = llm.bind_tools(all_tools)

    def auto_recall(state: NavAgentState, *, store: BaseStore) -> dict:
        """Search Store for relevant long-term memories, inject as context.

        Runs before the agent node each turn. Searches the
        AgentArtsMemoryStore for memories matching the user's latest
        message, filtered by actor_id (cross-session, user-scoped).
        Results are stored in state["memory_context"] and appended to
        the system prompt by call_model. Failures are silent -- the
        agent continues without memories.
        """
        if not config.AUTO_RECALL_ENABLED:
            return {"memory_context": ""}

        last_msg = state["messages"][-1]
        if not isinstance(last_msg, HumanMessage):
            return {"memory_context": ""}

        query = last_msg.content
        try:
            items = store.search(
                (),
                query=query,
                filter={"actor_id": config.ACTOR_ID},
                limit=config.AUTO_RECALL_TOP_K,
            )
        except Exception as e:
            # Graceful degradation: never block the agent
            import logging
            logging.getLogger(__name__).warning(
                f"Auto-recall failed, continuing without memories: {e}")
            return {"memory_context": ""}

        if not items:
            return {"memory_context": ""}

        lines = []
        for item in items:
            content = item.value.get("content", "")
            strategy = item.value.get("strategy_type", "")
            if content:
                tag = f"[{strategy}] " if strategy else ""
                lines.append(f"- {tag}{content}")

        if not lines:
            return {"memory_context": ""}
        return {"memory_context": "\n".join(lines)}

    def call_model(state: NavAgentState):
        """Invoke LLM with system prompt, memory context, and message state."""
        system_content = SYSTEM_PROMPT
        memory_ctx = state.get("memory_context", "")
        if memory_ctx:
            system_content += f"\n\n[Memory Context]\n{memory_ctx}"
        messages = [SystemMessage(content=system_content)] + state["messages"]
        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}

    def should_continue(state: NavAgentState) -> str:
        """Route to tools node if LLM made tool calls, else end."""
        last = state["messages"][-1]
        if getattr(last, "tool_calls", None):
            return "tools"
        return END

    # Build graph: START -> auto_recall -> agent -> (tools?) -> agent/END
    workflow = StateGraph(NavAgentState)
    workflow.add_node("auto_recall", auto_recall)
    workflow.add_node("agent", call_model)
    workflow.add_node("tools", ToolNode(all_tools))
    workflow.add_edge(START, "auto_recall")
    workflow.add_edge("auto_recall", "agent")
    workflow.add_conditional_edges("agent", should_continue)
    workflow.add_edge("tools", "agent")

    # Checkpointer: conversation persists to AgentArts Memory
    # thread_id == session_id (created on-demand by session_manager.py)
    checkpointer = AgentArtsMemorySessionSaver(
        space_id=SPACE_ID,
        api_key=API_KEY,
        verify_ssl=VERIFY_SSL,
        max_messages=20,
    )

    # Store: cross-session long-term memory for auto-injection
    store = AgentArtsMemoryStore(
        space_id=SPACE_ID,
        api_key=API_KEY,
        verify_ssl=VERIFY_SSL,
    )

    return workflow.compile(checkpointer=checkpointer, store=store), checkpointer, store


def main():
    """Entry point - dispatches to TUI or CLI mode."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Navigation Agent Demo (LangGraph + AgentArts Memory)")
    parser.add_argument(
        "--debug", action="store_true",
        help="Show SDK INFO logs and debug prints (default: clean mode)")
    parser.add_argument(
        "--cli", action="store_true",
        help="Use classic CLI interface (default: TUI)")
    args = parser.parse_args()

    import cli_flags
    cli_flags.DEBUG = args.debug

    # Suppress SDK INFO logs in clean mode (must be set before any SDK import)
    if not cli_flags.DEBUG:
        os.environ["AGENTARTS_LOG_LEVEL"] = "WARNING"

    _check_env()

    if args.cli:
        main_cli()
    else:
        main_tui()


def main_cli():
    """Classic CLI mode - original implementation."""
    print("=" * 60)
    print("Navigation Agent Demo (LangGraph + AgentArts Memory)")
    print("=" * 60)
    print(f"  Space ID:   {SPACE_ID}")
    print(f"  Model:      {OPENAI_MODEL_NAME}")
    print(f"  AMap Key:   {'set' if config.AMAP_KEY else 'NOT set (using mock data)'}")
    print("=" * 60)

    # --- Session selection ---
    import session_manager
    session_id, session_title = session_manager.select_session_interactive()

    # Validate session exists in current space
    if not session_manager.validate_session(session_id):
        print(f"\n[WARN] Session {session_id[:8]}... not found in current space.")
        print("       This session may belong to a different space.")
        print("       Creating a new session...")
        new_session = session_manager.create_new_session(session_title)
        session_id = new_session["session_id"]
        session_title = new_session["title"]
        print(f"[OK] New session created: {session_id[:8]}...")

    # Set the active session for recall_memory tool
    import memory_tools
    memory_tools.set_current_session(session_id)

    print(f"\n  Active Session ID: {session_id}")
    print(f"  Session Title:     {session_title}")
    print("=" * 60)
    print("Type 'quit' / 'exit' to stop.")
    print()

    agent, checkpointer, store = build_agent()

    from langchain_core.messages import HumanMessage

    thread_config = {
        "configurable": {
            "thread_id": session_id,
            "actor_id": ACTOR_ID,
            "assistant_id": ASSISTANT_ID,
        }
    }

    message_count = 0
    title_auto_set = bool(session_title and not session_title.startswith("Session "))

    try:
        while True:
            try:
                user_input = input("you: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break

            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit", "q"):
                break

            # Auto-generate title from first message if not set
            if not title_auto_set:
                auto_title = user_input[:30] + ("..." if len(user_input) > 30 else "")
                session_manager.update_session_title(session_id, auto_title)
                session_title = auto_title
                title_auto_set = True

            result = agent.invoke(
                {"messages": [HumanMessage(content=user_input)]},
                config=thread_config,
            )

            message_count += 1
            reply = result["messages"][-1]
            reply_text = reply.content if hasattr(reply, "content") else str(reply)
            print(f"agent: {reply_text}\n")
    finally:
        # Update session metadata on exit
        session_manager.update_session(session_id, message_count)
        checkpointer.close()
        store.close()
        print(f"Session '{session_title}' ended. Conversation saved to AgentArts Memory.")


def main_tui():
    """TUI mode - Textual-based interactive interface."""
    import cli_flags
    from tui_encoding import ensure_utf8_streams
    from tui_app import NavAgentApp, TUIStdoutBridge

    ensure_utf8_streams()

    app = NavAgentApp(debug=cli_flags.DEBUG)

    # Redirect stdout to chat log
    bridge = TUIStdoutBridge(app)
    old_stdout = sys.stdout
    sys.stdout = bridge

    try:
        app.run()
    finally:
        sys.stdout = old_stdout  # Restore


if __name__ == "__main__":
    main()
