/**
 * api.js — Fetch wrapper with JWT auth and self-hosted detection.
 */

const BASE = window.location.origin;

export const state = {
  token: localStorage.getItem('dm_token') || null,
  user:  JSON.parse(localStorage.getItem('dm_user') || 'null'),
  selfHosted: false,   // populated on init
  deploymentMode: 'saas',
};

/** Detect deployment mode from /health, and auto-authenticate in self-hosted mode */
export async function detectMode() {
  try {
    const r = await fetch(`${BASE}/health`);
    const d = await r.json();
    state.selfHosted    = d.self_hosted === true;
    state.deploymentMode = d.deployment_mode || 'saas';
  } catch {
    state.selfHosted = false;
  }

  // In self-hosted mode: silently get a guest JWT (no login needed)
  if (state.selfHosted && !state.token) {
    try {
      const r = await fetch(`${BASE}/auth/guest-token`, { method: 'POST' });
      if (r.ok) {
        const d = await r.json();
        setAuth(d.access_token, { id: d.user_id, email: d.email });
      }
    } catch { /* ignore — user will be prompted to login manually */ }
  }

  // In SaaS mode: validate any existing token from a previous session
  if (!state.selfHosted && state.token) {
    try {
      const r = await fetch(`${BASE}/billing/status`, {
        headers: { 'Authorization': `Bearer ${state.token}` },
      });
      if (r.status === 401) {
        // Stale or invalid token — clear auth so login page shows
        clearAuth();
      }
    } catch { /* network error — keep token, let views handle errors */ }
  }
}

/** Core fetch wrapper */
async function req(method, path, body) {
  const headers = { 'Content-Type': 'application/json' };
  if (state.token) headers['Authorization'] = `Bearer ${state.token}`;

  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  const text = await res.text();
  let data;
  try { data = JSON.parse(text); } catch { data = { detail: text }; }

  // A 401 on an authenticated request means the session token expired — clear it
  // and bounce to login. But a 401 from the auth endpoints themselves is just
  // bad credentials; let it propagate so the login form can show the error.
  const isAuthEndpoint = path.startsWith('/auth/login') || path.startsWith('/auth/register');
  if (res.status === 401 && state.token && !isAuthEndpoint) {
    logout();
    return;
  }

  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

export const api = {
  get:    (path)        => req('GET', path),
  post:   (path, body)  => req('POST', path, body),
  patch:  (path, body)  => req('PATCH', path, body),
  delete: (path)        => req('DELETE', path),
};

/* Auth helpers */
export function setAuth(token, user) {
  state.token = token;
  state.user  = user;
  localStorage.setItem('dm_token', token);
  localStorage.setItem('dm_user', JSON.stringify(user));
}

/** Clear auth state without triggering navigation (used by detectMode) */
function clearAuth() {
  state.token = null;
  state.user  = null;
  localStorage.removeItem('dm_token');
  localStorage.removeItem('dm_user');
}

export function logout() {
  clearAuth();
  window.location.hash = '#login';
  // Trigger full re-init so sidebar rebuilds without the sign-out button
  window.location.reload();
}

export function isLoggedIn() {
  return state.selfHosted || !!state.token;
}
