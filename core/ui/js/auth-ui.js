// SPDX-License-Identifier: AGPL-3.0-or-later
import { login, setupOwner } from './auth.js';

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function formValue(form, name) {
  const value = new FormData(form).get(name);
  return typeof value === 'string' ? value.trim() : '';
}

function setStatus(root, message, tone = 'neutral') {
  const status = root.querySelector('[data-role="auth-status"]');
  if (!status) return;
  status.textContent = message || '';
  status.dataset.tone = tone;
}

function renderRecoveryCodes(root, recoveryCodes, onContinue) {
  root.innerHTML = `
    <section class="auth-card auth-card--wide">
      <div class="auth-card-head">
        <p class="auth-eyebrow">Owner account created</p>
        <h1>Save your recovery codes</h1>
      </div>
      <p class="auth-copy">These codes are shown once. Store them somewhere durable before continuing.</p>
      <ol class="auth-recovery-list">
        ${(recoveryCodes || []).map((code) => `<li><code>${escapeHtml(code)}</code></li>`).join('')}
      </ol>
      <div class="auth-actions">
        <button type="button" class="btn primary" data-action="continue-after-recovery">I saved these codes</button>
      </div>
    </section>
  `;
  root.querySelector('[data-action="continue-after-recovery"]')?.addEventListener('click', () => {
    onContinue?.();
  });
}

function renderClaim(root, options) {
  const allowCancel = options.allowCancel === true;
  root.innerHTML = `
    <section class="auth-card auth-card--wide">
      <div class="auth-card-head">
        <p class="auth-eyebrow">Unclaimed local mode</p>
        <h1>Secure this BUS Core</h1>
      </div>
      <p class="auth-copy">Create the first owner account to enable login, users, permissions, recovery, and audit controls.</p>
      <form data-form="claim-owner" class="auth-form">
        <label>Username <input name="username" autocomplete="username" required></label>
        <label>Password <input name="password" type="password" autocomplete="new-password" required></label>
        <label>Display name <input name="display_name" autocomplete="name"></label>
        <label>Email <input name="email" type="email" autocomplete="email"></label>
        <label>Business name <input name="business_name" autocomplete="organization"></label>
        <div class="auth-status" data-role="auth-status" data-tone="neutral" aria-live="polite"></div>
        <div class="auth-actions">
          ${allowCancel ? '<button type="button" class="btn" data-action="cancel-claim">Cancel</button>' : ''}
          <button type="submit" class="btn primary">Create owner</button>
        </div>
      </form>
    </section>
  `;

  root.querySelector('[data-action="cancel-claim"]')?.addEventListener('click', () => {
    options.onCancel?.();
  });

  root.querySelector('[data-form="claim-owner"]')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const submit = form.querySelector('button[type="submit"]');
    const previousText = submit?.textContent || 'Create owner';
    if (submit) {
      submit.disabled = true;
      submit.textContent = 'Creating...';
    }
    setStatus(root, 'Creating owner account...');
    try {
      const payload = {
        username: formValue(form, 'username'),
        password: formValue(form, 'password'),
        display_name: formValue(form, 'display_name') || null,
        email: formValue(form, 'email') || null,
        business_name: formValue(form, 'business_name') || null,
      };
      const result = await setupOwner(payload);
      renderRecoveryCodes(root, result?.recovery_codes || [], options.onAuthenticated);
    } catch (error) {
      console.error('owner setup failed', error);
      setStatus(root, 'Unable to create the owner account. Check the fields and try again.', 'error');
    } finally {
      if (submit && root.contains(submit)) {
        submit.disabled = false;
        submit.textContent = previousText;
      }
    }
  });
}

function renderLogin(root, options) {
  root.innerHTML = `
    <section class="auth-card">
      <div class="auth-card-head">
        <p class="auth-eyebrow">Claimed mode</p>
        <h1>Sign in to BUS Core</h1>
      </div>
      <form data-form="login" class="auth-form">
        <label>Username <input name="username" autocomplete="username" required autofocus></label>
        <label>Password <input name="password" type="password" autocomplete="current-password" required></label>
        <div class="auth-status" data-role="auth-status" data-tone="neutral" aria-live="polite"></div>
        <div class="auth-actions">
          <button type="submit" class="btn primary">Log in</button>
        </div>
      </form>
    </section>
  `;

  root.querySelector('[data-form="login"]')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const submit = form.querySelector('button[type="submit"]');
    const previousText = submit?.textContent || 'Log in';
    if (submit) {
      submit.disabled = true;
      submit.textContent = 'Signing in...';
    }
    setStatus(root, 'Signing in...');
    try {
      await login({ username: formValue(form, 'username'), password: formValue(form, 'password') });
      options.onAuthenticated?.();
    } catch (error) {
      console.error('login failed', error);
      if (error?.error === 'setup_required' || error?.status === 409) {
        setStatus(root, 'This BUS Core is unclaimed. Create an owner account to enable login.', 'warn');
      } else {
        setStatus(root, 'Username or password was not accepted.', 'error');
      }
    } finally {
      if (submit) {
        submit.disabled = false;
        submit.textContent = previousText;
      }
    }
  });
}

export function mountAuthGate(container, options = {}) {
  if (!container) return;
  const state = options.state || {};
  const mode = options.mode || (state.mode === 'unclaimed' ? 'claim' : 'login');
  container.classList.remove('hidden');
  if (mode === 'claim') {
    renderClaim(container, options);
    return;
  }
  renderLogin(container, options);
}