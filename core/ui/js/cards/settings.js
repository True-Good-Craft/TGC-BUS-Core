// SPDX-License-Identifier: AGPL-3.0-or-later
import { apiGet, apiPost, ensureToken } from '../api.js';
import { mountAdmin } from './admin.js';

export async function settingsCard(el) {
  el.innerHTML = '<div class="settings-loading">Loading settings...</div>';

  let config = {};
  try {
    await ensureToken();
    config = await apiGet('/app/config');
  } catch (e) {
    console.error('Failed to load config', e);
    el.innerHTML = `
      <div class="card">
        <div class="card-title">Error</div>
        <p>Failed to load settings. Ensure server is running.</p>
      </div>`;
    return;
  }

  const launcher = config.launcher || {};
  const ui = config.ui || {};
  const backup = config.backup || {};
  const updates = config.updates || {};
  const updatesEnabledAtLoad = updates.enabled !== false;
  const startupChecksEnabledAtLoad = updates.check_on_startup !== false;

  el.innerHTML = '';
  const root = document.createElement('div');
  root.className = 'card settings-shell';

  root.innerHTML = `
    <header class="settings-page-header">
      <div class="card-title settings-page-title">Settings</div>
      <p class="settings-page-kicker">Configure system behavior, updates, and recovery controls.</p>
    </header>

    <section class="settings-primary-section">
      <div class="settings-section-head">
        <h2 class="settings-section-title">Primary Settings</h2>
      </div>

      <div class="settings-grid settings-grid--primary">
      <div class="settings-card settings-card--primary">
        <h3>System</h3>
        <label for="setting-theme" class="settings-label">Theme</label>
        <select id="setting-theme" class="settings-select" disabled>
          <option value="system">System (currently only mode)</option>
        </select>
        <p class="settings-subtext">Alternate themes are deferred. BUS Core uses system mode for now.</p>
        <label class="settings-label">Launcher Behavior</label>
        <div class="settings-stack">
          <label class="settings-check-row">
            <input type="checkbox" id="setting-start-tray" class="settings-check">
            <span>Start in Tray (do not open browser on launch)</span>
          </label>
        </div>
      </div>

      <div class="settings-card settings-card--primary">
        <h3>Updates</h3>
        <div class="settings-stack">
          <label class="settings-check-row">
            <input type="checkbox" id="setting-updates-enabled" class="settings-check">
            <span>Enable automatic update checks</span>
          </label>
          <p class="settings-subtext">Version and update status live in the sidebar, including manual "Check now".</p>
        </div>
      </div>

      <div class="settings-card settings-card--primary">
        <h3>Interface</h3>
        <label class="settings-check-row settings-check-row-strong">
          <input type="checkbox" data-role="american-mode" class="settings-check">
          <span>American mode (Imperial units)</span>
        </label>
        <p class="sub settings-subtext">Show inches/feet, ounces, and fluid ounces in the UI. Values are converted to metric before saving.</p>
      </div>

      <div class="settings-card settings-card--primary">
        <h3>Data Management</h3>
        <label for="setting-backup-dir" class="settings-label">Backup Directory</label>
        <input type="text" id="setting-backup-dir" readonly class="settings-input-readonly" value="">
        <div class="settings-help-text">To change this path, edit %LOCALAPPDATA%\\BUSCore\\config.json directly.</div>
      </div>
      </div>

      <div class="settings-save-row">
        <button id="btn-save" class="btn btn-primary settings-btn-save">Save Changes</button>
        <span id="save-feedback" class="settings-save-feedback">Saved. Restart required for launcher changes.</span>
      </div>
    </section>

    <section class="settings-operational-section">
      <div class="settings-section-head settings-section-head--operational">
        <h2 class="settings-section-title">Operational Controls</h2>
      </div>

      <div class="settings-card settings-card--operational">
        <h3 class="settings-section-title">Onboarding</h3>
        <p class="settings-subtext">Restart the first-run onboarding wizard from Settings.</p>
        <div class="settings-action-row">
          <button type="button" data-action="run-onboarding" class="btn btn-secondary">Run onboarding</button>
        </div>
      </div>

      <div class="settings-card settings-card--operational">
        <h3 class="settings-section-title">Security</h3>
        <p class="settings-subtext">Claim owner setup, current user, users, roles, sessions, and audit controls are available from Security when permitted.</p>
        <div class="settings-action-row">
          <a class="btn btn-secondary" href="#/security">Open Security</a>
        </div>
      </div>

      <div class="settings-card settings-card--operational">
        <h3 class="settings-section-title">Administration</h3>
        <div data-role="admin-section" class="settings-admin-host"></div>
      </div>
    </section>
  `;

  el.appendChild(root);

  const americanToggle = root.querySelector('[data-role="american-mode"]');
  if (americanToggle) {
    americanToggle.checked = !!(window.BUS_UNITS && window.BUS_UNITS.american);
    americanToggle.addEventListener('change', () => {
      if (window.BUS_UNITS) window.BUS_UNITS.american = americanToggle.checked;
    });
  }

  root.querySelector('[data-action="run-onboarding"]')?.addEventListener('click', () => {
    try {
      if (window.BUS_ONBOARDING?.clear) {
        window.BUS_ONBOARDING.clear();
      } else {
        localStorage.removeItem('bus.onboarding.completed');
      }
    } catch {}
    window.location.hash = '#/welcome';
  });

  const adminHost = root.querySelector('[data-role="admin-section"]');
  if (adminHost) {
    mountAdmin(adminHost);
  }

  // Populate
  const themeSelect = root.querySelector('#setting-theme');
  themeSelect.value = 'system';

  root.querySelector('#setting-start-tray').checked = !!launcher.auto_start_in_tray;
  root.querySelector('#setting-backup-dir').value = backup.default_directory || '';
  root.querySelector('#setting-updates-enabled').checked = updatesEnabledAtLoad;

  // Handlers
  const btnSave = root.querySelector('#btn-save');
  const feedback = root.querySelector('#save-feedback');

  btnSave.onclick = async () => {
    btnSave.disabled = true;
    const originalText = btnSave.textContent;
    btnSave.textContent = 'Saving...';

    const autoUpdatesEnabled = root.querySelector('#setting-updates-enabled').checked;
    const checkOnStartup = autoUpdatesEnabled
      ? (updatesEnabledAtLoad ? startupChecksEnabledAtLoad : true)
      : false;

    const payload = {
      ui: {
        theme: 'system',
      },
      launcher: {
        auto_start_in_tray: root.querySelector('#setting-start-tray').checked,
      },
      updates: {
        enabled: autoUpdatesEnabled,
        check_on_startup: checkOnStartup,
      },
    };

    try {
      await ensureToken();
      const res = await apiPost('/app/config', payload);
      if (res.ok) {
        feedback.style.opacity = '1';
        setTimeout(() => { feedback.style.opacity = '0'; }, 4000);
      }
    } catch (e) {
      console.error(e);
      alert('Failed to save settings.');
    } finally {
      btnSave.disabled = false;
      btnSave.textContent = originalText;
    }
  };
}
