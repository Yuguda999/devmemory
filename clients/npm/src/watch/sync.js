// On-demand sync — one scan of every local tool store, pushing new turns to the
// backend. Ported from the Python daemon's poll_once/_process/_exchanges + the
// sync_now entrypoint. This is how the Node client captures conversations WITHOUT
// a persistent daemon: `devmemory continue` (and the continue_here MCP tool)
// trigger one scoped scan of the local disk stores at session start.

import { apiCall } from "../api.js";
import { availableAdapters, key as convKey } from "./adapters.js";
import { resolveConversationProject, shouldSave } from "./project.js";
import { WatchState } from "./state.js";

const USER_CAP = 1500;
const ASSISTANT_CAP = 3000;

/**
 * Group an ordered message list into "User asked / Assistant response" blocks.
 * Consecutive same-role messages concatenate; a new user turn after an assistant
 * reply closes the previous block. Mirrors the Python daemon's `_exchanges`.
 */
export function exchanges(messages) {
  const blocks = [];
  let pendingUser = [];
  let pendingAssistant = [];

  const flush = () => {
    if (!pendingAssistant.length && !pendingUser.length) return;
    const user = pendingUser.join("\n").trim().slice(0, USER_CAP);
    const assistant = pendingAssistant.join("\n").trim().slice(0, ASSISTANT_CAP);
    const parts = [];
    if (user) parts.push(`User asked:\n${user}`);
    if (assistant) parts.push(`Assistant response:\n${assistant}`);
    if (parts.length) blocks.push(parts.join("\n\n"));
    pendingUser = [];
    pendingAssistant = [];
  };

  for (const msg of messages) {
    if (msg.role === "assistant") {
      pendingAssistant.push(msg.text);
    } else {
      if (pendingAssistant.length) flush();
      pendingUser.push(msg.text);
    }
  }
  flush();
  return blocks;
}

async function saveBlock(apiKey, project, content, sessionId) {
  const json = { project, block_type: "note", content, priority: 3 };
  if (sessionId) json.session_id = sessionId;
  const resp = await apiCall("POST", "/context", { apiKey, json });
  if (resp && resp.ok === false) throw new Error(resp.error || "save failed");
  return (resp && resp.session_id) || sessionId || null;
}

async function processConv(conv, state, apiKey, scopeSlug) {
  const k = convKey(conv);
  const already = state.savedCount(k);
  if (conv.messages.length <= already) return 0;

  const project = resolveConversationProject(conv.paths, conv.title, conv.remoteUrl);
  if (!project) return 0;
  if (scopeSlug != null && project.slug !== scopeSlug) return 0;

  const newMessages = conv.messages.slice(already);
  const blocks = exchanges(newMessages);
  if (!blocks.length) {
    // Consumed messages produced no saveable block — still advance the watermark
    // so we don't re-scan them forever.
    state.record(k, conv.messages.length, state.sessionId(k));
    return 0;
  }

  if (!shouldSave(project.slug)) return 0;

  let sessionId = state.sessionId(k);
  let saved = 0;
  for (const block of blocks) {
    const content = `[${conv.tool}] ${conv.title}\n\n${block}`;
    try {
      sessionId = (await saveBlock(apiKey, project, content, sessionId)) || sessionId;
      saved += 1;
    } catch {
      break; // network/backend/quota — stop this conv, keep the watermark honest
    }
  }

  // Advance watermark only if every block saved; else leave the unsaved tail.
  if (saved === blocks.length) state.record(k, conv.messages.length, sessionId);
  else state.record(k, already, sessionId);
  state.save();
  return saved;
}

/**
 * Run ONE scan of every local tool store and push new turns to the backend.
 * scopeSlug (optional) restricts saving to a single project; every other
 * project's watermark is left untouched. Never throws — a failed sync must never
 * break the caller (e.g. a restore). Returns the number of blocks saved.
 */
export async function syncNow(scopeSlug = null, apiKey) {
  let adapters;
  try {
    adapters = availableAdapters();
  } catch {
    return 0;
  }
  if (!adapters.length) return 0;

  const state = new WatchState();
  let total = 0;
  for (const adapter of adapters) {
    let convs;
    try {
      convs = adapter.conversations();
    } catch {
      continue; // one adapter failing must not sink the rest
    }
    for (const conv of convs) {
      try {
        total += await processConv(conv, state, apiKey, scopeSlug);
      } catch {
        /* skip a bad conversation */
      }
    }
  }
  return total;
}
