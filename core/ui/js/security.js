// SPDX-License-Identifier: AGPL-3.0-or-later
import {
  createUser,
  disableUser,
  enableUser,
  listAudit,
  listRoles,
  listSessions,
  listUsers,
  resetPassword,
  revokeSession,
  setUserRoles,
} from './auth.js';

const PERMISSIONS = {
  auditRead: 'audit.read',
  sessionsManage: 'sessions.manage',
  usersManage: 'users.manage',
  usersRead: 'users.read',
};

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function permissionsFor(state) {
  return new Set(state?.current_user?.permissions || []);
}

function hasPermission(state, permission) {
  return permissionsFor(state).has(permission);
}

function formatDate(value) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
}

function selectedValues(select) {
  return Array.from(select?.selectedOptions || []).map((option) => option.value);
}

function roleOptions(roles, selected = []) {
  const selectedSet = new Set(selected);
  return (roles || [])
    .map((role) => {
      const key = String(role.key || '');
      const label = role.name || key;
      return `<option value="${escapeHtml(key)}" ${selectedSet.has(key) ? 'selected' : ''}>${escapeHtml(label)}</option>`;
    })
    .join('');
}

function renderCurrentUser(state) {
  const user = state?.current_user;
  if (!user) return '';
  const permissions = user.permissions || [];
  return `
    <section class="security-panel">
      <div class="security-panel-head">
        <h3>Current User</h3>
      </div>
      <div class="security-kv-grid">
        <div><span>Username</span><strong>${escapeHtml(user.username)}</strong></div>
        <div><span>Display name</span><strong>${escapeHtml(user.display_name || '-')}</strong></div>
        <div><span>Roles</span><strong>${escapeHtml((user.roles || []).join(', ') || '-')}</strong></div>
        <div><span>Permissions</span><strong>${permissions.length}</strong></div>
      </div>
      <div class="security-permission-pills">
        ${permissions.slice(0, 18).map((permission) => `<span>${escapeHtml(permission)}</span>`).join('')}
        ${permissions.length > 18 ? `<span>${permissions.length - 18} more</span>` : ''}
      </div>
    </section>
  `;
}

function renderUnclaimed(onOpenClaim) {
  const section = document.createElement('section');
  section.className = 'security-panel security-panel--notice';
  section.innerHTML = `
    <div class="security-panel-head">
      <h3>Security</h3>
    </div>
    <p>BUS Core is running in unclaimed local mode. Create an owner account to enable login, users, permissions, recovery, and audit controls.</p>
    <div class="settings-action-row">
      <button type="button" class="btn primary" data-action="open-claim">Secure this BUS Core</button>
    </div>
  `;
  section.querySelector('[data-action="open-claim"]')?.addEventListener('click', () => onOpenClaim?.());
  return section;
}

