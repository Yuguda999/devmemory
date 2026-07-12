import { api } from '../api.js';
import { icon } from '../utils.js';

/** #forgot — request a password-reset link. Public (no auth). */
export function renderForgot(container) {
  container.innerHTML = `
    <div class="auth-screen">
      <div class="auth-card">
        <div class="auth-logo">
          <div class="auth-logo-icon">${icon('cpu', 22)}</div>
          <span class="auth-logo-text">DevMemory</span>
        </div>
        <div class="page-title" style="text-align:center;margin-bottom:6px">Reset password</div>
        <div class="page-subtitle" style="text-align:center;margin-bottom:18px">
          Enter your email and we'll send you a reset link.
        </div>
        <div id="auth-error" class="auth-error"></div>
        <div id="forgot-done" style="display:none">
          <div class="auth-note">${icon('mail-check', 16)} If an account with that email exists, a reset link is on its way.</div>
        </div>
        <form id="form-forgot">
          <div class="form-group">
            <label class="form-label">Email</label>
            <input id="forgot-email" type="email" class="form-input" placeholder="you@example.com" required>
          </div>
          <button type="submit" class="btn btn-primary" style="width:100%;margin-top:4px" id="forgot-submit">
            Send reset link
          </button>
          <div style="text-align:center;margin-top:14px">
            <a href="#login" class="auth-link">Back to sign in</a>
          </div>
        </form>
      </div>
    </div>
  `;

  const errEl = document.getElementById('auth-error');
  const form  = document.getElementById('form-forgot');

  form.addEventListener('submit', async e => {
    e.preventDefault();
    errEl.classList.remove('show');
    const btn = document.getElementById('forgot-submit');
    btn.disabled = true; btn.textContent = 'Sending…';
    try {
      await api.post('/auth/forgot-password', {
        email: document.getElementById('forgot-email').value,
      });
      form.style.display = 'none';
      document.getElementById('forgot-done').style.display = '';
    } catch (err) {
      errEl.textContent = err.message;
      errEl.classList.add('show');
      btn.disabled = false; btn.textContent = 'Send reset link';
    }
  });
}
