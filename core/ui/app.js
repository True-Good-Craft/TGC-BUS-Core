// SPDX-License-Identifier: AGPL-3.0-or-later
// TGC BUS Core (Business Utility System Core)
// Copyright (C) 2025 True Good Craft
//
// This file is part of TGC BUS Core.
//
// TGC BUS Core is free software: you can redistribute it and/or modify
// it under the terms of the GNU Affero General Public License as
// published by the Free Software Foundation, either version 3 of the
// License, or (at your option) any later version.
//
// TGC BUS Core is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU Affero General Public License for more details.
//
// You should have received a copy of the GNU Affero General Public License
// along with TGC BUS Core.  If not, see <https://www.gnu.org/licenses/>.

import { ensureToken } from "./js/token.js";
import { apiGet, apiPost, rawFetch } from "./js/api.js";
import { getAuthState, logout as authLogout } from "./js/auth.js";
import { mountAuthGate } from "./js/auth-ui.js";
import { mountBackupExport } from "./js/cards/backup.js";
import mountVendors from "./js/cards/vendors.js";
import { mountHome } from "./js/cards/home.js";
import "./js/cards/home_donuts.js";
import { mountInventory, unmountInventory } from "./js/cards/inventory.js";
import { mountManufacturing, unmountManufacturing } from "./js/cards/manufacturing.js";
import { mountRecipes, unmountRecipes } from "./js/cards/recipes.js";
import { settingsCard } from "./js/cards/settings.js";
import { mountLogsPage } from "./js/logs.js";
import { mountFinance } from "./js/cards/finance.js";
import { mountSecurity } from "./js/security.js";
import { toMetricBase, DIM_DEFAULTS_IMPERIAL } from "./js/lib/units.js";
import { bindSidebarUpdateControls, maybeRunStartupUpdateCheck } from "./js/update-check.js";

const ROUTES = {
  '#/welcome': showWelcome,
  '#/inventory': showInventory,
  '#/manufacturing': showManufacturing,
  '#/recipes': showRecipes,
  '#/contacts': showContacts,
  '#/runs': showRuns,
  '#/import': showImport,
  '#/settings': showSettings,
  '#/security': showSecurity,
  '#/logs': showLogs,
  '#/finance': showFinance,
  '#/home': showHome,
  '#/': showInventory,
  '': showInventory,
};

const ONBOARDING_STORAGE_KEY = 'bus.onboarding.completed';

function isOnboardingComplete() {
  try {
    return localStorage.getItem(ONBOARDING_STORAGE_KEY) === '1';
  } catch {
    return false;
  }
}

function setOnboardingComplete(done) {
  try {
    if (done) localStorage.setItem(ONBOARDING_STORAGE_KEY, '1');
    else localStorage.removeItem(ONBOARDING_STORAGE_KEY);
  } catch {}
}

window.BUS_ONBOARDING = {
  key: ONBOARDING_STORAGE_KEY,
  clear() {
    setOnboardingComplete(false);
  },
};

let runtimeBusMode = 'prod';
let runtimeSystemState = null;
let currentAuthState = null;
let authRefreshPromise = null;

const ROUTE_PERMISSIONS = {
  contacts: ['contacts.read'],
  finance: ['finance.read'],
  inventory: ['inventory.read'],
  logs: ['logs.read'],
  manufacturing: ['manufacturing.read'],
  recipes: ['recipes.read'],
  security: ['settings.read', 'users.read', 'users.manage', 'sessions.manage', 'audit.read'],
  settings: ['settings.read'],
};

function inDemoMode() {
  return runtimeBusMode === 'demo';
}

