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
import { rawFetch } from "./js/api.js";
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
  '#/inventory': showInventory,
  '#/manufacturing': showManufacturing,
  '#/recipes': showRecipes,
  '#/contacts': showContacts,
  '#/settings': showSettings,
  '#/logs': showLogs,
  '#/home': showHome,
  '#/': showInventory,
  '': showInventory,
};

function getHash() {
  return (window.location.hash || '#/home').replace(/\/+$/, '');
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
  [root, inventoryHost, contactsHost, settingsHost, manufacturingHost, recipesHost, logsHost].forEach((node) => {
    if (node) node.innerHTML = '';
  });
}

async function onRouteChange() {
  await ensureToken();
  const hash = getHash();

  if (hash === '#/admin') {
    location.hash = '#/settings';
    return;
  }

  const route = normalizeRoute(hash);
  setActiveNav(route);

  document.querySelector('[data-role="settings-screen"]')?.classList.add('hidden');
  clearCardHost();

  const fn = ROUTES[hash] || ROUTES['#/home'];
  await fn();
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
    try {
      const res = await rawFetch('/openapi.json', { credentials: 'include' });
      const j = await res.json();
      const el = document.querySelector('[data-role="ui-version"]');
      if (el && j?.info?.version) el.textContent = j.info.version;
    } catch (_) { /* non-fatal */ }
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
}

async function showRecipes() {
  document.querySelector('[data-role="home-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="contacts-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="settings-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="inventory-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="manufacturing-screen"]')?.classList.add('hidden');
  document.querySelector('[data-role="logs-screen"]')?.classList.add('hidden');
  const recipesScreen = document.querySelector('[data-role="recipes-screen"]');
  recipesScreen?.classList.remove('hidden');
  unmountInventory();
  unmountManufacturing();
  await mountRecipes();
}

