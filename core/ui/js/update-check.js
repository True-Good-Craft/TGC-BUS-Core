// SPDX-License-Identifier: AGPL-3.0-or-later
import { apiGet, ensureToken } from './api.js';

const LAST_SUCCESS_KEY = 'bus.updates.last_success_ms';
const STALE_AFTER_MS = 24 * 60 * 60 * 1000;
const AUTO_TIMER_MS = 15 * 60 * 1000;

let startupCheckDone = false;
let autoTimerId = null;
let autoCheckInFlight = false;

function sidebarEls() {
  return {
    status: document.querySelector('[data-role="update-status"]'),
    checkNow: document.querySelector('[data-role="update-check-now"]'),
    download: document.querySelector('[data-role="update-download"]'),
  };
}

function setSidebarStatus(text = '', tone = 'neutral') {
  const { status } = sidebarEls();
  if (!status) return;
  status.textContent = text;
  status.dataset.tone = tone;
}

function setDownloadLink(downloadUrl) {
  const { download } = sidebarEls();
  if (!download) return;
  if (!downloadUrl) {
    download.classList.add('hidden');
    download.removeAttribute('href');
    return;
  }
  download.classList.remove('hidden');
  download.href = downloadUrl;
}

function getLastSuccessMs() {
  try {
    return Number(localStorage.getItem(LAST_SUCCESS_KEY) || '0') || 0;
  } catch {
    return 0;
  }
}

function markSuccessNow() {
  try {
    localStorage.setItem(LAST_SUCCESS_KEY, String(Date.now()));
  } catch {}
}

function isStale() {
  const last = getLastSuccessMs();
  if (!last) return true;
  return (Date.now() - last) >= STALE_AFTER_MS;
}

async function getAutoPolicyEnabled() {
  await ensureToken();
  const cfg = await apiGet('/app/config');
  const updates = cfg?.updates || {};
  // Product policy: automatic checks default ON unless explicitly disabled.
  return updates.enabled !== false;
}

async function executeCheck({ manual = false } = {}) {
  const { checkNow } = sidebarEls();
  if (manual && checkNow) checkNow.disabled = true;
  setDownloadLink(null);
  setSidebarStatus('Checking for updates...', 'neutral');

  try {
    const res = await runUpdateCheck();
    if (res.error_code) {
      setSidebarStatus(`Check failed: ${res.error_message || res.error_code}`, 'error');
      return res;
    }
    markSuccessNow();
    if (res.update_available && res.latest_version) {
      setSidebarStatus(`Update available: ${res.latest_version}`, 'warn');
      setDownloadLink(res.download_url || null);
    } else {
      setSidebarStatus('Up to date', 'success');
    }
    return res;
  } catch {
    setSidebarStatus('Update check failed.', 'error');
    return null;
  } finally {
    if (manual && checkNow) checkNow.disabled = false;
  }
}

export async function runSidebarManualUpdateCheck() {
  return executeCheck({ manual: true });
}

export function bindSidebarUpdateControls() {
  const { checkNow } = sidebarEls();
  if (!checkNow || checkNow.dataset.bound === '1') return;
  checkNow.dataset.bound = '1';
  checkNow.addEventListener('click', () => {
    runSidebarManualUpdateCheck();
  });
}

export async function runUpdateCheck() {
  await ensureToken();
  return apiGet('/app/update/check');
}

export async function maybeRunStartupUpdateCheck() {
  if (startupCheckDone) return;
  startupCheckDone = true;
  bindSidebarUpdateControls();
  try {
    const enabled = await getAutoPolicyEnabled();
    if (!enabled) {
      setSidebarStatus('Automatic checks disabled', 'neutral');
      setDownloadLink(null);
      return;
    }

    // Product policy: run automatic check at launch.
    await executeCheck({ manual: false });

    // If app stays open, re-check once stale (older than 24h since last success).
    if (autoTimerId) clearInterval(autoTimerId);
    autoTimerId = window.setInterval(async () => {
      if (autoCheckInFlight) return;
      try {
        const stillEnabled = await getAutoPolicyEnabled();
        if (!stillEnabled || !isStale()) return;
        autoCheckInFlight = true;
        await executeCheck({ manual: false });
      } finally {
        autoCheckInFlight = false;
      }
    }, AUTO_TIMER_MS);
  } catch (_err) {
    // Silent by design (non-blocking startup behavior)
  }
}
