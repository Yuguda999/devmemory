import { api, state } from '../api.js';
import { icon, toast, spinner, copyText } from '../utils.js';

// ── Tool definitions — icons served from /static/icons/ ──────────────────────

function tomlSnippet(apiKey) {
  return `[mcp_servers.devmemory]
command = "devmemory"

[mcp_servers.devmemory.env]
DEVMEMORY_API_KEY = "${apiKey || 'dm_key_YOUR_KEY_HERE'}"
DEVMEMORY_HOST = "${window.location.origin}"`;
}
const TOOLS = [
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
    cli: 'claude mcp add devmemory devmemory -e DEVMEMORY_API_KEY={{API_KEY}} -e DEVMEMORY_HOST={{HOST}} -s user',
    sync: { badge: 'HOOK', tone: 'auto', text: 'SessionStart + Stop hooks capture the transcript automatically — deterministic, no daemon. Saves only the project you attach with <code>devmemory start</code>.' },
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
    sync: { badge: 'HOOK', tone: 'auto', text: 'The install command adds a <strong>SessionStart hook</strong> that injects the attached project\'s context automatically on every new session.' },
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
    sync: { badge: 'MCP + RULES', tone: '', text: 'Save/restore run through the MCP tools, driven by an always-on <code>~/.gemini/GEMINI.md</code> global rules file. Agent-driven — Antigravity exposes no verified per-turn IDE hook.' },
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
    sync: { badge: 'MCP', tone: '', text: 'MCP tools only — save and recall on demand from within the chat. No background auto-save.' },
  },
];


function mcpJsonSnippet(apiKey) {
  return JSON.stringify({
    mcpServers: {
      devmemory: {
        command: 'devmemory',
        env: { DEVMEMORY_API_KEY: apiKey || 'dm_key_YOUR_KEY_HERE', DEVMEMORY_HOST: window.location.origin }
      }
    }
  }, null, 2);
}

function copyToClipboard(text) {
  // Delegates to the shared helper, which falls back to execCommand on
  // insecure origins (http:// on a LAN IP) where navigator.clipboard is absent.
  copyText(text);
}

function escHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function toolImg(t, size = 36) {
  return `<img src="${t.icon}" alt="${t.name}" width="${size}" height="${size}" class="tool-img" style="background:${t.iconBg};border-radius:8px;padding:${size > 30 ? 5 : 3}px;object-fit:contain">`;
}


