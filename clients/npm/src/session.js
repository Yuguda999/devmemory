// `devmemory start | continue | stop | status` — the attach model (Node client).
//
// Writes the SAME ~/.devmemory/active.json marker + config.json the Python client
// uses, so a session attached here is honored by the Python watch daemon + hooks.
// The watch daemon itself is Python-only, so `start` does not spawn one — it
// attaches (scopes auto-save), persists the backend, and restores context.

import { host } from "./config.js";
import { resolveProject } from "./git.js";
import { runInject } from "./inject.js";
import { clearActive, readActive, writeActive, writeConfig } from "./store.js";
import { syncNow } from "./watch/sync.js";

// Scan local tool stores for this project and push new turns to the backend.
// Awaited (not fire-and-forget) because the CLI process exits when the command
// returns — a detached scan would be killed. Scoped + watermarked, so after the
// first drain it's fast. Never throws.
async function syncProject(slug, apiKey) {
  try {
    const n = await syncNow(slug, apiKey);
    if (n) console.log(`   Synced ${n} new turn(s) from local tool history.`);
  } catch {
    /* sync is best-effort */
  }
}

const DAEMON_NOTE =
  "   Auto-save for hook tools (Claude Code, Windsurf) runs via hooks from `devmemory install`.\n" +
  "   Local tool history (Claude Code, Cursor, Cline, Kilo, Codex) is scanned + pushed\n" +
  "   on demand each time you run `devmemory continue`. For near-real-time capture,\n" +
  "   run the optional Python daemon: pipx install devmemory-ai  &&  devmemory watch";

function persistConn({ host: h, apiKey }) {
  writeConfig({ host: h, api_key: apiKey });
}

async function restore(dir, tool, apiKey) {
  try {
    await runInject({ cwd: dir, tool, apiKey });
  } catch (e) {
    console.error(`⚠️  restore skipped: ${e.message}`);
  }
}

export async function runStart({ cwd, tool, host: h, apiKey }) {
  persistConn({ host: h, apiKey });
  const dir = cwd || process.cwd();
  const t = tool || "unknown";
  const project = resolveProject(dir);
  const marker = writeActive(project, t);
  console.log(`▶️  DevMemory attached to '${marker.name}' (${marker.slug}) via ${t}.`);
  console.log(`   Backend: ${host()}`);
  await syncProject(marker.slug, apiKey);
  await restore(dir, t, apiKey);
  console.log("   Switch tools later with: devmemory continue");
  console.log(DAEMON_NOTE);
}

export async function runContinue({ cwd, tool, host: h, apiKey }) {
  persistConn({ host: h, apiKey });
  const active = readActive();
  if (!active) {
    console.error("❌ No active session. Run `devmemory start` in a project first.");
    process.exit(1);
  }
  const dir = cwd || process.cwd();
  const t = tool || "unknown";
  const marker = writeActive(
    { slug: active.slug, name: active.name, remote_url: active.remote_url },
    t,
  );
  console.log(`⏩ Continuing '${marker.name}' (${marker.slug}) in ${t}.`);
  await syncProject(marker.slug, apiKey);
  await restore(dir, t, apiKey);
}

export function runStop() {
  const active = readActive();
  clearActive();
  if (active) {
    console.log(`⏹️  Detached from '${active.name}' (${active.slug}). Auto-save OFF.`);
    console.log("   (Any running Python watch daemon idles once the marker is cleared.)");
  } else {
    console.log("⏹️  No active session.");
  }
}

export function runStatus() {
  const active = readActive();
  if (!active) {
    console.log("DevMemory: no active session. Run `devmemory start` to attach.");
    return;
  }
  console.log("DevMemory active session:");
  console.log(`  project : ${active.name} (${active.slug})`);
  console.log(`  tool    : ${active.tool || "unknown"}`);
  console.log(`  backend : ${host()}`);
  console.log(`  since   : ${active.started_at || "?"}`);
}
