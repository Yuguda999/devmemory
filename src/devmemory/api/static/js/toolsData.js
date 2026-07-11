// Single source of truth for tool metadata, install methods, sync mechanisms,
// and config snippets. Imported by BOTH the in-app Setup view (js/views/setup.js)
// and the public docs page (js/docs.js) so the two never drift. Host is passed
// in by the caller — the app uses window.location.origin, docs uses a placeholder.

export const HOST_PLACEHOLDER = 'https://your-backend';
export const KEY_PLACEHOLDER = 'dm_key_YOUR_KEY_HERE';

// ── Supported tools ──────────────────────────────────────────────────────────
export const TOOLS = [
  {
    slug: 'claude-code',
    name: 'Claude Code',
    desc: "Anthropic's CLI coding agent",
    color: '#D97757',
    icon: '/static/icons/claude-code.svg',
    iconBg: 'rgba(217,119,87,0.12)',
    configs: {
      'Linux / macOS': '~/.claude.json',
      'Windows': '%USERPROFILE%\\.claude.json',
    },
    cli: 'claude mcp add devmemory devmemory mcp -e DEVMEMORY_API_KEY={{API_KEY}} -e DEVMEMORY_HOST={{HOST}} -s user',
    sync: { badge: 'HOOK + WATCH', tone: 'auto', text: 'SessionStart + Stop hooks capture the transcript automatically. <code>devmemory start</code> also runs the watch daemon over <code>~/.claude/projects</code> as a fallback, so the attached project saves even when the hooks aren\'t wired.' },
    note: 'Custom config dir? If you run Claude Code with <code>CLAUDE_CONFIG_DIR</code> set, <code>devmemory install</code> auto-detects it and writes to the right place. For several profiles at once, pass <code>--config-dir ~/.claude-a,~/.claude-b</code> (comma-separated) — one install per profile. The tool-native <code>claude mcp add … -s user</code> command already targets whatever profile is active.',
  },
  {
    slug: 'cursor',
    name: 'Cursor',
    desc: 'AI-first code editor',
    color: '#ffffff',
    icon: '/static/icons/cursor.svg',
    iconBg: 'rgba(255,255,255,0.08)',
    configs: {
      'Linux / macOS': '~/.cursor/mcp.json',
      'Windows': '%USERPROFILE%\\.cursor\\mcp.json',
    },
    sync: { badge: 'WATCH', tone: 'auto', text: '<code>devmemory start</code> launches a background daemon that tails Cursor\'s SQLite store (cursorDiskKV) and auto-saves the attached project.' },
  },
  {
    slug: 'windsurf',
    name: 'Windsurf',
    desc: "Codeium's AI IDE",
    color: '#ffffff',
    icon: '/static/icons/windsurf.svg',
    iconBg: 'rgba(255,255,255,0.08)',
    configs: {
      'Linux / macOS': '~/.codeium/windsurf/mcp_config.json',
      'Windows': '%USERPROFILE%\\.codeium\\windsurf\\mcp_config.json',
    },
    sync: { badge: 'HOOK', tone: 'auto', text: 'The install command wires a <code>post_cascade_response_with_transcript</code> hook that auto-saves each turn\'s plaintext transcript (for the attached project), plus <code>memories/global_rules.md</code> for restore.' },
  },
  {
    slug: 'augment',
    name: 'Augment Code',
    desc: 'VS Code AI extension',
    color: '#7C5CFC',
    icon: '/static/icons/augment.png',
    iconBg: 'rgba(124,92,252,0.12)',
    configs: {
      'Linux / macOS': '~/.augment/settings.json',
      'Windows': '%APPDATA%\\augment\\settings.json',
    },
    sync: { badge: 'HOOK + MCP', tone: 'auto', text: 'A <strong>SessionStart hook</strong> injects the attached project\'s context on every new session (restore). To attach + save, just say <strong>“continue”</strong> — the agent calls <code>continue_here</code> for the open folder and saves via the MCP tools as you work.' },
  },
  {
    slug: 'antigravity',
    name: 'Antigravity',
    desc: 'Google Gemini coding agent',
    color: '#4285F4',
    icon: '/static/icons/antigravity.svg',
    iconBg: 'rgba(66,133,244,0.12)',
    configs: {
      'All platforms': '~/.gemini/antigravity/mcp_config.json',
    },
    sync: { badge: 'MCP + RULES', tone: '', text: 'Just say <strong>“continue”</strong> (or “start on this project”) — the agent calls <code>continue_here</code> for the open folder, which attaches that project and restores its context. Saves happen via the MCP tools as you work, driven by the always-on <code>~/.gemini/GEMINI.md</code> rules file. No daemon (the store is encrypted); no CLI needed.' },
  },
  {
    slug: 'cline',
    name: 'Cline',
    desc: 'VS Code MCP extension',
    color: '#ffffff',
    icon: '/static/icons/cline.svg',
    iconBg: 'rgba(255,255,255,0.08)',
    configs: {
      'Linux': '~/.config/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json',
      'macOS': '~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json',
      'Windows': '%APPDATA%\\Code\\User\\globalStorage\\saoudrizwan.claude-dev\\settings\\cline_mcp_settings.json',
    },
    sync: { badge: 'WATCH', tone: 'auto', text: '<code>devmemory start</code> launches the daemon that tails Cline\'s JSON task history and auto-saves the attached project.' },
  },
  {
    slug: 'kilo',
    name: 'Kilo Code',
    desc: 'AI coding assistant',
    color: '#ffffff',
    icon: '/static/icons/kilo.svg',
    iconBg: 'rgba(255,255,255,0.08)',
    configs: {
      'Linux / macOS': '~/.config/kilo/kilo.jsonc',
      'Windows': '%USERPROFILE%\\.config\\kilo\\kilo.jsonc',
    },
    sync: { badge: 'WATCH', tone: 'auto', text: 'Cline fork — <code>devmemory start</code> launches the daemon that tails the same JSON format under a different extension id.' },
  },
  {
    slug: 'codex',
    name: 'Codex CLI',
    desc: "OpenAI's agentic coding CLI",
    color: '#ffffff',
    icon: '/static/icons/codex.svg',
    iconBg: 'rgba(255,255,255,0.08)',
    configFormat: 'toml',
    configs: {
      'Linux / macOS': '~/.codex/config.toml',
      'Windows': '%USERPROFILE%\\.codex\\config.toml',
    },
    cli: 'codex mcp add devmemory --command devmemory --env DEVMEMORY_API_KEY={{API_KEY}} --env DEVMEMORY_HOST={{HOST}}',
    sync: { badge: 'WATCH', tone: 'auto', text: '<code>devmemory start</code> launches the daemon that tails Codex\'s SQLite threads + rollout JSONL and auto-saves the attached project.' },
  },
  {
    slug: 'claude-desktop',
    name: 'Claude Desktop',
    desc: 'Claude Desktop app',
    color: '#D97757',
    icon: '/static/icons/claude-desktop.svg',
    iconBg: 'rgba(217,119,87,0.12)',
    configs: {
      'macOS': '~/Library/Application Support/Claude/claude_desktop_config.json',
      'Linux': '~/.config/Claude/claude_desktop_config.json',
      'Windows': '%APPDATA%\\Claude\\claude_desktop_config.json',
    },
    sync: { badge: 'MCP', tone: '', text: 'MCP tools only — say <strong>“continue”</strong> and the agent attaches + restores via <code>continue_here</code>, then saves as you work. No project folder in a desktop chat, so name the project (<code>project="…"</code>) if the agent can\'t infer one.' },
  },
];

