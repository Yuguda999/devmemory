// Local state under ~/.devmemory — shared by config, install, and the attach
// commands. These are the SAME files the Python client reads/writes
// (config.json, active.json), so the two clients interoperate: a marker written
// by `npx devmemory start` is honored by the Python watch daemon + hooks, and
// vice-versa.

import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

// Resolved lazily (not frozen at import) so a runtime HOME change — e.g. tests
// isolating a fresh HOME, or a process that re-homes itself — is honored.
const dir = () => join(homedir(), ".devmemory");
export const CONFIG_PATH = () => join(dir(), "config.json");
export const ACTIVE_PATH = () => join(dir(), "active.json");

function readJson(path) {
  try {
    return JSON.parse(readFileSync(path, "utf8"));
  } catch {
    return null;
  }
}

function writeJson(path, obj) {
  mkdirSync(dir(), { recursive: true });
  writeFileSync(path, `${JSON.stringify(obj, null, 2)}\n`, "utf8");
}

// ── Global config: { host, api_key } ────────────────────────────────────────
export function readConfig() {
  const d = readJson(CONFIG_PATH());
  return d && typeof d === "object" ? d : {};
}

export function writeConfig(kv) {
  const cfg = readConfig();
  for (const [k, v] of Object.entries(kv)) {
    if (v != null) cfg[k] = v;
  }
  writeJson(CONFIG_PATH(), cfg);
  // Keep the plaintext api_key file (read by config.js pickKey AND the Python
  // client) in sync — otherwise a stale key file shadows a fresh install's
  // config.json key and every call 401s. `install` should overwrite it.
  if (kv.api_key) {
    mkdirSync(dir(), { recursive: true });
    writeFileSync(join(dir(), "api_key"), `${String(kv.api_key).trim()}\n`, "utf8");
  }
  return cfg;
}

// ── Active-session marker: { slug, name, remote_url, tool, started_at } ──────
export function readActive() {
  const d = readJson(ACTIVE_PATH());
  return d && typeof d === "object" && d.slug ? d : null;
}

export function writeActive(project, tool) {
  const current = readActive();
  const started =
    current && current.slug === project.slug ? current.started_at : new Date().toISOString();
  const marker = {
    slug: project.slug,
    name: project.name,
    remote_url: project.remote_url ?? null,
    tool,
    started_at: started,
  };
  writeJson(ACTIVE_PATH(), marker);
  return marker;
}

export function clearActive() {
  try {
    rmSync(ACTIVE_PATH());
  } catch {
    /* already absent */
  }
}
