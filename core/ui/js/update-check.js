// SPDX-License-Identifier: AGPL-3.0-or-later
import { apiGet, ensureToken } from './api.js';

let startupCheckDone = false;

function ensureNoticeHost() {
  let host = document.querySelector('[data-role="update-notice"]');
  if (host) return host;
  host = document.createElement('div');
  host.setAttribute('data-role', 'update-notice');
  host.style.cssText = 'position:fixed;top:12px;right:12px;z-index:9999;max-width:420px;padding:10px 12px;border-radius:10px;background:#1f3f1f;color:#d8ffd8;border:1px solid #2f6f2f;box-shadow:0 2px 8px rgba(0,0,0,0.35);font-size:0.9em;';
  host.hidden = true;
  document.body.appendChild(host);
  return host;
}

function showNotice(message, tone = 'ok', downloadUrl = null) {
  const host = ensureNoticeHost();
  if (tone === 'warn') {
    host.style.background = '#4d3c11';
    host.style.color = '#ffe8a3';
    host.style.borderColor = '#8a6b1d';
  } else {
    host.style.background = '#1f3f1f';
    host.style.color = '#d8ffd8';
    host.style.borderColor = '#2f6f2f';
  }

  host.innerHTML = '';
  const text = document.createElement('span');
  text.textContent = message;
  host.appendChild(text);

  if (downloadUrl) {
    const space = document.createTextNode(' ');
    const link = document.createElement('a');
    link.href = downloadUrl;
    link.target = '_blank';
    link.rel = 'noopener';
    link.textContent = 'Download';
    link.style.color = 'inherit';
    link.style.textDecoration = 'underline';
    host.appendChild(space);
    host.appendChild(link);
  }

  host.hidden = false;
  window.setTimeout(() => {
    host.hidden = true;
  }, 5000);
}

export async function runUpdateCheck() {
  await ensureToken();
  return apiGet('/app/update/check');
}

export async function maybeRunStartupUpdateCheck() {
  if (startupCheckDone) return;
  startupCheckDone = true;
  try {
    await ensureToken();
    const cfg = await apiGet('/app/config');
    const updates = cfg?.updates || {};
    if (!updates.enabled || !updates.check_on_startup) return;

    const res = await runUpdateCheck();
    if (res.update_available && res.latest_version) {
      showNotice(`Update available: ${res.latest_version}`, 'warn', res.download_url || null);
    }
  } catch (_err) {
    // Silent by design (non-blocking startup behavior)
  }
}
