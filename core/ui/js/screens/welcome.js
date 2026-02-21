/* SPDX-License-Identifier: AGPL-3.0-or-later */
import { apiPost } from '../api.js';

let _container = null;

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

export async function mount(container) {
  if (!container) return;
  _container = container;

  _container.innerHTML = `
    <section class="card" style="max-width:760px; margin:18px auto;">
      <h1 style="margin-top:0;">Welcome to BUS Core</h1>
      <p style="color:#cbd5e1;">
        Your system is currently empty. Choose how you want to begin:
        load a deterministic demo factory dataset, or continue with a fresh system.
      </p>

      <div style="margin:20px 0;padding:14px;border:1px solid #334155;border-radius:10px;">
        <h2 style="margin:0 0 8px; font-size:1.05rem;">🇨🇦 Load AvoArrow Demo Factory</h2>
        <p style="margin:0 0 10px;color:#94a3b8;">Populate demo vendors, inventory, manufacturing, sales, refund, and expense records.</p>
        <button data-role="load-demo">Load Demo</button>
      </div>

      <div style="margin:20px 0;padding:14px;border:1px solid #334155;border-radius:10px;">
        <h2 style="margin:0 0 8px; font-size:1.05rem;">🧰 Start Fresh</h2>
        <p style="margin:0 0 10px;color:#94a3b8;">Continue with an empty system and configure your own data.</p>
        <button data-role="start-empty" style="background:#374151;">Start with Empty System</button>
      </div>

      <p data-role="welcome-error" style="min-height:20px;color:#fda4af;"></p>
    </section>
  `;

  const errEl = _container.querySelector('[data-role="welcome-error"]');
  const loadBtn = _container.querySelector('[data-role="load-demo"]');
  const freshBtn = _container.querySelector('[data-role="start-empty"]');

  if (loadBtn) {
    loadBtn.addEventListener('click', async () => {
      loadBtn.disabled = true;
      if (errEl) errEl.textContent = '';
      try {
        await apiPost('/app/demo/load', {});
        toast('Demo Loaded');
        location.hash = '#/home';
      } catch (err) {
        if (errEl) errEl.textContent = String(err?.message || 'Failed to load demo');
        toast('Failed to load demo', 'error');
      } finally {
        loadBtn.disabled = false;
      }
    });
  }

  if (freshBtn) {
    freshBtn.addEventListener('click', () => {
      location.hash = '#/home';
    });
  }
}

export function unmount() {
  if (_container) _container.innerHTML = '';
  _container = null;
}
