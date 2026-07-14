// Local-store adapters — ported from the Python daemon's watch/adapters/*.
//
// Each adapter reads one AI tool's on-disk conversation store and yields a
// uniform shape: { tool, id, title, messages:[{role,text}], paths:[], remoteUrl }.
// `id` must be stable across scans so the watermark tracks it.
//
// File-based adapters (Claude Code, Cline/Kilo, Codex rollout, generic) work on
// any Node >=18. The SQLite-backed adapters (Cursor, Codex thread index) need
// `node:sqlite` (Node >=22.5); where it's unavailable they simply report
// unavailable, so nothing breaks on older runtimes — no native dependency.

import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { homedir, platform } from "node:os";
import { basename, join } from "node:path";

// ── Optional node:sqlite (Node >=22.5) ──────────────────────────────────────
let DatabaseSync = null;
try {
  ({ DatabaseSync } = await import("node:sqlite"));
} catch {
  /* older Node — Cursor/Codex-index adapters stay unavailable */
}

function openRo(dbPath) {
  if (!DatabaseSync || !existsSync(dbPath)) return null;
  try {
    return new DatabaseSync(dbPath, { readOnly: true });
  } catch {
    return null;
  }
}

function home(p) {
  return p.replace(/^~/, homedir());
}

function readLines(path) {
  try {
    return readFileSync(path, "utf8").split(/\r?\n/);
  } catch {
    return null;
  }
}

function key(conv) {
  return `${conv.tool}:${conv.id}`;
}

// ── Claude Code — ~/.claude/projects/<slug>/<sessionId>.jsonl ────────────────
const CLAUDE_ROLES = new Set(["user", "assistant"]);

function claudeText(content) {
  if (typeof content === "string") return content.trim();
  if (Array.isArray(content)) {
    const parts = [];
    for (const b of content) {
      if (b && typeof b === "object") {
        if (b.type === "text" || (b.text !== undefined && b.type === undefined)) {
          parts.push(b.text || "");
        }
      } else if (typeof b === "string") {
        parts.push(b);
      }
    }
    return parts.filter(Boolean).join("\n").trim();
  }
  return "";
}

function claudeMessage(obj) {
  if (!CLAUDE_ROLES.has(obj.type)) return null;
  if (obj.isSidechain) return null;
  const msg = obj.message;
  if (!msg || typeof msg !== "object") return null;
  if (!CLAUDE_ROLES.has(msg.role)) return null;
  const text = claudeText(msg.content);
  if (!text) return null;
  return { role: msg.role, text };
}

class ClaudeCodeAdapter {
  constructor(dir) {
    this.name = "claude-code";
    this._dir = dir || join(homedir(), ".claude", "projects");
  }

  _files() {
    if (!existsSync(this._dir)) return [];
    const files = [];
    for (const sub of readdirSync(this._dir)) {
      const subPath = join(this._dir, sub);
      try {
        if (!statSync(subPath).isDirectory()) continue;
        for (const f of readdirSync(subPath)) {
          if (f.endsWith(".jsonl")) files.push(join(subPath, f));
        }
      } catch {
        /* skip unreadable dir */
      }
    }
    return files.sort();
  }

  available() {
    return this._files().length > 0;
  }

  conversations() {
    const out = [];
    for (const file of this._files()) {
      const conv = this._build(file);
      if (conv && conv.messages.length) out.push(conv);
    }
    return out;
  }

  _build(file) {
    const lines = readLines(file);
    if (lines === null) return null;
    const messages = [];
    const cwds = [];
    for (const line of lines) {
      const t = line.trim();
      if (!t) continue;
      let obj;
      try {
        obj = JSON.parse(t);
      } catch {
        continue;
      }
      if (!obj || typeof obj !== "object") continue;
      if (typeof obj.cwd === "string" && obj.cwd && !cwds.includes(obj.cwd)) cwds.push(obj.cwd);
      const msg = claudeMessage(obj);
      if (msg) messages.push(msg);
    }
    let title = "";
    for (const m of messages) {
      if (m.role === "user" && m.text) {
        title = m.text.split(/\r?\n/)[0].slice(0, 120);
        break;
      }
    }
    return {
      tool: this.name,
      id: file,
      title: title || basename(file, ".jsonl").slice(0, 120),
      messages,
      paths: cwds,
      remoteUrl: null,
    };
  }
}

// ── Cline / Kilo — VS Code globalStorage tasks/<id>/api_conversation_history.json
const CODE_USER = {
  linux: "~/.config/Code/User/globalStorage",
  darwin: "~/Library/Application Support/Code/User/globalStorage",
  win32: "~/AppData/Roaming/Code/User/globalStorage",
};
const CWD_RE = /Current Working Directory \(([^)]+)\)/g;

