// SPDX-License-Identifier: AGPL-3.0-or-later
// Manufacturing Runs & History Card

import { ensureToken } from '../api.js';
import { RecipesAPI } from '../api/recipes.js';
import * as canonical from '../api/canonical.js';
import { fromBaseQty, fmtQty, dimensionForUnit } from '../lib/units.js';

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  Object.entries(attrs).forEach(([k, v]) => {
    if (k === 'class') node.className = v;
    else if (k === 'text') node.textContent = v;
    else node.setAttribute(k, v);
  });
  (Array.isArray(children) ? children : [children]).forEach((child) => {
    if (child === null || child === undefined) return;
    node.append(child);
  });
  return node;
}

let _state = {
  recipes: [],
  selectedRecipe: null,
};

const recipeNameCache = (window._recipeNameCache = window._recipeNameCache || Object.create(null));

function fmtHumanQty(value, uom) {
  const normalizedUom = String(uom || '').trim();
  return `${String(value ?? '0')}${normalizedUom ? ` ${normalizedUom}` : ''}`;
}

function toDecimalString(value) {
  const raw = String(value ?? '').trim().replace(/,/g, '');
  if (!raw || raw === '.' || raw === '-.') return '0';
  return raw.startsWith('.') ? `0${raw}` : raw;
}

function decimalToNumber(value) {
  const parsed = Number(toDecimalString(value));
  return Number.isFinite(parsed) ? parsed : NaN;
}

function scaleQuantityDecimal(value, factor) {
  const qty = decimalToNumber(value);
  if (!Number.isFinite(qty)) return '0';
  return toDecimalString(String(qty * factor));
}

function formatManufactureError(err) {
  const payload = err?.payload || err?.data || {};
  const detail = payload?.detail ?? payload;
  if (detail && typeof detail === 'object' && detail.error === 'insufficient_stock' && Array.isArray(detail.shortages)) {
    const rows = detail.shortages.map((s) => {
      const itemId = s?.item_id ?? s?.component ?? '?';
      const req = s?.required ?? '?';
      const avail = s?.available ?? '?';
      return `item ${itemId} need ${req}, have ${avail}`;
    });
    return `Insufficient stock: ${rows.join(' | ')}`;
  }
  if (detail?.message) return String(detail.message);
  if (typeof detail === 'string') return detail;
  if (payload?.error) return String(payload.error);
  return err?.message || 'Run failed.';
}

function _runConfirmText({ recipeName, outputQty, adhoc }) {
  const title = adhoc ? 'Confirm Ad-hoc Manufacturing Run' : 'Confirm Manufacturing Run';
  const name = recipeName ? `Recipe: ${recipeName}` : 'Recipe: (unknown)';
  const qty = `Output Qty: ${outputQty}`;
  return `${title}\n\n${name}\n${qty}\n\nThis will update stock (FIFO). Proceed?`;
}

export async function mountManufacturing() {
  await ensureToken();
  _state = { recipes: [], selectedRecipe: null };
  const container = document.querySelector('[data-tab-panel="manufacturing"]');
  if (!container) return;

  container.innerHTML = '';
  container.classList.add('manufacturing-shell');

  const grid = el('div', { class: 'manufacturing-grid' });
  const leftPanel = el('div', { class: 'manufacturing-panel-left' });
  const rightPanel = el('div', { class: 'manufacturing-panel-right' });

  grid.append(leftPanel, rightPanel);
  container.append(grid);

  await renderNewRunForm(leftPanel);
  await renderHistoryList(rightPanel);
}

export function unmountManufacturing() {
  _state = { recipes: [], selectedRecipe: null };
  const container = document.querySelector('[data-tab-panel="manufacturing"]');
  if (container) container.innerHTML = '';
}

