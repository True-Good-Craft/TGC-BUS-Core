/* SPDX-License-Identifier: AGPL-3.0-or-later */
import { mountDashboard } from "../cards/dashboard.js";

let _container = null;

export async function mount(container) {
  if (!container) return;
  _container = container;
  _container.innerHTML = '';
  await mountDashboard();
}

export function unmount() {
  if (_container) _container.innerHTML = '';
  _container = null;
}