function renderUsersSection(root, users, roles, canManage) {
  const section = document.createElement('section');
  section.className = 'security-panel';
  section.innerHTML = `
    <div class="security-panel-head security-panel-head--split">
      <h3>Users</h3>
      <span>${users.length} total</span>
    </div>
    ${canManage ? `
      <form class="security-create-user" data-form="create-user">
        <input name="username" placeholder="Username" required>
        <input name="password" type="password" placeholder="Temporary password" required>
        <input name="display_name" placeholder="Display name">
        <input name="email" type="email" placeholder="Email">
        <select name="roles" multiple aria-label="Initial roles">${roleOptions(roles, ['viewer'])}</select>
        <button type="submit" class="btn primary">Create user</button>
      </form>
    ` : ''}
    <div class="security-table-wrap">
      <table class="security-table">
        <thead><tr><th>User</th><th>Email</th><th>Status</th><th>Roles</th><th>Last login</th><th>Actions</th></tr></thead>
        <tbody>
          ${users.map((user) => `
            <tr data-user-id="${escapeHtml(user.id)}">
              <td><strong>${escapeHtml(user.username)}</strong><span>${escapeHtml(user.display_name || '')}</span></td>
              <td>${escapeHtml(user.email || '-')}</td>
              <td><span class="security-status ${user.is_enabled ? 'security-status--ok' : 'security-status--off'}">${user.is_enabled ? 'Enabled' : 'Disabled'}</span></td>
              <td>
                ${canManage ? `<select multiple data-field="roles">${roleOptions(roles, user.roles || [])}</select>` : escapeHtml((user.roles || []).join(', ') || '-')}
              </td>
              <td>${escapeHtml(formatDate(user.last_login_at))}</td>
              <td>
                ${canManage ? `
                  <div class="security-row-actions">
                    <button type="button" data-action="${user.is_enabled ? 'disable-user' : 'enable-user'}">${user.is_enabled ? 'Disable' : 'Enable'}</button>
                    <button type="button" data-action="reset-password">Reset password</button>
                    <button type="button" data-action="save-roles">Save roles</button>
                  </div>
                ` : '-'}
              </td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>
  `;

  section.querySelector('[data-form="create-user"]')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    await createUser({
      username: String(data.get('username') || '').trim(),
      password: String(data.get('password') || ''),
      display_name: String(data.get('display_name') || '').trim() || null,
      email: String(data.get('email') || '').trim() || null,
      roles: selectedValues(form.querySelector('[name="roles"]')),
      must_change_password: true,
    });
    form.reset();
    await refreshAfterSecurityMutation(root);
  });

  section.addEventListener('click', async (event) => {
    const button = event.target instanceof HTMLElement ? event.target.closest('button[data-action]') : null;
    if (!button) return;
    const row = button.closest('tr[data-user-id]');
    const userId = row?.getAttribute('data-user-id');
    if (!userId) return;
    const action = button.getAttribute('data-action');
    button.disabled = true;
    try {
      if (action === 'disable-user') await disableUser(userId);
      if (action === 'enable-user') await enableUser(userId);
      if (action === 'save-roles') await setUserRoles(userId, selectedValues(row.querySelector('[data-field="roles"]')));
      if (action === 'reset-password') {
        const newPassword = window.prompt('Enter a new temporary password for this user.');
        if (!newPassword) return;
        await resetPassword(userId, { new_password: newPassword, must_change_password: true, revoke_sessions: true });
      }
      await refreshAfterSecurityMutation(root);
    } catch (error) {
      console.error('user management action failed', error);
      handleSecurityError(root, error, error?.error === 'last_enabled_owner' ? 'The last enabled owner cannot be disabled or stripped.' : 'User action failed.');
    } finally {
      button.disabled = false;
    }
  });

  return section;
}

function renderSessionsSection(root, sessions) {
  const section = document.createElement('section');
  section.className = 'security-panel';
  section.innerHTML = `
    <div class="security-panel-head security-panel-head--split">
      <h3>Sessions</h3>
      <span>${sessions.length} shown</span>
    </div>
    <div class="security-table-wrap">
      <table class="security-table">
        <thead><tr><th>User</th><th>Created</th><th>Expires</th><th>Last seen</th><th>Status</th><th>Actions</th></tr></thead>
        <tbody>
          ${sessions.map((session) => `
            <tr data-session-id="${escapeHtml(session.id)}">
              <td>${escapeHtml(session.username || session.user_id)}</td>
              <td>${escapeHtml(formatDate(session.created_at))}</td>
              <td>${escapeHtml(formatDate(session.expires_at))}</td>
              <td>${escapeHtml(formatDate(session.last_seen_at))}</td>
              <td><span class="security-status ${session.revoked_at ? 'security-status--off' : 'security-status--ok'}">${session.revoked_at ? 'Revoked' : 'Active'}</span></td>
              <td>${session.revoked_at ? '-' : '<button type="button" data-action="revoke-session">Revoke</button>'}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>
  `;
  section.addEventListener('click', async (event) => {
    const button = event.target instanceof HTMLElement ? event.target.closest('button[data-action="revoke-session"]') : null;
    if (!button) return;
    const sessionId = button.closest('tr[data-session-id]')?.getAttribute('data-session-id');
    if (!sessionId) return;
    button.disabled = true;
    try {
      await revokeSession(sessionId);
      await refreshAfterSecurityMutation(root);
    } catch (error) {
      console.error('session revoke failed', error);
      handleSecurityError(root, error, 'Session revoke failed.');
    } finally {
      button.disabled = false;
    }
  });
  return section;
}

function renderAuditSection(events) {
  const section = document.createElement('section');
  section.className = 'security-panel';
  section.innerHTML = `
    <div class="security-panel-head security-panel-head--split">
      <h3>Audit</h3>
      <span>${events.length} latest</span>
    </div>
    <div class="security-table-wrap">
      <table class="security-table">
        <thead><tr><th>When</th><th>Action</th><th>Actor</th><th>Target</th><th>Detail</th></tr></thead>
        <tbody>
          ${events.map((event) => `
            <tr>
              <td>${escapeHtml(formatDate(event.created_at))}</td>
              <td>${escapeHtml(event.action)}</td>
              <td>${escapeHtml(event.actor_user_id || '-')}</td>
              <td>${escapeHtml([event.target_type, event.target_id].filter(Boolean).join(':') || '-')}</td>
              <td><code>${escapeHtml(event.detail ? JSON.stringify(event.detail) : '-')}</code></td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>
  `;
  return section;
}

function setSecurityStatus(root, message, tone = 'neutral') {
  const status = root.querySelector('[data-role="security-status"]');
  if (!status) return;
  status.textContent = message || '';
  status.dataset.tone = tone;
}

async function refreshAuthForSecurity(root) {
  const options = root.__securityOptions || {};
  const refresh = options.onAuthRefresh || window.BUS_AUTH?.refresh;
  if (typeof refresh !== 'function') return options.authState || window.BUS_AUTH?.state || null;
  const state = await refresh({ render: true });
  root.__securityOptions = { ...options, authState: state };
  if (state?.mode === 'claimed' && !state.current_user) options.onLoginRequired?.();
  return state;
}

async function refreshAfterSecurityMutation(root) {
  const state = await refreshAuthForSecurity(root);
  if (state?.mode === 'claimed' && !state.current_user) return;
  await refreshSecurity(root);
}

function handleSecurityError(root, error, fallback) {
  if (error?.status === 401 || error?.error === 'auth_required') {
    root.__securityOptions?.onLoginRequired?.();
    setSecurityStatus(root, 'Login required.', 'error');
    return;
  }
  if (error?.status === 403 || error?.error === 'permission_denied') {
    refreshAfterSecurityMutation(root).catch((refreshError) => console.warn('auth refresh after permission error failed', refreshError));
    setSecurityStatus(root, 'Permission denied.', 'error');
    return;
  }
  setSecurityStatus(root, fallback, 'error');
}

async function refreshSecurity(root) {
  const mountOptions = root.__securityOptions || {};
  await mountSecurity(root, mountOptions);
}

export async function mountSecurity(container, options = {}) {
  if (!container) return;
  container.__securityOptions = options;
  const state = options.authState || window.BUS_AUTH?.state || null;
  container.innerHTML = `
    <div class="security-shell">
      <div class="security-heading">
        <h2>Security</h2>
        <p>Manage claimed-mode identity, sessions, and audit visibility according to your backend permissions.</p>
      </div>
      <div class="security-status-line" data-role="security-status" data-tone="neutral" aria-live="polite"></div>
      <div data-role="security-body" class="security-body"></div>
    </div>
  `;
  const body = container.querySelector('[data-role="security-body"]');
  if (!body) return;

  if (!state || state.mode === 'unclaimed') {
    body.appendChild(renderUnclaimed(options.onOpenClaim));
    return;
  }

  body.insertAdjacentHTML('beforeend', renderCurrentUser(state));

  const canReadUsers = hasPermission(state, PERMISSIONS.usersRead);
  const canManageUsers = hasPermission(state, PERMISSIONS.usersManage);
  const canManageSessions = hasPermission(state, PERMISSIONS.sessionsManage);
  const canReadAudit = hasPermission(state, PERMISSIONS.auditRead);

  const rolesResult = canReadUsers ? await listRoles().catch((error) => ({ error })) : { roles: [] };
  const roles = rolesResult.roles || [];

  if (canReadUsers) {
    const usersResult = await listUsers().catch((error) => ({ error }));
    if (usersResult.error) setSecurityStatus(container, 'Users could not be loaded.', 'error');
    else body.appendChild(renderUsersSection(container, usersResult.users || [], roles, canManageUsers));
  }

  if (canManageSessions) {
    const sessionsResult = await listSessions().catch((error) => ({ error }));
    if (sessionsResult.error) setSecurityStatus(container, 'Sessions could not be loaded.', 'error');
    else body.appendChild(renderSessionsSection(container, sessionsResult.sessions || []));
  }

  if (canReadAudit) {
    const auditResult = await listAudit().catch((error) => ({ error }));
    if (auditResult.error) setSecurityStatus(container, 'Audit events could not be loaded.', 'error');
    else body.appendChild(renderAuditSection(auditResult.events || []));
  }

  if (!canReadUsers && !canManageSessions && !canReadAudit) {
    const notice = document.createElement('section');
    notice.className = 'security-panel security-panel--notice';
    notice.innerHTML = '<p>No security management permissions are available for this user.</p>';
    body.appendChild(notice);
  }
}