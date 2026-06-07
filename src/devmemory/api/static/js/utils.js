/**
 * Lucide icon helper — returns an inline SVG string.
 * Lucide UMD exports PascalCase keys, so we convert kebab-case to PascalCase.
 * @param {string} name - Lucide icon name in kebab-case (e.g. 'folder-git-2', 'key-round')
 * @param {number} size - Icon size in px (default 18)
 * @param {string} cls  - Additional CSS class
 */
export function icon(name, size = 18, cls = '') {
  // Convert kebab-case to PascalCase: 'layout-dashboard' → 'LayoutDashboard'
  const pascalName = name.replace(/(^|-)([a-z0-9])/g, (_, __, c) => c.toUpperCase());
  const def = lucide.icons[pascalName];
  if (!def) return '';
  const el = lucide.createElement(def);
  el.setAttribute('width', size);
  el.setAttribute('height', size);
  el.setAttribute('class', `lucide-icon ${cls}`.trim());
  return el.outerHTML;
}

/** Toast notification helper */
export function toast(msg, type = 'success') {
  const c = document.getElementById('toast-container');
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.innerHTML = `<div class="toast-dot"></div><span>${msg}</span>`;
  c.appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

/** Format ISO date string nicely */
export function fmtDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

/** Format ISO date with time */
export function fmtDateTime(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

/** Status badge HTML */
export function statusBadge(status) {
  const map = { active: 'badge-active', paused: 'badge-paused', completed: 'badge-completed', archived: 'badge-archived' };
  return `<span class="badge ${map[status] || ''}">${status}</span>`;
}

/** Block type chip HTML */
export function blockChip(type) {
  return `<span class="chip chip-${type}">${type.replace('_', ' ')}</span>`;
}

/** Tier badge HTML */
export function tierBadge(tier) {
  return `<span class="badge badge-${tier}">${tier.toUpperCase()}</span>`;
}

/** Progress bar HTML */
export function progressBar(used, max, label) {
  if (max === null || max === undefined) {
    return `<div class="progress-bar-wrap">
      <div class="progress-labels">
        <span class="progress-label">${label}</span>
        <span class="progress-pct">${used} / ∞</span>
      </div>
      <div class="progress-track"><div class="progress-fill" style="width:0%"></div></div>
    </div>`;
  }
  const pct = Math.min(100, Math.round((used / max) * 100));
  const cls = pct >= 90 ? 'danger' : pct >= 70 ? 'warn' : '';
  return `<div class="progress-bar-wrap">
    <div class="progress-labels">
      <span class="progress-label">${label}</span>
      <span class="progress-pct">${used} / ${max} (${pct}%)</span>
    </div>
    <div class="progress-track"><div class="progress-fill ${cls}" style="width:${pct}%"></div></div>
  </div>`;
}

/** Spinner HTML */
export function spinner() {
  return `<div class="loading-wrap"><div class="spinner"></div></div>`;
}

/** Empty state HTML — accepts a Lucide icon name */
export function emptyState(iconName, title, desc = '') {
  return `<div class="empty-state">
    <div class="empty-icon">${icon(iconName, 40)}</div>
    <div class="empty-title">${title}</div>
    ${desc ? `<div class="empty-desc">${desc}</div>` : ''}
  </div>`;
}

/** Copy text to clipboard */
export async function copyText(text, btn) {
  try {
    await navigator.clipboard.writeText(text);
    const orig = btn.textContent;
    btn.textContent = 'Copied!';
    setTimeout(() => btn.textContent = orig, 1800);
  } catch {
    toast('Could not copy to clipboard', 'error');
  }
}
