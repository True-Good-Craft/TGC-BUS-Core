// SPDX-License-Identifier: AGPL-3.0-or-later
// Inventory card with smart input parsing.

import { apiGetJson, apiPost, apiPut, apiDelete, ensureToken } from '../api.js';
import * as canonical from '../api/canonical.js';
import { fromBaseUnitPrice, fmtMoney } from '../lib/units.js';
import { unitOptionsList, dimensionForUnit, DIM_DEFAULTS_IMPERIAL, DIM_DEFAULTS_METRIC } from '../lib/units.js';

const UNIT_OPTIONS = {
  length: ['mm', 'cm', 'm'],
  area: ['mm2', 'cm2', 'm2'],
  volume: ['mm3', 'cm3', 'm3', 'ml', 'l'],
  weight: ['mg', 'g', 'kg'],
  count: ['ea'],
};

const UNIT_LABEL = {
  mm: 'mm',
  cm: 'cm',
  m: 'm',
  mm2: 'mm²',
  cm2: 'cm²',
  m2: 'm²',
  mm3: 'mm³',
  cm3: 'cm³',
  m3: 'm³',
  ml: 'ml',
  l: 'l',
  mg: 'mg',
  g: 'g',
  kg: 'kg',
  ea: 'ea',
};


// Keep delegated handler binding stable across route changes
let _rootEl = null;
let _clickBound = false;
function _onRootClick(e) {
  const addBtn = e.target.closest('[data-role="btn-add-item"]');
  if (addBtn) {
    e.preventDefault();
    openItemModal(); // create mode
  }
}

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

function decimalString(v) {
  const s = String(v ?? '').trim().replace(/,/g, '');
  if (s === '' || s === '.' || s === '-.') return '0';
  return s.startsWith('.') ? `0${s}` : s;
}

let reloadInventory = null;

export function mountInventory() {
  const container = document.querySelector('[data-role="inventory-root"]');
  if (!container) return;
  _rootEl = container;
  _mountInventory(container);
  // Bind once for delegated toolbar events
  if (!_clickBound) {
    _rootEl.addEventListener('click', _onRootClick);
    _clickBound = true;
  }
}

// Needed by app.js router; ensures route changes don’t leak handlers/modals
export function unmountInventory() {
  // Close any open modals from this card
  document.querySelectorAll('.modal-overlay').forEach((el) => {
    try {
      if (typeof el._inventoryCleanup === 'function') el._inventoryCleanup();
    } catch (_) {/* ignore */}
    el.remove();
  });
  // Remove delegated click binding
  if (_rootEl && _clickBound) {
    _rootEl.removeEventListener('click', _onRootClick);
    _clickBound = false;
  }
}

async function fetchItems(state) {
  state.items = await apiGetJson('/app/items');
  window.__inventory_items = state.items;
  return state.items;
}

function formatMoney(n) {
  const v = Number(n ?? 0);
  return v.toLocaleString(undefined, { style: 'currency', currency: 'USD' });
}

function formatItemPrice(item) {
  if (item?.is_product) {
    return item?.price != null ? formatMoney(item.price) : '—';
  }
  return item?.fifo_unit_cost_display || (item?.price != null ? formatMoney(item.price) : '—');
}

function toast(message, tone = 'ok') {
  const el = document.createElement('div');
  el.textContent = message;
  el.style.position = 'fixed';
  el.style.bottom = '20px';
  el.style.right = '20px';
  el.style.padding = '12px 14px';
  el.style.borderRadius = '10px';
  el.style.background = tone === 'error' ? '#5b1f1f' : '#1f3b2f';
  el.style.color = 'var(--fg)';
  el.style.boxShadow = '0 8px 20px rgba(0,0,0,0.4)';
  el.style.zIndex = '9999';
  document.body.appendChild(el);
  setTimeout(() => {
    el.style.opacity = '0';
    el.style.transition = 'opacity 0.3s ease';
    setTimeout(() => el.remove(), 300);
  }, 2000);
}

function formatOnHandDisplay(item) {
  if (item?.stock_on_hand_display) {
    return String(item.stock_on_hand_display);
  }
  if (item?.quantity_decimal != null && item?.uom) {
    return `${item.quantity_decimal} ${item.uom}`;
  }
  if (item?.quantity_display?.value != null && item?.quantity_display?.unit) {
    return `${item.quantity_display.value} ${item.quantity_display.unit}`;
  }
  return '—';
}

function renderTable(state) {
  const tbody = state.tableBody;
  tbody.innerHTML = '';
  state.items.forEach((item) => {
    const row = el('tr', { 'data-role': 'item-row', 'data-id': item.id });
    const vendorText = item.vendor?.name || item.vendor || '—';
    const priceText = formatItemPrice(item);
    row.append(
      el('td', { class: 'c', text: item.name || 'Item' }),
      el('td', { class: 'c', text: formatOnHandDisplay(item) }),
      el('td', { class: 'c', text: priceText }),
      el('td', { class: 'c', text: vendorText }),
      el('td', { class: 'c', text: item.location || '—' }),
    );
    tbody.append(row);
  });
}

function renderInventory(root, state) {
  renderTable(state);
}

async function adjustQuantity(itemId) {
  const deltaStr = prompt('Adjust quantity by (e.g. -2 or 5):');
  if (deltaStr === null) return;
  const delta = Number(deltaStr);
  if (!Number.isFinite(delta)) return alert('Enter a valid number');
  await ensureToken();
  await apiPost('/app/inventory/run', { inputs: {}, outputs: { [itemId]: delta } });
}