async function renderNewRunForm(parent) {
  try {
    const list = await RecipesAPI.list();
    _state.recipes = (list || []).filter((r) => !r.archived);
  } catch {
    parent.append(el('div', { class: 'error' }, 'Failed to load recipes.'));
    return;
  }

  const card = el('div', { class: 'card' });
  const headerRow = el('div', { class: 'mfg-header-row' }, [
    el('h2', { text: 'New Manufacturing Run' }),
    el('a', { href: '#/recipes', class: 'btn small mfg-manage-recipes' }, 'Manage Recipes'),
  ]);

  const formGrid = el('div', { class: 'form-grid mfg-form-grid' });

  const recipeSelect = el('select', { id: 'run-recipe', class: 'mfg-select' });
  recipeSelect.append(el('option', { value: '' }, '— Select Recipe —'));
  _state.recipes.forEach((r) => {
    const id = r.id ?? r.recipe_id;
    const nm = r.name ?? r.title ?? r.label ?? r.recipe_name ?? r.slug;
    if (id != null && nm) recipeNameCache[String(id)] = String(nm);
    recipeSelect.append(el('option', { value: r.id }, r.name));
  });

  formGrid.append(el('label', { class: 'mfg-field' }, [el('div', { class: 'mfg-label', text: 'Recipe' }), recipeSelect]));

  const qtyInput = el('input', {
    id: 'run-qty',
    class: 'mfg-select',
    type: 'number',
    min: '0.001',
    step: '0.001',
    value: '1',
  });
  formGrid.append(el('label', { class: 'mfg-field' }, [el('div', { class: 'mfg-label', text: 'Output Quantity' }), qtyInput]));

  const tableContainer = el('div', { class: 'projection-table mfg-projection-wrap' });
  const table = el('table', { class: 'mfg-projection-table' });
  const thead = el('thead', {}, [
    el('tr', { class: 'mfg-projection-head' }, [
      el('th', { text: 'Item' }),
      el('th', { text: 'Role' }),
      el('th', { class: 'mfg-col-right', text: 'Stock' }),
      el('th', { class: 'mfg-col-right', text: 'Change' }),
    ]),
  ]);
  const tbody = el('tbody');
  table.append(thead, tbody);
  tableContainer.append(table);

  const emptyMsg = el('div', { class: 'mfg-empty-msg', text: 'Select a recipe to view projection.' });
  tableContainer.append(emptyMsg);

  const btnRow = el('div', { class: 'mfg-btn-row' });
  const statusMsg = el('span', { class: 'mfg-status-msg', 'data-tone': 'neutral' });
  const runBtn = el('button', { class: 'btn primary mfg-run-btn', disabled: 'true' }, 'Run Production');
  btnRow.append(statusMsg, runBtn);

  card.append(headerRow, formGrid, tableContainer, btnRow);
  parent.append(card);

  const setProjectionVisible = (visible) => {
    table.classList.toggle('hidden', !visible);
    emptyMsg.classList.toggle('hidden', visible);
  };

  const setStatus = (text = '', tone = 'neutral') => {
    statusMsg.textContent = text;
    statusMsg.dataset.tone = tone;
  };

  setProjectionVisible(false);

  const updateProjection = async () => {
    const rid = recipeSelect.value;
    if (!rid) {
      tbody.innerHTML = '';
      setProjectionVisible(false);
      runBtn.disabled = true;
      _state.selectedRecipe = null;
      return;
    }

    try {
      const fullRecipe = await RecipesAPI.get(rid);
      if (fullRecipe?.archived) {
        setStatus('This recipe is archived and cannot be run.', 'error');
        tbody.innerHTML = '';
        setProjectionVisible(false);
        runBtn.disabled = true;
        _state.selectedRecipe = null;
        return;
      }

      _state.selectedRecipe = fullRecipe;
      tbody.innerHTML = '';
      setProjectionVisible(true);
      runBtn.disabled = false;

      const baseOutput = decimalToNumber(fullRecipe.quantity_decimal || '1');
      const requestedOutput = decimalToNumber(qtyInput.value || fullRecipe.quantity_decimal || '1');
      if (Number.isFinite(baseOutput) && baseOutput > 0 && Number.isFinite(requestedOutput) && requestedOutput > 0) {
        const factor = requestedOutput / baseOutput;

        (fullRecipe.items || []).forEach((ri) => {
          const row = el('tr', { class: 'mfg-projection-row' });
          const item = ri.item || {};
          const stock = item.stock_on_hand_display?.value ?? '—';
          const scaledChange = scaleQuantityDecimal(ri.quantity_decimal || '0', factor);
          const change = fmtHumanQty(`-${scaledChange}`, ri.uom || ri.item?.uom);
          row.append(
            el('td', { text: ri.item?.name || `Item #${ri.item_id}` }),
            el('td', { class: 'mfg-muted-cell', text: (ri.optional ?? ri.is_optional) ? 'Optional' : 'Input' }),
            el('td', { class: 'mfg-col-right', text: stock }),
            el('td', { class: 'mfg-col-right', text: change }),
          );
          tbody.append(row);
        });

        if (fullRecipe.output_item_id) {
          const row = el('tr', { class: 'mfg-projection-row' });
          row.append(
            el('td', { text: fullRecipe.output_item?.name || `Item #${fullRecipe.output_item_id}` }),
            el('td', { class: 'mfg-output-cell', text: 'Output' }),
            el('td', { class: 'mfg-col-right', text: '—' }),
            el('td', { class: 'mfg-col-right mfg-output-cell', text: fmtHumanQty(toDecimalString(qtyInput.value || fullRecipe.quantity_decimal || '1'), fullRecipe.uom || fullRecipe.output_item?.uom) }),
          );
          tbody.append(row);
        }
        return;
      }

      setStatus('Output quantity must be a positive number.', 'error');
      runBtn.disabled = true;

      (fullRecipe.items || []).forEach((ri) => {
        const row = el('tr', { class: 'mfg-projection-row' });
        const item = ri.item || {};
        const stock = item.stock_on_hand_display?.value ?? '—';
        const change = fmtHumanQty(`-${ri.quantity_decimal || '0'}`, ri.uom || ri.item?.uom);
        row.append(
          el('td', { text: ri.item?.name || `Item #${ri.item_id}` }),
          el('td', { class: 'mfg-muted-cell', text: (ri.optional ?? ri.is_optional) ? 'Optional' : 'Input' }),
          el('td', { class: 'mfg-col-right', text: stock }),
          el('td', { class: 'mfg-col-right', text: change }),
        );
        tbody.append(row);
      });

    } catch {
      setStatus('Error calculating projection.', 'error');
    }
  };

  recipeSelect.addEventListener('change', updateProjection);
  qtyInput.addEventListener('input', updateProjection);

  runBtn.addEventListener('click', async () => {
    if (!_state.selectedRecipe) return;
    try {
      const recipeId = Number(_state.selectedRecipe.id);
      if (!Number.isInteger(recipeId) || recipeId <= 0) throw new Error('Select a valid recipe.');
      const qtyDecimal = toDecimalString(qtyInput.value || '0');
      const qtyNumber = decimalToNumber(qtyDecimal);
      if (!Number.isFinite(qtyNumber) || qtyNumber <= 0) {
        setStatus('Output quantity must be a positive number.', 'error');
        return;
      }

      const outputUom = String(
        _state.selectedRecipe?.uom ||
        _state.selectedRecipe?.output_item?.uom ||
        _state.selectedRecipe?.output_item?.display_unit ||
        ''
      ).trim();
      if (!outputUom) {
        setStatus('Missing output unit (uom). Cannot run manufacturing.', 'error');
        runBtn.disabled = false;
        runBtn.textContent = 'Run Production';
        return;
      }
      const payload = {
        recipe_id: recipeId,
        quantity_decimal: qtyDecimal,
        uom: outputUom,
      };

      const recipeName = (
        _state.selectedRecipe.name ||
        _state.selectedRecipe.title ||
        _state.selectedRecipe.label ||
        document.querySelector('#run-recipe option:checked')?.textContent ||
        ''
      );
      const ok = window.confirm(_runConfirmText({ recipeName, outputQty: `${payload.quantity_decimal} ${payload.uom}`, adhoc: false }));
      if (!ok) return;

      runBtn.disabled = true;
      runBtn.textContent = 'Processing...';
      setStatus('', 'neutral');

      await canonical.manufactureRecipe(payload);

      setStatus('Run Complete!', 'success');
      await updateProjection();
      await loadRecentRuns30d();
      runBtn.textContent = 'Run Production';
      runBtn.disabled = false;
    } catch (e) {
      const payload = e?.payload || e?.data || {};
      setStatus(formatManufactureError(e), 'error');
      runBtn.disabled = false;
      runBtn.textContent = 'Run Production';
    }
  });
}

