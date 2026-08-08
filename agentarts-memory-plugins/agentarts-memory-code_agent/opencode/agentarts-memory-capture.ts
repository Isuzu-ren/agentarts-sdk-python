// agentarts-memory-code_agent OpenCode plugin — TypeScript Plugin SDK implementation.
//
// Drop this file into ~/.config/opencode/plugins/ and reference it in
// ~/.config/opencode/opencode.json:
//   { "plugin": ["./plugins/agentarts-memory-capture.ts"] }
//
// Requires: @opencode-ai/plugin types (provided by OpenCode at runtime).

import type { Plugin } from "@opencode-ai/plugin";

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------
const REST_URL =
  process.env.AGENTARTS_MEMORY_SERVER_URL || "http://127.0.0.1:8719";
const DEBUG = process.env.AGENTARTS_MEMORY_DEBUG === "1";
const DEFAULT_USER_ID =
  process.env.AGENTARTS_MEMORY_USER_ID || "opencode-user";

const SEARCH_MEM_NUM = 5;
const SEARCH_SUMMARY_NUM = 3;
const DEFAULT_THRESHOLD = 0.3;

function authHeaders(): Record<string, string> {
  return { "Content-Type": "application/json" };
}

// ---------------------------------------------------------------------------
// HTTP helpers
// ---------------------------------------------------------------------------
async function post(
  path: string,
  body: Record<string, unknown>,
  timeoutMs = 3000,
): Promise<void> {
  try {
    const res = await fetch(`${REST_URL}/${path}`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (DEBUG && !res.ok)
      console.error(`[agentarts] POST /${path} returned ${res.status}`);
  } catch (e) {
    if (DEBUG) console.error(`[agentarts] POST /${path} failed:`, (e as Error).message);
  }
}

async function postJson(
  path: string,
  body: Record<string, unknown>,
  timeoutMs = 0,
): Promise<unknown | null> {
  try {
    const opts: RequestInit = {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify(body),
    };
    if (timeoutMs > 0) opts.signal = AbortSignal.timeout(timeoutMs);
    const res = await fetch(`${REST_URL}/${path}`, opts);
    if (res.ok) return await res.json();
    if (DEBUG) console.error(`[agentarts] POST /${path} returned ${res.status}`);
  } catch (e) {
    if (DEBUG)
      console.error(`[agentarts] POST /${path} (json) failed:`, (e as Error).message);
  }
  return null;
}

// ---------------------------------------------------------------------------
// High-level operations
// ---------------------------------------------------------------------------
async function addMessages(
  messages: Array<{ role: string; content: string }>,
  scopeId: string,
  userId = DEFAULT_USER_ID,
): Promise<void> {
  await post("add_messages/", { messages, user_id: userId, scope_id: scopeId });
}

async function searchAndFormat(
  query: string,
  scopeId: string,
  userId = DEFAULT_USER_ID,
): Promise<string> {
  const [memResult, summaryResult] = await Promise.all([
    postJson("search_memory/", {
      query,
      num: SEARCH_MEM_NUM,
      user_id: userId,
      scope_id: scopeId,
      threshold: DEFAULT_THRESHOLD,
    }),
    postJson("search_summary/", {
      query,
      num: SEARCH_SUMMARY_NUM,
      user_id: userId,
      scope_id: scopeId,
      threshold: DEFAULT_THRESHOLD,
    }),
  ]);

  const memItems = ((memResult as any)?.results || []) as Array<Record<string, unknown>>;
  const summaryItems = ((summaryResult as any)?.results || []) as Array<Record<string, unknown>>;
  const lines: string[] = [];

  if (memItems.length) {
    lines.push("## Related Memories");
    for (const r of memItems) {
      const label = r.type ? `[${r.type}]` : "";
      lines.push(
        `- ${label} ${String(r.content || "").slice(0, 300)} (score: ${Number(r.score || 0).toFixed(2)})`,
      );
    }
  }
  if (summaryItems.length) {
    if (lines.length) lines.push("");
    lines.push("## Related History Summaries");
    for (const r of summaryItems) {
      lines.push(
        `- ${String(r.content || "").slice(0, 300)} (score: ${Number(r.score || 0).toFixed(2)})`,
      );
    }
  }
  return lines.join("\n");
}

// ---------------------------------------------------------------------------
// System prompt instructions
// ---------------------------------------------------------------------------
const AGENTARTS_INSTRUCTIONS = `<agentarts-memory-instructions>
You have access to Huawei Cloud AgentArts Memory for persistent cross-session memory.

Relevant memories are automatically injected before each turn. The conversation prompt
is recorded to long-term memory after each user turn.

Use /recall [query] to search past memories, and /remember [content] to explicitly save.
Never fabricate memory results — only present what the tools return.
</agentarts-memory-instructions>`;

// ---------------------------------------------------------------------------
// Session state
// ---------------------------------------------------------------------------
let activeSessionId: string | null = null;
const DEFAULT_SCOPE_ID = process.env.AGENTARTS_MEMORY_PROJECT_NAME || "opencode-default";
let projectScopeId: string = DEFAULT_SCOPE_ID;
const contextInjectedSessions = new Set<string>();
const sessionLastUserQuery = new Map<string, string>();
const sessionPendingAdd = new Map<string, string>();
const sessionSearchResult = new Map<string, string>();

// ---------------------------------------------------------------------------
// Plugin
// ---------------------------------------------------------------------------
export const AgentArtsMemoryCapturePlugin: Plugin = async (ctx) => {
  const cwd = ctx.worktree || ctx.project?.id || "";
  if (cwd) {
    const raw = cwd.replace(/[\\/]+$/, "");
    const derived = raw.split(/[\\/]/).pop()?.trim();
    if (derived) projectScopeId = derived;
  }

  return {
    event: async ({ event }) => {
      const type = event.type;
      const props = (event as any).properties || {};

      // ── session.created ──
      if (type === "session.created") {
        const info = props.info as Record<string, unknown> | undefined;
        activeSessionId = (info?.id as string) || props.sessionID || null;
        if (!activeSessionId) return;
        contextInjectedSessions.delete(activeSessionId);
        sessionLastUserQuery.delete(activeSessionId);
        sessionPendingAdd.delete(activeSessionId);
        sessionSearchResult.delete(activeSessionId);
        // Probe health — best-effort, never fatal.
        try {
          await fetch(`${REST_URL}/health`, {
            method: "GET",
            headers: authHeaders(),
            signal: AbortSignal.timeout(800),
          });
        } catch {}
      }

      // ── session.deleted ──
      if (type === "session.deleted") {
        const sid = (props.info as any)?.id || props.sessionID || activeSessionId;
        if (sid) {
          if (sid === activeSessionId) activeSessionId = null;
          contextInjectedSessions.delete(sid);
          sessionLastUserQuery.delete(sid);
          sessionPendingAdd.delete(sid);
          sessionSearchResult.delete(sid);
        }
      }

      // ── message.updated (assistant) ──
      // AI 回复结束后，把之前存的用户 query 写入记忆（延后写入避免打断对话）
      if (type === "message.updated") {
        const info = props.info as Record<string, unknown> | undefined;
        if (!info) return;
        if (info.role === "assistant") {
          const sid = props.sessionID || (info.sessionID as string) || activeSessionId;
          if (!sid) return;
          const pendingQuery = sessionPendingAdd.get(sid);
          if (!pendingQuery) return;
          sessionPendingAdd.delete(sid);
          await addMessages([{ role: "user", content: pendingQuery }], projectScopeId);
        }
      }
    },

    // ── chat.message ──
    // Store the user query, mark it pending for later add, AND run the search.
    "chat.message": async (input: any, output: any) => {
      const sid = input.sessionID || activeSessionId;
      if (!sid) return;

      const parts = output.parts || [];
      const textParts = parts.filter(
        (p: any) => p.type === "text" && !p.synthetic && !p.ignored,
      );
      const userText = textParts.map((p: any) => p.text || "").join("\n");
      if (!userText) return;

      const query = userText.slice(0, 2000);

      sessionLastUserQuery.set(sid, query);
      sessionPendingAdd.set(sid, userText.slice(0, 8000));

      // Search once per user message, cache the result.
      const searchResult = await searchAndFormat(query, projectScopeId, DEFAULT_USER_ID);
      if (searchResult) sessionSearchResult.set(sid, searchResult);
      else sessionSearchResult.delete(sid);
    },

    // ── experimental.chat.system.transform ──
    "experimental.chat.system.transform": async (input: any, output: any) => {
      const sid = input.sessionID || activeSessionId;
      if (!sid) return;
      if (!Array.isArray(output.system)) return;

      // Inject usage instructions once per session.
      if (!contextInjectedSessions.has(sid)) {
        output.system.push(AGENTARTS_INSTRUCTIONS);
        contextInjectedSessions.add(sid);
      }

      // Inject cached search result (read-only, no re-search).
      const cachedResult = sessionSearchResult.get(sid);
      if (cachedResult) {
        output.system.push(cachedResult);
      }
    },

    // ── experimental.session.compacting ──
    "experimental.session.compacting": async (input: any, output: any) => {
      const sid = input.sessionID || activeSessionId;
      if (!sid) return;

      const cachedResult = sessionSearchResult.get(sid);
      const context =
        cachedResult ||
        (sessionLastUserQuery.has(sid)
          ? await searchAndFormat(sessionLastUserQuery.get(sid)!, projectScopeId, DEFAULT_USER_ID)
          : "");
      if (context && Array.isArray(output.context)) {
        output.context.push(context);
      }
    },

    // ── config ──
    config: async (input: any) => {
      if (DEBUG) {
        console.error("[agentarts] config loaded:", { theme: input.theme, model: input.model });
      }
    },
  };
};
