// `devmemory install` — write the DevMemory MCP entry into an AI tool's config.
// The MCP server is launched as `npx -y devmemory mcp`, so no global install or
// PATH juggling is needed.

import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir, platform } from "node:os";
import { dirname, join } from "node:path";

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
    wrote++;
  }
  if (wrote === 0) {
    console.log("⚠️  No matching tools detected. Try an explicit --tool <name>.");
    return;
  }
  if (host) console.log(`   Backend: ${host}`);
  console.log("\n🎉 Restart your AI tool to activate DevMemory.");
}
