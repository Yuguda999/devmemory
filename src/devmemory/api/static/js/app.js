import { detectMode, isLoggedIn, logout, state } from './api.js';
import { icon } from './utils.js';
import { renderLogin }     from './views/login.js';
import { renderDashboard } from './views/dashboard.js';
import { renderProjects }  from './views/projects.js';
import { renderSessions }  from './views/sessions.js';
import { renderKeys }      from './views/keys.js';
import { renderBilling }   from './views/billing.js';

const ROUTES = {
  '#login':     { label: 'Login',     render: renderLogin,    nav: false },
  '#dashboard': { label: 'Dashboard', render: renderDashboard, icon: 'layout-dashboard' },
  '#projects':  { label: 'Projects',  render: renderProjects,  icon: 'folder-git-2' },
  '#sessions':  { label: 'Sessions',  render: renderSessions,  icon: 'layers' },
  '#keys':      { label: 'API Keys',  render: renderKeys,      icon: 'key-round' },
  '#billing':   { label: 'Billing',   render: renderBilling,   icon: 'credit-card' },
};

async function init() {
  await detectMode();

  // Build sidebar
  const sidebar = document.getElementById('sidebar');
  const navItems = Object.entries(ROUTES).filter(([,r]) => r.nav !== false);

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
      <hr class="divider">
      ${isLoggedIn() && !state.selfHosted ? `
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
  document.getElementById('btn-logout')?.addEventListener('click', () => { if (confirm('Sign out?')) logout(); });

  // Route on hash change
  window.addEventListener('hashchange', route);
  route();
}

function route() {
  const rawHash = window.location.hash || '#dashboard';
  const [hash, queryStr] = rawHash.split('?');
  const params = Object.fromEntries(new URLSearchParams(queryStr || ''));

  // Auth guard
  if (!isLoggedIn()) {
    if (hash !== '#login') { window.location.hash = '#login'; return; }
  } else if (hash === '#login') {
    window.location.hash = '#dashboard'; return;
  }

  const target = ROUTES[hash] || ROUTES['#dashboard'];

  // Update active nav
  document.querySelectorAll('.nav-link[data-route]').forEach(b => {
    b.classList.toggle('active', b.dataset.route === hash);
  });

  const main = document.getElementById('main');
  if (hash === '#login') {
    // Login fills entire viewport — remove sidebar layout
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
}

init();