export async function _mountInventory(container) {
  await ensureToken();
  const state = { items: [], tableBody: null };

  function openStockOutModal(prefill) {
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    const card = document.createElement('div');
    card.className = 'modal-card';
    card.style.maxWidth = '420px';
    card.style.background = 'var(--surface)';
    card.style.border = '1px solid var(--border)';
    card.style.borderRadius = '10px';

    const title = document.createElement('div');
    title.className = 'modal-title';
    title.textContent = 'Stock Out (FIFO)';
    card.appendChild(title);

    const errorBanner = document.createElement('div');
    errorBanner.className = 'error-banner';
    errorBanner.hidden = true;
    card.appendChild(errorBanner);

    const body = document.createElement('div');
    body.className = 'modal-body';

    const itemRow = document.createElement('div');
    itemRow.className = 'field-row';
    const itemLabel = document.createElement('label');
    itemLabel.textContent = 'Item';
    const itemWrap = document.createElement('div');
    itemWrap.className = 'field-input';
    const itemSelect = document.createElement('select');
    itemSelect.required = true;
    (state.items || []).forEach((it) => {
      const opt = document.createElement('option');
      opt.value = it.id;
      opt.textContent = it.name || `Item #${it.id}`;
      opt.dataset.uom = it.uom || it.display_unit || 'ea';
      itemSelect.appendChild(opt);
    });
    if (prefill?.item_id) itemSelect.value = String(prefill.item_id);
    itemWrap.appendChild(itemSelect);
    itemRow.append(itemLabel, itemWrap);

    const qtyRow = document.createElement('div');
    qtyRow.className = 'field-row';
    const qtyLabel = document.createElement('label');
    qtyLabel.textContent = 'Quantity';
    const qtyWrap = document.createElement('div');
    qtyWrap.className = 'field-input';
    const qtyInput = document.createElement('input');
    qtyInput.type = 'number';
    qtyInput.min = '0.001';
    qtyInput.step = '0.001';
    qtyInput.value = prefill?.qty ? String(prefill.qty) : '1';
    qtyWrap.appendChild(qtyInput);
    qtyRow.append(qtyLabel, qtyWrap);

    const reasonRow = document.createElement('div');
    reasonRow.className = 'field-row';
    const reasonLabel = document.createElement('label');
    reasonLabel.textContent = 'Reason';
    const reasonWrap = document.createElement('div');
    reasonWrap.className = 'field-input';
    const reasonSelect = document.createElement('select');
    ['sold', 'loss', 'theft', 'other'].forEach((v) => {
      const opt = document.createElement('option');
      opt.value = v;
      opt.textContent = v.charAt(0).toUpperCase() + v.slice(1);
      reasonSelect.appendChild(opt);
    });
    reasonSelect.value = prefill?.reason || 'sold';
    reasonWrap.appendChild(reasonSelect);
    reasonRow.append(reasonLabel, reasonWrap);

    // Sale price (sold only)
    const priceRow = document.createElement('div');
    priceRow.className = 'field-row';
    const priceLabel = document.createElement('label');
    priceLabel.textContent = 'Sale unit price ($)';
    const priceInput = document.createElement('input');
    priceInput.type = 'number';
    priceInput.step = '0.01';
    priceInput.min = '0';
    priceInput.placeholder = '0.00';
    priceInput.value = '';
    priceRow.append(priceLabel, priceInput);

    const noteRow = document.createElement('div');
    noteRow.className = 'field-row';
    const noteLabel = document.createElement('label');
    noteLabel.textContent = 'Note (optional)';
    const noteWrap = document.createElement('div');
    noteWrap.className = 'field-input';
    const noteInput = document.createElement('input');
    noteInput.type = 'text';
    noteInput.placeholder = 'Order #, comment…';
    if (prefill?.note) noteInput.value = prefill.note;
    noteWrap.appendChild(noteInput);
    noteRow.append(noteLabel, noteWrap);

    const actions = document.createElement('div');
    actions.className = 'modal-actions';
    const cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.className = 'btn';
    cancelBtn.textContent = 'Cancel';
    const submitBtn = document.createElement('button');
    submitBtn.type = 'button';
    submitBtn.className = 'btn primary';
    submitBtn.textContent = 'Confirm Stock Out';
    actions.append(submitBtn, cancelBtn);

    body.append(itemRow, qtyRow, reasonRow, priceRow, noteRow, actions);
    card.appendChild(body);
    overlay.appendChild(card);
    overlay._inventoryCleanup = () => overlay.remove();
    document.body.appendChild(overlay);

    const close = () => overlay.remove();
    overlay.addEventListener('click', (ev) => {
      if (ev.target === overlay) close();
    });
    card.addEventListener('click', (ev) => ev.stopPropagation());
    cancelBtn.addEventListener('click', (ev) => { ev.preventDefault(); close(); });

    function updatePriceVisibility() {
      const reason = String(reasonSelect.value || 'sold');
      priceRow.style.display = (reason === 'sold') ? '' : 'none';
      if (reason === 'sold') {
        const itemId = Number(itemSelect.value || 0);
        const item = (window.__inventory_items || []).find((x) => Number(x.id) === itemId);
        if (item && priceInput.value === '') {
          const p = Number(item.price ?? 0);
          priceInput.value = Number.isFinite(p) ? String(p) : '';
        }
      }
    }

    itemSelect.addEventListener('change', updatePriceVisibility);
    reasonSelect.addEventListener('change', updatePriceVisibility);
    updatePriceVisibility();

    submitBtn.addEventListener('click', async (ev) => {
      ev.preventDefault();
      errorBanner.hidden = true;
      errorBanner.textContent = '';

      const itemId = Number(itemSelect.value);
      const qtyVal = String(decimalString(qtyInput.value));
      const reason = String(reasonSelect.value || 'sold');
      const note = noteInput.value ? noteInput.value : null;

      if (!Number.isInteger(itemId) || Number(qtyVal) <= 0) {
        errorBanner.textContent = 'Select an item and enter a positive quantity.';
        errorBanner.hidden = false;
        return;
      }

      try {
        await ensureToken();
        const payload = {
          item_id: itemId,
          quantity_decimal: qtyVal,
          uom: itemSelect.options[itemSelect.selectedIndex]?.dataset?.uom || 'ea',
          reason,
          note,
        };
        if (reason === 'sold') {
          payload.record_cash_event = true;
          const dollars = Number(priceInput.value ?? 0);
          payload.sell_unit_price_cents = Number.isFinite(dollars) ? Math.round(dollars * 100) : 0;
        }
        await canonical.stockOut(payload);
        close();
        await reloadInventory?.();
        alert('Stock out recorded.');
      } catch (e) {
        const detail = e?.payload?.detail;
        const shortages = detail?.shortages;
        const message = shortages ? `Insufficient stock:\n${JSON.stringify(shortages)}` : (detail || e?.message || 'Stock out failed');
        errorBanner.textContent = message;
        errorBanner.hidden = false;
      }
    });
  }

  function openRefundModal(state, onDone) {
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    const card = document.createElement('div');
    card.className = 'modal-card';
    card.style.maxWidth = '460px';
    card.style.background = 'var(--surface)';
    card.style.border = '1px solid var(--border)';
    card.style.borderRadius = '10px';

    const title = document.createElement('div');
    title.className = 'modal-title';
    title.textContent = 'Refund';
    card.appendChild(title);

    const errorBanner = document.createElement('div');
    errorBanner.className = 'error-banner';
    errorBanner.hidden = true;
    card.appendChild(errorBanner);

    const body = document.createElement('div');
    body.className = 'modal-body';

    const itemRow = document.createElement('div');
    itemRow.className = 'field-row';
    const itemLabel = document.createElement('label');
    itemLabel.textContent = 'Item';
    const itemWrap = document.createElement('div');
    itemWrap.className = 'field-input';
    const itemSelect = document.createElement('select');
    itemSelect.required = true;
    (state.items || []).forEach((it) => {
      const opt = document.createElement('option');
      opt.value = it.id;
      opt.textContent = it.name || `Item #${it.id}`;
      opt.dataset.uom = it.uom || it.display_unit || 'ea';
      itemSelect.appendChild(opt);
    });
    itemWrap.appendChild(itemSelect);
    itemRow.append(itemLabel, itemWrap);

    const qtyRow = document.createElement('div');
    qtyRow.className = 'field-row';
    const qtyLabel = document.createElement('label');
    qtyLabel.textContent = 'Quantity';
    const qtyWrap = document.createElement('div');
    qtyWrap.className = 'field-input';
    const qtyInput = document.createElement('input');
    qtyInput.type = 'number';
    qtyInput.min = '0.001';
    qtyInput.step = '0.001';
    qtyInput.value = '1';
    qtyWrap.appendChild(qtyInput);
    qtyRow.append(qtyLabel, qtyWrap);

    const amountRow = document.createElement('div');
    amountRow.className = 'field-row';
    const amountLabel = document.createElement('label');
    amountLabel.textContent = 'Refund amount ($)';
    const amountWrap = document.createElement('div');
    amountWrap.className = 'field-input';
    const amountInput = document.createElement('input');
    amountInput.type = 'number';
    amountInput.step = '0.01';
    amountInput.min = '0';
    amountInput.placeholder = '0.00';
    amountWrap.appendChild(amountInput);
    amountRow.append(amountLabel, amountWrap);

    const restockRow = document.createElement('div');
    restockRow.className = 'field-row';
    const restockLabel = document.createElement('label');
    restockLabel.textContent = 'Return to stock';
    const restockWrap = document.createElement('div');
    restockWrap.className = 'field-input';
    const restockInput = document.createElement('input');
    restockInput.type = 'checkbox';
    restockWrap.appendChild(restockInput);
    restockRow.append(restockLabel, restockWrap);

    const relatedRow = document.createElement('div');
    relatedRow.className = 'field-row';
    const relatedLabel = document.createElement('label');
    relatedLabel.textContent = 'Related source ID (optional)';
    const relatedWrap = document.createElement('div');
    relatedWrap.className = 'field-input';
    const relatedInput = document.createElement('input');
    relatedInput.type = 'text';
    relatedInput.placeholder = 'source_id from sale';
    relatedWrap.appendChild(relatedInput);
    relatedRow.append(relatedLabel, relatedWrap);

    const restockCostRow = document.createElement('div');
    restockCostRow.className = 'field-row';
    const restockCostLabel = document.createElement('label');
    restockCostLabel.textContent = 'Restock cost basis ($)';
    const restockCostWrap = document.createElement('div');
    restockCostWrap.className = 'field-input';
    const restockCostInput = document.createElement('input');
    restockCostInput.type = 'number';
    restockCostInput.step = '0.01';
    restockCostInput.min = '0';
    restockCostInput.placeholder = '0.00';
    restockCostWrap.appendChild(restockCostInput);
    restockCostRow.append(restockCostLabel, restockCostWrap);

    const actions = document.createElement('div');
    actions.className = 'modal-actions';
    const cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.className = 'btn';
    cancelBtn.textContent = 'Cancel';
    const submitBtn = document.createElement('button');
    submitBtn.type = 'button';
    submitBtn.className = 'btn primary';
    submitBtn.textContent = 'Submit Refund';
    actions.append(submitBtn, cancelBtn);

    body.append(itemRow, qtyRow, amountRow, restockRow, relatedRow, restockCostRow, actions);
    card.appendChild(body);
    overlay.appendChild(card);
    overlay._inventoryCleanup = () => overlay.remove();
    document.body.appendChild(overlay);

    const close = () => overlay.remove();
    overlay.addEventListener('click', (ev) => {
      if (ev.target === overlay) close();
    });
    card.addEventListener('click', (ev) => ev.stopPropagation());
    cancelBtn.addEventListener('click', (ev) => { ev.preventDefault(); close(); });

    function updateRestockVisibility() {
      const restock = restockInput.checked;
      const related = relatedInput.value.trim();
      restockCostRow.style.display = (restock && !related) ? '' : 'none';
    }

    restockInput.addEventListener('change', updateRestockVisibility);
    relatedInput.addEventListener('input', updateRestockVisibility);
    updateRestockVisibility();

    submitBtn.addEventListener('click', async (ev) => {
      ev.preventDefault();
      errorBanner.hidden = true;
      errorBanner.textContent = '';

      const itemId = Number(itemSelect.value);
      const quantityDecimal = String(decimalString(qtyInput.value));
      const refundDollars = Number(amountInput.value);
      const restockInventory = Boolean(restockInput.checked);
      const relatedSourceId = relatedInput.value.trim();

      if (!Number.isInteger(itemId) || Number(quantityDecimal) <= 0) {
        errorBanner.textContent = 'Select an item and enter a positive quantity.';
        errorBanner.hidden = false;
        return;
      }
      if (!Number.isFinite(refundDollars) || refundDollars <= 0) {
        errorBanner.textContent = 'Enter a positive refund amount.';
        errorBanner.hidden = false;
        return;
      }

      if (restockInventory && !relatedSourceId) {
        const restockDollars = Number(restockCostInput.value);
        if (!Number.isFinite(restockDollars) || restockDollars <= 0) {
          toast('Restock cost basis is required when returning to stock.', 'error');
          return;
        }
      }

      try {
        await ensureToken();
        const payload = {
          item_id: itemId,
          quantity_decimal: quantityDecimal,
          uom: itemSelect.options[itemSelect.selectedIndex]?.dataset?.uom || 'ea',
          refund_amount_cents: Math.round(refundDollars * 100),
          restock_inventory: restockInventory,
          related_source_id: relatedSourceId || null,
        };
        if (restockInventory && !relatedSourceId) {
          const restockDollars = Number(restockCostInput.value);
          payload.restock_unit_cost_cents = Math.round(restockDollars * 100);
        }
        await apiPost('/app/finance/refund', payload);
        toast('Refund recorded.');
        close();
        if (typeof onDone === 'function') await onDone();
      } catch (e) {
        const detail = e?.payload?.detail;
        errorBanner.textContent = detail || e?.message || 'Refund failed';
        errorBanner.hidden = false;
      }
    });
  }

  container.innerHTML = '';
  const root = container;
  const addBtn = el('button', { id: 'add-item-btn', class: 'btn', 'data-role': 'btn-add-item' }, '+ Add Item');
  const stockOutBtn = el('button', { class: 'btn secondary', type: 'button' }, '− Stock Out');
  const refundBtn = el('button', { class: 'btn' }, 'Refund');
  const controls = el('div', { class: 'inventory-controls toolbar' }, [
    addBtn,
    stockOutBtn,
    refundBtn,
  ]);
  stockOutBtn.addEventListener('click', () => openStockOutModal());
  refundBtn.addEventListener('click', () => openRefundModal(state, async () => {
    await fetchItems(state);
    renderInventory(root, state);
  }));
  const table = el('table', { id: 'inventory-table', class: 'table-clickable inventory-table' });
  const colgroup = el('colgroup');
  ['20%', '20%', '20%', '20%', '20%'].forEach((width) => {
    colgroup.append(el('col', { style: `width:${width}` }));
  });
  const thead = el('thead', {}, [
    el('tr', {}, [
      el('th', { text: 'Name' }),
      el('th', { text: 'Quantity' }),
      el('th', { text: 'Price' }),
      el('th', { text: 'Vendor' }),
      el('th', { text: 'Location' }),
    ]),
  ]);
  table.append(colgroup, thead, el('tbody'));
  container.append(controls, table);
  state.tableBody = table.querySelector('tbody');

  reloadInventory = async () => {
    await fetchItems(state);
    renderTable(state);
  };

  table.addEventListener('click', async (e) => {
    const btn = e.target.closest('button');
    const row = e.target.closest('tr[data-role="item-row"]');
    // Toggle details when clicking a row (but not on buttons)
    if (row && !btn) {
      const id = Number(row.getAttribute('data-id'));
      const item = state.items.find((it) => it.id === id);
      if (!item) return;
      await toggleDetailsRow(table, row, item);
      return;
    }
    if (!btn) return;
    const id = Number(btn.getAttribute('data-id')) || Number(btn.closest('[data-id]')?.getAttribute('data-id'));
    const action = btn.getAttribute('data-action');
    const item = state.items.find((it) => it.id === id);
    if (!item) return;
    if (action === 'edit') {
      openItemModal(item);
    }
    if (action === 'delete') {
      if (!(await confirmDelete())) return;
      await ensureToken();
      await apiDelete(`/app/items/${id}`);
      state.items = state.items.filter((it) => it.id !== id);
      renderTable(state);
    }
  });

  function kv(label, value) {
    return el('div', { class: 'kv' }, [ el('div', { class: 'k', text: label }), el('div', { class: 'v', text: value }) ]);
  }

  async function toggleDetailsRow(tableEl, rowEl, item) {
    if (rowEl.nextElementSibling && rowEl.nextElementSibling.classList.contains('row-details')) {
      rowEl.nextElementSibling.remove();
      return;
    }

    tableEl.querySelectorAll('.row-details').forEach((r) => r.remove());

    let detail = item;
    try {
      detail = await apiGetJson(`/app/items/${item.id}`);
      if (detail && typeof detail === 'object') {
        state.items = state.items.map((it) => (it.id === item.id ? { ...it, ...detail } : it));
      }
    } catch (err) {
      detail = { ...item, _error: err?.message || 'Unable to load details' };
    }

    const colCount = tableEl.querySelector('thead tr').children.length || rowEl.children.length;
    const priceText = formatItemPrice(detail);
    const kvNodes = [
      detail.sku ? kv('SKU', detail.sku) : null,
      kv('Vendor', detail.vendor || '—'),
      kv('Price', priceText),
      kv('Location', detail.location || '—'),
    ].filter(Boolean);

    const batchRows = (detail.batches_summary && detail.batches_summary.length)
      ? detail.batches_summary.map((b) => el('tr', {}, [
          el('td', { text: b.entered ? new Date(b.entered).toLocaleDateString() : '—' }),
          el('td', { text: `${b.remaining_int} / ${b.original_int}` }),
          el('td', { text: b.unit_cost_display || '—' }),
        ]))
      : [el('tr', {}, [el('td', { class: 'c', colspan: '3', text: 'No batches' })])];

    const batchTable = el('table', { class: 'subtable' }, [
      el('thead', {}, [
        el('tr', {}, [
          el('th', { text: 'Entered' }),
          el('th', { text: 'Remaining / Original' }),
          el('th', { text: 'Unit Cost' }),
        ]),
      ]),
      el('tbody', {}, batchRows),
    ]);

    const dimension = detail.dimension === 'weight' ? 'mass' : (detail.dimension || 'count');
    const displayUnit = detail.display_unit || (dimension === 'area'
      ? 'm2'
      : dimension === 'length'
        ? 'm'
        : dimension === 'mass'
          ? 'g'
          : dimension === 'volume'
            ? 'l'
            : 'ea');

    const details = el('tr', { class: 'row-details' }, [
      el('td', { colspan: String(colCount) }, [
        el('div', {
          class: 'details',
          'data-dimension': dimension,
          'data-display-unit': displayUnit,
        }, [
          kvNodes.length ? el('div', { class: 'grid' }, kvNodes) : null,
          detail.notes ? el('div', { class: 'notes', text: detail.notes }) : null,
          batchTable,
          detail._error ? el('div', { class: 'notes', text: detail._error }) : null,
          el('div', { class: 'row-actions' }, [
            el('button', { type: 'button', 'data-action': 'edit', 'data-id': item.id }, 'Edit'),
            el('button', { type: 'button', 'data-action': 'delete', 'data-id': item.id, class: 'danger' }, 'Delete'),
          ]),
        ]),
      ]),
    ]);

    rowEl.after(details);
    enhanceDetailsPanel(details.querySelector('.details'));
  }

  function confirmDelete() {
    // Keep UI simple; replace with nicer modal if desired
    return Promise.resolve(window.confirm('Delete this item? This cannot be undone.'));
  }

  bindDetailsObserver(container);
  await reloadInventory();
}

