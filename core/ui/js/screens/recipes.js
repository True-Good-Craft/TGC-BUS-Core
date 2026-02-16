/* SPDX-License-Identifier: AGPL-3.0-or-later */
import { mountRecipes, unmountRecipes } from "../cards/recipes.js";

let _container = null;

export async function mount(container) {
  if (!container) return;
  _container = container;
  _container.innerHTML = '<div data-tab-panel="recipes"></div>';
  await mountRecipes();
}

export function unmount() {
  unmountRecipes();
  if (_container) _container.innerHTML = '';
  _container = null;
}