async function renderHistoryList(parent) {
  const card = el('div', { class: 'card' });
  card.append(el('h2', { text: 'Recent Runs (30d)' }));

  const list = el('div', { id: 'mf-recent-panel', class: 'history-list mfg-recent-panel' });
  card.append(list);
  parent.append(card);

  await loadRecentRuns30d();
}

async function loadRecentRuns30d() {
  const panel = document.getElementById('mf-recent-panel');
  if (!panel) return;

  panel.innerHTML = `
    <div class="mf-runs-grid mf-runs-head">
      <div>Recipe</div><div>Date</div><div>Qty</div>
    </div>
    <div id="mf-runs-body"></div>
  `;
  const body = panel.querySelector('#mf-runs-body');

  try {
    const ledger = await canonical.ledgerHistory({ limit: 200 });
    const rows = Array.isArray(ledger?.movements) ? ledger.movements : [];
    const runs = rows.filter((r) => String(r.source_kind || '').toLowerCase().includes('manufact'));

    if (!runs.length) {
      body.innerHTML = '<div class="mf-runs-empty">No runs in the last 30 days.</div>';
      return;
    }

    const groupedRuns = [];
    const runBySourceId = new Map();
    runs.forEach((r) => {
      const sourceId = r.source_id ? String(r.source_id) : '';
      if (!sourceId) {
        groupedRuns.push(r);
        return;
      }
      if (!runBySourceId.has(sourceId)) {
        runBySourceId.set(sourceId, r);
        groupedRuns.push(r);
        return;
      }
      const existing = runBySourceId.get(sourceId);
      const existingTs = Date.parse(existing?.created_at || '');
      const candidateTs = Date.parse(r?.created_at || '');
      if (Number.isFinite(candidateTs) && (!Number.isFinite(existingTs) || candidateTs > existingTs)) {
        runBySourceId.set(sourceId, r);
        const idx = groupedRuns.indexOf(existing);
        if (idx >= 0) groupedRuns[idx] = r;
      }
    });

    const frag = document.createDocumentFragment();
    groupedRuns.forEach((r) => {
      const ts = r.created_at || '';
      const d = ts ? new Date(ts) : null;
      const dateStr = d ? d.toLocaleDateString() : '';
      const rid = r.source_id ? String(r.source_id) : null;
      const recipeName = (rid && recipeNameCache[rid]) || (rid ? `Run ${rid}` : (r.source_kind ? String(r.source_kind) : '(manufacture)'));
      const qty = fmtHumanQty(r.quantity_decimal, r.uom);
      const row = document.createElement('div');
      row.className = 'mf-runs-grid mf-runs-row';
      row.innerHTML = `<div title="${recipeName}">${recipeName}</div><div>${dateStr}</div><div>${qty}</div>`;
      frag.appendChild(row);
    });
    body.replaceChildren(frag);
  } catch {
    body.innerHTML = '<div class="mf-runs-empty">Failed to load recent runs.</div>';
  }
}

