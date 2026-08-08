"""FastAPI application exposing AgentArts Memory over local HTTP.

Endpoints (trailing slash to match the convention used by hook scripts):
  GET  /health
  POST /add_messages/
  POST /search_memory/
  POST /list_memories/
  POST /search_summary/
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .agentarts_client import (
    DEFAULT_LIST_LIMIT,
    DEFAULT_MIN_SCORE,
    DEFAULT_TOP_K,
    AgentArtsMemoryClient,
)

logger = logging.getLogger("agentarts_memory_code_agent.server")

# ── single shared client instance ──
_client: AgentArtsMemoryClient | None = None


def get_client() -> AgentArtsMemoryClient:
    global _client
    if _client is None:
        _client = AgentArtsMemoryClient()
    return _client


def reset_client(client: AgentArtsMemoryClient | None = None) -> None:
    """Replace the shared client (used by tests)."""
    global _client
    _client = client


# ── request models ──
class MessageItem(BaseModel):
    role: str
    content: str


class AddMessagesRequest(BaseModel):
    messages: list[MessageItem]
    user_id: str = "cc-user"
    scope_id: str = "default"


class SearchRequest(BaseModel):
    query: str
    num: int = Field(default=DEFAULT_TOP_K, ge=1, le=100)
    user_id: str = "cc-user"
    scope_id: str = "default"
    threshold: float = Field(default=DEFAULT_MIN_SCORE, ge=0.0, le=1.0)


class ListRequest(BaseModel):
    limit: int = Field(default=DEFAULT_LIST_LIMIT, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    user_id: str | None = None
    scope_id: str | None = None


app = FastAPI(
    title="AgentArts Memory Agent Server",
    version="0.1.0",
    description="Local HTTP adapter over Huawei Cloud AgentArts Memory for Claude Code / Codex / OpenCode hooks.",
)


@app.get("/health")
def health() -> dict[str, Any]:
    return get_client().health()


@app.post("/add_messages/")
def add_messages(req: AddMessagesRequest) -> dict[str, Any]:
    try:
        return get_client().add_messages(
            [m.model_dump() for m in req.messages],
            user_id=req.user_id,
            scope_id=req.scope_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("add_messages failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/search_memory/")
def search_memory(req: SearchRequest) -> dict[str, Any]:
    try:
        results = get_client().search_memories(
            query=req.query,
            user_id=req.user_id,
            scope_id=req.scope_id,
            num=req.num,
            threshold=req.threshold,
        )
        return {"results": results, "total": len(results), "query": req.query}
    except Exception as exc:  # noqa: BLE001
        logger.warning("search_memory failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/list_memories/")
def list_memories(req: ListRequest) -> dict[str, Any]:
    try:
        results = get_client().list_memories(
            user_id=req.user_id,
            scope_id=req.scope_id,
            limit=req.limit,
            offset=req.offset,
        )
        return {"results": results, "total": len(results)}
    except Exception as exc:  # noqa: BLE001
        logger.warning("list_memories failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/search_summary/")
def search_summary(req: SearchRequest) -> dict[str, Any]:
    """Summary search — reuse list_memories filtered to summary-like types.

    AgentArts has no dedicated summary endpoint, so we list memories and
    return those whose strategy_type looks summary-like; falling back to the
    full list when no summary-type memories exist.
    """
    try:
        all_mem = get_client().list_memories(
            user_id=req.user_id,
            scope_id=req.scope_id,
            limit=max(req.num * 5, DEFAULT_LIST_LIMIT),
            offset=0,
        )
        summary_types = {"summary", "episodic", "user_preference"}
        summaries = [m for m in all_mem if m.get("type") in summary_types]
        if not summaries:
            summaries = all_mem
        summaries = summaries[: req.num]
        return {"results": summaries, "total": len(summaries), "query": req.query}
    except Exception as exc:  # noqa: BLE001
        logger.warning("search_summary failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
