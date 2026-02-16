// Copyright (C) 2025 BUS Core Authors
// SPDX-License-Identifier: AGPL-3.0-or-later

// Legacy route shim kept for compatibility. Canonical routing is in /ui/app.js.
import { registerRoute } from '../router.js';
import { mountManufacturing, unmountManufacturing } from '../cards/manufacturing.js';

registerRoute('/manufacturing', mount);

async function mount(root) {
  unmountManufacturing();
  if (root) root.innerHTML = '<div data-tab-panel="manufacturing"></div>';
  await mountManufacturing();
}
