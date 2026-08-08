#!/usr/bin/env node
// UserPromptSubmit — record user query + inject relevant memories via stdout.
import {
  resolveProject,
  addMessages,
  searchAndFormat,
  isSdkChildContext,
  coerceText,
  formatOutput,
  DEFAULT_USER_ID,
} from "./_shared.mjs";

async function main() {
  let input = "";
  for await (const chunk of process.stdin) input += chunk;
  let data;
  try { data = JSON.parse(input); } catch { return; }
  if (isSdkChildContext(data)) return;

  const cwd = data.cwd || process.cwd();
  const scopeId = resolveProject(cwd);
  const prompt = coerceText(data.prompt ?? data.userPrompt ?? "");
  if (!prompt) return;

  // Fire-and-forget background write — never block the agent loop.
  addMessages([{ role: "user", content: prompt }], scopeId, DEFAULT_USER_ID).catch(() => {});

  // Search for relevant context and inject via stdout.
  const context = await searchAndFormat(prompt, scopeId, DEFAULT_USER_ID);
  if (context) process.stdout.write(formatOutput(context, "userPromptSubmit"));

  setTimeout(() => process.exit(0), 300).unref();
}

main();