// ---- Expanded row normalization (unit-aware, loop-safe) ----
const _processedDetailsPanels = new WeakSet();
let _detailsObserverBound = false;

function enhanceDetailsPanel(panel) {
  if (!panel || _processedDetailsPanels.has(panel)) return;
  const unit = panel.dataset.displayUnit || 'ea';

  // Hide duplicate Price/Location rows (label + value)
  panel.querySelectorAll('.kv').forEach((kv) => {
    const label = (kv.querySelector('.k')?.textContent || '').trim().toLowerCase();
    if (label === 'price' || label === 'location') {
      kv.style.display = 'none';
    }
  });

  const nodes = panel.querySelectorAll('td, .td, .value, div, span, .v');

  // Convert first "X / Y" to display unit and add tooltip
  for (const n of nodes) {
    const s = (n.textContent || '').trim().replace(/,/g, '');
    const m = s.match(/^(-?\d+)\s*\/\s*(-?\d+)$/);
    if (!m) continue;
    const baseRemain = parseInt(m[1], 10);
    const baseOrig = parseInt(m[2], 10);
    if (Number.isNaN(baseRemain) || Number.isNaN(baseOrig)) continue;
    n.textContent = `${baseRemain} / ${baseOrig} ${unit}`;
    n.title = `${baseRemain.toLocaleString()} / ${baseOrig.toLocaleString()}`;
    break;
  }

  // Normalize money per unit
  for (const n of nodes) {
    const s = (n.textContent || '').trim().replace(/,/g, '');
    const m = s.match(/^\$?\s*([0-9.]+)\s*\/\s*([A-Za-z_²^2]+)\s*$/);
    if (!m) continue;
    const val = parseFloat(m[1]);
    const shownUnit = m[2].replace(/[²^2]/g, '2').toLowerCase();
    if (shownUnit === unit) {
      n.textContent = `$${fmtMoney(val)} / ${unit}`;
      break;
    }
    const converted = fromBaseUnitPrice(val, unit, dim);
    n.textContent = `$${fmtMoney(converted)} / ${unit}`;
    n.title = `${val} / ${shownUnit} (base)`;
    break;
  }

  // Notes block: constrain and avoid spill
  const noteEl = panel.querySelector('.notes');
  if (noteEl) {
    const txt = (noteEl.textContent || '').trim();
    const block = document.createElement('div');
    block.className = 'inv-note';
    block.style.cssText = 'margin:8px 0 10px; padding:8px 10px; border:1px solid rgba(36,48,65,.6); border-radius:8px; background:rgba(0,0,0,.12); color:#a9b7c8; max-width:70ch;';
    const h = document.createElement('div');
    h.textContent = 'Notes';
    h.style.cssText = 'font-weight:600; margin-bottom:4px; color:#e7eef7;';
    const p = document.createElement('div');
    p.textContent = txt;
    p.style.cssText = 'white-space:normal; overflow-wrap:anywhere;';
    block.append(h, p);
    noteEl.replaceWith(block);
  }

  _processedDetailsPanels.add(panel);
}

