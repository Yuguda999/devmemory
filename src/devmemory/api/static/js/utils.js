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

/** Copy text to the clipboard.
 *
 * navigator.clipboard is only available in secure contexts (HTTPS or
 * localhost). When the dashboard is served over plain HTTP on a LAN IP or
 * 0.0.0.0, it is undefined — so we fall back to a temporary <textarea> +
 * execCommand('copy'), which works in insecure contexts.
 */
export async function copyText(text, btn) {
  const ok = await writeClipboard(text);
  if (ok) {
    if (btn) {
      const orig = btn.textContent;
      btn.textContent = 'Copied!';
      setTimeout(() => btn.textContent = orig, 1800);
    } else {
      toast('Copied to clipboard');
    }
  } else {
    toast('Could not copy — select the text and copy manually', 'error');
  }
}

async function writeClipboard(text) {
  // Preferred path: async Clipboard API (secure contexts only).
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch { /* fall through to legacy path */ }
  }
  // Legacy fallback for insecure contexts (http:// on a LAN IP).
  try {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    ta.style.position = 'fixed';
    ta.style.top = '-1000px';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(ta);
    return ok;
  } catch {
    return false;
  }
}

/**
 * Styled confirmation dialog — a themed replacement for window.confirm().
 * Returns a Promise that resolves to true (confirmed) or false (cancelled).
 *
 * @param {object} opts
 * @param {string} opts.title        - Dialog heading.
 * @param {string} [opts.message]    - Body text.
 * @param {string} [opts.confirmText] - Confirm button label (default "Confirm").
 * @param {string} [opts.cancelText]  - Cancel button label (default "Cancel").
 * @param {boolean} [opts.danger]     - Style the confirm button as destructive.
 * @param {string} [opts.icon]        - Lucide icon name shown beside the title.
 */
export function confirmDialog(opts = {}) {
  const {
    title = 'Are you sure?',
    message = '',
    confirmText = 'Confirm',
    cancelText = 'Cancel',
    danger = false,
    icon: iconName = danger ? 'alert-triangle' : 'help-circle',
  } = opts;

  return new Promise((resolve) => {
    const backdrop = document.createElement('div');
    backdrop.className = 'confirm-backdrop';
    backdrop.innerHTML = `
      <div class="confirm-panel" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title">
        <div class="confirm-icon ${danger ? 'danger' : ''}">${icon(iconName, 22)}</div>
        <div class="confirm-title" id="confirm-title">${title}</div>
        ${message ? `<div class="confirm-message">${message}</div>` : ''}
        <div class="confirm-actions">
          <button class="btn btn-ghost" id="confirm-cancel">${cancelText}</button>
          <button class="btn ${danger ? 'btn-danger' : 'btn-primary'}" id="confirm-ok">${confirmText}</button>
        </div>
      </div>
    `;

    function close(result) {
      document.removeEventListener('keydown', onKey);
      backdrop.classList.add('closing');
      setTimeout(() => backdrop.remove(), 120);
      resolve(result);
    }
    function onKey(e) {
      if (e.key === 'Escape') close(false);
      else if (e.key === 'Enter') close(true);
    }

    backdrop.addEventListener('click', (e) => { if (e.target === backdrop) close(false); });
    document.addEventListener('keydown', onKey);
    document.body.appendChild(backdrop);
    backdrop.querySelector('#confirm-cancel').addEventListener('click', () => close(false));
    backdrop.querySelector('#confirm-ok').addEventListener('click', () => close(true));
    // Focus the confirm button so Enter/Space works immediately.
    backdrop.querySelector('#confirm-ok').focus();
  });
}