function setRuntimeSystemState(state) {
  runtimeSystemState = state && typeof state === 'object' ? state : null;
  runtimeBusMode = runtimeSystemState?.bus_mode === 'demo' ? 'demo' : 'prod';
  renderDemoBanner();
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function authPermissions() {
  return new Set(currentAuthState?.current_user?.permissions || []);
}

function hasAuthPermission(permission) {
  if (currentAuthState?.mode === 'unclaimed') return true;
  return authPermissions().has(permission);
}

function canMountNormalApp() {
  return currentAuthState?.mode === 'unclaimed' || !!currentAuthState?.current_user;
}

function publishAuthState() {
  window.BUS_AUTH = {
    state: currentAuthState,
    permissions: Array.from(authPermissions()),
    hasPermission: hasAuthPermission,
    refresh: refreshAuthState,
    openClaim: openClaimScreen,
  };
  document.dispatchEvent(new CustomEvent('bus:auth-state', { detail: currentAuthState }));
}

async function refreshAuthState(options = {}) {
  if (authRefreshPromise) return authRefreshPromise;
  authRefreshPromise = (async () => {
    try {
      currentAuthState = await getAuthState();
      publishAuthState();
      if (options.render !== false) renderAuthChrome();
      return currentAuthState;
    } finally {
      authRefreshPromise = null;
    }
  })();
  return authRefreshPromise;
}

function normalAppElement() {
  return document.getElementById('app');
}

function authGateElement() {
  return document.querySelector('[data-role="auth-gate-screen"]');
}

function setNormalAppVisible(visible) {
  normalAppElement()?.classList.toggle('hidden', !visible);
}

function applyPermissionNav() {
  document.querySelectorAll('[data-role="nav-link"]').forEach((link) => {
    const route = link.getAttribute('data-route') || '';
    const required = ROUTE_PERMISSIONS[route];
    const allowed = !required || required.some((permission) => hasAuthPermission(permission));
    link.classList.toggle('hidden', !allowed);
  });
}

function renderAuthBanner() {
  const banner = document.querySelector('[data-role="auth-banner"]');
  if (!banner) return;
  if (currentAuthState?.mode !== 'unclaimed') {
    banner.classList.add('hidden');
    banner.innerHTML = '';
    return;
  }
  banner.classList.remove('hidden');
  banner.innerHTML = `
    <div>
      <strong>BUS Core is running in unclaimed local mode.</strong>
      <p>Create an owner account to enable login, users, permissions, recovery, and audit controls.</p>
    </div>
    <button type="button" data-action="secure-bus-core">Secure this BUS Core</button>
  `;
  banner.querySelector('[data-action="secure-bus-core"]')?.addEventListener('click', () => openClaimScreen());
}

function renderAuthChrome() {
  const zone = document.querySelector('[data-role="sidebar-auth-zone"]');
  applyPermissionNav();
  renderAuthBanner();
  if (!zone) return;
  if (currentAuthState?.mode === 'claimed' && currentAuthState.current_user) {
    const user = currentAuthState.current_user;
    zone.classList.remove('hidden');
    zone.innerHTML = `
      <div class="sidebar-auth-user">
        <span class="sidebar-auth-label">Signed in</span>
        <strong>${escapeHtml(user.display_name || user.username || 'User')}</strong>
        <span>${escapeHtml((user.roles || []).join(', ') || 'claimed')}</span>
      </div>
      <button type="button" class="btn sidebar-logout-btn" data-action="logout">Log out</button>
    `;
    zone.querySelector('[data-action="logout"]')?.addEventListener('click', async () => {
      await authLogout().catch((error) => console.warn('logout failed', error));
      currentAuthState = null;
      settingsMounted = false;
      await refreshAuthState();
      if (currentAuthState?.mode === 'claimed' && currentAuthState.login_required) {
        showLoginGate();
      } else {
        setNormalAppVisible(true);
        onRouteChange().catch(err => console.error('route change failed', err));
      }
    });
    return;
  }
  if (currentAuthState?.mode === 'unclaimed') {
    zone.classList.remove('hidden');
    zone.innerHTML = `
      <div class="sidebar-auth-user">
        <span class="sidebar-auth-label">Security</span>
        <strong>Unclaimed local</strong>
      </div>
      <button type="button" class="btn sidebar-logout-btn" data-action="open-claim">Secure</button>
    `;
    zone.querySelector('[data-action="open-claim"]')?.addEventListener('click', () => openClaimScreen());
    return;
  }
  zone.classList.add('hidden');
  zone.innerHTML = '';
}

async function continueAfterAuth() {
  currentAuthState = null;
  settingsMounted = false;
  initialBootPromise = null;
  await refreshAuthState();
  if (!canMountNormalApp()) {
    showLoginGate();
    return;
  }
  setNormalAppVisible(true);
  authGateElement()?.classList.add('hidden');
  await runInitialBootRedirect();
  await onRouteChange();
}

function showLoginGate() {
  setNormalAppVisible(false);
  document.querySelector('[data-role="demo-banner"]')?.classList.add('hidden');
  document.querySelector('[data-role="auth-banner"]')?.classList.add('hidden');
  const gate = authGateElement();
  if (!gate) return;
  mountAuthGate(gate, {
    state: currentAuthState,
    mode: 'login',
    onAuthenticated: continueAfterAuth,
  });
}

function openClaimScreen() {
  const gate = authGateElement();
  if (!gate) return;
  setNormalAppVisible(false);
  document.querySelector('[data-role="demo-banner"]')?.classList.add('hidden');
  document.querySelector('[data-role="auth-banner"]')?.classList.add('hidden');
  mountAuthGate(gate, {
    state: currentAuthState,
    mode: 'claim',
    allowCancel: currentAuthState?.mode === 'unclaimed',
    onCancel: () => {
      gate.classList.add('hidden');
      if (currentAuthState?.mode === 'unclaimed') {
        setNormalAppVisible(true);
        renderAuthChrome();
      }
    },
    onAuthenticated: continueAfterAuth,
  });
}

async function handleStartFreshShop(button) {
  const trigger = button instanceof HTMLButtonElement ? button : null;
  const originalText = trigger?.textContent || 'Start Fresh Shop';
  if (trigger) {
    trigger.disabled = true;
    trigger.textContent = 'Preparing...';
  }

  try {
    await ensureToken();
    const response = await apiPost('/app/system/start-fresh', {});
    if (!response || response.ok !== true) {
      throw new Error('start_fresh_failed');
    }
    setOnboardingComplete(true);
    setRuntimeSystemState({ ...(runtimeSystemState || {}), bus_mode: 'prod' });
    setBootHash('#/home');
    window.location.reload();
  } catch (err) {
    console.error('start fresh failed', err);
    alert('Unable to start a fresh production database. Please try again.');
  } finally {
    if (trigger) {
      trigger.disabled = false;
      trigger.textContent = originalText;
    }
  }
}

function renderDemoBanner() {
  const banner = document.querySelector('[data-role="demo-banner"]');
  if (!banner) return;

  if (!inDemoMode()) {
    banner.classList.add('hidden');
    banner.innerHTML = '';
    return;
  }

  banner.classList.remove('hidden');
  banner.innerHTML = `
    <div>
      <strong>Demo Data Active</strong>
      <p>You are viewing the BUS Core demo environment.</p>
    </div>
    <button type="button" data-action="start-fresh-shop">Start Fresh Shop</button>
  `;

  banner
    .querySelector('[data-action="start-fresh-shop"]')
    ?.addEventListener('click', (event) => {
      const target = event.currentTarget;
      handleStartFreshShop(target);
    });
}

function normalizeHash(rawHash) {
  let hash = (rawHash || '#/home').trim();
  if (!hash || hash === '#') return '#/home';
  if (!hash.startsWith('#')) hash = `#${hash}`;
  if (!hash.startsWith('#/')) hash = hash.replace(/^#/, '#/');
  if (hash.length > 2) hash = hash.replace(/\/+$/, '');

  if (hash === '#/admin') return '#/settings';
  if (hash === '#/dashboard') return '#/home';
  if (hash === '#/items') return '#/inventory';
  if (hash === '#/vendors') return '#/contacts';

  const itemsDetail = hash.match(/^#\/items\/([^/]+)$/);
  if (itemsDetail) return `#/inventory/${itemsDetail[1]}`;

  const vendorsDetail = hash.match(/^#\/vendors\/([^/]+)$/);
  if (vendorsDetail) return `#/contacts/${vendorsDetail[1]}`;

  return hash;
}

function normalizeRoute(hash) {
  return (hash.replace('#/', '') || 'inventory').split(/[\/?]/)[0];
}

const setActiveNav = (route) => {
  document.querySelectorAll('[data-role="nav-link"]').forEach(a => {
    const is = a.getAttribute('data-route') === route;
    a.classList.toggle('active', !!is);
  });
};

function showScreen(name) {
  const home = document.querySelector('[data-role="home-screen"]');
  const tools = document.querySelector('[data-role="tools-screen"]');
  if (home)  home.classList.toggle('hidden',  name !== 'home');
  if (tools) tools.classList.toggle('hidden', name !== 'tools');
}

let settingsMounted = false;
let suppressNextHashchange = false;
let initialBootPromise = null;

const ensureContactsMounted = async () => {
  const host = document.querySelector('[data-view="contacts"]');
  if (!host) return;
  await mountVendors(host);
};

function clearCardHost() {
  const root = document.getElementById('card-root')
    || document.getElementById('tools-root')
    || document.getElementById('main-root');
  const inventoryHost = document.querySelector('[data-role="inventory-root"]');
  const contactsHost = document.querySelector('[data-view="contacts"]');
  const settingsHost = document.querySelector('[data-role="settings-root"]');
  const securityHost = document.querySelector('[data-role="security-root"]');
  const manufacturingHost = document.querySelector('[data-tab-panel="manufacturing"]');
  const recipesHost = document.querySelector('[data-tab-panel="recipes"]');
  const logsHost = document.querySelector('[data-role="logs-root"]');
  const financeHost = document.querySelector('[data-role="finance-root"]');
  const welcomeHost = document.querySelector('[data-role="welcome-root"]');
  [root, inventoryHost, contactsHost, settingsHost, securityHost, manufacturingHost, recipesHost, logsHost, financeHost, welcomeHost]
    .filter(Boolean)
    .forEach((n) => {
      n.innerHTML = '';
    });
}

function setBootHash(hash) {
  if (window.location.hash === hash) return;
  suppressNextHashchange = true;
  window.location.hash = hash;
}

async function runInitialBootRedirect() {
  if (initialBootPromise) return initialBootPromise;
  initialBootPromise = (async () => {
    const initialHashRaw = window.location.hash || '#/home';
    const initialHash = normalizeHash(initialHashRaw);

    await refreshAuthState();
    if (!canMountNormalApp()) {
      showLoginGate();
      return true;
    }

    setNormalAppVisible(true);
    authGateElement()?.classList.add('hidden');
    await ensureToken();

    let state = null;
    try {
      state = await apiGet('/app/system/state');
    } catch (_) {
      state = null;
    }
    setRuntimeSystemState(state);

    if (inDemoMode() && !isOnboardingComplete() && initialHash !== '#/welcome') {
      setBootHash('#/welcome');
      return true;
    }

    if (!inDemoMode() && initialHash === '#/welcome') {
      setBootHash('#/home');
      return true;
    }

    if (!initialHashRaw || initialHashRaw === '#') {
      setBootHash('#/home');
      return true;
    }

    return false;
  })();
  return initialBootPromise;
}

async function onRouteChange() {
  await refreshAuthState();
  if (!canMountNormalApp()) {
    showLoginGate();
    return;
  }
  setNormalAppVisible(true);
  authGateElement()?.classList.add('hidden');
  await ensureToken();
  const raw = window.location.hash || '#/home';
  const canonical = normalizeHash(raw);

  if (canonical !== raw) {
    window.location.hash = canonical;
    return;
  }

  if (inDemoMode() && !isOnboardingComplete() && canonical !== '#/welcome') {
    setBootHash('#/welcome');
    return;
  }
  if (!inDemoMode() && canonical === '#/welcome') {
    setBootHash('#/home');
    return;
  }

  renderDemoBanner();
  window.BUS_ROUTE = { path: canonical, base: canonical, id: null };

  const detailMatch = canonical.match(/^#\/(inventory|contacts|recipes|runs)\/([^/]+)$/);
  const baseHash = detailMatch ? `#/${detailMatch[1]}` : canonical;
  const detailId = detailMatch ? decodeURIComponent(detailMatch[2]) : null;
  const hash = canonical;

  if (detailMatch) {
    window.BUS_ROUTE = { path: canonical, base: baseHash, id: detailId };
  }

  const route = normalizeRoute(baseHash);

  setActiveNav(route);

  document.querySelector('[data-role="settings-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="security-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="welcome-screen"]')?.classList.add('hidden');
  clearCardHost();

  const fn = ROUTES[hash] || (detailMatch ? ROUTES[baseHash] : null);
  if (fn) {
    await fn();
    return;
  }

  await showNotFound(canonical);
}

window.addEventListener('hashchange', () => {
  if (suppressNextHashchange) {
    suppressNextHashchange = false;
    return;
  }
  onRouteChange().catch(err => console.error('route change failed', err));
});
window.addEventListener('load', async () => {
  await runInitialBootRedirect();
  if (!canMountNormalApp()) return;
  onRouteChange().catch(err => console.error('route change failed', err));
});

// ---- American mode (imperial) toggle state ----
window.BUS_UNITS = {
  get american() {
    try { return localStorage.getItem('bus.american_mode') === '1'; } catch { return false; }
  },
  set american(v) {
    try { localStorage.setItem('bus.american_mode', v ? '1' : '0'); } catch {}
    // fire a lightweight event so forms can re-render their unit pickers
    document.dispatchEvent(new CustomEvent('bus:units-mode', { detail: { american: !!v } }));
  }
};

document.addEventListener('DOMContentLoaded', async () => {
  try {
    await refreshAuthState();
    if (!canMountNormalApp()) {
      showLoginGate();
      return;
    }
    await ensureToken();
    bindSidebarUpdateControls();
    // UI version stamp (from FastAPI OpenAPI info.version)
    {
      const el = document.querySelector('[data-role="ui-version"]');
      if (el) {
        try {
          const res = await rawFetch('/openapi.json', { credentials: 'include' });
          const j = await res.json();
          el.textContent = j?.info?.version ?? 'unknown';
        } catch (_) { el.textContent = 'unknown'; }
      }
    }
    await maybeRunStartupUpdateCheck();
    console.log('BOOT OK');
  } catch (e) {
    console.error('BOOT FAIL', e);
  }
});

async function showContacts() {
  // Close Tools drawer if open
  unmountInventory();
  unmountManufacturing();
  unmountRecipes();
  document.querySelector('[data-role="home-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="inventory-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="recipes-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="manufacturing-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="logs-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="finance-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="welcome-screen"]')?.classList.add('hidden');
  const contactsScreen = document.querySelector('[data-role="contacts-screen"]');
  contactsScreen?.classList.remove('hidden');
  await ensureContactsMounted();
}

async function showInventory() {
  document.querySelector('[data-role="home-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="contacts-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="settings-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="recipes-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="manufacturing-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="logs-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="finance-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="welcome-screen"]')?.classList.add('hidden');
  unmountManufacturing();
  unmountRecipes();
  document.querySelector('[data-role="inventory-screen"]')?.classList.remove('hidden');
  mountInventory();
}

async function showManufacturing() {
  document.querySelector('[data-role="home-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="contacts-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="settings-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="recipes-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="inventory-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="logs-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="finance-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="welcome-screen"]')?.classList.add('hidden');
  const screen = document.querySelector('[data-role="manufacturing-screen"]');
  screen?.classList.remove('hidden');
  unmountInventory();
  unmountRecipes();
  await mountManufacturing();
}

async function showSettings() {
  unmountInventory();
  unmountManufacturing();
  unmountRecipes();
  document.querySelector('[data-role="contacts-screen"]')?.classList.add('hidden');
  showScreen(null);
  document.querySelector('[data-role="manufacturing-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="recipes-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="logs-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="finance-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="welcome-screen"]')?.classList.add('hidden');
  const settingsScreen = document.querySelector('[data-role="settings-screen"]');
  settingsScreen?.classList.remove('hidden');
  const host = document.querySelector('[data-role="settings-root"]');
  if (host && (!settingsMounted || !host.hasChildNodes())) {
    settingsCard(host);
    settingsMounted = true;
  }
}

async function showSecurity() {
  unmountInventory();
  unmountManufacturing();
  unmountRecipes();
  document.querySelector('[data-role="home-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="contacts-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="settings-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="inventory-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="manufacturing-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="recipes-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="logs-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="finance-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="welcome-screen"]')?.classList.add('hidden');
  const securityScreen = document.querySelector('[data-role="security-screen"]');
  securityScreen?.classList.remove('hidden');
  const host = document.querySelector('[data-role="security-root"]');
  if (host) {
    await mountSecurity(host, {
      authState: currentAuthState,
      onOpenClaim: openClaimScreen,
    });
  }
}

async function showLogs() {
  unmountInventory();
  unmountManufacturing();
  unmountRecipes();
  document.querySelector('[data-role="home-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="contacts-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="settings-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="inventory-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="manufacturing-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="recipes-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="finance-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="welcome-screen"]')?.classList.add('hidden');
  const logsScreen = document.querySelector('[data-role="logs-screen"]');
  logsScreen?.classList.remove('hidden');
  const host = document.querySelector('[data-role="logs-root"]');
  if (host) {
    host.innerHTML = '';
    mountLogsPage(host);
  }
}


async function showFinance() {
  unmountInventory();
  unmountManufacturing();
  unmountRecipes();
  document.querySelector('[data-role="home-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="contacts-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="settings-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="inventory-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="manufacturing-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="recipes-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="logs-screen"]')?.classList.add('hidden');
  const financeScreen = document.querySelector('[data-role="finance-screen"]');
  financeScreen?.classList.remove('hidden');
  mountFinance();
}

async function showHome() {
  showScreen('home');   // show only Home
  mountHome();          // keep existing Home logic
  unmountInventory();   // ensure Inventory hides when returning Home
  document.querySelector('[data-role="inventory-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="contacts-screen"]')?.classList.add('hidden');
  unmountManufacturing();
  unmountRecipes();
  document.querySelector('[data-role="manufacturing-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="logs-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="finance-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="welcome-screen"]')?.classList.add('hidden');
}

async function showRecipes() {
  document.querySelector('[data-role="home-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="contacts-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="settings-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="inventory-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="manufacturing-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="logs-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="finance-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="welcome-screen"]')?.classList.add('hidden');
  const recipesScreen = document.querySelector('[data-role="recipes-screen"]');
  recipesScreen?.classList.remove('hidden');
  unmountInventory();
  unmountManufacturing();
  await mountRecipes();
}

function renderInlinePanel(title, message, badHash = null) {
  const screen = document.querySelector('[data-role="home-screen"]');
  if (!screen) return;
  screen.classList.remove('hidden');
  screen.innerHTML = `
    <div class="card">
      <h2>${title}</h2>
      <p>${message}</p>
      ${badHash ? `<p><code>${badHash}</code></p>` : ''}
      <p><a href="#/home">Back to Home</a></p>
    </div>
  `;
}

async function showNotFound(badHash) {
  unmountInventory();
  unmountManufacturing();
  unmountRecipes();
  document.querySelector('[data-role="contacts-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="settings-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="inventory-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="manufacturing-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="recipes-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="logs-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="finance-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="welcome-screen"]')?.classList.add('hidden');
  showScreen('home');
  renderInlinePanel('404 — Not Found', 'The requested route does not exist.', badHash);
}

async function showRuns() {
  unmountInventory();
  unmountManufacturing();
  unmountRecipes();
  document.querySelector('[data-role="contacts-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="settings-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="inventory-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="manufacturing-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="recipes-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="logs-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="finance-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="welcome-screen"]')?.classList.add('hidden');
  showScreen('home');
  renderInlinePanel('Runs', 'Runs screen not implemented yet');
}

async function showImport() {
  unmountInventory();
  unmountManufacturing();
  unmountRecipes();
  document.querySelector('[data-role="contacts-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="settings-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="inventory-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="manufacturing-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="recipes-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="logs-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="finance-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="welcome-screen"]')?.classList.add('hidden');
  showScreen('home');
  renderInlinePanel('Import', 'Import screen not implemented yet');
}

async function showWelcome() {
  if (!inDemoMode()) {
    setBootHash('#/home');
    return;
  }
  unmountInventory();
  unmountManufacturing();
  unmountRecipes();
  document.querySelector('[data-role="home-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="contacts-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="settings-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="inventory-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="manufacturing-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="recipes-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="logs-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="finance-screen"]')?.classList.add('hidden');
  const welcomeScreen = document.querySelector('[data-role="welcome-screen"]');
  welcomeScreen?.classList.remove('hidden');
  const host = document.querySelector('[data-role="welcome-root"]');
  if (!host) return;

  const pages = [
    {
      title: 'Welcome',
      body: 'Welcome to BUS Core. This guided setup explains the system and demo environment before entering the application.',
    },
    {
      title: 'System explanation',
      body: 'BUS Core tracks inventory using base units and FIFO costing so movements, costs, and finance totals stay consistent.',
    },
    {
      title: 'Demo system explanation',
      body: 'You are running a deterministic demo database with pre-seeded data so you can review workflows safely before going live.',
    },
    {
      title: 'EULA acceptance',
      body: 'You must accept the BUS Core End User License Agreement to continue.',
      requireEula: true,
    },
    {
      title: 'Enter application',
      body: 'Onboarding is complete. Select Enter application to continue.',
    },
  ];

  let idx = 0;
  let eulaAccepted = false;
  let eulaReachedEnd = false;
  let eulaMarkdown = null;
  let eulaLoadStarted = false;

  const escapeHtml = (value) => String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  const renderEulaContent = () => {
    if (typeof eulaMarkdown !== 'string') {
      return '<p class="eula-loading">Loading EULA...</p>';
    }
    /*
If a markdown renderer such as "marked" is present it will be used.
Otherwise the EULA is rendered as plain text inside a <pre> block.
*/
    if (window.marked?.parse) {
      try {
        return window.marked.parse(eulaMarkdown);
      } catch (error) {
        console.error('EULA markdown render failed', error);
      }
    }
    return `<pre class="eula-pre">${escapeHtml(eulaMarkdown)}</pre>`;
  };

  const loadEula = async () => {
    if (eulaLoadStarted) return;
    eulaLoadStarted = true;
    try {
      const response = await fetch('/license/EULA.md');
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      eulaMarkdown = await response.text();
    } catch (error) {
      console.error('Failed to load EULA.md', error);
      eulaMarkdown = 'Unable to load EULA.md. Please verify the file is present and retry onboarding.';
    } finally {
      render();
    }
  };

  const render = () => {
    const page = pages[idx];
    const isLast = idx === pages.length - 1;
    const requireEula = page.requireEula === true;
    if (requireEula) {
      try {
        const storedEula = localStorage.getItem('buscore.eulaAccepted') === 'true';
        if (storedEula) eulaAccepted = true;
      } catch {}
    }
    const nextDisabled = requireEula && !eulaAccepted;
    const eulaHtml = requireEula ? renderEulaContent() : '';
    const eulaReady = requireEula && typeof eulaMarkdown === 'string';
    host.innerHTML = `
      <div class="card welcome-card">
        <h2 class="welcome-title">${page.title}</h2>
        <p class="welcome-body">${page.body}</p>
        ${requireEula ? `
          <div class="eula-container">
            <div id="eula-scroll">${eulaHtml}</div>
            <div class="eula-actions">
              <input type="checkbox" id="eula-accept" data-role="eula-check" ${eulaAccepted ? 'checked' : ''} ${eulaReachedEnd && eulaReady ? '' : 'disabled'}>
              <label for="eula-accept">I have read and accept the BUS Core End User License Agreement</label>
            </div>
          </div>
        ` : ''}
        <p class="welcome-step">Step ${idx + 1} of ${pages.length}</p>
        <div class="welcome-actions">
          <button type="button" data-action="welcome-back" ${idx === 0 ? 'disabled' : ''}>Back</button>
          <button type="button" data-action="welcome-next" ${nextDisabled ? 'disabled' : ''}>${isLast ? 'Enter application' : 'Continue'}</button>
        </div>
      </div>
    `;

    if (requireEula && !eulaLoadStarted) {
      void loadEula();
    }

    const eulaScroll = host.querySelector('#eula-scroll');
    if (requireEula && eulaReady && eulaScroll) {
      if (!eulaScroll.dataset.listenerAttached) {
        eulaScroll.dataset.listenerAttached = 'true';
        eulaScroll.addEventListener('scroll', () => {
          if (eulaScroll.scrollTop + eulaScroll.clientHeight >= eulaScroll.scrollHeight - 4) {
            const checkbox = document.getElementById('eula-accept');
            if (checkbox) checkbox.disabled = false;
            eulaReachedEnd = true;
          }
        });
      }
      if (eulaScroll.scrollHeight <= eulaScroll.clientHeight) {
        const checkbox = document.getElementById('eula-accept');
        if (checkbox) checkbox.disabled = false;
        eulaReachedEnd = true;
      }
      if (eulaScroll.scrollTop + eulaScroll.clientHeight >= eulaScroll.scrollHeight - 4) {
        const checkbox = document.getElementById('eula-accept');
        if (checkbox) checkbox.disabled = false;
        eulaReachedEnd = true;
      }
    }

    host.querySelector('#eula-accept')?.addEventListener('change', (event) => {
      eulaAccepted = !!event.target?.checked;
      if (eulaAccepted) {
        try {
          localStorage.setItem('buscore.eulaAccepted', 'true');
        } catch {}
      }
      render();
    });

    host.querySelector('[data-action="welcome-back"]')?.addEventListener('click', () => {
      if (idx > 0) {
        idx -= 1;
        render();
      }
    });

    host.querySelector('[data-action="welcome-next"]')?.addEventListener('click', () => {
      if (requireEula && !eulaAccepted) {
        return;
      }
      if (isLast) {
        setOnboardingComplete(true);
        window.location.hash = '#/home';
        return;
      }
      idx += 1;
      render();
    });
  };

  render();
}

