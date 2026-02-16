/* SPDX-License-Identifier: AGPL-3.0-or-later */
import mountVendors from "../cards/vendors.js";

let _container = null;

export async function mount(container) {
  if (!container) return;
  _container = container;
  _container.innerHTML = '<div class="card" data-view="contacts"></div>';
  const host = _container.querySelector('[data-view="contacts"]');
  await mountVendors(host);
}

export function unmount() {
  if (_container) _container.innerHTML = '';
  _container = null;
}