function bindDetailsObserver(root = document.getElementById('app') || document.body) {
  if (_detailsObserverBound) return;
  const observer = new MutationObserver((records) => {
    if (!location.hash.includes('/inventory')) return;
    records.forEach((r) => {
      r.addedNodes?.forEach((node) => {
        if (!(node instanceof HTMLElement)) return;
        if (node.matches?.('.details[data-dimension]')) enhanceDetailsPanel(node);
        node.querySelectorAll?.('.details[data-dimension]')?.forEach(enhanceDetailsPanel);
      });
    });
  });
  observer.observe(root, { childList: true, subtree: true });
  _detailsObserverBound = true;
  // initial scan
  (root.querySelectorAll?.('.details[data-dimension]') || []).forEach(enhanceDetailsPanel);
}

// ---------- Shallow/Deep Modal ----------
async function fetchVendors() {
  // Not specified in the SoT you've given me: exact vendor endpoint/shape.
  // Try /app/vendors first; fall back to /app/contacts.
  try {
    const v = await apiGetJson('/app/vendors?is_vendor=true');
    if (Array.isArray(v)) return v;
  } catch (_) {/* ignore */}
  try {
    const c = await apiGetJson('/app/contacts?is_vendor=true');
    if (Array.isArray(c)) {
      // Map into minimal { id, name } expected by dropdown
      return c.map(x => ({ id: x.id ?? x.contact_id ?? x.uuid ?? null, name: x.name ?? x.display ?? '—' }))
              .filter(x => x.id != null);
    }
  } catch (_) {/* ignore */}
  return [];
}

