// `devmemory install` — write the DevMemory MCP entry into an AI tool's config.
// The MCP server is launched as `npx -y devmemory mcp`, so no global install or
// PATH juggling is needed.

import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir, platform } from "node:os";
import { dirname, join } from "node:path";

import { writeConfig } from "./store.js";

const HOME = homedir();
const APPDATA = process.env.APPDATA || join(HOME, "AppData", "Roaming");

function expand(p) {
  return p
    .replace(/^~/, HOME)
    .replace(/%APPDATA%/g, APPDATA)
    .replace(/%USERPROFILE%/g, HOME);
}

// slug → { name, paths per platform() key: 'linux' | 'darwin' | 'win32' }
const TOOLS = {
  "claude-code": {
    name: "Claude Code",
    paths: { linux: "~/.claude.json", darwin: "~/.claude.json", win32: "~/.claude.json" },
    alwaysAttempt: true,
  },
  cursor: {
    name: "Cursor",
    paths: { linux: "~/.cursor/mcp.json", darwin: "~/.cursor/mcp.json", win32: "~/.cursor/mcp.json" },
  },
  windsurf: {
    name: "Windsurf",
    paths: {
      linux: "~/.codeium/windsurf/mcp_config.json",
      darwin: "~/.codeium/windsurf/mcp_config.json",
      win32: "~/.codeium/windsurf/mcp_config.json",
    },
  },
  "claude-desktop": {
    name: "Claude Desktop",
    paths: {
      linux: "~/.config/Claude/claude_desktop_config.json",
      darwin: "~/Library/Application Support/Claude/claude_desktop_config.json",
      win32: "%APPDATA%/Claude/claude_desktop_config.json",
    },
  },
  antigravity: {
    name: "Antigravity",
    paths: {
      linux: "~/.gemini/antigravity/mcp_config.json",
      darwin: "~/.gemini/antigravity/mcp_config.json",
      win32: "~/.gemini/antigravity/mcp_config.json",
    },
  },
  cline: {
    name: "Cline",
    paths: {
      linux: "~/.config/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json",
      darwin: "~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json",
      win32: "%APPDATA%/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json",
    },
  },
  kilo: {
    name: "Kilo Code",
    paths: {
      linux: "~/.config/kilo/kilo.jsonc",
      darwin: "~/.config/kilo/kilo.jsonc",
      win32: "~/.config/kilo/kilo.jsonc",
    },
  },
};

export const TOOL_SLUGS = Object.keys(TOOLS);

// Always-on rules files that instruct the agent to use the DevMemory MCP tools
// (restore on start, save each turn). This is how save/restore is driven for
// tools with no per-turn transcript hook. `append: true` preserves any
// hand-written content; otherwise the file is ours to overwrite.
const RULES = {
  windsurf: { path: "~/.codeium/windsurf/memories/global_rules.md", append: false },
  antigravity: { path: "~/.gemini/GEMINI.md", append: true },
};

const RULES_CONTENT = `# DevMemory — Persistent Cross-Tool Memory

You have DevMemory MCP tools. Use them proactively every session — do NOT wait to be asked.

- SESSION START / on "continue" or "resume": call get_context (or generate_resume_prompt) to restore prior work before doing anything else.
- AFTER EACH CODE CHANGE: save_context with block_type='code' — what changed and why.
- AFTER EACH KEY DECISION: save_context with block_type='decision'.
- ON EVERY ERROR: save_context with block_type='error' — message + attempted fix.
- BEFORE ENDING: save_context with block_type='next_step' — exactly what to do next.
- AT ANY NATURAL PAUSE: save_context with block_type='note'.

This keeps context alive when the user switches AI tools or runs out of credits. Saving is core to why DevMemory exists — a session with no saved blocks cannot be recovered.
`;

/** Write the DevMemory rules file for a tool, if it has one. Returns the path or null. */
function installRules(slug) {
  const rule = RULES[slug];
  if (!rule) return null;
  const path = expand(rule.path);
  mkdirSync(dirname(path), { recursive: true });
  if (rule.append) {
    const existing = existsSync(path) ? readFileSync(path, "utf8") : "";
    if (existing.toLowerCase().includes("devmemory")) return path; // already present
    const sep = existing && !existing.endsWith("\n") ? "\n" : "";
    writeFileSync(path, existing + sep + RULES_CONTENT, "utf8");
  } else {
    writeFileSync(path, RULES_CONTENT, "utf8");
  }
  return path;
}

function mcpEntry(apiKey, host, client) {
  const env = { DEVMEMORY_API_KEY: apiKey };
  if (host) env.DEVMEMORY_HOST = host;
  if (client) env.DEVMEMORY_CLIENT = client;
  return { command: "npx", args: ["-y", "@commanderzero/devmemory", "mcp"], env };
}

function toolPath(tool) {
  const tmpl = tool.paths[platform()] || tool.paths.linux;
  return expand(tmpl);
}

function readJsonConfig(path) {
  if (!existsSync(path)) return {};
  try {
    const text = readFileSync(path, "utf8")
      .split("\n")
      .filter((l) => !l.trimStart().startsWith("//")) // tolerate JSONC (Kilo)
      .join("\n");
    return text.trim() ? JSON.parse(text) : {};
  } catch {
    return {};
  }
}

/** Write/merge the devmemory MCP entry into one tool's config. Returns the path. */
export function installTool(slug, apiKey, host) {
  const tool = TOOLS[slug];
  if (!tool) throw new Error(`Unknown tool '${slug}'. Supported: ${TOOL_SLUGS.join(", ")}, all`);
  const path = toolPath(tool);
  const cfg = readJsonConfig(path);
  if (!cfg.mcpServers || typeof cfg.mcpServers !== "object") cfg.mcpServers = {};
  cfg.mcpServers.devmemory = mcpEntry(apiKey, host, slug);
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, JSON.stringify(cfg, null, 2) + "\n", "utf8");
  return path;
}

export function runInstall({ tool, apiKey, host }) {
  if (!apiKey) {
    console.error("❌ API key required. Use --api-key dm_key_...");
    process.exit(1);
  }
  // Persist backend + key globally so `devmemory start/continue/inject` reach
  // the right backend without re-passing flags (same config.json the Python
  // client reads).
  writeConfig({ host, api_key: apiKey });
  const slugs = tool === "all" ? TOOL_SLUGS : [tool];
  let wrote = 0;
  for (const slug of slugs) {
    const t = TOOLS[slug];
    if (!t) {
      console.error(`❌ Unknown tool '${slug}'. Supported: ${TOOL_SLUGS.join(", ")}, all`);
      process.exit(1);
    }
    const path = toolPath(t);
    // For --all, only configure tools that appear installed (their config dir exists).
    if (tool === "all" && !t.alwaysAttempt && !existsSync(dirname(path))) continue;
    installTool(slug, apiKey, host);
    console.log(`✅ ${t.name}: configured → ${path}`);
    const rulesPath = installRules(slug);
    if (rulesPath) console.log(`   Rules: ${rulesPath} (auto-read every session)`);
    wrote++;
  }
  if (wrote === 0) {
    console.log("⚠️  No matching tools detected. Try an explicit --tool <name>.");
    return;
  }
  if (host) console.log(`   Backend: ${host}`);
  console.log("\n🎉 Restart your AI tool to activate DevMemory.");
}
