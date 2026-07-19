import { api, setUser } from '../api.js';
import { fmtDate, spinner, emptyState, toast, icon } from '../utils.js';

/** #settings — profile, password, email, and notification preferences. */
export async function renderSettings(container) {
  container.innerHTML = `
    <div class="page-header">
      <div>
        <div class="page-title">Settings</div>
        <div class="page-subtitle">Manage your profile, password, and notifications</div>
      </div>
    </div>
    <div class="page-content" id="settings-body">${spinner()}</div>
  `;

  const body = document.getElementById('settings-body');

  let me;
  try {
    me = await api.get('/account/me');
    setUser({
      id: me.id, email: me.email, display_name: me.display_name,
      email_verified: me.email_verified, tier: me.tier,
    });
  } catch (err) {
    body.innerHTML = emptyState('alert-triangle', 'Failed to load settings', err.message);
    return;
  }

  const verifiedBadge = me.email_verified
    ? '<span class="badge badge-active">Verified</span>'
    : '<span class="badge badge-paused">Unverified</span>';

  body.innerHTML = `
    <div class="two-col">
      <!-- Profile -->
      <div class="card" style="margin-bottom:20px">
        <div class="section-title" style="margin-bottom:14px">Profile</div>
        <div class="form-group">
          <label class="form-label">Display name</label>
          <input id="set-name" type="text" class="form-input" value="${escapeAttr(me.display_name)}" maxlength="100">
        </div>
        <div class="form-group">
          <label class="form-label">Email ${verifiedBadge}</label>
          <input id="set-email-display" type="email" class="form-input" value="${escapeAttr(me.email)}" disabled>
        </div>
        ${!me.email_verified ? `
          <div class="auth-note" style="margin-bottom:12px">
            ${icon('mail', 14)} Your email isn't verified.
            <a href="#" id="btn-resend" class="auth-link">Resend verification</a>
          </div>` : ''}
        <div style="display:flex;gap:10px;flex-wrap:wrap">
          <button class="btn btn-primary btn-sm" id="btn-save-profile">Save profile</button>
        </div>
      </div>

      <!-- Password -->
      <div class="card" style="margin-bottom:20px">
        <div class="section-title" style="margin-bottom:14px">Password</div>
        <div class="form-group">
          <label class="form-label">Current password</label>
          <input id="set-cur-pw" type="password" class="form-input" placeholder="••••••••">
        </div>
        <div class="form-group">
          <label class="form-label">New password</label>
          <input id="set-new-pw" type="password" class="form-input" placeholder="Min 8 characters" minlength="8">
        </div>
        <div class="form-group">
          <label class="form-label">Confirm new password</label>
          <input id="set-new-pw2" type="password" class="form-input" placeholder="Re-enter password" minlength="8">
        </div>
        <button class="btn btn-primary btn-sm" id="btn-change-pw">Change password</button>
      </div>
    </div>

    <!-- Notifications -->
    <div class="card" style="max-width:560px">
      <div class="section-title" style="margin-bottom:6px">Email notifications</div>
      <div class="page-subtitle" style="margin-bottom:14px">
        Transactional emails (verification, password reset) are always sent.
      </div>
      ${toggleRow('security_alerts', 'Security alerts', 'New sign-ins and password/email changes', me.notification_prefs.security_alerts)}
      ${toggleRow('account_events', 'Account updates', 'Welcome message and plan changes', me.notification_prefs.account_events)}
    </div>

    <div class="page-subtitle" style="margin-top:18px">Member since ${fmtDate(me.created_at)}</div>
  `;

  // ── Profile ──
  document.getElementById('btn-save-profile').addEventListener('click', async () => {
    const display_name = document.getElementById('set-name').value.trim();
    if (!display_name) { toast('Display name cannot be empty', 'error'); return; }
    const btn = document.getElementById('btn-save-profile');
    btn.disabled = true; btn.textContent = 'Saving…';
    try {
      const updated = await api.patch('/account/profile', { display_name });
      setUser({ display_name: updated.display_name });
      if (window.__buildSidebar) window.__buildSidebar();
      toast('Profile updated');
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      btn.disabled = false; btn.textContent = 'Save profile';
    }
  });

  document.getElementById('btn-resend')?.addEventListener('click', async (e) => {
    e.preventDefault();
    try {
      await api.post('/auth/resend-verification', { email: me.email });
      toast('Verification email sent');
    } catch (err) { toast(err.message, 'error'); }
  });

  // ── Change password ──
  document.getElementById('btn-change-pw').addEventListener('click', async () => {
    const current_password = document.getElementById('set-cur-pw').value;
    const new_password     = document.getElementById('set-new-pw').value;
    const confirm          = document.getElementById('set-new-pw2').value;
    if (!current_password || !new_password) { toast('Fill in all password fields', 'error'); return; }
    if (new_password.length < 8) { toast('New password must be at least 8 characters', 'error'); return; }
    if (new_password !== confirm) { toast('New passwords do not match', 'error'); return; }
    const btn = document.getElementById('btn-change-pw');
    btn.disabled = true; btn.textContent = 'Changing…';
    try {
      await api.post('/account/change-password', { current_password, new_password });
      toast('Password changed');
      ['set-cur-pw', 'set-new-pw', 'set-new-pw2'].forEach(id => document.getElementById(id).value = '');
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      btn.disabled = false; btn.textContent = 'Change password';
    }
  });

  // ── Notification toggles ──
  body.querySelectorAll('[data-pref]').forEach(el => {
    el.addEventListener('change', async () => {
      const key = el.dataset.pref;
      const value = el.checked;
      el.disabled = true;
      try {
        await api.patch('/account/notifications', { [key]: value });
        toast('Preferences saved');
      } catch (err) {
        el.checked = !value;  // revert on failure
        toast(err.message, 'error');
      } finally {
        el.disabled = false;
      }
    });
  });
}

function toggleRow(key, title, desc, checked) {
  return `
    <label class="toggle-row">
      <div>
        <div class="toggle-title">${title}</div>
        <div class="toggle-desc">${desc}</div>
      </div>
      <span class="toggle-switch">
        <input type="checkbox" data-pref="${key}" ${checked ? 'checked' : ''}>
        <span class="toggle-slider"></span>
      </span>
    </label>`;
}

function escapeAttr(s) {
  return String(s ?? '').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
