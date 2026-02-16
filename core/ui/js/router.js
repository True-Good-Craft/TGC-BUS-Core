// Copyright (C) 2025 BUS Core Authors
// SPDX-License-Identifier: AGPL-3.0-or-later

// Legacy router shim (disabled): app.js is the canonical SPA router.
const routes = {};

export function registerRoute(path, render) {
  routes[path] = render;
}

export function navigate(path) {
  if (location.hash !== `#${path}`) location.hash = `#${path}`;
}

export function renderLegacyRoute() {
  const path = location.hash.replace(/^#/, '') || '/home';
  const target = document.getElementById('app');
  const fn = routes[path] || routes['/home'];
  if (target && fn) fn(target);
}
