// SPDX-License-Identifier: AGPL-3.0-or-later
import { apiGet, apiPost, ensureToken } from '../api.js';
import { mountAdmin } from './admin.js';


function toast(message, tone = 'ok') {
  const el = document.createElement('div');
  el.textContent = message;
  el.style.position = 'fixed';
  el.style.right = '16px';
  el.style.bottom = '16px';
  el.style.zIndex = '9999';
  el.style.padding = '10px 12px';
  el.style.borderRadius = '10px';
  el.style.color = '#fff';
  el.style.background = tone === 'error' ? '#9f1239' : '#065f46';
  el.style.boxShadow = '0 8px 22px rgba(0,0,0,.35)';
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 2200);
}

async function renderDemoSection(root) {
  const section = document.createElement('section');
  section.style.marginTop = '16px';
  section.className = 'card';
  section.innerHTML = '<h2 style="margin:0 0 12px;font-size:1.15em;font-weight:700;">Demo Data</h2><div data-role="demo-body">Loading...</div>';

  const body = section.querySelector('[data-role="demo-body"]');
  try {
    const state = await apiGet('/app/system/state');
    if (state?.is_empty) {
      body.innerHTML = `
        <p style="margin:0 0 10px;color:#cbd5e1;">Load the deterministic AvoArrow demo factory dataset.</p>
        <button data-role="load-demo-factory">Load Demo Factory</button>
      `;
      const btn = body.querySelector('[data-role="load-demo-factory"]');
      btn?.addEventListener('click', async () => {
        btn.disabled = true;
        const old = btn.textContent;
        btn.textContent = 'Loading...';
        try {
          await apiPost('/app/demo/load', {});
          toast('Demo Loaded');
          location.hash = '#/home';
          location.reload();
        } catch (err) {
          toast(String(err?.message || 'Failed to load demo'), 'error');
          btn.disabled = false;
          btn.textContent = old;
        }
      });
    } else {
      body.innerHTML = '<p style="margin:0;color:#94a3b8;">Demo already loaded or system contains data.</p>';
    }
  } catch (err) {
    body.innerHTML = `<p style="margin:0;color:#fda4af;">${String(err?.message || 'Failed to load system state')}</p>`;
  }

  root.appendChild(section);
}

export async function settingsCard(el) {
  el.innerHTML = '<div style="padding:20px;">Loading settings...</div>';

  let config = {};
  try {
      await ensureToken();
      config = await apiGet('/app/config');
  } catch (e) {
      console.error("Failed to load config", e);
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

  el.innerHTML = '';
  const root = document.createElement('div');
  root.className = "card";
  root.style.maxWidth = "600px";

  root.innerHTML = `
    <div class="card-title" style="margin-bottom:20px; font-size:1.2em; font-weight:bold;">Settings</div>

    <div style="margin-bottom:20px;">
      <label style="display:block; margin-bottom:8px; font-weight:600; color:#ccc;">Theme</label>
      <select id="setting-theme" style="width:100%; max-width:300px; padding:10px; border-radius:10px; background:#2a2c30; color:#e6e6e6; border:1px solid #444;">
        <option value="system">System</option>
        <option value="light">Light</option>
        <option value="dark">Dark</option>
      </select>
    </div>

    <div style="margin-bottom:20px;">
      <label style="display:block; margin-bottom:8px; font-weight:600; color:#ccc;">Launcher Behavior</label>
      <div style="display:flex; flex-direction:column; gap:10px;">
        <label style="display:flex; align-items:center; gap:10px; cursor:pointer;">
          <input type="checkbox" id="setting-start-tray" style="transform:scale(1.2);">
          <span>Start in Tray (do not open browser on launch)</span>
        </label>
        <label style="display:flex; align-items:center; gap:10px; cursor:pointer;">
          <input type="checkbox" id="setting-close-tray" style="transform:scale(1.2);">
          <span>Close to Tray (keep running when window closes)</span>
        </label>
      </div>
    </div>

    <div style="margin-bottom:20px;">
      <label style="display:block; margin-bottom:8px; font-weight:600; color:#ccc;">Backup Directory</label>
      <input type="text" id="setting-backup-dir" readonly
             style="width:100%; padding:10px; border-radius:10px; background:#232428; color:#888; border:1px solid #444;"
             value="">
      <div style="font-size:0.85em; color:#666; margin-top:4px;">To change this path, edit config.json directly.</div>
    </div>

    <div style="margin-top:30px; border-top:1px solid #333; padding-top:20px;">
       <button id="btn-save" class="btn btn-primary" style="padding:10px 20px; border-radius:10px; background:#007bff; color:white; border:none; cursor:pointer; font-weight:bold;">Save Changes</button>
       <span id="save-feedback" style="margin-left:15px; opacity:0; transition:opacity 0.3s; color:#4caf50; font-weight:500;">Saved. Restart required for launcher changes.</span>
    </div>
  `;

  el.appendChild(root);

  const unitsSection = document.createElement('div');
  unitsSection.style.marginBottom = '20px';
  unitsSection.innerHTML = `
    <label style="display:flex; align-items:center; gap:10px; cursor:pointer; font-weight:600; color:#ccc;">
      <input type="checkbox" data-role="american-mode" style="transform:scale(1.2);">
      <span>American mode (Imperial units)</span>
    </label>
    <p class="sub" style="margin:6px 0 0; color:#aaa;">Show inches/feet, ounces, and fluid ounces in the UI. Values are converted to metric before saving.</p>
  `;
  const saveBlock = root.querySelector('#btn-save')?.parentElement;
  if (saveBlock) {
    root.insertBefore(unitsSection, saveBlock);
  }

  const americanToggle = unitsSection.querySelector('[data-role="american-mode"]');
  if (americanToggle) {
    americanToggle.checked = !!(window.BUS_UNITS && window.BUS_UNITS.american);
    americanToggle.addEventListener('change', () => {
      if (window.BUS_UNITS) window.BUS_UNITS.american = americanToggle.checked;
    });
  }

  const adminSection = document.createElement('section');
  adminSection.style.marginTop = '16px';
  adminSection.innerHTML = `
    <h2 style="margin:0 0 12px;font-size:1.15em;font-weight:700;">Administration</h2>
    <div data-role="admin-section"></div>
  `;

  el.appendChild(adminSection);

  const adminHost = adminSection.querySelector('[data-role="admin-section"]');
  if (adminHost) {
    mountAdmin(adminHost);
  }

  await renderDemoSection(el);

  // Populate
  const themeSelect = root.querySelector('#setting-theme');
  themeSelect.value = ui.theme || 'system';

  root.querySelector('#setting-start-tray').checked = !!launcher.auto_start_in_tray;
  root.querySelector('#setting-close-tray').checked = !!launcher.close_to_tray;
  root.querySelector('#setting-backup-dir').value = backup.default_directory || '';

  // Handlers
  const btnSave = root.querySelector('#btn-save');
  const feedback = root.querySelector('#save-feedback');

  btnSave.onclick = async () => {
      btnSave.disabled = true;
      const originalText = btnSave.textContent;
      btnSave.textContent = 'Saving...';

      const payload = {
          ui: {
              theme: themeSelect.value
          },
          launcher: {
              auto_start_in_tray: root.querySelector('#setting-start-tray').checked,
              close_to_tray: root.querySelector('#setting-close-tray').checked
          }
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
