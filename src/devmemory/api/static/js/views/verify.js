import { api, isLoggedIn } from '../api.js';
import { icon, spinner } from '../utils.js';

/** #verify?token=… — confirm an email address. Public; auto-submits the token. */
export async function renderVerify(container, params = {}) {
  const token = params.token || '';

  function shell(inner) {
    container.innerHTML = `
      <div class="auth-screen"><div class="auth-card">
        <div class="auth-logo"><div class="auth-logo-icon">${icon('cpu', 22)}</div>
          <span class="auth-logo-text">DevMemory</span></div>
        ${inner}
      </div></div>`;
  }

  if (!token) {
    shell(`
      <div class="auth-error show">This verification link is missing its token.</div>
      <div style="text-align:center;margin-top:14px"><a href="#login" class="auth-link">Back to sign in</a></div>`);
    return;
  }

  shell(`<div style="text-align:center;padding:20px 0">${spinner()}<div class="page-subtitle" style="margin-top:10px">Verifying your email…</div></div>`);

  // Where to send the user afterward: dashboard if signed in, else sign-in.
  const nextHash = isLoggedIn() ? '#dashboard' : '#login';
  const nextLabel = isLoggedIn() ? 'Go to dashboard' : 'Go to sign in';

  try {
    const res = await api.post('/auth/verify-email', { token });
    shell(`
      <div class="auth-note">${icon('check-circle', 16)} ${res.message || 'Your email has been verified.'}</div>
      <a href="${nextHash}" class="btn btn-primary" style="width:100%;margin-top:16px;text-align:center">${nextLabel}</a>`);
  } catch (err) {
    shell(`
      <div class="auth-error show">${err.message}</div>
      <div style="text-align:center;margin-top:14px"><a href="#login" class="auth-link">Back to sign in</a></div>`);
  }
}
