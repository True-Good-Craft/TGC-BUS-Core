// SPDX-License-Identifier: AGPL-3.0-or-later
import { apiGet, apiPost, ensureToken } from './api.js';

let startupCheckDone = false;

function sidebarEls() {
  return {
    status: document.querySelector('[data-role="update-status"]'),
    checkNow: document.querySelector('[data-role="update-check-now"]'),
    stage: document.querySelector('[data-role="update-stage"]'),
  };
}

function setSidebarStatus(text = '', tone = 'neutral') {
  const { status } = sidebarEls();
  if (!status) return;
  status.textContent = text;
  status.dataset.tone = tone;
}

function setStageButton({ visible, disabled = false, label = 'Update' }) {
  const { stage } = sidebarEls();
  if (!stage) return;
  stage.textContent = label;
  stage.disabled = !!disabled;
  if (visible) {
    stage.classList.remove('hidden');
    return;
  }
  stage.classList.add('hidden');
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
  setStageButton({ visible: false, disabled: false, label: 'Update' });
  setSidebarStatus('Checking for updates...', 'neutral');

  try {
    const res = await runUpdateCheck();
    if (res.error_code) {
      setSidebarStatus(`Check failed: ${res.error_message || res.error_code}`, 'error');
      return res;
    }
    if (res.update_available && res.latest_version) {
      setSidebarStatus(`Update available: ${res.latest_version}`, 'warn');
      setStageButton({ visible: true, disabled: false, label: 'Update' });
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
  const { checkNow, stage } = sidebarEls();
  if (!checkNow || checkNow.dataset.bound === '1') return;
  checkNow.dataset.bound = '1';
  checkNow.addEventListener('click', () => {
    runSidebarManualUpdateCheck();
  });

  if (stage && stage.dataset.bound !== '1') {
    stage.dataset.bound = '1';
    stage.addEventListener('click', () => {
      runSidebarManualUpdateStage();
    });
  }
}

export async function runUpdateCheck() {
  await ensureToken();
  return apiGet('/app/update/check');
}

export async function runSidebarManualUpdateStage() {
  const { checkNow } = sidebarEls();
  setStageButton({ visible: true, disabled: true, label: 'Updating...' });
  if (checkNow) checkNow.disabled = true;
  setSidebarStatus('Staging verified update...', 'neutral');

  try {
    await ensureToken();
    const res = await apiPost('/app/update/stage', {});
    if (!res?.ok) {
      setSidebarStatus(`Update failed: ${res?.error_message || res?.error_code || 'unknown_error'}`, 'error');
      setStageButton({ visible: true, disabled: false, label: 'Update' });
      return res;
    }

    setStageButton({ visible: false, disabled: false, label: 'Update' });
    setSidebarStatus('Update verified and ready.', 'success');

    const nextVersion = res.latest_version ? ` ${res.latest_version}` : '';
    const prompt = `Update${nextVersion} is verified and ready. Restart into verified version now?`;
    if (window.confirm(prompt)) {
      setSidebarStatus('Update is verified and ready. Restart BUS Core to run the verified newer version.', 'success');
    } else {
      setSidebarStatus('Update is verified and ready. Restart BUS Core when you are ready.', 'success');
    }
    return res;
  } catch {
    setSidebarStatus('Update staging failed.', 'error');
    setStageButton({ visible: true, disabled: false, label: 'Update' });
    return null;
  } finally {
    if (checkNow) checkNow.disabled = false;
  }
}

export async function maybeRunStartupUpdateCheck() {
  if (startupCheckDone) return;
  startupCheckDone = true;
  bindSidebarUpdateControls();
  try {
    const enabled = await getStartupPolicyEnabled();
    if (!enabled) {
      setSidebarStatus('Startup update checks disabled\n(use Check now)', 'neutral');
      setStageButton({ visible: false, disabled: false, label: 'Update' });
      return;
    }

    // Product policy: run one startup check when not explicitly disabled.
    await executeCheck({ manual: false });
  } catch (_err) {
    // Silent by design (non-blocking startup behavior)
  }
}
