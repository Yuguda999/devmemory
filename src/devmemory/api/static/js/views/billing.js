import { api } from '../api.js';
import { tierBadge, progressBar, spinner, emptyState, icon } from '../utils.js';

export async function renderBilling(container) {
  container.innerHTML = `
    <div class="page-header">
      <div>
        <div class="page-title">Billing & Quota</div>
        <div class="page-subtitle">Your current plan, limits and usage</div>
      </div>
    </div>
    <div class="page-content" id="billing-body">${spinner()}</div>
  `;

  const body = document.getElementById('billing-body');
  try {
    const data = await api.get('/billing/status');
    const { tier, limits, usage } = data;

    const fmt = v => v === null || v === undefined ? 'Unlimited' : v.toLocaleString();

    body.innerHTML = `
      <div class="two-col">
        <!-- Tier card -->
        <div class="card" style="display:flex;flex-direction:column;gap:16px">
          <div>
            <div class="card-title">Current Plan</div>
            <div style="font-size:32px;font-weight:800;margin-top:8px">${tierBadge(tier)}</div>
          </div>
          <hr class="divider" style="margin:0">
          <div>
            <div class="card-title" style="margin-bottom:12px">Usage Summary</div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
              <div style="background:var(--bg-elevated);border-radius:var(--radius-sm);padding:14px">
                <div style="font-size:11px;color:var(--text-muted);margin-bottom:4px">Projects</div>
                <div style="font-size:24px;font-weight:700;color:var(--accent)">${usage.projects}</div>
              </div>
              <div style="background:var(--bg-elevated);border-radius:var(--radius-sm);padding:14px">
                <div style="font-size:11px;color:var(--text-muted);margin-bottom:4px">Sessions</div>
                <div style="font-size:24px;font-weight:700;color:var(--blue)">${usage.total_sessions}</div>
              </div>
            </div>
          </div>
          ${tier !== 'team' ? `
          <div style="background:rgba(124,110,247,0.08);border:1px solid rgba(124,110,247,0.2);border-radius:var(--radius-sm);padding:14px">
            <div style="font-size:13px;font-weight:600;margin-bottom:4px">${icon('sparkles', 15)} Upgrade to ${tier === 'free' ? 'Pro' : 'Team'}</div>
            <div style="font-size:12.5px;color:var(--text-secondary)">Get more projects, sessions, and context blocks.</div>
          </div>` : ''}
        </div>

        <!-- Usage bars -->
        <div class="card">
          <div class="card-title" style="margin-bottom:16px">Quota</div>
          ${progressBar(usage.projects, limits.max_projects, 'Projects')}
          ${progressBar(usage.total_sessions,
            limits.max_sessions_per_project && limits.max_projects
              ? limits.max_sessions_per_project * Math.max(usage.projects, 1)
              : null,
            'Total Sessions')}
        </div>
      </div>

      <!-- Limits comparison table -->
      <div class="card" style="margin-top:16px">
        <div class="section-title" style="margin-bottom:16px">Plan Comparison</div>
        <div class="table-wrap">
          <table>
            <thead><tr>
              <th>Feature</th>
              <th style="text-align:center">Free</th>
              <th style="text-align:center">Pro</th>
              <th style="text-align:center">Team</th>
            </tr></thead>
            <tbody style="cursor:default">
              ${[
                ['Projects',              '3',       '25',    'Unlimited'],
                ['Sessions / project',    '10',      '100',   'Unlimited'],
                ['Blocks / session',      '500',     '5,000', 'Unlimited'],
                ['REST API access',       '✓',       '✓',     '✓'],
                ['MCP tool access',       '✓',       '✓',     '✓'],
                ['Priority support',      '✗',       '✓',     '✓'],
              ].map(([label, free, pro, team]) => `
                <tr>
                  <td style="font-weight:500">${label}</td>
                  <td style="text-align:center;color:${tier==='free'?'var(--accent)':'var(--text-muted)'}">${free}</td>
                  <td style="text-align:center;color:${tier==='pro'?'var(--accent)':'var(--text-muted)'}">${pro}</td>
                  <td style="text-align:center;color:${tier==='team'?'var(--accent)':'var(--text-muted)'}">${team}</td>
                </tr>`).join('')}
            </tbody>
          </table>
        </div>
      </div>
    `;
  } catch (err) {
    body.innerHTML = emptyState('alert-triangle', 'Failed to load billing status', err.message);
  }
}