export function openItemModal(item = null) {
  const isEdit = !!(item && item.id);

  // Container (modal)
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  const card = document.createElement('div');
  card.className = 'modal-card';
  card.style.maxWidth = '460px';           // spec width
  card.style.background = 'var(--surface)';
  card.style.border = '1px solid var(--border)';
  card.style.borderRadius = '10px';

  const title = document.createElement('div');
  title.className = 'modal-title';
  title.textContent = (isEdit ? 'Edit' : 'Add') + ' Item';
  card.appendChild(title);

  const errorBanner = document.createElement('div');
  errorBanner.id = 'add-item-error';
  errorBanner.className = 'error-banner';
  errorBanner.hidden = true;
  card.appendChild(errorBanner);

  // FORM state
  let expanded = !!(item?.sku || item?.vendor_id || item?.notes);

  // Elements – Speed Surface
  const fName = inputRow('Name', 'text', item?.name ?? '', { autofocus: true });

  const unitSelect = createUnitSelect('item-unit');
  const unitRow = fieldRowWithElement('Unit', unitSelect);

  const qtyInput = document.createElement('input');
  qtyInput.type = 'number';
  qtyInput.id = 'item-qty-dec';
  qtyInput.setAttribute('step', '0.001');
  qtyInput.setAttribute('min', '0');
  qtyInput.required = true;
  const qtyChip = document.createElement('span');
  qtyChip.className = 'pill';
  qtyChip.textContent = '';
  const qtyWrap = document.createElement('div');
  qtyWrap.className = 'field-input';
  qtyWrap.style.display = 'flex';
  qtyWrap.style.alignItems = 'center';
  qtyWrap.style.gap = '8px';
  qtyWrap.append(qtyInput, qtyChip);
  const qtyRow = document.createElement('div');
  qtyRow.className = 'field-row';
  const qtyLabel = document.createElement('label');
  qtyLabel.textContent = 'Quantity';
  qtyRow.append(qtyLabel, qtyWrap);

  const qtyPreview = document.createElement('div');
  qtyPreview.id = 'item-qty-preview';
  qtyPreview.className = 'muted';

  const costInput = document.createElement('input');
  costInput.type = 'number';
  costInput.id = 'item-cost-dec';
  costInput.setAttribute('step', '0.01');
  costInput.setAttribute('min', '0');
  const costUnitSelect = createUnitSelect('item-cost-unit');
  const lockCostUnit = document.createElement('input');
  lockCostUnit.type = 'checkbox';
  lockCostUnit.id = 'item-lock-cost-unit';
  lockCostUnit.checked = true;
  const costUnitLockLabel = document.createElement('label');
  costUnitLockLabel.className = 'inline-check';
  costUnitLockLabel.htmlFor = 'item-lock-cost-unit';
  costUnitLockLabel.append(lockCostUnit, document.createTextNode('Lock cost to unit'));
  const costWrap = document.createElement('div');
  costWrap.className = 'field-input';
  costWrap.style.display = 'flex';
  costWrap.style.alignItems = 'center';
  costWrap.style.gap = '8px';
  const slash = document.createElement('span');
  slash.textContent = '/';
  costWrap.append(costInput, slash, costUnitSelect, costUnitLockLabel);
  const costRow = document.createElement('div');
  costRow.className = 'field-row';
  const costLabel = document.createElement('label');
  costLabel.textContent = 'Cost';
  costRow.append(costLabel, costWrap);

  const isProductInput = document.createElement('input');
  isProductInput.type = 'checkbox';
  isProductInput.id = 'item-is-product';
  const productLabel = document.createElement('label');
  productLabel.className = 'inline-check';
  productLabel.htmlFor = 'item-is-product';
  productLabel.append(isProductInput, document.createTextNode('This is a product (use fixed price)'));
  const productRow = fieldRowWithElement('', productLabel);
  productRow.classList.add('inline-row');

  const fPrice = inputRow('Price', 'number', item?.price ?? '', { step: '0.01', min: '0' });
  const priceInput = fPrice.querySelector('input');
  if (priceInput) priceInput.id = 'item-price-dec';
  const fLocation = inputRow('Location', 'text', item?.location ?? '');

  let addBatchToggleRow = null;
  let addBatchToggle = null;
  let batchFields = null;
  let addBatchBtnRow = null;
  let addBatchBtn = null;

  if (!isEdit) {
    addBatchToggle = document.createElement('input');
    addBatchToggle.type = 'checkbox';
    addBatchToggle.id = 'item-add-batch';
    addBatchToggle.checked = true;
    const addBatchLabel = document.createElement('label');
    addBatchLabel.className = 'inline-check';
    addBatchLabel.htmlFor = 'item-add-batch';
    addBatchLabel.append(addBatchToggle, document.createTextNode('Add opening batch now'));
    addBatchToggleRow = fieldRowWithElement('', addBatchLabel);
    addBatchToggleRow.classList.add('inline-row');

    batchFields = document.createElement('div');
    batchFields.id = 'field-batch';
    batchFields.append(qtyRow, costRow, qtyPreview);
  }

  if (isEdit && item?.id) {
    addBatchBtnRow = document.createElement('div');
    addBatchBtnRow.className = 'field-row';
    const spacer = document.createElement('label');
    spacer.textContent = '';
    const wrap = document.createElement('div');
    wrap.className = 'field-input';
    addBatchBtn = document.createElement('button');
    addBatchBtn.type = 'button';
    addBatchBtn.className = 'btn';
    addBatchBtn.textContent = 'Add Batch';
    wrap.appendChild(addBatchBtn);
    addBatchBtnRow.append(spacer, wrap);
  }

  // Elements – Hinge
  const hinge = document.createElement('button');
  hinge.type = 'button';
  hinge.className = 'link';
  hinge.textContent = '+ Add Details (SKU, Vendor, Notes)';
  hinge.style.margin = '8px 0';

  // Elements – Ledger Surface (hidden by default)
  const ledger = document.createElement('div');
  ledger.style.display = expanded ? 'block' : 'none';
  const fSku = inputRow('SKU', 'text', item?.sku ?? '');

  const vendorRow = document.createElement('div');
  vendorRow.className = 'field-row';
  const vendorLabel = document.createElement('label');
  vendorLabel.textContent = 'Vendor';
  vendorRow.appendChild(vendorLabel);
  const vendorInputWrap = document.createElement('div');
  vendorInputWrap.className = 'field-input';
  const vendorSelect = document.createElement('select');
  vendorSelect.style.width = '100%';
  vendorSelect.innerHTML = '<option value="">—</option>';
  vendorInputWrap.appendChild(vendorSelect);
  vendorRow.appendChild(vendorInputWrap);

  const typeRow = document.createElement('div');
  typeRow.className = 'field-row';
  const typeLabel = document.createElement('label');
  typeLabel.textContent = 'Item Type';
  const typeWrap = document.createElement('div');
  typeWrap.className = 'field-input';
  const typeSelect = document.createElement('select');
  typeSelect.innerHTML = `
    <option value="Product">Product</option>
    <option value="Material">Material</option>
    <option value="Component">Component</option>`;
  typeSelect.value = item?.type ?? 'Product';
  typeWrap.appendChild(typeSelect);
  typeRow.append(typeLabel, typeWrap);

  const notesRow = document.createElement('div');
  notesRow.className = 'field-row';
  const notesLabel = document.createElement('label');
  notesLabel.textContent = 'Notes';
  const notesWrap = document.createElement('div');
  notesWrap.className = 'field-input';
  const notes = document.createElement('textarea');
  notes.rows = 2;
  notes.value = item?.notes ?? '';
  notesWrap.appendChild(notes);
  notesRow.append(notesLabel, notesWrap);

  ledger.append(fSku, vendorRow, typeRow, notesRow);

  // Footer (Save/Cancel) – always visible
  const footer = document.createElement('div');
  footer.className = 'modal-actions';
  const saveBtn = document.createElement('button');
  saveBtn.type = 'button';
  saveBtn.className = 'btn primary';
  saveBtn.textContent = 'Save';
  const cancelBtn = document.createElement('button');
  cancelBtn.type = 'button';
  cancelBtn.className = 'btn';
  cancelBtn.textContent = 'Cancel';
  footer.append(saveBtn, cancelBtn);

  // Assemble card
  const content = document.createElement('div');
  content.className = 'modal-body';
  const divider = document.createElement('hr');
  divider.className = 'thin';

  content.append(fName, unitRow, productRow, fPrice, divider);
  if (addBatchToggleRow) content.append(addBatchToggleRow);
  if (batchFields) {
    content.append(batchFields);
  } else {
    content.append(qtyRow, costRow, qtyPreview);
  }
  if (addBatchBtnRow) content.append(addBatchBtnRow);
  content.append(fLocation, hinge, ledger, footer);
  card.appendChild(content);
  overlay.appendChild(card);
  document.body.appendChild(overlay);

  // Auto-focus and prefill qty badge if editing
  fName.querySelector('input')?.focus();
  initAddItemFormDefaults();

  const populateVendors = (vendorsList, selectedId = null) => {
    vendorSelect.innerHTML = '<option value="">—</option>';
    vendorsList.forEach(v => {
      const opt = document.createElement('option');
      opt.value = v.id;
      opt.textContent = v.name ?? `#${v.id}`;
      vendorSelect.appendChild(opt);
    });
    const createOpt = document.createElement('option');
    createOpt.value = '__create__';
    createOpt.textContent = 'Create new vendor…';
    vendorSelect.appendChild(createOpt);
    if (selectedId) {
      vendorSelect.value = String(selectedId);
    } else if (item?.vendor_id) {
      vendorSelect.value = String(item.vendor_id);
    }
  };

  const onContactSaved = async (ev) => {
    const saved = ev.detail;
    if (!saved?.id || !saved.is_vendor) return;
    const refreshed = await fetchVendors();
    if (!Array.isArray(refreshed) || !refreshed.length) return;
    populateVendors(refreshed, saved.id);
  };

  vendorSelect.addEventListener('change', () => {
    if (vendorSelect.value === '__create__') {
      window.dispatchEvent(new CustomEvent('open-contacts-modal', { detail: { prefill: { is_vendor: true, is_org: true } } }));
      vendorSelect.value = '';
    }
  });

  function currentDimension() {
    return dimensionForUnit(unitSelect.value || costUnitSelect.value) || 'count';
  }


  function serverErrorMessage(err) {
    if (err?.detail?.error === 'validation_error') {
      const fields = err.detail.fields || {};
      const parts = Object.entries(fields).map(([k, v]) => `${k}: ${v}`);
      if (parts.length) return parts.join(' • ');
    }
    return err?.detail?.message || err?.message || err?.error || 'Error';
  }

  function updatePreview() {
    if (addBatchToggle && !addBatchToggle.checked) {
      qtyPreview.textContent = '';
      return;
    }
    const unit = unitSelect.value;
    const priceUnitSel = lockCostUnit.checked ? unit : (costUnitSelect.value || unit);
    const val = qtyInput.value;
    if (!unit || val === '') {
      qtyPreview.textContent = '';
      return;
    }
    const qtyShow = decimalString(val || 0);
    const priceShow = decimalString(costInput?.value || 0);
    if (priceUnitSel !== unit) {
      qtyPreview.textContent = 'Cost unit must match item unit for opening batch.';
      return;
    }
    qtyPreview.textContent = `Will send: ${qtyShow} ${unit} @ ${priceShow} / ${unit}`;
  }

  function syncUnitState() {
    qtyChip.textContent = unitSelect.value || '';
    if (lockCostUnit.checked) {
      costUnitSelect.value = unitSelect.value;
      costUnitSelect.disabled = true;
    } else {
      costUnitSelect.disabled = false;
    }
    updatePreview();
  }

  function syncProductPriceVisibility() {
    if (!priceInput) return;
    const showPrice = isProductInput.checked;
    fPrice.hidden = !showPrice;
    priceInput.disabled = !showPrice;
    priceInput.required = showPrice;
  }

  function syncBatchVisibility() {
    const showBatch = addBatchToggle ? addBatchToggle.checked : true;
    if (batchFields) batchFields.hidden = !showBatch;
    qtyRow.hidden = batchFields ? !showBatch : false;
    if (costRow && batchFields) costRow.hidden = !showBatch;
    qtyPreview.style.display = showBatch ? 'block' : 'none';
    qtyInput.required = isEdit ? true : showBatch;
  }

  function initAddItemFormDefaults() {
    const defaultUnitGuess = () => {
      const american = !!(window.BUS_UNITS && window.BUS_UNITS.american);
      const defaults = american ? DIM_DEFAULTS_IMPERIAL : DIM_DEFAULTS_METRIC;
      const dim = item?.dimension || 'count';
      return defaults[dim] || defaults.count || 'ea';
    };
    const initialUnit = item?.display_unit || item?.uom || item?.unit || item?.quantity_display?.unit || defaultUnitGuess();
    populateUnitOptions(unitSelect, initialUnit);
    populateUnitOptions(costUnitSelect, initialUnit);
    qtyChip.textContent = unitSelect.value;
    costUnitSelect.value = unitSelect.value;
    costUnitSelect.disabled = lockCostUnit.checked;
    const qtyVal = item?.quantity_display?.value ?? (item?.qty ?? '');
    if (qtyVal !== undefined && qtyVal !== null) qtyInput.value = qtyVal;
    if (isProductInput) {
      isProductInput.checked = !!item?.is_product;
      if (priceInput && item?.price != null) priceInput.value = item.price;
      syncProductPriceVisibility();
    }
    if (addBatchToggle) {
      addBatchToggle.checked = true;
      if (costInput) costInput.value = '';
    }
    syncBatchVisibility();
    syncUnitState();
  }

  // Load vendors (async)
  (async () => {
    const vs = await fetchVendors();
    if (!vs.length) {
      vendorSelect.replaceWith(helpLinkToVendors());
      return;
    }
    populateVendors(vs);
    window.addEventListener('contacts:saved', onContactSaved);
  })();

  // Hinge toggle
  hinge.addEventListener('click', () => {
    expanded = !expanded;
    ledger.style.display = expanded ? 'block' : 'none';
    hinge.textContent = expanded ? '– Hide Details' : '+ Add Details (SKU, Vendor, Notes)';
  });

  // Guard against backdrop click + ESC closing; only Cancel closes
  const escBlocker = (e) => {
    if (e.key === 'Escape') {
      e.stopPropagation();
      e.preventDefault();
    }
  };
  document.addEventListener('keydown', escBlocker, true);

  const cleanup = () => {
    window.removeEventListener('contacts:saved', onContactSaved);
    document.removeEventListener('keydown', escBlocker, true);
    document.removeEventListener('bus:units-mode', onUnitsMode);
  };

  const closeModalSafely = () => {
    cleanup();
    closeStockInModal();
    overlay.remove();
  };

  overlay._inventoryCleanup = closeModalSafely;

  cancelBtn.addEventListener('click', (e) => {
    e.preventDefault();
    closeModalSafely();
  });
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) {
      e.stopPropagation();
    }
  }, true);
  card.addEventListener('click', (e) => e.stopPropagation());

  unitSelect.addEventListener('change', () => syncUnitState());
  costUnitSelect.addEventListener('change', () => { if (!lockCostUnit.checked) updatePreview(); });
  lockCostUnit.addEventListener('change', () => {
    costUnitSelect.disabled = lockCostUnit.checked;
    if (lockCostUnit.checked) costUnitSelect.value = unitSelect.value;
    updatePreview();
  });
  qtyInput.addEventListener('input', () => updatePreview());
  if (addBatchToggle) addBatchToggle.addEventListener('change', () => { syncBatchVisibility(); updatePreview(); });
  isProductInput.addEventListener('change', () => { syncProductPriceVisibility(); updatePreview(); });
  if (addBatchBtn) addBatchBtn.addEventListener('click', () => openStockInModal());

  const onUnitsMode = () => {
    populateUnitOptions(unitSelect, unitSelect.value);
    populateUnitOptions(costUnitSelect, costUnitSelect.value);
    syncUnitState();
  };
  document.addEventListener('bus:units-mode', onUnitsMode);

  function fieldValue(rowSel) {
    return rowSel.querySelector('input,textarea,select')?.value ?? '';
  }

  function fieldRowWithElement(labelText, element) {
    const row = document.createElement('div');
    row.className = 'field-row';
    const label = document.createElement('label');
    label.textContent = labelText;
    const wrap = document.createElement('div');
    wrap.className = 'field-input';
    if (element) wrap.appendChild(element);
    row.append(label, wrap);
    return row;
  }

  function createSelect(id, options = []) {
    const select = document.createElement('select');
    if (id) select.id = id;
    select.required = true;
    options.forEach(([value, text]) => {
      const opt = document.createElement('option');
      opt.value = value;
      opt.textContent = text;
      select.appendChild(opt);
    });
    return select;
  }

  function populateUnitOptions(select, preset) {
    const american = !!(window.BUS_UNITS && window.BUS_UNITS.american);
    const groups = unitOptionsList({ american });
    const current = preset || select.value;
    select.innerHTML = '';
    groups.forEach((group) => {
      const og = document.createElement('optgroup');
      og.label = group.label;
      group.units.forEach((u) => {
        const opt = document.createElement('option');
        opt.value = u;
        opt.textContent = u.replace('_', '-');
        og.appendChild(opt);
      });
      select.appendChild(og);
    });
    if (current && select.querySelector(`option[value="${current}"]`)) {
      select.value = current;
    } else if (!select.value) {
      const fallbackDim = dimensionForUnit(current) || 'count';
      const defaults = american ? DIM_DEFAULTS_IMPERIAL : DIM_DEFAULTS_METRIC;
      const target = defaults[fallbackDim] || defaults.count || 'ea';
      if (select.querySelector(`option[value="${target}"]`)) {
        select.value = target;
      } else if (select.options.length) {
        select.selectedIndex = 0;
      }
    }
  }

  function createUnitSelect(id) {
    const select = document.createElement('select');
    if (id) select.id = id;
    select.required = true;
    populateUnitOptions(select);
    return select;
  }

  function inputRow(labelText, type, value = '', attrs = {}) {
    const row = document.createElement('div');
    row.className = 'field-row';
    const label = document.createElement('label');
    label.textContent = labelText;
    const wrap = document.createElement('div');
    wrap.className = 'field-input';
    const input = document.createElement(type === 'textarea' ? 'textarea' : 'input');
    if (type !== 'textarea') input.type = type;
    input.value = value;
    Object.entries(attrs).forEach(([k, v]) => { if (v != null) input.setAttribute(k, v); });
    wrap.appendChild(input);
    row.append(label, wrap);
    return row;
  }

  function helpLinkToVendors() {
    const a = document.createElement('a');
    a.href = '#/contacts';
    a.textContent = 'No vendors found. Go to Vendors.';
    a.className = 'link';
    return a;
  }

  let stockInOverlay = null;

  function closeStockInModal() {
    if (stockInOverlay) {
      stockInOverlay.remove();
      stockInOverlay = null;
    }
  }

  function openStockInModal() {
    if (!item?.id) return;
    closeStockInModal();

    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    const card = document.createElement('div');
    card.className = 'modal-card';
    card.style.maxWidth = '420px';
    card.style.background = 'var(--surface)';
    card.style.border = '1px solid var(--border)';
    card.style.borderRadius = '10px';

    const title = document.createElement('div');
    title.className = 'modal-title';
    title.textContent = 'Add Batch';
    card.appendChild(title);

    const stockError = document.createElement('div');
    stockError.className = 'error-banner';
    stockError.hidden = true;
    card.appendChild(stockError);

    const body = document.createElement('div');
    body.className = 'modal-body';

    const stockUnitSelect = createSelect('stockin-unit');
    const dim = item.dimension || 'count';
    const unitOptions = [...(UNIT_OPTIONS[dim] || ['ea'])];
    if (item.uom && !unitOptions.includes(item.uom)) unitOptions.push(item.uom);
    stockUnitSelect.innerHTML = unitOptions.map((u) => `<option value="${u}">${UNIT_LABEL[u] || u}</option>`).join('');
    stockUnitSelect.value = item.uom && unitOptions.includes(item.uom) ? item.uom : unitOptions[0];
    const stockUnitRow = fieldRowWithElement('Unit', stockUnitSelect);

    const stockQtyInput = document.createElement('input');
    stockQtyInput.type = 'number';
    stockQtyInput.setAttribute('step', '0.001');
    stockQtyInput.setAttribute('min', '0');
    const stockQtyRow = fieldRowWithElement('Quantity', stockQtyInput);

    const stockCostInput = document.createElement('input');
    stockCostInput.type = 'number';
    stockCostInput.setAttribute('step', '0.01');
    stockCostInput.setAttribute('min', '0');
    const stockCostRow = fieldRowWithElement('Unit Cost', stockCostInput);

    const stockActions = document.createElement('div');
    stockActions.className = 'modal-actions';
    const stockSave = document.createElement('button');
    stockSave.type = 'button';
    stockSave.className = 'btn primary';
    stockSave.textContent = 'Save Batch';
    const stockCancel = document.createElement('button');
    stockCancel.type = 'button';
    stockCancel.className = 'btn';
    stockCancel.textContent = 'Cancel';
    stockActions.append(stockSave, stockCancel);

    body.append(stockUnitRow, stockQtyRow, stockCostRow, stockActions);
    card.appendChild(body);
    overlay.appendChild(card);
    overlay._inventoryCleanup = closeStockInModal;
    document.body.appendChild(overlay);

    overlay.addEventListener('click', (ev) => {
      if (ev.target === overlay) closeStockInModal();
    });
    card.addEventListener('click', (ev) => ev.stopPropagation());

    stockCancel.addEventListener('click', (ev) => {
      ev.preventDefault();
      closeStockInModal();
    });

    async function submitStockIn() {
      if (stockError) {
        stockError.hidden = true;
        stockError.textContent = '';
      }

      if (stockQtyInput.value === '') {
        stockError.textContent = 'Enter a quantity to stock in.';
        stockError.hidden = false;
        return;
      }

      const qtyDecimal = decimalString(stockQtyInput.value);
      const unitCost = stockCostInput.value === '' ? undefined : Math.round(Number(stockCostInput.value) * 100);
      const payload = {
        item_id: item.id,
        uom: stockUnitSelect.value,
        quantity_decimal: qtyDecimal,
        unit_cost_cents: Number.isFinite(unitCost) ? unitCost : undefined,
      };

      try {
        await ensureToken();
        await canonical.stockIn(payload);
        closeStockInModal();
        await reloadInventory?.();
      } catch (err) {
        const msg = serverErrorMessage(err) || 'Stock-in failed.';
        if (stockError) {
          stockError.textContent = msg;
          stockError.hidden = false;
        }
      }
    }

    stockSave.addEventListener('click', async (ev) => {
      ev.preventDefault();
      await submitStockIn();
    });

    stockInOverlay = overlay;
  }

  function markInvalid(el) {
    el.style.borderColor = '#ef4444';
    setTimeout(() => { el.style.borderColor = 'var(--border)'; }, 1500);
  }

  // Save handler (works in collapsed or expanded)
  saveBtn.addEventListener('click', async (e) => {
    e.preventDefault();
    const name = fieldValue(fName).trim();

    if (errorBanner) {
      errorBanner.hidden = true;
      errorBanner.textContent = '';
    }

    // Client-side validation
    if (!name) return markInvalid(fName.querySelector('input'));

    const unitVal = unitSelect.value;
    const priceUnitSel = lockCostUnit.checked ? unitVal : (costUnitSelect.value || unitVal);
    const qtyVal = qtyInput.value;
    const addOpeningBatch = addBatchToggle ? addBatchToggle.checked : false;
    const dimensionVal = currentDimension();

    if (!unitVal) return markInvalid(unitSelect);
    if ((isEdit || addOpeningBatch) && qtyVal === '') return markInvalid(qtyInput);

    const priceVal = (() => {
      const parsed = priceInput ? parseFloat(priceInput.value) : parseFloat(fieldValue(fPrice));
      if (Number.isFinite(parsed)) return parsed;
      if (item?.price != null) return item.price;
      return 0;
    })();

    const payload = {
      name,
      sku: (fieldValue(fSku) || '').trim() || undefined,
      vendor_id: vendorSelect && vendorSelect.tagName === 'SELECT' ? (vendorSelect.value || undefined) : undefined,
      location: (fieldValue(fLocation) || '').trim() || undefined,
      type: (expanded ? fieldValue(typeRow) : 'Product') || 'Product',
      notes: expanded ? (notes.value.trim() || undefined) : undefined,
      dimension: dimensionVal,
      uom: unitVal,
      unit: unitVal,
      display_unit: unitVal,
      is_product: isProductInput.checked,
      quantity_decimal: isEdit ? qtyVal : '0',
    };

    if (isProductInput.checked) {
      payload.price_decimal = priceInput?.value ?? String(priceVal ?? 0);
      payload.price = priceVal;
    }

    const url = isEdit ? `/items/${item.id}` : '/items';
    const method = isEdit ? apiPut : apiPost;
    try {
      await ensureToken();
      const savedItem = await method(url, payload, { headers: { 'Content-Type': 'application/json' } });

      if (!isEdit && addOpeningBatch) {
        if (!qtyVal || Number(qtyVal) <= 0) {
          const msg = 'Quantity required for opening batch.';
          if (errorBanner) {
            errorBanner.textContent = msg;
            errorBanner.hidden = false;
          }
          return;
        }

        if (priceUnitSel !== unitVal) {
          const msg = 'Opening batch cost unit must match item unit.';
          if (errorBanner) {
            errorBanner.textContent = msg;
            errorBanner.hidden = false;
          }
          markInvalid(costUnitSelect);
          return;
        }

        const unitCostCents = Math.round(Number(costInput?.value || 0) * 100);
        const stockPayload = {
          item_id: savedItem?.id,
          uom: unitVal,
          quantity_decimal: decimalString(qtyVal),
          unit_cost_cents: Number.isFinite(unitCostCents) ? unitCostCents : undefined,
        };

        try {
          await ensureToken();
          await canonical.stockIn(stockPayload);
        } catch (err) {
          const msg = serverErrorMessage(err);
          if (errorBanner) {
            errorBanner.textContent = msg;
            errorBanner.hidden = false;
          }
          markInvalid(saveBtn);
          return;
        }
      }

      closeModalSafely();
      reloadInventory?.(); // existing function in this module to refresh table
    } catch (err) {
      const serverMsg = err?.detail?.message || err?.error || err?.message || 'Save failed.';
      if (errorBanner) {
        errorBanner.textContent = serverMsg;
        errorBanner.hidden = false;
      }
      markInvalid(saveBtn);
    }
  });
}