// ── Install methods (ordered: no-venv paths first) ───────────────────────────
export const INSTALL_METHODS = [
  { badge: 'Node', label: 'nothing to install (recommended)', cmd: 'npx -y @commanderzero/devmemory --help' },
  { badge: 'Python', label: 'pipx — isolated env, managed for you', cmd: 'pipx install devmemory-ai' },
  { badge: 'Python', label: 'uv tool', cmd: 'uv tool install devmemory-ai' },
  { badge: 'Python', label: 'pip — needs a venv on PEP 668 systems', cmd: 'pip install devmemory-ai' },
];

// ── Auto-save mechanisms ─────────────────────────────────────────────────────
export const SYNC_MECHANISMS = [
  { badge: 'HOOK', tone: 'auto', label: 'Tool-fired hook', text: 'The tool itself fires a hook that hands us a plaintext transcript — deterministic, no daemon. <code>devmemory install</code> wires it. <strong>Claude Code</strong>, <strong>Windsurf</strong>, <strong>Augment</strong>.' },
  { badge: 'WATCH', tone: 'auto', label: 'Watch daemon', text: 'For tools with no hook, <code>devmemory start</code> launches a background daemon that tails the tool\'s local store. <strong>Cursor</strong>, <strong>Cline</strong>, <strong>Kilo</strong>, <strong>Codex</strong>, and <strong>Claude Code</strong> (fallback for its <code>~/.claude/projects</code> transcripts).' },
  { badge: 'MCP + RULES', tone: '', label: 'Agent-driven', text: 'Say <strong>“continue”</strong> (or “start on this project”) and the agent calls <code>continue_here</code> for the open folder — attaching that project and restoring it — then saves via the MCP tools as you work, driven by an always-on rules file. Works in any MCP tool. <strong>Antigravity</strong> (<code>~/.gemini/GEMINI.md</code>), <strong>Claude Desktop</strong>.' },
  { badge: 'CLI', tone: '', label: 'Manual inject', text: '<code>devmemory inject</code> writes context to <code>CLAUDE.md</code> / rules files on demand.' },
];

