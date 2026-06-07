import { api } from '../api.js';
import { fmtDate, spinner, emptyState, icon } from '../utils.js';

export async function renderProjects(container) {
  container.innerHTML = `
    <div class="page-header">
      <div>
        <div class="page-title">Projects</div>
        <div class="page-subtitle">All repositories tracked by DevMemory</div>
      </div>
    </div>
    <div class="page-content" id="proj-body">${spinner()}</div>
  `;

  const body = document.getElementById('proj-body');
  try {
    const data = await api.get('/projects');
    const projects = data.projects || [];

    if (!projects.length) {
      body.innerHTML = emptyState('folder-git-2', 'No projects yet',
        'Projects are created automatically when an AI tool calls save_context or start_session for a new git repository.');
      return;
    }

    body.innerHTML = `
      <div style="margin-bottom:12px;font-size:13px;color:var(--text-muted)">${projects.length} project${projects.length !== 1 ? 's' : ''}</div>
      <div class="projects-grid">
        ${projects.map(p => `
          <div class="project-card" data-project-id="${p.id}" onclick="window.location.hash='#sessions?project=${p.id}'">
            <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:8px">
              <div class="project-name">${p.name}</div>
              <span style="font-size:11px;color:var(--text-muted);background:rgba(255,255,255,0.05);padding:2px 8px;border-radius:6px;white-space:nowrap;flex-shrink:0">View sessions →</span>
            </div>
            <div class="project-slug">${p.slug}</div>
            ${p.remote_url ? `<div class="project-url" title="${p.remote_url}">${icon('link', 13)} ${p.remote_url}</div>` : '<div class="project-slug" style="color:var(--text-muted)">No remote URL</div>'}
            <div class="project-meta">
              <span>${icon('calendar', 13)} ${fmtDate(p.created_at)}</span>
              <span>Updated ${fmtDate(p.updated_at)}</span>
            </div>
          </div>`).join('')}
      </div>
    `;
  } catch (err) {
    body.innerHTML = emptyState('alert-triangle', 'Failed to load projects', err.message);
  }
}
