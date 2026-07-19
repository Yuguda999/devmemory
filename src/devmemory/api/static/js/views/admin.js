import { api } from '../api.js';
import {
  icon, spinner, emptyState, toast, tierBadge, statusBadge, fmtDate, confirmDialog,
} from '../utils.js';

let _search = '';

export async function renderAdmin(container) {
  container.innerHTML = `
    <div class="page-header">
      <div>
        <div class="page-title">Admin</div>
        <div class="page-subtitle">Platform overview, users, and payments</div>
      </div>
    </div>
    <div class="page-content" id="admin-body">${spinner()}</div>
  `;
  const body = document.getElementById('admin-body');

  let stats;
  try {
    stats = await api.get('/admin/stats');
  } catch (err) {
    body.innerHTML = /admin access/i.test(err.message)
      ? emptyState('shield', 'Admin access required', 'Your account is not an administrator.')
      : emptyState('alert-triangle', 'Failed to load admin data', err.message);
    return;
  }

  body.innerHTML = `
    <div class="stats-grid" id="admin-stats"></div>
    <div class="card" style="margin-top:16px">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:14px;flex-wrap:wrap">
        <div class="section-title">Users <span style="color:var(--text-muted);font-weight:400">(${stats.users_total})</span></div>
        <input id="admin-user-search" class="form-input" placeholder="Search email…" style="max-width:240px" value="${_search}">
      </div>
      <div id="admin-users">${spinner()}</div>
    </div>
    <div class="card" style="margin-top:16px">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:14px;flex-wrap:wrap">
        <div class="section-title">Payments</div>
        <select id="admin-inv-filter" class="form-input" style="max-width:160px">
          <option value="">All</option>
          <option value="paid">Paid</option>
          <option value="pending">Pending</option>
          <option value="expired">Expired</option>
        </select>
      </div>
      <div id="admin-invoices">${spinner()}</div>
    </div>
  `;

  renderStats(stats);
  loadUsers();
  loadInvoices('');

  const searchEl = document.getElementById('admin-user-search');
  let t;
  searchEl.addEventListener('input', () => {
    clearTimeout(t);
    t = setTimeout(() => { _search = searchEl.value.trim(); loadUsers(); }, 300);
  });
  document.getElementById('admin-inv-filter').addEventListener('change', (e) => loadInvoices(e.target.value));
}

function renderStats(s) {
  const tierStr = `${s.tiers.free || 0} / ${s.tiers.pro || 0} / ${s.tiers.team || 0}`;
  const cards = [
    ['Users', s.users_total, `${s.users_active} active · ${s.users_verified} verified`],
    ['Revenue', `${s.revenue_ada} ₳`, `${s.invoices_paid} paid · ${s.invoices_pending} pending`],
    ['Tiers (free/pro/team)', tierStr, 'subscriptions'],
    ['Content', s.projects, `${s.sessions} sessions · ${s.context_blocks} blocks`],
  ];
  document.getElementById('admin-stats').innerHTML = cards.map(([label, val, sub]) => `
    <div class="stat-card">
      <div class="stat-label">${label}</div>
      <div class="stat-value" style="font-size:${String(val).length > 8 ? '17px' : '24px'}">${val}</div>
      <div class="stat-sub">${sub}</div>
    </div>
  `).join('');
}

