import { api } from '../api.js';
import { icon } from '../utils.js';

/** #reset?token=… — set a new password from an emailed link. Public (no auth). */
export function renderReset(container, params = {}) {
  const token = params.token || '';

  if (!token) {
    container.innerHTML = `
      <div class="auth-screen"><div class="auth-card">
        <div class="auth-logo"><div class="auth-logo-icon">${icon('cpu', 22)}</div>
          <span class="auth-logo-text">DevMemory</span></div>
        <div class="auth-error show">This reset link is missing its token. Request a new one.</div>
        <div style="text-align:center;margin-top:14px"><a href="#forgot" class="auth-link">Request a new link</a></div>
      </div></div>`;
    return;
  }

  container.innerHTML = `
    <div class="auth-screen">
      <div class="auth-card">
        <div class="auth-logo">
          <div class="auth-logo-icon">${icon('cpu', 22)}</div>
          <span class="auth-logo-text">DevMemory</span>
        </div>
        <div class="page-title" style="text-align:center;margin-bottom:18px">Choose a new password</div>
        <div id="auth-error" class="auth-error"></div>
        <div id="reset-done" style="display:none">
          <div class="auth-note">${icon('check-circle', 16)} Password reset. You can sign in now.</div>
          <a href="#login" class="btn btn-primary" style="width:100%;margin-top:14px;text-align:center">Go to sign in</a>
        </div>
        <form id="form-reset">
          <div class="form-group">
            <label class="form-label">New password</label>
            <input id="reset-pw" type="password" class="form-input" placeholder="Min 8 characters" required minlength="8">
          </div>
          <div class="form-group">
            <label class="form-label">Confirm password</label>
            <input id="reset-pw2" type="password" class="form-input" placeholder="Re-enter password" required minlength="8">
          </div>
          <button type="submit" class="btn btn-primary" style="width:100%;margin-top:4px" id="reset-submit">
            Reset password
          </button>
        </form>
      </div>
    </div>
  `;

  const errEl = document.getElementById('auth-error');
  const form  = document.getElementById('form-reset');

  function showErr(msg) { errEl.textContent = msg; errEl.classList.add('show'); }

  form.addEventListener('submit', async e => {
    e.preventDefault();
    errEl.classList.remove('show');
    const pw  = document.getElementById('reset-pw').value;
    const pw2 = document.getElementById('reset-pw2').value;
    if (pw !== pw2) { showErr('Passwords do not match.'); return; }
    const btn = document.getElementById('reset-submit');
    btn.disabled = true; btn.textContent = 'Resetting…';
    try {
      await api.post('/auth/reset-password', { token, new_password: pw });
      form.style.display = 'none';
      document.getElementById('reset-done').style.display = '';
    } catch (err) {
      showErr(err.message);
      btn.disabled = false; btn.textContent = 'Reset password';
    }
  });
}