export async function renderSetup(container) {
  let apiKeys = [];
  try {
    const data = await api.get('/auth/api-keys');
    apiKeys = data.keys || [];
  } catch { }

  const firstKey = apiKeys.find(k => !k.revoked);
  const displayKey = firstKey ? `dm_key_...${firstKey.prefix?.slice(-8) || ''}` : 'dm_key_YOUR_KEY_HERE';

  container.innerHTML = `
    <div class="page-header">
      <div>
        <div class="page-title">${icon('rocket', 22)} Setup Guide</div>
        <div class="page-subtitle">Connect DevMemory to your AI coding tools</div>
      </div>
    </div>
    <div class="page-content" id="setup-body">

      <!-- ── Quick Start ────────────────────────────────────────── -->
      <div class="card setup-section">
        <div class="setup-section-header">
          <div class="setup-section-icon">${icon('terminal', 18)}</div>
          <div>
            <h3>Quick Start</h3>
            <p class="setup-section-desc">Get up and running in 30 seconds</p>
          </div>
        </div>
        <div class="setup-steps">
          <div class="setup-step">
            <div class="step-indicator">
              <span class="step-number">1</span>
              <div class="step-line"></div>
            </div>
            <div class="step-body">
              <div class="step-title">Install DevMemory</div>
              <div class="step-code">
                <code>npx -y @commanderzero/devmemory --help</code>
                <button class="code-copy-btn" data-copy="npx -y @commanderzero/devmemory --help">${icon('copy', 13)}</button>
              </div>
              <div class="step-alt"><strong>Node path — nothing to install.</strong> Prefer Python? <code>pipx install devmemory-ai</code> or <code>uv tool install devmemory-ai</code> (both isolate for you). Plain <code>pip install devmemory-ai</code> works too, but needs a virtual environment on PEP 668 systems (modern Debian/Ubuntu).</div>
            </div>
          </div>

          <div class="setup-step">
            <div class="step-indicator">
              <span class="step-number">2</span>
              <div class="step-line"></div>
            </div>
            <div class="step-body">
              <div class="step-title">Get your API key</div>
              ${firstKey
                ? `<div class="api-key-pill"><span class="key-dot"></span><code>${escHtml(displayKey)}</code></div>`
                : `<div class="step-warning">${icon('alert-triangle', 14)} No API key found — <a href="#keys">create one first</a></div>`
              }
            </div>
          </div>

          <div class="setup-step">
            <div class="step-indicator">
              <span class="step-number">3</span>
              <div class="step-line"></div>
            </div>
            <div class="step-body">
              <div class="step-title">Install for your AI tool</div>
              <div class="step-code">
                <code>devmemory install --tool cursor --api-key YOUR_KEY --host ${window.location.origin}</code>
                <button class="code-copy-btn" data-copy="devmemory install --tool cursor --api-key YOUR_KEY --host ${window.location.origin}">${icon('copy', 13)}</button>
              </div>
              <div class="step-alt">…or with Node — no Python needed:</div>
              <div class="step-code">
                <code>npx -y @commanderzero/devmemory install --tool cursor --api-key YOUR_KEY --host ${window.location.origin}</code>
                <button class="code-copy-btn" data-copy="npx -y @commanderzero/devmemory install --tool cursor --api-key YOUR_KEY --host ${window.location.origin}">${icon('copy', 13)}</button>
              </div>
              <div class="step-alt">Use <code>--tool all</code> to configure every detected tool at once. <code>--host</code> points the client at this server.</div>
            </div>
          </div>

          <div class="setup-step">
            <div class="step-indicator">
              <span class="step-number">4</span>
              <div class="step-line"></div>
            </div>
            <div class="step-body">
              <div class="step-title">Start a session in your project</div>
              <div class="step-code">
                <code>devmemory start</code>
                <button class="code-copy-btn" data-copy="devmemory start">${icon('copy', 13)}</button>
              </div>
              <div class="step-alt">Run inside the project you're working on. DevMemory attaches to <strong>that one project</strong>, restores its saved context, and auto-saves as you work — nothing is saved until you start. Runs as long as you're coding; idle gaps are fine.</div>
            </div>
          </div>

          <div class="setup-step">
            <div class="step-indicator">
              <span class="step-number last">5</span>
            </div>
            <div class="step-body" style="padding-bottom:0">
              <div class="step-title">Switch tools anytime</div>
              <div class="step-code">
                <code>devmemory continue</code>
                <button class="code-copy-btn" data-copy="devmemory continue">${icon('copy', 13)}</button>
              </div>
              <div class="step-alt">Open the same project in another tool and run this — your context loads there and saving resumes from the new tool. End with <code>devmemory stop</code>.</div>
            </div>
          </div>
        </div>
      </div>

      <!-- ── Supported Tools ────────────────────────────────────── -->
      <div class="card setup-section">
        <div class="setup-section-header">
          <div class="setup-section-icon">${icon('layers', 18)}</div>
          <div>
            <h3>Supported Tools</h3>
            <p class="setup-section-desc">Select a tool to view its setup instructions</p>
          </div>
        </div>
        <div class="tool-list" id="tool-list">
          ${TOOLS.map(t => `
            <button class="tool-row" data-tool="${t.slug}" style="--tool-color:${t.color}">
              <div class="tool-row-icon">${toolImg(t, 36)}</div>
              <div class="tool-row-body">
                <div class="tool-row-name">${t.name}</div>
                <div class="tool-row-desc">${t.desc}</div>
              </div>
              ${t.sync ? `<span class="sync-badge${t.sync.tone === 'auto' ? ' auto' : ''}" style="margin-right:8px">${t.sync.badge}</span>` : ''}
              <div class="tool-row-arrow">${icon('chevron-right', 15)}</div>
            </button>
          `).join('')}
        </div>
        <div id="tool-detail" class="tool-detail-panel" style="display:none"></div>
      </div>

      <!-- ── Auto-Sync ──────────────────────────────────────────── -->
      <div class="card setup-section">
        <div class="setup-section-header">
          <div class="setup-section-icon">${icon('refresh-cw', 18)}</div>
          <div>
            <h3>Automatic Context Sync</h3>
            <p class="setup-section-desc">Switch tools without losing context — zero copy-paste</p>
          </div>
        </div>

        <div class="sync-flow">
          <div class="sync-node">
            <div class="sync-node-icon">${icon('code-2', 20)}</div>
            <div class="sync-node-label">Tool A saves context</div>
            <div class="sync-node-sub">Goals, decisions, errors</div>
          </div>
          <div class="sync-arrow">${icon('arrow-right', 16)}</div>
          <div class="sync-node sync-node-center">
            <div class="sync-node-icon">${icon('database', 20)}</div>
            <div class="sync-node-label">DevMemory</div>
            <div class="sync-node-sub">Persistent storage</div>
          </div>
          <div class="sync-arrow">${icon('arrow-right', 16)}</div>
          <div class="sync-node">
            <div class="sync-node-icon">${icon('download', 20)}</div>
            <div class="sync-node-label">Tool B auto-loads</div>
            <div class="sync-node-sub">Continues seamlessly</div>
          </div>
        </div>

        <div class="step-alt" style="margin-bottom:14px">
          <strong>Opt-in, one project at a time.</strong> Auto-save is scoped to the project you attach with <code>devmemory start</code> — nothing is saved until you do. Move to another tool with <code>devmemory continue</code>, end with <code>devmemory stop</code>, check state with <code>devmemory status</code>. The mechanisms below are <em>how</em> each tool captures turns once attached.
        </div>

        <div class="sync-methods">
          <div class="sync-method">
            <div class="sync-method-label">
              <span class="sync-badge auto">HOOK</span>
              Tool-fired hook
            </div>
            <div class="step-alt">The tool itself fires a hook that hands us a plaintext transcript — deterministic, no daemon. <code>devmemory install</code> wires it. <strong>Claude Code</strong>, <strong>Windsurf</strong>, <strong>Augment</strong>.</div>
          </div>
          <div class="sync-method">
            <div class="sync-method-label">
              <span class="sync-badge auto">WATCH</span>
              Watch daemon
            </div>
            <div class="step-alt">For tools with no hook, <code>devmemory start</code> launches a background daemon that tails the tool's local store. <strong>Cursor</strong>, <strong>Cline</strong>, <strong>Kilo</strong>, <strong>Codex</strong>. Run <code>devmemory watch --list</code> to see what's detected.</div>
          </div>
          <div class="sync-method">
            <div class="sync-method-label">
              <span class="sync-badge">MCP + RULES</span>
              Agent-driven
            </div>
            <div class="step-alt">Save/restore run through the MCP tools, driven by an always-on global rules file. Used where the IDE exposes no verified per-turn hook. <strong>Antigravity</strong> (<code>~/.gemini/GEMINI.md</code>).</div>
          </div>
          <div class="sync-method">
            <div class="sync-method-label">
              <span class="sync-badge">CLI</span>
              Manual inject
            </div>
            <div class="step-code">
              <code>devmemory inject --cwd /path/to/project</code>
              <button class="code-copy-btn" data-copy="devmemory inject --cwd /path/to/project">${icon('copy', 13)}</button>
            </div>
            <div class="step-alt">Writes context to <code>CLAUDE.md</code> and <code>.augment/rules/devmemory.md</code> on demand.</div>
          </div>
        </div>
        <div class="step-alt" style="margin-top:12px">Windsurf and Antigravity encrypt conversations on disk — Windsurf is captured via the plaintext transcript its hook provides; Antigravity has no verified per-turn hook, so it saves/restores through the MCP tools + rules.</div>
      </div>

      <!-- ── Connection Status ──────────────────────────────────── -->
      <div class="card setup-section">
        <div class="setup-section-header">
          <div class="setup-section-icon">${icon('activity', 18)}</div>
          <div>
            <h3>Connection Status</h3>
            <p class="setup-section-desc">Verify DevMemory is running and accessible</p>
          </div>
        </div>
        <div class="connection-test">
          <button class="btn btn-primary" id="btn-test">${icon('zap', 14)} Run Diagnostics</button>
          <div id="test-result"></div>
        </div>
      </div>

    </div>
  `;

  // ── Event handlers ───────────────────────────────────────────
  document.getElementById('tool-list').addEventListener('click', e => {
    const row = e.target.closest('.tool-row');
    if (!row) return;
    showToolDetail(row.dataset.tool, displayKey);
  });

  container.addEventListener('click', e => {
    const btn = e.target.closest('.code-copy-btn');
    if (!btn) return;
    e.stopPropagation();
    copyToClipboard(btn.dataset.copy);
  });

  document.getElementById('btn-test').addEventListener('click', async () => {
    const el = document.getElementById('test-result');
    el.innerHTML = `<div class="test-running">${spinner()} Running diagnostics…</div>`;
    try {
      const t0 = Date.now();
      const data = await fetch('/health').then(r => r.json());
      const ms = Date.now() - t0;
      el.innerHTML = `
        <div class="test-result-card success">
          <div class="test-status">${icon('check-circle', 18)} Connected</div>
          <div class="test-details">
            <div class="test-detail"><span>Status</span><span>${data.status || 'ok'}</span></div>
            <div class="test-detail"><span>Latency</span><span>${ms}ms</span></div>
            <div class="test-detail"><span>Endpoint</span><span>${window.location.origin}</span></div>
          </div>
        </div>`;
    } catch {
      el.innerHTML = `
        <div class="test-result-card failure">
          <div class="test-status">${icon('x-circle', 18)} Connection Failed</div>
          <div class="test-detail-msg">Could not reach DevMemory. Start the REST server with <code>devmemory --rest</code></div>
        </div>`;
    }
  });
}