// ── Copy-paste prompts (say these to any MCP-connected AI tool) ──────────────
// The agent maps these to DevMemory MCP tools; it uses the open project folder
// as the project, so the user never has to name one (except "switch project").
export const PROMPTS = [
  {
    label: 'Continue / attach this project',
    text: 'Use DevMemory: continue where we left off on this project. Attach this folder and load my saved context before we start.',
  },
  {
    label: 'Save progress now',
    text: 'Save our progress to DevMemory now — the current goal, the key decisions we made, and the next steps to pick up later.',
  },
  {
    label: 'Check what is saved',
    text: 'What has DevMemory saved for this project so far? Load the latest context and summarise it.',
  },
  {
    label: 'Start saving a fresh project',
    text: 'Start tracking this project in DevMemory: attach this folder and save our goal so context survives if I switch tools.',
  },
  {
    label: 'Switch to another project',
    text: 'Attach DevMemory to the project named "PROJECT_NAME" and load its saved context.',
  },
];

// ── Config snippets (host + key parameterized) ───────────────────────────────
export function tomlSnippet(host, apiKey) {
  return `[mcp_servers.devmemory]
command = "devmemory"

[mcp_servers.devmemory.env]
DEVMEMORY_API_KEY = "${apiKey || KEY_PLACEHOLDER}"
DEVMEMORY_HOST = "${host}"`;
}

export function mcpJsonSnippet(host, apiKey) {
  return JSON.stringify({
    mcpServers: {
      devmemory: {
        command: 'devmemory',
        args: ['mcp'],
        env: { DEVMEMORY_API_KEY: apiKey || KEY_PLACEHOLDER, DEVMEMORY_HOST: host },
      },
    },
  }, null, 2);
}

export function installCmd(slug, host, apiKey = 'YOUR_KEY') {
  return `devmemory install --tool ${slug} --api-key ${apiKey} --host ${host}`;
}

export function npxInstallCmd(slug, host, apiKey = 'YOUR_KEY') {
  return `npx -y @commanderzero/devmemory install --tool ${slug} --api-key ${apiKey} --host ${host}`;
}
