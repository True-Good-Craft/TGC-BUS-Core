// SPDX-License-Identifier: AGPL-3.0-or-later
import { apiGet, ensureToken } from './api.js';

const LIGHTHOUSE_BASE_URL = 'https://lighthouse.buscore.ca';

let startupCheckDone = false;

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

function resolveDownloadUrl(downloadUrl) {
  if (!downloadUrl || typeof downloadUrl !== 'string') return null;
  if (/^https?:\/\//i.test(downloadUrl)) return downloadUrl;

  const normalizedPath = downloadUrl.startsWith('/') ? downloadUrl : `/${downloadUrl}`;
  return `${LIGHTHOUSE_BASE_URL}${normalizedPath}`;
}

function setDownloadLink(downloadUrl) {
  const { download } = sidebarEls();
  if (!download) return;
  const resolvedDownloadUrl = resolveDownloadUrl(downloadUrl);
  if (!resolvedDownloadUrl) {
    download.classList.add('hidden');
    download.removeAttribute('href');
    return;
  }
  download.classList.remove('hidden');
  download.href = resolvedDownloadUrl;
}

async function getStartupPolicyEnabled() {
  await ensureToken();
  const cfg = await apiGet('/app/config');
  const updates = cfg?.updates || {};
  // Product policy: update checks are default-on and opt-out.
  return updates.enabled !== false && updates.check_on_startup !== false;
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
    const enabled = await getStartupPolicyEnabled();
    if (!enabled) {
      setSidebarStatus('Startup update checks disabled\n(use Check now)', 'neutral');
      setDownloadLink(null);
      return;
    }

    // Product policy: run one startup check when not explicitly disabled.
    await executeCheck({ manual: false });
  } catch (_err) {
    // Silent by design (non-blocking startup behavior)
  }
}
