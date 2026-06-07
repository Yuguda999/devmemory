import { api } from '../api.js';
import { fmtDate, fmtDateTime, statusBadge, blockChip, spinner, emptyState, toast, icon } from '../utils.js';

let _modal = null;

function closeModal() {
  if (_modal) { _modal.remove(); _modal = null; }
}

async function openSessionModal(session) {
  closeModal();
  const backdrop = document.createElement('div');
  backdrop.className = 'modal-backdrop';
  backdrop.innerHTML = `
    <div class="modal-panel" id="session-modal">
      <div class="modal-header">
        <div>
          <div class="modal-title">${session.title}</div>
          <div class="modal-subtitle">
            ${statusBadge(session.status)} &nbsp;
            <span style="color:var(--text-muted);font-size:12px">${session.tool_source || ''} · ${fmtDateTime(session.created_at)}</span>
          </div>
        </div>
        <button class="modal-close" id="modal-close-btn">${icon('x', 16)}</button>
      </div>
      <div class="modal-body" id="modal-body">${spinner()}</div>
    </div>
  `;
  document.body.appendChild(backdrop);
  _modal = backdrop;

  backdrop.addEventListener('click', e => { if (e.target === backdrop) closeModal(); });
  document.getElementById('modal-close-btn').addEventListener('click', closeModal);

  const body = document.getElementById('modal-body');
  try {
    const data = await api.get(`/sessions/${session.id}/blocks?limit=200`);
    const blocks = data.blocks || [];

    if (!blocks.length) {
      body.innerHTML = emptyState('file-text', 'No context blocks', 'Blocks are saved by AI tools using save_context.');
      return;
    }

    body.innerHTML = `
      <div style="margin-bottom:14px;font-size:13px;color:var(--text-muted)">${blocks.length} block${blocks.length !== 1 ? 's' : ''}</div>
      <div class="block-list" id="block-list">
        ${blocks.map(b => renderBlock(b)).join('')}
      </div>
    `;

    document.getElementById('block-list').addEventListener('click', async e => {
      const btn = e.target.closest('[data-delete-block]');
      if (!btn) return;
      const id = btn.dataset.deleteBlock;
      if (!confirm('Delete this context block?')) return;
      try {
        await api.delete(`/context-blocks/${id}`);
        btn.closest('.block-item').remove();
        toast('Block deleted');
      } catch (err) {
        toast(err.message, 'error');
      }
    });
  } catch (err) {
    body.innerHTML = emptyState('alert-triangle', 'Failed to load blocks', err.message);
  }
}

function renderBlock(b) {
  const isCode = b.block_type === 'code';
  return `
    <div class="block-item" id="block-${b.id}">
      <div class="block-header">
        ${blockChip(b.block_type)}
        <span class="block-priority">priority ${b.priority}</span>
      </div>
      ${isCode
        ? `<pre class="block-code">${escHtml(b.content)}</pre>`
        : `<div class="block-content">${escHtml(b.content)}</div>`}
      <div class="block-footer">
        <span class="block-date">${fmtDateTime(b.created_at)}</span>
        <button class="btn btn-danger btn-sm" data-delete-block="${b.id}">Delete</button>
      </div>
    </div>
  `;
}

function escHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

export async function renderSessions(container, params) {
  // Parse params — support ?project=xxx from project card clicks
  const initProject = params?.project || '';

  container.innerHTML = `
    <div class="page-header">
      <div>
        <div class="page-title">Sessions</div>
        <div class="page-subtitle">Development sessions across all projects</div>
      </div>
    </div>
    <div class="page-content" id="sess-body">
      <div class="filters-row" id="filters-row">
        <select class="filter-select" id="filter-project">
          <option value="">All Projects</option>
        </select>
        <select class="filter-select" id="filter-status">
          <option value="">All Statuses</option>
          <option value="active">Active</option>
          <option value="paused">Paused</option>
          <option value="completed">Completed</option>
          <option value="archived">Archived</option>
        </select>
      </div>
      <div id="sessions-table">${spinner()}</div>
    </div>
  `;

  // Load projects for filter dropdown
  api.get('/projects').then(d => {
    const sel = document.getElementById('filter-project');
    if (!sel) return;
    (d.projects || []).forEach(p => {
      const o = document.createElement('option');
      o.value = p.id; o.textContent = p.name;
      if (p.id === initProject) o.selected = true;
      sel.appendChild(o);
    });
    if (initProject) loadSessions();
  }).catch(() => {});

  if (initProject) {
    // pre-select handled above
  }

  document.getElementById('filter-project')?.addEventListener('change', loadSessions);
  document.getElementById('filter-status')?.addEventListener('change', loadSessions);

  loadSessions();

  async function loadSessions() {
    const tableEl = document.getElementById('sessions-table');
    if (!tableEl) return;
    tableEl.innerHTML = spinner();

    const project = document.getElementById('filter-project')?.value || '';
    const status  = document.getElementById('filter-status')?.value || '';
    let url = '/sessions?limit=50';
    if (project) url += `&project_id=${project}`;
    if (status)  url += `&status=${status}`;

    try {
      const data = await api.get(url);
      const sessions = data.sessions || [];

      if (!sessions.length) {
        tableEl.innerHTML = emptyState('layers', 'No sessions found', 'Try adjusting the filters above.');
        return;
      }

      tableEl.innerHTML = `
        <div style="margin-bottom:10px;font-size:13px;color:var(--text-muted)">${sessions.length} session${sessions.length !== 1 ? 's' : ''}</div>
        <div class="card" style="padding:0;overflow:hidden">
          <div class="table-wrap">
            <table>
              <thead><tr>
                <th>Title</th><th>Status</th><th>Tool</th><th>Created</th><th>Updated</th>
              </tr></thead>
              <tbody id="sess-tbody">
                ${sessions.map(s => `
                  <tr data-session-id="${s.id}" style="cursor:pointer">
                    <td style="max-width:260px">
                      <div style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:500">${s.title}</div>
                    </td>
                    <td>${statusBadge(s.status)}</td>
                    <td style="color:var(--text-muted);font-size:12px">${s.tool_source || '—'}</td>
                    <td style="color:var(--text-muted);font-size:12px">${fmtDate(s.created_at)}</td>
                    <td style="color:var(--text-muted);font-size:12px">${fmtDate(s.updated_at)}</td>
                  </tr>`).join('')}
              </tbody>
            </table>
          </div>
        </div>
      `;

      // Attach session data so we can open modal without extra fetch
      const sessionMap = Object.fromEntries(sessions.map(s => [s.id, s]));
      document.getElementById('sess-tbody').addEventListener('click', e => {
        const row = e.target.closest('tr[data-session-id]');
        if (!row) return;
        openSessionModal(sessionMap[row.dataset.sessionId]);
      });

    } catch (err) {
      tableEl.innerHTML = emptyState('alert-triangle', 'Failed to load sessions', err.message);
    }
  }
}