function clineText(content) {
  if (typeof content === "string") return content.trim();
  if (Array.isArray(content)) {
    return content
      .filter((b) => b && typeof b === "object" && b.type === "text")
      .map((b) => b.text || "")
      .filter(Boolean)
      .join("\n")
      .trim();
  }
  return "";
}

class ClineAdapter {
  constructor(tasksDir, name = "cline", extId = "saoudrizwan.claude-dev") {
    this.name = name;
    const root = home(CODE_USER[platform()] || CODE_USER.linux);
    this._tasksDir = tasksDir || join(root, extId, "tasks");
  }

  available() {
    try {
      return statSync(this._tasksDir).isDirectory();
    } catch {
      return false;
    }
  }

  conversations() {
    if (!this.available()) return [];
    const out = [];
    let entries;
    try {
      entries = readdirSync(this._tasksDir).sort();
    } catch {
      return [];
    }
    for (const taskId of entries) {
      const hist = join(this._tasksDir, taskId, "api_conversation_history.json");
      if (!existsSync(hist)) continue;
      const conv = this._build(taskId, hist);
      if (conv && conv.messages.length) out.push(conv);
    }
    return out;
  }

  _build(taskId, hist) {
    let raw;
    try {
      raw = JSON.parse(readFileSync(hist, "utf8"));
    } catch {
      return null;
    }
    if (!Array.isArray(raw)) return null;
    const messages = [];
    const paths = [];
    let title = "";
    for (const entry of raw) {
      if (!entry || typeof entry !== "object") continue;
      if (entry.role !== "user" && entry.role !== "assistant") continue;
      const text = clineText(entry.content);
      if (!text) continue;
      for (const m of text.matchAll(CWD_RE)) paths.push(m[1].trim());
      const clean = text.split("<environment_details>")[0].trim();
      if (!clean) continue;
      if (entry.role === "user" && !title) title = clean.slice(0, 120);
      messages.push({ role: entry.role, text: clean });
    }
    return {
      tool: this.name,
      id: taskId,
      title: title || `${this.name} task ${taskId}`,
      messages,
      paths,
      remoteUrl: null,
    };
  }
}

class KiloAdapter extends ClineAdapter {
  constructor(tasksDir) {
    super(tasksDir, "kilo", "kilocode.kilo-code");
  }
}

// ── Codex — ~/.codex/state_*.sqlite (threads index) + rollout JSONL ──────────
const CODEX_ROLES = new Set(["user", "assistant"]);

function codexText(content) {
  if (typeof content === "string") return content.trim();
  if (Array.isArray(content)) {
    const parts = [];
    for (const b of content) {
      if (b && typeof b === "object") {
        if (["input_text", "output_text", "text"].includes(b.type) || b.text !== undefined) {
          parts.push(b.text || "");
        }
      } else if (typeof b === "string") {
        parts.push(b);
      }
    }
    return parts.filter(Boolean).join("\n").trim();
  }
  return "";
}

function codexMessage(obj) {
  let node = obj;
  if (node.payload && typeof node.payload === "object") node = node.payload;
  if (![undefined, "message", "response_item"].includes(node.type) && node.role === undefined) {
    return null;
  }
  if (!CODEX_ROLES.has(node.role)) return null;
  const text = codexText(node.content);
  if (!text) return null;
  return { role: node.role, text };
}

function codexStateDbs() {
  const dir = join(homedir(), ".codex");
  try {
    return readdirSync(dir)
      .filter((f) => /^state_.*\.sqlite$/.test(f))
      .sort()
      .map((f) => join(dir, f));
  } catch {
    return [];
  }
}

class CodexAdapter {
  constructor(stateDb) {
    this.name = "codex";
    this._explicit = stateDb || null;
  }

  _dbs() {
    if (this._explicit) return existsSync(this._explicit) ? [this._explicit] : [];
    return codexStateDbs();
  }

  available() {
    if (!DatabaseSync) return false;
    for (const dbPath of this._dbs()) {
      const db = openRo(dbPath);
      if (!db) continue;
      try {
        const has = db
          .prepare("SELECT 1 FROM sqlite_master WHERE type='table' AND name='threads'")
          .get();
        if (has) return true;
      } catch {
        /* skip */
      } finally {
        db.close();
      }
    }
    return false;
  }

  conversations() {
    const out = [];
    for (const dbPath of this._dbs()) {
      const db = openRo(dbPath);
      if (!db) continue;
      let rows = [];
      try {
        rows = db
          .prepare("SELECT id, rollout_path, cwd, git_origin_url, title FROM threads")
          .all();
      } catch {
        db.close();
        continue;
      }
      db.close();
      for (const r of rows) {
        const conv = this._build(r.id, r.rollout_path, r.cwd, r.git_origin_url, r.title);
        if (conv && conv.messages.length) out.push(conv);
      }
    }
    return out;
  }

