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

import { toMetricBase, DIM_DEFAULTS_IMPERIAL } from "./lib/units.js";

// --- single-auth helpers: atomic token + retry on 401 ---

// Wrap fetch to convert imperial -> metric for known endpoints when American mode is ON.
(function wrapFetch(){
  const $fetch = window.fetch.bind(window);
  window.fetch = async function(input, init){
    try {
      if (!window.BUS_UNITS.american) return $fetch(input, init);
      const url = (typeof input === 'string') ? input : input.url;
      // Only touch known mutate endpoints
      const targets = ['/app/purchase', '/app/adjust', '/app/consume', '/app/stock/out'];
      if (!targets.some(t => url && url.includes(t))) return $fetch(input, init);
      if (!init || !init.body || typeof init.body !== 'string') return $fetch(input, init);
      let payload = JSON.parse(init.body);
      // Heuristics: determine dimension
      const dim = payload.dimension || payload.item_dimension || payload.dim || 'area'; // default harmlessly
      const unit = payload.qty_unit || payload.unit || payload.unit_price_unit || DIM_DEFAULTS_IMPERIAL[dim];
      const converted = toMetricBase({
        dimension: dim,
        qty: payload.qty ?? payload.quantity ?? payload.amount,
        qtyUnit: unit,
        unitPrice: payload.unit_price ?? payload.price,
        priceUnit: payload.price_unit ?? unit
      });
      if (!converted.sendUnits) {
        if (payload.qty != null)       payload.qty = converted.qtyBase;
        if (payload.quantity != null)  payload.quantity = converted.qtyBase;
        if (payload.amount != null)    payload.amount = converted.qtyBase;
        if (payload.unit_price != null) payload.unit_price = converted.pricePerBase;
        // remove *_unit to indicate base units
        delete payload.qty_unit; delete payload.price_unit; delete payload.unit;
      }
      init = { ...init, body: JSON.stringify(payload) };
    } catch (e) {
      // fail open: do not block request
    }
    return $fetch(input, init);
  };
})();

let _tokenCache = null;        // string | null
let _tokenPromise = null;      // Promise<string> | null

export async function ensureToken() {
  if (_tokenCache) return _tokenCache;
  if (_tokenPromise) return _tokenPromise; // in-flight, await it

  _tokenPromise = (async () => {
    // FIX: 'omit' -> 'same-origin' to allow Set-Cookie to work
    const r = await fetch('/session/token', { credentials: 'same-origin' });
    if (!r.ok) throw new Error(`token fetch failed: ${r.status}`);
    const j = await r.json();
    _tokenCache = j.token;
    _tokenPromise = null;
    return _tokenCache;
  })();

  return _tokenPromise;
}

function clearToken() {
  _tokenCache = null;
  _tokenPromise = null;
}

async function withAuth(init = {}) {
  // Ensure we have established the session (and planted the cookie)
  await ensureToken();

  const headers = new Headers(init.headers || {});
  // REMOVED: X-Session-Token header (Backend is cookie-only now)

  // FIX: 'same-origin' ensures the browser sends the cookie
  return { ...init, headers, credentials: 'same-origin' };
}

export async function request(url, init) {
  // first attempt
  let resp = await fetch(url, await withAuth(init || {}));
  if (resp.status !== 401) return resp;

  // single retry path: refresh token and resend
  clearToken();
  await ensureToken();
  resp = await fetch(url, await withAuth(init || {}));
  return resp;
}

// Convenience wrappers. Keep signatures stable.
export const apiGet  = (url, init) => request(url, { method: 'GET', ...(init || {}) });
export const apiPost = (url, body, init) => request(url, { method: 'POST', body, ...(init || {}) });
export const apiJson = (url, obj, init) =>
  request(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(obj || {}),
    ...(init || {})
  });

export const apiGetJson = async (url, init) => {
  const r = await apiGet(url, init);
  return r.json();
};

// --- end single-auth helpers ---

export const apiJsonJson = (url, obj, init) => apiJson(url, obj, init).then(res => res.json());
