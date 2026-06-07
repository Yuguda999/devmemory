import { api } from '../api.js';
import { fmtDate, fmtDateTime, spinner, emptyState, toast, copyText, icon } from '../utils.js';

export async function renderKeys(container) {
  container.innerHTML = `
    <div class="page-header">
      <div>
        <div class="page-title">API Keys</div>
        <div class="page-subtitle">Manage keys for programmatic access and MCP tools</div>
      </div>
      <button class="btn btn-primary" id="btn-create-key">+ New Key</button>
    </div>
    <div class="page-content">
      <!-- Create form -->
      <div id="create-key-form" class="card" style="display:none;margin-bottom:20px;max-width:480px">
        <div class="section-title" style="margin-bottom:14px">Create New Key</div>
        <div class="form-group">
          <label class="form-label">Key Name</label>
          <input id="key-name-input" type="text" class="form-input" placeholder="e.g. Cursor MCP, Claude Desktop">
        </div>
        <div id="key-reveal-wrap" style="display:none">
          <div style="background:rgba(62,207,142,0.08);border:1px solid rgba(62,207,142,0.25);border-radius:var(--radius-sm);padding:14px;margin-bottom:14px">
            <div style="font-size:12.5px;color:var(--green);font-weight:600;margin-bottom:6px">${icon('shield-alert', 14)} Copy this key now — it won't be shown again</div>
            <div id="key-reveal-value" class="key-reveal" style="position:relative">
              <span id="key-text"></span>
              <button class="copy-btn" id="copy-key-btn">Copy</button>
            </div>
          </div>
        </div>
        <div style="display:flex;gap:10px">
          <button class="btn btn-primary btn-sm" id="btn-submit-key">Create Key</button>
          <button class="btn btn-ghost btn-sm" id="btn-cancel-key">Cancel</button>
        </div>
      </div>

      <!-- Keys table -->
      <div id="keys-body">${spinner()}</div>
    </div>
  `;

  document.getElementById('btn-create-key').addEventListener('click', () => {
    const f = document.getElementById('create-key-form');
    f.style.display = f.style.display === 'none' ? '' : 'none';
    document.getElementById('key-reveal-wrap').style.display = 'none';
    document.getElementById('key-name-input').value = '';
  });

  document.getElementById('btn-cancel-key').addEventListener('click', () => {
    document.getElementById('create-key-form').style.display = 'none';
  });

  document.getElementById('btn-submit-key').addEventListener('click', async () => {
    const name = document.getElementById('key-name-input').value.trim();
    if (!name) { toast('Please enter a key name', 'error'); return; }
    const btn = document.getElementById('btn-submit-key');
    btn.disabled = true; btn.textContent = 'Creating…';
    try {
      const data = await api.post('/auth/api-keys', { name });
      document.getElementById('key-text').textContent = data.key;
      document.getElementById('key-reveal-wrap').style.display = '';
      document.getElementById('copy-key-btn').addEventListener('click', function() {
        copyText(data.key, this);
      });
      btn.disabled = false; btn.textContent = 'Create Key';
      loadKeys();
    } catch (err) {
      toast(err.message, 'error');
      btn.disabled = false; btn.textContent = 'Create Key';
    }
  });

  async function loadKeys() {
    const body = document.getElementById('keys-body');
    body.innerHTML = spinner();
    try {
      const data = await api.get('/auth/api-keys');
      const keys = data.keys || [];
      if (!keys.length) {
        body.innerHTML = emptyState('key-round', 'No API keys yet', 'Create a key above to use with MCP tools.');
        return;
      }
      body.innerHTML = `
        <div class="card" style="padding:0;overflow:hidden">
          <div class="table-wrap">
            <table>
              <thead><tr>
                <th>Name</th><th>Prefix</th><th>Status</th><th>Last Used</th><th>Created</th><th></th>
              </tr></thead>
              <tbody>
                ${keys.map(k => `
                  <tr>
                    <td style="font-weight:500">${k.name}</td>
                    <td><code style="font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--accent)">${k.prefix}…</code></td>
                    <td>${k.revoked
                      ? '<span class="badge badge-archived">Revoked</span>'
                      : '<span class="badge badge-active">Active</span>'}</td>
                    <td style="color:var(--text-muted);font-size:12px">${fmtDateTime(k.last_used_at)}</td>
                    <td style="color:var(--text-muted);font-size:12px">${fmtDate(k.created_at)}</td>
                    <td>
                      ${!k.revoked ? `<button class="btn btn-danger btn-sm" data-revoke-key="${k.id}">Revoke</button>` : ''}
                    </td>
                  </tr>`).join('')}
              </tbody>
            </table>
          </div>
        </div>
      `;

      body.addEventListener('click', async e => {
        const btn = e.target.closest('[data-revoke-key]');
        if (!btn) return;
        if (!confirm('Revoke this API key? This cannot be undone.')) return;
        try {
          await api.delete(`/auth/api-keys/${btn.dataset.revokeKey}`);
          toast('Key revoked');
          loadKeys();
        } catch (err) { toast(err.message, 'error'); }
      });

    } catch (err) {
      body.innerHTML = emptyState('alert-triangle', 'Failed to load keys', err.message);
    }
  }

  loadKeys();
}