  _build(threadId, rolloutPath, cwd, gitUrl, title) {
    if (!rolloutPath) return null;
    const path = home(String(rolloutPath));
    if (!existsSync(path)) return null;
    const lines = readLines(path);
    if (lines === null) return null;
    const messages = [];
    for (const line of lines) {
      const t = line.trim();
      if (!t) continue;
      let obj;
      try {
        obj = JSON.parse(t);
      } catch {
        continue;
      }
      if (!obj || typeof obj !== "object") continue;
      const msg = codexMessage(obj);
      if (msg) messages.push(msg);
    }
    return {
      tool: this.name,
      id: String(threadId),
      title: (title || "Codex session").slice(0, 120),
      messages,
      paths: cwd ? [cwd] : [],
      remoteUrl: gitUrl || null,
    };
  }
}

// ── Cursor — SQLite cursorDiskKV (composerData + bubbleId rows) ──────────────
const CURSOR_DB = {
  linux: "~/.config/Cursor/User/globalStorage/state.vscdb",
  darwin: "~/Library/Application Support/Cursor/User/globalStorage/state.vscdb",
  win32: "~/AppData/Roaming/Cursor/User/globalStorage/state.vscdb",
};
const CURSOR_ROLE = { 1: "user", 2: "assistant" };

function jloads(value) {
  if (!value) return null;
  try {
    const obj = JSON.parse(value);
    return obj && typeof obj === "object" ? obj : null;
  } catch {
    return null;
  }
}

function collectPaths(node, out, depth = 0) {
  if (depth > 7 || out.length > 40) return;
  if (typeof node === "string") {
    if (
      (node.startsWith("/") || node.startsWith("file://")) &&
      (node.match(/\//g) || []).length >= 2 &&
      node.length < 400
    ) {
      out.push(node);
    }
  } else if (Array.isArray(node)) {
    for (const v of node) collectPaths(v, out, depth + 1);
  } else if (node && typeof node === "object") {
    for (const v of Object.values(node)) collectPaths(v, out, depth + 1);
  }
}

class CursorAdapter {
  constructor(dbPath) {
    this.name = "cursor";
    this._db = dbPath || home(CURSOR_DB[platform()] || CURSOR_DB.linux);
  }

  available() {
    return Boolean(DatabaseSync) && existsSync(this._db);
  }

  conversations() {
    const db = openRo(this._db);
    if (!db) return [];
    const out = [];
    try {
      const rows = db
        .prepare("SELECT key, value FROM cursorDiskKV WHERE key LIKE 'composerData:%'")
        .all();
      const bubbleStmt = db.prepare("SELECT value FROM cursorDiskKV WHERE key = ?");
      for (const { key: k, value } of rows) {
        const conv = this._build(bubbleStmt, k, value);
        if (conv && conv.messages.length) out.push(conv);
      }
    } catch {
      /* schema mismatch → nothing */
    } finally {
      db.close();
    }
    return out;
  }

  _build(bubbleStmt, k, value) {
    const data = jloads(value);
    if (!data) return null;
    const composerId = data.composerId || k.split(":").slice(1).join(":");
    const title = (data.text || data.name || "Untitled Cursor chat").trim();
    const headers = data.fullConversationHeadersOnly;
    if (!Array.isArray(headers)) return null;
    const messages = [];
    const paths = [];
    for (const header of headers) {
      if (!header || typeof header !== "object") continue;
      const bubbleId = header.bubbleId;
      if (!bubbleId) continue;
      const role = CURSOR_ROLE[header.type];
      if (!role) continue;
      let row;
      try {
        row = bubbleStmt.get(`bubbleId:${composerId}:${bubbleId}`);
      } catch {
        continue;
      }
      const bubble = row ? jloads(row.value) : null;
      if (!bubble) continue;
      const text = (bubble.text || "").trim();
      collectPaths(bubble, paths);
      if (text) messages.push({ role, text });
    }
    return {
      tool: this.name,
      id: composerId,
      title: title.slice(0, 120) || "Untitled Cursor chat",
      messages,
      paths,
      remoteUrl: null,
    };
  }
}

export function availableAdapters() {
  const all = [
    new ClaudeCodeAdapter(),
    new CursorAdapter(),
    new ClineAdapter(),
    new KiloAdapter(),
    new CodexAdapter(),
  ];
  const out = [];
  for (const a of all) {
    try {
      if (a.available()) out.push(a);
    } catch {
      /* skip a broken adapter */
    }
  }
  return out;
}

export { ClaudeCodeAdapter, ClineAdapter, KiloAdapter, CodexAdapter, CursorAdapter, key };
