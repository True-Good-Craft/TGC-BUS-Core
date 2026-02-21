/* SPDX-License-Identifier: AGPL-3.0-or-later */
import { mountManufacturing, unmountManufacturing } from "../cards/manufacturing.js";

let _container = null;

export async function mount(container) {
  if (!container) return;
  _container = container;
  _container.innerHTML = '<div data-tab-panel="manufacturing"></div>';
  await mountManufacturing();
}

export function unmount() {
  unmountManufacturing();
  if (_container) _container.innerHTML = '';
  _container = null;
}
