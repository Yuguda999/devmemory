// Renders the docs sections that share data with the in-app Setup view, from the
// single source js/toolsData.js — so install commands, the tool matrix, and the
// sync mechanisms never drift between /docs and /app#setup. Static prose stays in
// docs.html; this only fills the marked placeholders.

import { INSTALL_METHODS, PROMPTS, SYNC_MECHANISMS, TOOLS } from './toolsData.js';

const esc = (s) =>
  String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

const copyIcon =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';

function codeBlock(cmd, comment) {
  const c = comment ? `<span class="tok-c"># ${esc(comment)}</span>\n` : '';
  return `<div class="code"><button class="copy-btn" data-copy="${esc(cmd)}">${copyIcon}</button><pre>${c}<span class="tok-k">${esc(cmd)}</span></pre></div>`;
}

function renderInstall(el) {
  el.innerHTML = INSTALL_METHODS.map((m) => codeBlock(m.cmd, `${m.badge} — ${m.label}`)).join('');
}

function renderTools(el) {
  const rows = TOOLS.map((t) => {
    const firstPath = Object.values(t.configs)[0] || '';
    return `<tr>
      <td>${esc(t.name)}</td>
      <td><span class="tok-k">${esc(t.sync?.badge || '')}</span></td>
      <td><code>${esc(firstPath)}</code></td>
    </tr>`;
  }).join('');
  el.innerHTML = `<div class="table-wrap"><table>
    <thead><tr><th>Tool</th><th>Auto-save</th><th>MCP config path</th></tr></thead>
    <tbody>${rows}</tbody>
  </table></div>`;
}

function renderMechanisms(el) {
  el.innerHTML = SYNC_MECHANISMS.map((m) => `
    <div class="note" style="align-items:flex-start">
      <span class="tok-k" style="font:600 11px var(--mono);letter-spacing:.04em">${esc(m.badge)}</span>
      <p><strong>${esc(m.label)}.</strong> ${m.text}</p>
    </div>`).join('');
}

function renderPrompts(el) {
  el.innerHTML = PROMPTS.map((p) => `
    <p style="margin:18px 0 6px;font-weight:600">${esc(p.label)}</p>
    <div class="code"><button class="copy-btn" data-copy="${esc(p.text)}">${copyIcon}</button><pre>${esc(p.text)}</pre></div>`).join('');
}

const install = document.getElementById('docs-install');
if (install) renderInstall(install);
const tools = document.getElementById('docs-tools');
if (tools) renderTools(tools);
const mech = document.getElementById('docs-mechanisms');
if (mech) renderMechanisms(mech);
const prompts = document.getElementById('docs-prompts');
if (prompts) renderPrompts(prompts);
