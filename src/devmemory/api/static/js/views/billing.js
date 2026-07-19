import { api } from '../api.js';
import { tierBadge, progressBar, spinner, emptyState, icon, toast, copyText } from '../utils.js';

export async function renderBilling(container) {
  stopPolling();
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
            <div style="font-size:13px;font-weight:600;margin-bottom:8px">${icon('sparkles', 15)} Upgrade to ${tier === 'free' ? 'Pro' : 'Team'}</div>
            <div style="font-size:12.5px;color:var(--text-secondary);margin-bottom:12px">Pay in ADA on Cardano. More projects, sessions, and context blocks.</div>
            <div style="display:flex;gap:8px;flex-wrap:wrap">
              ${tier === 'free' ? `<button class="btn btn-primary" data-upgrade="pro">Upgrade to Pro</button>` : ''}
              <button class="btn btn-primary" data-upgrade="team">Upgrade to Team</button>
            </div>
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
                ['Projects',              '10',      '25',    'Unlimited'],
                ['Sessions / project',    '30',      '100',   'Unlimited'],
                ['Blocks / session',      '1,500',   '5,000', 'Unlimited'],
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

    body.querySelectorAll('[data-upgrade]').forEach(btn => {
      btn.addEventListener('click', () => startUpgrade(btn.dataset.upgrade));
    });
  } catch (err) {
    body.innerHTML = emptyState('alert-triangle', 'Failed to load billing status', err.message);
  }
}

function openPayModal(inner) {
  closePayModal();
  const backdrop = document.createElement('div');
  backdrop.className = 'confirm-backdrop';
  backdrop.id = 'pay-backdrop';
  backdrop.innerHTML = `
    <div class="pay-modal" role="dialog" aria-modal="true" aria-labelledby="pay-modal-title">
      <button class="pay-modal-close" id="pay-modal-close" aria-label="Close">${icon('x', 18)}</button>
      <div id="pay-modal-body">${inner}</div>
    </div>
  `;
  backdrop.addEventListener('click', (e) => { if (e.target === backdrop) closePayModal(); });
  document.addEventListener('keydown', onPayKey);
  document.body.appendChild(backdrop);
  backdrop.querySelector('#pay-modal-close').addEventListener('click', () => closePayModal());
  return backdrop.querySelector('#pay-modal-body');
}

function onPayKey(e) { if (e.key === 'Escape') closePayModal(); }

function closePayModal() {
  stopPolling();
  document.removeEventListener('keydown', onPayKey);
  const b = document.getElementById('pay-backdrop');
  if (b) { b.classList.add('closing'); setTimeout(() => b.remove(), 120); }
}

async function startUpgrade(tier) {
  const bodyEl = openPayModal(`<div style="padding:20px 0">${spinner()}</div>`);
  try {
    const inv = await api.post('/billing/upgrade', { tier });
    renderPayPanel(inv);
  } catch (err) {
    // 503 = payments not configured on this server.
    const msg = /not configured/i.test(err.message)
      ? 'Cardano payments are not enabled on this server yet.'
      : err.message;
    if (bodyEl) bodyEl.innerHTML = emptyState('alert-triangle', 'Could not start upgrade', msg);
  }
}

let _pollTimer = null;
let _countdownTimer = null;

function renderPayPanel(inv) {
  const panel = document.getElementById('pay-modal-body');
  if (!panel) return;
  const ada = (Math.round(inv.amount_ada * 1e6) / 1e6).toString();
  const devMode = localStorage.getItem('dm_dev') === '1';

  panel.innerHTML = `
    <div class="card-title" id="pay-modal-title">Complete your upgrade to ${inv.tier.toUpperCase()}</div>
    <div style="font-size:12.5px;color:var(--text-secondary);margin:6px 0 18px">
      Send the exact amount to this address on <b>${inv.network}</b>. It confirms automatically.
    </div>

    <div style="font-size:11px;color:var(--text-muted);margin-bottom:6px">AMOUNT</div>
    <div style="display:flex;gap:8px;align-items:center;margin-bottom:14px">
      <div style="flex:1;font-size:22px;font-weight:700">${ada} <span style="font-size:14px;color:var(--text-muted)">ADA</span></div>
      <button class="btn btn-ghost btn-sm" data-copy="${ada}" title="Copy amount">${icon('copy',15)}</button>
    </div>

    <div style="font-size:11px;color:var(--text-muted);margin-bottom:6px">TO ADDRESS</div>
    <div style="display:flex;gap:8px;align-items:center;margin-bottom:18px">
      <code style="flex:1;background:var(--bg-base);padding:10px 12px;border-radius:var(--radius-sm);word-break:break-all;font-size:12px">${inv.pay_to_address}</code>
      <button class="btn btn-ghost btn-sm" data-copy="${inv.pay_to_address}" title="Copy address">${icon('copy',15)}</button>
    </div>

    <div style="display:flex;align-items:center;gap:10px;padding-top:14px;border-top:1px solid var(--border)">
      <div class="spinner-dot" style="width:9px;height:9px;border-radius:50%;background:var(--blue);flex:none;animation:pulse 1.4s ease-in-out infinite"></div>
      <div style="flex:1">
        <div id="pay-status" style="font-size:13px;font-weight:500">Waiting for payment…</div>
        <div id="pay-expiry" style="font-size:11.5px;color:var(--text-muted)"></div>
      </div>
      ${devMode ? `<button class="btn btn-ghost btn-sm" id="sim-pay">Simulate (dev)</button>` : ''}
    </div>
    <style>@keyframes pulse{0%,100%{opacity:.35}50%{opacity:1}}</style>
  `;

  panel.querySelectorAll('[data-copy]').forEach(b =>
    b.addEventListener('click', () => copyText(b.dataset.copy, b)));

  const statusEl = document.getElementById('pay-status');
  const expiryEl = document.getElementById('pay-expiry');

  const finish = (res) => {
    if (res.status === 'paid') {
      closePayModal();
      toast(`Payment confirmed — upgraded to ${res.tier.toUpperCase()}!`);
      setTimeout(() => renderBilling(document.getElementById('main')), 800);
      return true;
    }
    if (res.status === 'expired') {
      stopPolling();
      statusEl.textContent = 'Payment window expired — start a new upgrade.';
      expiryEl.textContent = '';
      return true;
    }
    return false;
  };

  const poll = async () => {
    try { finish(await api.get(`/billing/invoice/${inv.invoice_id}`)); } catch { /* keep waiting */ }
  };

  const sim = document.getElementById('sim-pay');
  if (sim) sim.addEventListener('click', async () => {
    try { finish(await api.post(`/billing/invoice/${inv.invoice_id}/simulate-paid`, {})); }
    catch (err) { statusEl.textContent = err.message; }
  });

  // Silent auto-detect + expiry countdown.
  stopPolling();
  _pollTimer = setInterval(poll, 8000);
  const expiresAt = new Date(inv.expires_at).getTime();
  const tick = () => {
    const ms = expiresAt - Date.now();
    if (ms <= 0) { expiryEl.textContent = ''; return; }
    const m = Math.floor(ms / 60000), s = Math.floor((ms % 60000) / 1000);
    expiryEl.textContent = `Expires in ${m}:${String(s).padStart(2, '0')}`;
  };
  tick();
  _countdownTimer = setInterval(tick, 1000);
}

function stopPolling() {
  if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
  if (_countdownTimer) { clearInterval(_countdownTimer); _countdownTimer = null; }
}
