/* SPDX-License-Identifier: AGPL-3.0-or-later */
import { mountInventory, unmountInventory } from "../cards/inventory.js";

let _container = null;

export async function mount(container) {
  if (!container) return;
  _container = container;
  _container.innerHTML = '<div data-role="inventory-root" class="card"></div>';
  await mountInventory();
}

export function unmount() {
  unmountInventory();
  if (_container) _container.innerHTML = '';
  _container = null;
}
