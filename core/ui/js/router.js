// Copyright (C) 2025 BUS Core Authors
// SPDX-License-Identifier: AGPL-3.0-or-later

// core/ui/js/router.js
const LEGACY_ROUTER_ENABLED = false;

const routes = {};

export function registerRoute(path, render) {
  routes[path] = render;
}

export function navigate(path) {
  if (location.hash !== `#${path}`) location.hash = `#${path}`;
  render();
}

function render() {
  const path = location.hash.replace(/^#/, '') || '/home';
  const target = document.getElementById('app');
  const fn = routes[path] || routes['/home'];
  target.innerHTML = '';
  fn(target);
}

function initLegacyRouter() {
  window.addEventListener('hashchange', render); // initLegacyRouter binding
  window.addEventListener('DOMContentLoaded', render); // initLegacyRouter binding
}

if (LEGACY_ROUTER_ENABLED) {
  initLegacyRouter();
} else {
  console.warn('[LEGACY ROUTER] disabled (shell/app.js is canonical).');
}
