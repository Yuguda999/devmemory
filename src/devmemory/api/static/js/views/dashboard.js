import { api, state } from '../api.js';
import { fmtDate, statusBadge, tierBadge, progressBar, spinner, emptyState, icon } from '../utils.js';

export async function renderDashboard(container) {
  container.innerHTML = `
    <div class="page-header">
      <div>
        <div class="page-title">Dashboard</div>
        <div class="page-subtitle">Your development memory at a glance</div>
      </div>
    </div>
    <div class="page-content" id="dash-body">${spinner()}</div>
  `;

  const body = document.getElementById('dash-body');

  try {
    const [billing, projects, sessions] = await Promise.all([
      api.get('/billing/status').catch(() => null),
      api.get('/projects'),
      api.get('/sessions?limit=5'),
    ]);

    const user = state.user;
    const tier = billing?.tier || 'free';
    const usage  = billing?.usage  || { projects: 0, total_sessions: 0 };
    const limits = billing?.limits || { max_projects: null, max_sessions_per_project: null };

    const activeSessions = (sessions?.sessions || []).filter(s => s.status === 'active').length;

    body.innerHTML = `
      <!-- Welcome -->
      <div class="welcome-banner">
        <div class="welcome-title">Welcome back${user?.email ? ', ' + user.email.split('@')[0] : ''}</div>
        <div class="welcome-sub">Here's what's been stored in your dev memory.</div>
      </div>

      <!-- Stats -->
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-label">Projects</div>
          <div class="stat-value" style="color:var(--accent)">${projects?.count ?? 0}</div>
          <div class="stat-sub">${limits.max_projects ? `of ${limits.max_projects} max` : 'unlimited'}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Total Sessions</div>
          <div class="stat-value" style="color:var(--blue)">${usage.total_sessions}</div>
          <div class="stat-sub">across all projects</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Active Sessions</div>
          <div class="stat-value" style="color:var(--green)">${activeSessions}</div>
          <div class="stat-sub">currently in progress</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Plan</div>
          <div class="stat-value" style="font-size:22px;margin-top:4px">${tierBadge(tier)}</div>
          <div class="stat-sub">current subscription</div>
        </div>
      </div>

      <div class="two-col">
        <!-- Usage -->
        ${billing ? `
        <div class="card">
          <div class="section-title">Quota Usage</div>
          ${progressBar(usage.projects, limits.max_projects, 'Projects')}
          ${progressBar(usage.total_sessions, limits.max_projects ? limits.max_projects * 10 : null, 'Sessions')}
        </div>
        ` : ''}

        <!-- Recent Sessions -->
        <div class="card" style="grid-column: ${billing ? 'auto' : '1/-1'}">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px">
            <div class="section-title" style="margin:0">Recent Sessions</div>
            <a href="#sessions" style="font-size:12px;color:var(--accent)">View all →</a>
          </div>
          ${sessions?.sessions?.length ? `
          <div class="table-wrap">
            <table>
              <thead><tr>
                <th>Title</th><th>Status</th><th>Tool</th><th>Updated</th>
              </tr></thead>
              <tbody>
                ${sessions.sessions.map(s => `
                  <tr onclick="window.location.hash='#sessions'">
                    <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${s.title}</td>
                    <td>${statusBadge(s.status)}</td>
                    <td style="color:var(--text-muted);font-size:12px">${s.tool_source || '—'}</td>
                    <td style="color:var(--text-muted);font-size:12px">${fmtDate(s.updated_at)}</td>
                  </tr>`).join('')}
              </tbody>
            </table>
          </div>
          ` : emptyState('layers', 'No sessions yet', 'Sessions are created automatically by the MCP tools.')}
        </div>
      </div>

      <!-- Projects preview -->
      <div style="margin-top:16px">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px">
          <div class="section-title">Projects</div>
          <a href="#projects" style="font-size:12px;color:var(--accent)">View all →</a>
        </div>
        ${projects?.projects?.length ? `
          <div class="projects-grid">
            ${projects.projects.slice(0,3).map(p => `
              <div class="project-card" onclick="window.location.hash='#projects'">
                <div class="project-name">${p.name}</div>
                <div class="project-slug">${p.slug}</div>
                ${p.remote_url ? `<div class="project-url">${p.remote_url}</div>` : ''}
                <div class="project-meta">
                  <span>Created ${fmtDate(p.created_at)}</span>
                </div>
              </div>`).join('')}
          </div>
        ` : emptyState('folder-git-2', 'No projects yet', 'Projects are auto-detected from git remotes.')}
      </div>
    `;
  } catch (err) {
    body.innerHTML = `<div class="empty-state"><div class="empty-title">Failed to load dashboard</div><div class="empty-desc">${err.message}</div></div>`;
  }
}
