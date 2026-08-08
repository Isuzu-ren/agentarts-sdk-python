"""Entry point to launch the AgentArts Memory adapter server."""

from __future__ import annotations

import uvicorn

def main() -> None:
    import os

    host = os.getenv("AGENTARTS_MEMORY_SERVER_HOST", "127.0.0.1")
    port = int(os.getenv("AGENTARTS_MEMORY_SERVER_PORT", "8719"))
    uvicorn.run(
        "server.app:app",
        host=host,
        port=port,
        log_level=os.getenv("AGENTARTS_MEMORY_LOG_LEVEL", "info"),
    )


if __name__ == "__main__":
    main()
