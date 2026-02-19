// SPDX-License-Identifier: AGPL-3.0-or-later
// TGC BUS Core (Business Utility System Core)

import { ensureToken } from "./js/token.js";
import { toMetricBase, DIM_DEFAULTS_IMPERIAL } from "./js/lib/units.js";

import * as homeModule from "./js/screens/home.js";
import * as inventoryModule from "./js/screens/inventory.js";
import * as contactsModule from "./js/screens/contacts.js";
import * as recipesModule from "./js/screens/recipes.js";
import * as manufacturingModule from "./js/screens/manufacturing.js";
import * as logsModule from "./js/screens/logs.js";
import * as financeModule from "./js/screens/finance.js";
import * as settingsModule from "./js/screens/settings.js";
import * as welcomeModule from "./js/screens/welcome.js";

const ROUTES = {
  home: { container: '[data-role="home-screen"]', module: homeModule },
  inventory: { container: '[data-role="inventory-screen"]', module: inventoryModule },
  contacts: { container: '[data-role="contacts-screen"]', module: contactsModule },
  recipes: { container: '[data-role="recipes-screen"]', module: recipesModule },
  manufacturing: { container: '[data-role="manufacturing-screen"]', module: manufacturingModule },
  logs: { container: '[data-role="logs-screen"]', module: logsModule },
  finance: { container: '[data-role="finance-screen"]', module: financeModule },
  settings: { container: '[data-role="settings-screen"]', module: settingsModule },
  welcome: { container: '[data-role="welcome-screen"]', module: welcomeModule },
};

let currentScreen = null;

let firstRunGuardChecked = false;

async function shouldRedirectToWelcome(route) {
  if (route !== "home" || firstRunGuardChecked) return false;
  firstRunGuardChecked = true;
  try {
    const res = await fetch('/app/system/state', { credentials: 'include' });
    if (!res.ok) return false;
    const state = await res.json();
    return !!state?.is_empty;
  } catch (_) {
    return false;
  }
}

function hideAllScreens() {
  Object.values(ROUTES).forEach((r) => {
    document.querySelector(r.container)?.classList.add('hidden');
  });
}

function updateSidebarActive(route) {
  document.querySelectorAll('[data-role="nav-link"]').forEach((link) => {
    link.classList.toggle(
      'active',
      link.dataset.route === route
    );
  });
}

function routeFromHash() {
  const route = (location.hash.replace('#/', '') || 'home').split(/[/?]/)[0];
  if (route === 'admin') return 'settings';
  return route;
}

async function handleRouteChange() {
  await ensureToken();

  const requestedRoute = routeFromHash();
  const activeRoute = ROUTES[requestedRoute] ? requestedRoute : 'home';

  if (activeRoute !== 'welcome' && await shouldRedirectToWelcome(activeRoute)) {
    if (location.hash !== '#/welcome') location.hash = '#/welcome';
    return;
  }

  const spec = ROUTES[activeRoute] || ROUTES.home;

  if (currentScreen?.unmount) await currentScreen.unmount();
  hideAllScreens();

  const container = document.querySelector(spec.container);
  if (!container) return;

  await spec.module.mount(container);
  container.classList.remove('hidden');

  currentScreen = spec.module;
  updateSidebarActive(activeRoute);
}

window.addEventListener('hashchange', () => {
  handleRouteChange().catch((err) => console.error('route change failed', err));
});

window.addEventListener('load', () => {
  handleRouteChange().catch((err) => console.error('route change failed', err));
});

if (!location.hash) location.hash = '#/home';

// ---- American mode (imperial) toggle state ----
window.BUS_UNITS = {
  get american() {
    try { return localStorage.getItem('bus.american_mode') === '1'; } catch { return false; }
  },
  set american(v) {
    try { localStorage.setItem('bus.american_mode', v ? '1' : '0'); } catch {}
    document.dispatchEvent(new CustomEvent('bus:units-mode', { detail: { american: !!v } }));
  }
};

// Wrap fetch to convert imperial -> metric for known endpoints when American mode is ON.
(function wrapFetch(){
  const $fetch = window.fetch.bind(window);
  window.fetch = async function(input, init){
    try {
      if (!window.BUS_UNITS.american) return $fetch(input, init);
      const url = (typeof input === 'string') ? input : input.url;
      const targets = ['/app/purchase', '/app/adjust', '/app/consume', '/app/stock/out'];
      if (!targets.some(t => url && url.includes(t))) return $fetch(input, init);
      if (!init || !init.body || typeof init.body !== 'string') return $fetch(input, init);
      let payload = JSON.parse(init.body);
      const dim = payload.dimension || payload.item_dimension || payload.dim || 'area';
      const unit = payload.qty_unit || payload.unit || payload.unit_price_unit || DIM_DEFAULTS_IMPERIAL[dim];
      const converted = toMetricBase({
        dimension: dim,
        qty: payload.qty ?? payload.quantity ?? payload.amount,
        qtyUnit: unit,
        unitPrice: payload.unit_price ?? payload.price,
        priceUnit: payload.price_unit ?? unit
      });
      if (!converted.sendUnits) {
        if (payload.qty != null) payload.qty = converted.qtyBase;
        if (payload.quantity != null) payload.quantity = converted.qtyBase;
        if (payload.amount != null) payload.amount = converted.qtyBase;
        if (payload.unit_price != null) payload.unit_price = converted.pricePerBase;
        delete payload.qty_unit;
        delete payload.price_unit;
        delete payload.unit;
      }
      init = { ...init, body: JSON.stringify(payload) };
    } catch (_) {
      // fail open
    }
    return $fetch(input, init);
  };
})();

document.addEventListener('DOMContentLoaded', async () => {
  try {
    await ensureToken();
    try {
      const res = await fetch('/openapi.json', { credentials: 'include' });
      const j = await res.json();
      const el = document.querySelector('[data-role="ui-version"]');
      if (el && j?.info?.version) el.textContent = j.info.version;
    } catch (_) {}
  } catch (e) {
    console.error('BOOT FAIL', e);
  }
});
