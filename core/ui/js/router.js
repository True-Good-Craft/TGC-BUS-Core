// Copyright (C) 2025 BUS Core Authors
// SPDX-License-Identifier: AGPL-3.0-or-later

// core/ui/js/router.js
const LEGACY_ROUTER_ENABLED = false;
const HOME_ROUTE = '/home';
const RESERVED_ROUTE_KEYS = new Set(['__proto__', 'constructor', 'prototype', 'toString']);

// Legacy compatibility router only. shell/app.js is the canonical active router.
const routes = Object.create(null);


function normalizeRoute(path) {
  if (typeof path !== 'string') return HOME_ROUTE;
  const normalized = path.trim() || HOME_ROUTE;
  if (RESERVED_ROUTE_KEYS.has(normalized)) return HOME_ROUTE;
  return normalized;
}


function hasRoute(path) {
  return Object.prototype.hasOwnProperty.call(routes, path);
}


function resolveRoute(path) {
  const normalizedPath = normalizeRoute(path);
  const handler = hasRoute(normalizedPath) ? routes[normalizedPath] : routes[HOME_ROUTE];
  return typeof handler === 'function' ? handler : null;
}

export function registerRoute(path, render) {
  const normalizedPath = normalizeRoute(path);
  if (typeof render !== 'function') return;
  routes[normalizedPath] = render;
}

export function navigate(path) {
  const normalizedPath = normalizeRoute(path);
  if (location.hash !== `#${normalizedPath}`) location.hash = `#${normalizedPath}`;
  render();
}

function render() {
  const path = normalizeRoute(location.hash.replace(/^#/, ''));
  const target = document.getElementById('app');
  const handler = resolveRoute(path);
  if (!target || typeof handler !== 'function') return;
  target.innerHTML = '';
  handler(target);
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
