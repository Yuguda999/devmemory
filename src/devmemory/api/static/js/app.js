import { detectMode, isLoggedIn, logout, state } from './api.js';
import { icon, confirmDialog } from './utils.js';
import { renderLogin }     from './views/login.js';
import { renderDashboard } from './views/dashboard.js';
import { renderProjects }  from './views/projects.js';
import { renderSessions }  from './views/sessions.js';
import { renderKeys }      from './views/keys.js';
import { renderBilling }   from './views/billing.js';
import { renderSetup }     from './views/setup.js';
import { renderSettings }  from './views/settings.js';
import { renderForgot }    from './views/forgot.js';
import { renderReset }     from './views/reset.js';
import { renderVerify }    from './views/verify.js';

const ROUTES = {
  '#login':     { label: 'Login',     render: renderLogin,    nav: false },
  '#forgot':    { label: 'Forgot',    render: renderForgot,   nav: false },
  '#reset':     { label: 'Reset',     render: renderReset,    nav: false },
  '#verify':    { label: 'Verify',    render: renderVerify,   nav: false },
  '#dashboard': { label: 'Dashboard', render: renderDashboard, icon: 'layout-dashboard' },
  '#projects':  { label: 'Projects',  render: renderProjects,  icon: 'folder-git-2' },
  '#sessions':  { label: 'Sessions',  render: renderSessions,  icon: 'layers' },
  '#keys':      { label: 'API Keys',  render: renderKeys,      icon: 'key-round' },
  '#setup':     { label: 'Setup',     render: renderSetup,     icon: 'rocket' },
  '#billing':   { label: 'Billing',   render: renderBilling,   icon: 'credit-card' },
  '#settings':  { label: 'Settings',  render: renderSettings,  icon: 'settings' },
};

// Reachable without being logged in (and rendered full-screen, no sidebar).
const PUBLIC_ROUTES = ['#login', '#forgot', '#reset', '#verify'];

/** Build or rebuild the sidebar to reflect current auth state */
function buildSidebar() {
  const sidebar = document.getElementById('sidebar');
  const navItems = Object.entries(ROUTES).filter(([,r]) => r.nav !== false);

  const showSignOut = isLoggedIn() && !state.selfHosted;

  sidebar.innerHTML = `
    <div class="sidebar-logo">
      <div class="logo-icon">${icon('cpu', 18)}</div>
      <span class="logo-text">DevMemory</span>
    </div>
    <nav class="sidebar-nav">
      <div class="nav-section-label">Navigation</div>
      ${navItems.map(([hash, r]) => `
        <button class="nav-link" data-route="${hash}" id="nav-${hash.slice(1)}">
          <span class="nav-icon">${icon(r.icon, 16)}</span>${r.label}
        </button>`).join('')}
      ${showSignOut ? `
        <hr class="divider">
        <button class="nav-link" id="btn-logout" style="color:var(--red)">
          <span class="nav-icon">${icon('log-out', 16)}</span>Sign Out
        </button>` : ''}
    </nav>
    <div class="sidebar-footer">
      <div class="user-card">
        <div class="user-avatar">${state.user?.email?.[0]?.toUpperCase() || '?'}</div>
        <div class="user-info">
          <div class="user-name">${state.selfHosted ? 'Self-Hosted' : (state.user?.email || 'Guest')}</div>
          <div class="user-tier">${state.selfHosted ? 'Local Instance' : 'DevMemory'}</div>
        </div>
      </div>
    </div>
  `;

  // Nav click handlers
  document.querySelectorAll('.nav-link[data-route]').forEach(btn => {
    btn.addEventListener('click', () => { window.location.hash = btn.dataset.route; });
  });
  document.getElementById('btn-logout')?.addEventListener('click', async () => {
    const ok = await confirmDialog({
      title: 'Sign out?',
      message: 'You will need to sign in again to access your dashboard.',
      confirmText: 'Sign Out',
      danger: true,
    });
    if (ok) logout();
  });
}

// Expose buildSidebar for login.js to call after successful login
window.__buildSidebar = buildSidebar;

/** Create the mobile hamburger + backdrop once, and wire the drawer toggle. */
function ensureMobileChrome() {
  if (document.getElementById('menu-toggle')) return;
  const btn = document.createElement('button');
  btn.id = 'menu-toggle';
  btn.className = 'menu-toggle';
  btn.setAttribute('aria-label', 'Toggle navigation');
  btn.innerHTML = icon('menu', 20);
  const backdrop = document.createElement('div');
  backdrop.id = 'sidebar-backdrop';
  backdrop.className = 'sidebar-backdrop';
  document.body.append(btn, backdrop);

  const sidebar = document.getElementById('sidebar');
  btn.addEventListener('click', () => {
    const open = sidebar.classList.toggle('open');
    backdrop.classList.toggle('show', open);
  });
  backdrop.addEventListener('click', () => {
    sidebar.classList.remove('open');
    backdrop.classList.remove('show');
  });
}

async function init() {
  await detectMode();
  buildSidebar();
  ensureMobileChrome();

  // Route on hash change
  window.addEventListener('hashchange', route);
  route();
}

function route() {
  const rawHash = window.location.hash || '#dashboard';
  const [hash, queryStr] = rawHash.split('?');
  const params = Object.fromEntries(new URLSearchParams(queryStr || ''));

  // Auth guard. Public routes (login + password/verify flows) are always
  // reachable; everything else requires a session.
  const isPublic = PUBLIC_ROUTES.includes(hash);
  if (!isLoggedIn()) {
    if (!isPublic) { window.location.hash = '#login'; return; }
  } else if (hash === '#login') {
    window.location.hash = '#dashboard'; return;
  }

  const target = ROUTES[hash] || ROUTES['#dashboard'];

  // Update active nav
  document.querySelectorAll('.nav-link[data-route]').forEach(b => {
    b.classList.toggle('active', b.dataset.route === hash);
  });

  const sidebar = document.getElementById('sidebar');
  const main = document.getElementById('main');
  // Public auth pages fill the whole viewport with no sidebar. When a logged-in
  // user opens #verify (email-change confirm), keep the full-screen card too.
  const fullScreen = isPublic;
  if (fullScreen) {
    document.getElementById('app').style.display = 'block';
    sidebar.style.display = 'none';
    main.style.display = 'block';
    target.render(main, params);
  } else {
    document.getElementById('app').style.display = '';
    sidebar.style.display = '';
    main.style.display = '';
    target.render(main, params);
  }

  // Mobile drawer: close on every navigation; hide the hamburger on auth pages.
  sidebar.classList.remove('open');
  document.getElementById('sidebar-backdrop')?.classList.remove('show');
  const menuToggle = document.getElementById('menu-toggle');
  if (menuToggle) menuToggle.style.display = fullScreen ? 'none' : '';
}

init();
