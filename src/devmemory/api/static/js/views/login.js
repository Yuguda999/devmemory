import { api, setAuth } from '../api.js';
import { toast, icon } from '../utils.js';

export function renderLogin(container) {
  container.innerHTML = `
    <div class="auth-screen">
      <div class="auth-card">
        <div class="auth-logo">
          <div class="auth-logo-icon">${icon('cpu', 22)}</div>
          <span class="auth-logo-text">DevMemory</span>
        </div>
        <div class="auth-tabs">
          <button class="auth-tab active" id="tab-login">Sign In</button>
          <button class="auth-tab" id="tab-register">Register</button>
        </div>
        <div id="auth-error" class="auth-error"></div>

        <!-- Login Form -->
        <form id="form-login">
          <div class="form-group">
            <label class="form-label">Email</label>
            <input id="login-email" type="email" class="form-input" placeholder="you@example.com" required>
          </div>
          <div class="form-group">
            <label class="form-label">Password</label>
            <input id="login-password" type="password" class="form-input" placeholder="••••••••" required>
          </div>
          <button type="submit" class="btn btn-primary" style="width:100%;margin-top:4px" id="login-submit">
            Sign In
          </button>
        </form>

        <!-- Register Form (hidden) -->
        <form id="form-register" style="display:none">
          <div class="form-group">
            <label class="form-label">Display Name</label>
            <input id="reg-name" type="text" class="form-input" placeholder="Your Name" required>
          </div>
          <div class="form-group">
            <label class="form-label">Email</label>
            <input id="reg-email" type="email" class="form-input" placeholder="you@example.com" required>
          </div>
          <div class="form-group">
            <label class="form-label">Password</label>
            <input id="reg-password" type="password" class="form-input" placeholder="Min 8 characters" required minlength="8">
          </div>
          <button type="submit" class="btn btn-primary" style="width:100%;margin-top:4px" id="reg-submit">
            Create Account
          </button>
        </form>
      </div>
    </div>
  `;

  const errEl   = document.getElementById('auth-error');
  const tabLogin = document.getElementById('tab-login');
  const tabReg   = document.getElementById('tab-register');
  const fLogin   = document.getElementById('form-login');
  const fReg     = document.getElementById('form-register');

  function showErr(msg) {
    errEl.textContent = msg;
    errEl.classList.add('show');
  }
  function clearErr() { errEl.classList.remove('show'); }

  tabLogin.addEventListener('click', () => {
    tabLogin.classList.add('active'); tabReg.classList.remove('active');
    fLogin.style.display = ''; fReg.style.display = 'none';
    clearErr();
  });
  tabReg.addEventListener('click', () => {
    tabReg.classList.add('active'); tabLogin.classList.remove('active');
    fReg.style.display = ''; fLogin.style.display = 'none';
    clearErr();
  });

  fLogin.addEventListener('submit', async e => {
    e.preventDefault(); clearErr();
    const btn = document.getElementById('login-submit');
    btn.disabled = true; btn.textContent = 'Signing in…';
    try {
      const data = await api.post('/auth/login', {
        email:    document.getElementById('login-email').value,
        password: document.getElementById('login-password').value,
      });
      setAuth(data.access_token, { id: data.user_id, email: data.email });
      window.location.hash = '#dashboard';
    } catch (err) {
      showErr(err.message);
      btn.disabled = false; btn.textContent = 'Sign In';
    }
  });

  fReg.addEventListener('submit', async e => {
    e.preventDefault(); clearErr();
    const btn = document.getElementById('reg-submit');
    btn.disabled = true; btn.textContent = 'Creating account…';
    try {
      await api.post('/auth/register', {
        display_name: document.getElementById('reg-name').value,
        email:        document.getElementById('reg-email').value,
        password:     document.getElementById('reg-password').value,
      });
      toast('Account created! Please sign in.');
      tabLogin.click();
      btn.disabled = false; btn.textContent = 'Create Account';
    } catch (err) {
      showErr(err.message);
      btn.disabled = false; btn.textContent = 'Create Account';
    }
  });
}