function showToolDetail(slug, apiKey) {
  const t = TOOLS.find(x => x.slug === slug);
  if (!t) return;

  const detail = document.getElementById('tool-detail');
  const isToml = t.configFormat === 'toml';
  const snippet = isToml ? tomlSnippet(apiKey) : mcpJsonSnippet(apiKey);
  const configLabel = isToml ? 'TOML Configuration (~/.codex/config.toml)' : 'JSON Configuration';
  const cliInstall = `devmemory install --tool ${t.slug} --api-key YOUR_KEY --host ${window.location.origin}`;
  const npxInstall = `npx -y @commanderzero/devmemory install --tool ${t.slug} --api-key YOUR_KEY --host ${window.location.origin}`;

  const configRows = Object.entries(t.configs).map(([os, path]) => `
    <div class="config-path-row">
      <span class="config-os-badge">${os}</span>
      <code class="config-file-path">${escHtml(path)}</code>
    </div>`).join('');

  detail.style.display = 'block';
  detail.innerHTML = `
    <div class="detail-header" style="--tool-color:${t.color}">
      <div class="detail-header-left">
        ${toolImg(t, 40)}
        <div>
          <div class="detail-title">${t.name}</div>
          <div class="detail-desc">${t.desc}</div>
        </div>
      </div>
      <button class="detail-close" id="detail-close">${icon('x', 15)}</button>
    </div>
    <div class="detail-body">
      <div class="detail-method">
        <div class="detail-method-label">
          <span class="method-badge recommended">Recommended</span>
          Automatic Setup via CLI
        </div>
        <div class="step-code lg">
          <code>${escHtml(cliInstall)}</code>
          <button class="code-copy-btn" data-copy="${escHtml(cliInstall)}">${icon('copy', 13)}</button>
        </div>
        <div class="detail-method-label" style="margin-top:12px">
          <span class="method-badge">Node / npx</span>
          No Python required
        </div>
        <div class="step-code lg">
          <code>${escHtml(npxInstall)}</code>
          <button class="code-copy-btn" data-copy="${escHtml(npxInstall)}">${icon('copy', 13)}</button>
        </div>
      </div>

      ${t.cli ? `
      <div class="detail-method">
        <div class="detail-method-label">
          <span class="method-badge">Alternative</span>
          Tool-native CLI
        </div>
        <div class="step-code lg">
          <code>${escHtml(t.cli.replace('{{API_KEY}}', apiKey).replace('{{HOST}}', window.location.origin))}</code>
          <button class="code-copy-btn" data-copy="${escHtml(t.cli.replace('{{API_KEY}}', apiKey).replace('{{HOST}}', window.location.origin))}">${icon('copy', 13)}</button>
        </div>
      </div>` : ''}

      <div class="detail-method">
        <div class="detail-method-label">
          <span class="method-badge">Manual</span>
          ${escHtml(configLabel)}
        </div>
        <div class="config-paths-list">${configRows}</div>
        <div class="step-code lg multi">
          <code>${escHtml(snippet)}</code>
          <button class="code-copy-btn top-right" data-copy="${escHtml(snippet)}">${icon('copy', 13)}</button>
        </div>
      </div>

      ${t.sync ? `
      <div class="detail-method">
        <div class="detail-method-label">
          <span class="method-badge${t.sync.tone === 'auto' ? ' recommended' : ''}">${t.sync.badge}</span>
          Context sync
        </div>
        <div class="detail-note">
          <div class="detail-note-icon">${icon('info', 14)}</div>
          <div class="detail-note-text">${t.sync.text}</div>
        </div>
      </div>` : ''}

      ${isToml ? `
      <div class="detail-note">
        <div class="detail-note-icon">${icon('info', 14)}</div>
        <div class="detail-note-text">Codex uses <strong>TOML format</strong> instead of JSON. Add the block above to <code>~/.codex/config.toml</code>, or run <code>codex mcp add devmemory -- devmemory</code> and Codex will write the config for you.</div>
      </div>` : ''}
    </div>
  `;

  detail.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

  document.querySelectorAll('.tool-row').forEach(r => r.classList.remove('active'));
  document.querySelector(`.tool-row[data-tool="${slug}"]`)?.classList.add('active');

  document.getElementById('detail-close').addEventListener('click', () => {
    detail.style.display = 'none';
    document.querySelectorAll('.tool-row').forEach(r => r.classList.remove('active'));
  });
}
