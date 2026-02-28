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
import { apiGet, rawFetch } from "./js/api.js";
import { mountBackupExport } from "./js/cards/backup.js";
import mountVendors from "./js/cards/vendors.js";
import { mountHome } from "./js/cards/home.js";
import "./js/cards/home_donuts.js";
import { mountInventory, unmountInventory } from "./js/cards/inventory.js";
import { mountManufacturing, unmountManufacturing } from "./js/cards/manufacturing.js";
import { mountRecipes, unmountRecipes } from "./js/cards/recipes.js";
import { settingsCard } from "./js/cards/settings.js";
import { mountLogsPage } from "./js/logs.js";
import { toMetricBase, DIM_DEFAULTS_IMPERIAL } from "./js/lib/units.js";

const ROUTES = {
  '#/welcome': showWelcome,
  '#/inventory': showInventory,
  '#/manufacturing': showManufacturing,
  '#/recipes': showRecipes,
  '#/contacts': showContacts,
  '#/runs': showRuns,
  '#/import': showImport,
  '#/settings': showSettings,
  '#/logs': showLogs,
  '#/home': showHome,
  '#/': showInventory,
  '': showInventory,
};

const ONBOARDING_STORAGE_KEY = 'bus.onboarding.completed';
const ONBOARDING_ALLOWLIST = new Set(['#/welcome', '#/settings']);

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
  const manufacturingHost = document.querySelector('[data-tab-panel="manufacturing"]');
  const recipesHost = document.querySelector('[data-tab-panel="recipes"]');
  const logsHost = document.querySelector('[data-role="logs-root"]');
  const welcomeHost = document.querySelector('[data-role="welcome-root"]');
  [root, inventoryHost, contactsHost, settingsHost, manufacturingHost, recipesHost, logsHost, welcomeHost].forEach((node) => {
    if (node) node.innerHTML = '';
  });
}

async function enforceFirstRunRedirect(baseHash) {
  if (baseHash === '#/welcome') return false;
  if (ONBOARDING_ALLOWLIST.has(baseHash)) return false;
  if (isOnboardingComplete()) return false;
  let state;
  try {
    state = await apiGet('/app/system/state');
  } catch (_) {
    return false;
  }
  if (!state || typeof state !== 'object') return false;
  if (state.is_first_run !== true && state.is_first_run !== false) return false;
  if (!state.counts || typeof state.counts !== 'object' || Array.isArray(state.counts)) return false;
  if (state.demo_allowed !== true && state.demo_allowed !== false) return false;
  if (!Array.isArray(state.basis)) return false;
  if (state.is_first_run !== true) return false;
  if (window.location.hash !== baseHash) return false;
  window.location.hash = '#/welcome';
  return true;
}

async function onRouteChange() {
  await ensureToken();
  const raw = window.location.hash || '#/home';
  const canonical = normalizeHash(raw);

  if (canonical !== raw) {
    window.location.hash = canonical;
    return;
  }

  window.BUS_ROUTE = { path: canonical, base: canonical, id: null };

  const detailMatch = canonical.match(/^#\/(inventory|contacts|recipes|runs)\/([^/]+)$/);
  const baseHash = detailMatch ? `#/${detailMatch[1]}` : canonical;
  const detailId = detailMatch ? decodeURIComponent(detailMatch[2]) : null;
  const hash = canonical;

  if (detailMatch) {
    window.BUS_ROUTE = { path: canonical, base: baseHash, id: detailId };
  }

  const route = normalizeRoute(baseHash);

  if (await enforceFirstRunRedirect(baseHash)) {
    return;
  }

  setActiveNav(route);

  document.querySelector('[data-role="settings-screen"]')?.classList.add('hidden');
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
  onRouteChange().catch(err => console.error('route change failed', err));
});
window.addEventListener('load', () => {
  onRouteChange().catch(err => console.error('route change failed', err));
});

if (!location.hash) location.hash = '#/home';

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
    await ensureToken();
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
  document.querySelector('[data-role="welcome-screen"]')?.classList.add('hidden');
  const settingsScreen = document.querySelector('[data-role="settings-screen"]');
  settingsScreen?.classList.remove('hidden');
  const host = document.querySelector('[data-role="settings-root"]');
  if (host && (!settingsMounted || !host.hasChildNodes())) {
    settingsCard(host);
    settingsMounted = true;
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
  document.querySelector('[data-role="welcome-screen"]')?.classList.add('hidden');
  const logsScreen = document.querySelector('[data-role="logs-screen"]');
  logsScreen?.classList.remove('hidden');
  const host = document.querySelector('[data-role="logs-root"]');
  if (host) {
    host.innerHTML = '';
    mountLogsPage(host);
  }
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
  document.querySelector('[data-role="welcome-screen"]')?.classList.add('hidden');
}

async function showRecipes() {
  document.querySelector('[data-role="home-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="contacts-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="settings-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="inventory-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="manufacturing-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="logs-screen"]')?.classList.add('hidden');
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
  document.querySelector('[data-role="welcome-screen"]')?.classList.add('hidden');
  showScreen('home');
  renderInlinePanel('Import', 'Import screen not implemented yet');
}

async function showWelcome() {
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
  const welcomeScreen = document.querySelector('[data-role="welcome-screen"]');
  welcomeScreen?.classList.remove('hidden');
  const host = document.querySelector('[data-role="welcome-root"]');
  if (!host) return;

  const pages = [
    {
      title: 'Welcome to BUS Core',
      body: 'Track items by on-hand quantity and cost batches. The app can show simple item totals while keeping purchase batches for FIFO costing.',
    },
    {
      title: 'FIFO means oldest cost moves first',
      body: 'When stock leaves inventory, BUS Core consumes the oldest available batch. This keeps unit cost and margins grounded in actual purchase order history.',
    },
    {
      title: 'Recipes and manufacturing runs',
      body: 'Recipes define what gets consumed and produced. Manufacturing runs execute those recipes and write inventory + journal entries together.',
    },
    {
      title: 'Cost vs price',
      body: 'Cost tracks what inventory is worth internally. Price is what you charge customers. Keep both updated so reports make sense.',
    },
    {
      title: 'Vendors and linkage',
      body: 'Link items to vendors to preserve sourcing context for purchasing and replenishment. This helps when costs drift or lead times change.',
    },
  ];

  let idx = 0;
  const render = () => {
    const page = pages[idx];
    const isLast = idx === pages.length - 1;
    host.innerHTML = `
      <div class="card" style="max-width:760px; margin:0 auto;">
        <h2 style="margin:0 0 8px;">${page.title}</h2>
        <p style="margin:0 0 12px; color:#d1d5db;">${page.body}</p>
        <p style="margin:0 0 18px; font-size:12px; color:#9ca3af;">Step ${idx + 1} of ${pages.length}</p>
        <div style="display:flex; gap:8px; justify-content:flex-end;">
          <button type="button" data-action="welcome-back" ${idx === 0 ? 'disabled' : ''}>Back</button>
          <button type="button" data-action="welcome-next">${isLast ? 'Finish onboarding' : 'Next'}</button>
        </div>
      </div>
    `;
    host.querySelector('[data-action="welcome-back"]')?.addEventListener('click', () => {
      if (idx > 0) {
        idx -= 1;
        render();
      }
    });
    host.querySelector('[data-action="welcome-next"]')?.addEventListener('click', () => {
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