async function loadUsers() {
  const el = document.getElementById('admin-users');
  el.innerHTML = spinner();
  try {
    const { users } = await api.get(`/admin/users?limit=100&search=${encodeURIComponent(_search)}`);
    if (!users.length) { el.innerHTML = emptyState('users', 'No users'); return; }
    el.innerHTML = `
      <div class="table-wrap"><table>
        <thead><tr>
          <th>Email</th><th>Tier</th><th>Status</th><th style="text-align:center">Projects</th>
          <th style="text-align:center">Sessions</th><th>Joined</th><th></th>
        </tr></thead>
        <tbody>
          ${users.map(u => `
            <tr data-uid="${u.id}" data-email="${u.email}">
              <td style="font-weight:500">${u.email}${u.is_admin ? ` <span class="chip">admin</span>` : ''}${!u.email_verified ? ` <span class="chip" style="opacity:.6">unverified</span>` : ''}</td>
              <td>
                <select class="input input-sm js-tier" data-uid="${u.id}">
                  ${['free', 'pro', 'team'].map(t => `<option value="${t}" ${u.tier === t ? 'selected' : ''}>${t}</option>`).join('')}
                </select>
              </td>
              <td>${u.is_active ? statusBadge('active') : statusBadge('canceled')}</td>
              <td style="text-align:center">${u.projects}</td>
              <td style="text-align:center">${u.sessions}</td>
              <td style="color:var(--text-muted);font-size:12px">${fmtDate(u.created_at)}</td>
              <td style="text-align:right;white-space:nowrap">
                <button class="btn btn-ghost btn-sm js-toggle-active" data-uid="${u.id}" data-active="${u.is_active}" data-email="${u.email}">
                  ${u.is_active ? 'Deactivate' : 'Activate'}
                </button>
                <button class="btn btn-ghost btn-sm js-toggle-admin" data-uid="${u.id}" data-admin="${u.is_admin}" data-email="${u.email}">
                  ${u.is_admin ? 'Revoke admin' : 'Make admin'}
                </button>
              </td>
            </tr>`).join('')}
        </tbody>
      </table></div>
    `;
    wireUserActions();
  } catch (err) {
    el.innerHTML = emptyState('alert-triangle', 'Failed to load users', err.message);
  }
}

function wireUserActions() {
  document.querySelectorAll('.js-tier').forEach(sel =>
    sel.addEventListener('change', () => patchUser(sel.dataset.uid, { tier: sel.value }, `Tier → ${sel.value}`)));

  document.querySelectorAll('.js-toggle-active').forEach(btn =>
    btn.addEventListener('click', async () => {
      const active = btn.dataset.active === 'true';
      const ok = await confirmDialog({
        title: active ? 'Deactivate user?' : 'Activate user?',
        message: `${active ? 'Block' : 'Restore'} access for ${btn.dataset.email}?`,
        confirmText: active ? 'Deactivate' : 'Activate',
        danger: active,
      });
      if (ok) patchUser(btn.dataset.uid, { is_active: !active }, 'Updated');
    }));

  document.querySelectorAll('.js-toggle-admin').forEach(btn =>
    btn.addEventListener('click', async () => {
      const isAdmin = btn.dataset.admin === 'true';
      const ok = await confirmDialog({
        title: isAdmin ? 'Revoke admin?' : 'Grant admin?',
        message: `${isAdmin ? 'Remove' : 'Give'} superadmin access ${isAdmin ? 'from' : 'to'} ${btn.dataset.email}?`,
        confirmText: isAdmin ? 'Revoke' : 'Grant',
        danger: isAdmin,
      });
      if (ok) patchUser(btn.dataset.uid, { is_admin: !isAdmin }, 'Updated');
    }));
}

async function patchUser(uid, body, okMsg) {
  try {
    await api.patch(`/admin/users/${uid}`, body);
    toast(okMsg);
    loadUsers();
  } catch (err) {
    toast(err.message, 'error');
    loadUsers();
  }
}

async function loadInvoices(status) {
  const el = document.getElementById('admin-invoices');
  el.innerHTML = spinner();
  try {
    const { invoices } = await api.get(`/admin/invoices?limit=100${status ? `&status=${status}` : ''}`);
    if (!invoices.length) { el.innerHTML = emptyState('wallet', 'No payments'); return; }
    el.innerHTML = `
      <div class="table-wrap"><table>
        <thead><tr><th>User</th><th>Tier</th><th>Amount</th><th>Status</th><th>Network</th><th>Tx</th><th>Date</th></tr></thead>
        <tbody>
          ${invoices.map(i => `
            <tr>
              <td>${i.user_email}</td>
              <td>${tierBadge(i.tier)}</td>
              <td>${i.amount_ada} ₳</td>
              <td>${statusBadge(i.status === 'paid' ? 'active' : i.status === 'pending' ? 'pending' : 'canceled')} ${i.status}</td>
              <td style="font-size:12px;color:var(--text-muted)">${i.network}</td>
              <td style="font-family:monospace;font-size:11px">${i.tx_hash ? i.tx_hash.slice(0, 12) + '…' : '—'}</td>
              <td style="color:var(--text-muted);font-size:12px">${fmtDate(i.created_at)}</td>
            </tr>`).join('')}
        </tbody>
      </table></div>
    `;
  } catch (err) {
    el.innerHTML = emptyState('alert-triangle', 'Failed to load payments', err.message);
  }
}
