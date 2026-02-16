/* SPDX-License-Identifier: AGPL-3.0-or-later */
import { mountLogsPage } from "../logs.js";

let _container = null;

export async function mount(container) {
  if (!container) return;
  _container = container;
  _container.innerHTML = '<div data-role="logs-root"></div>';
  const host = _container.querySelector('[data-role="logs-root"]');
  mountLogsPage(host);
}

export function unmount() {
  if (_container) _container.innerHTML = '';
  _container = null;
}
