// SPDX-License-Identifier: AGPL-3.0-or-later
import { apiGet, ensureToken } from '../api.js';
import { RecipesAPI } from '../api/recipes.js';

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  Object.entries(attrs).forEach(([k, v]) => {
    if (v == null) return;
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

let _items = [];
let _recipes = [];
let _activeId = null;
let _draft = null;

const UOMS_BY_DIMENSION = {
  length: ['mm', 'cm', 'm'],
  area: ['mm2', 'cm2', 'm2'],
  volume: ['mm3', 'cm3', 'ml', 'l', 'm3'],
  weight: ['mg', 'g', 'kg'],
  count: ['ea'],
};

function findItem(itemId) {
  return _items.find((i) => String(i.id) === String(itemId));
}

function decimalString(v) {
  const s = String(v ?? '').trim().replace(/,/g, '');
  if (s === '' || s === '.' || s === '-.') return '0';
  return s.startsWith('.') ? `0${s}` : s;
}

function scaleDecimalString(value, factor) {
  const n = Number(String(value ?? '').trim());
  if (!Number.isFinite(n)) return decimalString(value);
  return decimalString(String(n * factor));
}

function toUiCountUom(uom) {
  return String(uom || '').trim().toLowerCase() === 'mc' ? 'ea' : String(uom || '').trim();
}

function toUiCountQuantity(quantityDecimal, uom) {
  return String(uom || '').trim().toLowerCase() === 'mc'
    ? scaleDecimalString(quantityDecimal, 1 / 1000)
    : String(quantityDecimal ?? '');
}

function normalizeDimension(dim) {
  const d = String(dim || '').trim().toLowerCase();
  if (d === 'mass') return 'weight';
  return d;
}

function uomOptionsForItem(item) {
  const dim = normalizeDimension(item?.dimension) || 'count';
  const options = [...(UOMS_BY_DIMENSION[dim] || ['ea'])];
  const itemUom = toUiCountUom(item?.uom);
  if (itemUom && !options.includes(itemUom)) options.unshift(itemUom);
  return options;
}

function setSelectOptions(selectEl, options, selectedValue, placeholder = null) {
  selectEl.innerHTML = '';
  if (placeholder !== null) {
    selectEl.append(el('option', { value: '' }, placeholder));
  }
  options.forEach((u) => {
    const label = u === 'mc' ? 'mc (1/1000 ea)' : u;
    selectEl.append(el('option', { value: u }, label));
  });

  if (selectedValue && options.includes(selectedValue)) {
    selectEl.value = selectedValue;
  } else if (placeholder !== null) {
    selectEl.value = '';
  } else if (options.length) {
    selectEl.value = options[0];
  }
}

function isStrictPositiveDecimal(value) {
  const raw = String(value ?? '').trim().replace(/,/g, '');
  if (!raw) return false;
  if (!/^(?:\d+|\d*\.\d+)$/.test(raw)) return false;
  const n = Number(raw);
  return Number.isFinite(n) && n > 0;
}

function formatRecipeError(e) {
  const data = e?.data ?? e?.payload ?? {};
  const detail = data?.detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => d?.msg || d?.message || JSON.stringify(d)).join(' | ');
  }
  if (detail && typeof detail === 'object') {
    if (detail.error && detail.keys) return `${detail.error}: ${detail.keys.join(', ')}`;
    if (detail.error) return String(detail.error);
    if (detail.message) return String(detail.message);
    return JSON.stringify(detail);
  }
  if (typeof detail === 'string') return detail;
  return e?.message || 'Save failed';
}

function newRecipeDraft() {
  return {
    id: null,
    name: '',
    output_item_id: null,
    quantity_decimal: '1',
    uom: '',
    archived: false,
    notes: '',
    items: [],
  };
}

function blankRecipeItem(sort = 0) {
  return {
    item_id: null,
    quantity_decimal: '',
    uom: '',
    optional: false,
    sort,
  };
}

function normalizeRecipe(data) {
  const outputUomRaw = data.uom || '';
  const outputUomUi = toUiCountUom(outputUomRaw);
  return {
    id: data.id,
    name: data.name || '',
    output_item_id: data.output_item_id ?? null,
    quantity_decimal: data.quantity_decimal ? toUiCountQuantity(String(data.quantity_decimal), outputUomRaw) : '1',
    uom: outputUomUi || '',
    archived: data.archived === true || data.is_archived === true,
    notes: data.notes || '',
    items: (data.items || []).map((it, idx) => ({
      item_id: it.item_id ?? null,
      quantity_decimal: it.quantity_decimal != null ? toUiCountQuantity(String(it.quantity_decimal), it.uom || it.item?.uom) : '',
      uom: toUiCountUom(it.uom || (it.item?.uom || '')),
      optional: it.optional === true || it.is_optional === true,
      sort: Number.isFinite(it.sort ?? it.sort_order) ? (it.sort ?? it.sort_order) : idx,
    })),
  };
}

async function refreshData() {
  _items = await apiGet('/app/items');
  _recipes = await RecipesAPI.list();
  window.__recipes = _recipes;
}

function handleRecipesDeepLink(listPanel, editorPanel) {
  const r = window.BUS_ROUTE;
  if (!r || r.base !== '#/recipes' || !r.id) return;
  const id = String(r.id);

  const list = window.__recipes || _recipes || [];
  const it = (list || []).find((x) => String(x?.id) === id);

  if (it) {
    _activeId = it.id;
    _draft = normalizeRecipe(it);
    renderList(listPanel, editorPanel);
    renderEditor(editorPanel, listPanel);
  } else {
    alert(`Recipe not found: ${id}`);
    window.location.hash = '#/recipes';
  }

  window.BUS_ROUTE = { ...r, id: null };
}

export async function mountRecipes() {
  await ensureToken();
  const container = document.querySelector('[data-tab-panel="recipes"]');
  if (!container) return;
  container.innerHTML = '';
  container.classList.add('recipes-shell');

  try {
    await refreshData();
  } catch {
    container.textContent = 'Failed to load recipes.';
    return;
  }

  const grid = el('div', { class: 'recipes-grid' });
  const listPanel = el('div', { class: 'card recipes-list-panel' });
  const editorPanel = el('div', { class: 'card recipes-editor-panel' });

  grid.append(listPanel, editorPanel);
  container.append(grid);

  renderList(listPanel, editorPanel);
  renderEmpty(editorPanel);
  handleRecipesDeepLink(listPanel, editorPanel);
}

export function unmountRecipes() {
  _items = [];
  _recipes = [];
  _activeId = null;
  _draft = null;
  const container = document.querySelector('[data-tab-panel="recipes"]');
  if (container) container.innerHTML = '';
}

function renderList(container, editor) {
  container.innerHTML = '';

  const header = el('div', { class: 'recipes-list-header' }, [
    el('h2', { class: 'recipes-list-title', text: 'Recipes' }),
    el('button', { class: 'btn primary small recipes-new-btn', text: '+ New' }),
  ]);
  header.lastChild.onclick = () => {
    _activeId = null;
    _draft = newRecipeDraft();
    renderEditor(editor, container);
  };

  const search = el('input', {
    type: 'search',
    class: 'recipes-filter-input',
    placeholder: 'Filter...',
  });
  const list = el('div', { class: 'recipes-list' });

  const paint = (term = '') => {
    list.innerHTML = '';
    const q = term.trim().toLowerCase();
    _recipes
      .filter((r) => !q || String(r.name || '').toLowerCase().includes(q))
      .forEach((r) => {
        const row = el('div', { class: 'recipe-row' }, [
          el('span', { class: 'recipe-row-name', text: r.name }),
          el('span', { class: 'recipe-row-arrow', text: '→' }),
        ]);
        if (r.id === _activeId) row.classList.add('active');
        row.onclick = async () => {
          _activeId = r.id;
          _draft = normalizeRecipe(await RecipesAPI.get(r.id));
          renderEditor(editor, container);
        };
        list.append(row);
      });
  };

  search.addEventListener('input', (e) => paint(e.target.value));
  paint();
  container.append(header, search, list);
}

function renderEmpty(editor) {
  editor.innerHTML = '';
  editor.append(el('div', { class: 'recipes-empty', text: 'Select a recipe to edit.' }));
}

function setStatus(statusEl, text = '', tone = 'neutral') {
  statusEl.textContent = text;
  statusEl.dataset.tone = tone;
}

function renderEditor(editor, leftPanel) {
  editor.innerHTML = '';
  if (!_draft) {
    renderEmpty(editor);
    return;
  }

  const status = el('div', { class: 'recipes-status', 'data-tone': 'neutral' });

  const nameRow = el('div', { class: 'recipes-row' });
  const nameInput = el('input', {
    type: 'text',
    class: 'recipes-input recipes-input--grow',
    value: _draft.name,
  });
  nameInput.addEventListener('input', () => { _draft.name = nameInput.value; });
  nameRow.append(el('label', { class: 'recipes-row-label', text: 'Name' }), nameInput);

  const outputRow = el('div', { class: 'recipes-row recipes-row--wrap' });
  const outSel = el('select', { id: 'recipe-output', class: 'recipes-input recipes-input--grow' });
  outSel.append(el('option', {
    value: '',
    disabled: 'true',
    selected: _draft.output_item_id == null ? 'selected' : null,
  }, '— Output Item —'));
  _items.forEach((i) => outSel.append(el('option', { value: String(i.id) }, i.name)));
  if (_draft.output_item_id != null) outSel.value = String(_draft.output_item_id);

  const outUomInput = el('select', {
    class: 'recipes-input recipes-input--uom',
  });
  const initialOutItem = findItem(_draft.output_item_id);
  setSelectOptions(outUomInput, uomOptionsForItem(initialOutItem), _draft.uom || initialOutItem?.uom || '', null);
  outUomInput.addEventListener('change', () => { _draft.uom = outUomInput.value; });

  outSel.addEventListener('change', () => {
    const parsed = parseInt(outSel.value, 10);
    _draft.output_item_id = Number.isFinite(parsed) ? parsed : null;
    const outItem = findItem(_draft.output_item_id);
    const preferred = _draft.uom || outItem?.uom || '';
    setSelectOptions(outUomInput, uomOptionsForItem(outItem), preferred, null);
    _draft.uom = outUomInput.value || '';
  });

  const outQtyInput = el('input', {
    type: 'text',
    class: 'recipes-input recipes-input--qty',
    value: _draft.quantity_decimal || '1',
  });
  outQtyInput.addEventListener('input', () => { _draft.quantity_decimal = outQtyInput.value; });

  outputRow.append(
    el('label', { class: 'recipes-row-label', text: 'Output' }),
    outSel,
    outQtyInput,
    outUomInput,
  );

  const flagsRow = el('div', { class: 'recipes-flags-row' });
  const archivedToggle = el('input', { type: 'checkbox' });
  archivedToggle.checked = _draft.archived === true;
  archivedToggle.addEventListener('change', () => { _draft.archived = archivedToggle.checked; });
  flagsRow.append(archivedToggle, el('span', { class: 'recipes-flag-label', text: 'Archived' }));

  const notes = el('textarea', {
    class: 'recipes-textarea',
    placeholder: 'Notes',
    value: _draft.notes || '',
  });
  notes.addEventListener('input', () => { _draft.notes = notes.value; });

  const itemsBox = el('div', { class: 'recipes-items-box' });
  const itemsHeader = el('div', { class: 'recipes-items-header' }, [
    el('h4', { class: 'recipes-items-title', text: 'Input Items' }),
    el('button', { class: 'btn small recipes-add-item-btn', text: '+ Add' }),
  ]);

  const table = el('table', { class: 'recipes-items-table' });
  const thead = el('thead', { class: 'recipes-items-thead' }, el('tr', {}, [
    el('th', { class: 'recipes-th-left' }, 'Item'),
    el('th', { class: 'recipes-th-right' }, 'Quantity'),
    el('th', { class: 'recipes-th-right' }, 'UOM'),
    el('th', { class: 'recipes-th-center' }, 'Optional'),
    el('th', { class: 'recipes-th-actions' }, ''),
  ]));
  const tbody = el('tbody');
  table.append(thead, tbody);

  function renderItemRows() {
    tbody.innerHTML = '';
    _draft.items.forEach((ri, idx) => {
      const row = el('tr', { class: 'recipes-item-row' });

      const itemSel = el('select', { class: 'recipes-input recipes-input--full' });
      itemSel.append(el('option', {
        value: '',
        selected: ri.item_id == null ? 'selected' : null,
      }, '— Select —'));
      _items.forEach((i) => itemSel.append(el('option', {
        value: String(i.id),
        selected: String(i.id) === String(ri.item_id) ? 'selected' : null,
      }, i.name)));
      itemSel.addEventListener('change', () => {
        ri.item_id = itemSel.value ? Number(itemSel.value) : null;
        const meta = findItem(ri.item_id);
        const preferred = meta?.uom || ri.uom || '';
        setSelectOptions(uomInput, uomOptionsForItem(meta), preferred, '— Select —');
        ri.uom = uomInput.value;
      });

      const qtyInput = el('input', {
        type: 'text',
        class: 'recipes-input recipes-input--qty recipes-input--right',
        value: ri.quantity_decimal ?? '',
      });
      qtyInput.addEventListener('input', () => {
        ri.quantity_decimal = qtyInput.value;
      });

      const uomInput = el('select', {
        class: 'recipes-input recipes-input--uom',
      });
      const currentItem = findItem(ri.item_id);
      setSelectOptions(uomInput, uomOptionsForItem(currentItem), ri.uom ?? currentItem?.uom ?? '', '— Select —');
      uomInput.addEventListener('change', () => {
        ri.uom = uomInput.value;
      });

      const optBox = el('input', { type: 'checkbox' });
      optBox.checked = ri.optional === true;
      optBox.addEventListener('change', () => {
        ri.optional = optBox.checked;
      });

      const delBtn = el('button', { class: 'btn small recipes-del-item-btn', text: '✕' });
      delBtn.onclick = () => {
        _draft.items.splice(idx, 1);
        _draft.items = _draft.items.map((it, sidx) => ({ ...it, sort: sidx }));
        renderItemRows();
      };

      row.append(
        el('td', { class: 'recipes-td' }, itemSel),
        el('td', { class: 'recipes-td recipes-td-right' }, qtyInput),
        el('td', { class: 'recipes-td recipes-td-right' }, uomInput),
        el('td', { class: 'recipes-td recipes-td-center' }, optBox),
        el('td', { class: 'recipes-td recipes-td-right' }, delBtn),
      );
      tbody.append(row);
    });
  }

  itemsHeader.lastChild.onclick = () => {
    _draft.items.push(blankRecipeItem(_draft.items.length));
    renderItemRows();
  };

  renderItemRows();
  itemsBox.append(itemsHeader, table);

  const actions = el('div', { class: 'recipes-actions' });
  const saveBtn = el('button', { class: 'btn primary recipes-save-btn', text: 'Save Recipe' });
  const deleteBtn = el('button', {
    id: 'recipe-delete',
    class: 'btn recipes-delete-btn',
    text: 'Delete',
  });
  deleteBtn.disabled = !_draft.id;

  function serializeDraft() {
    const nameVal = (_draft.name || '').trim();
    const outItemId = Number(_draft.output_item_id);
    const outQtyRaw = String(_draft.quantity_decimal || '').trim();
    const outQty = decimalString(outQtyRaw || '0');
    const outUom = String(_draft.uom || '').trim();
    const itemErrors = [];

    const cleanedItems = (_draft.items || [])
      .map((it, idx) => {
        const itemId = Number(it.item_id);
        const qtyRaw = String(it.quantity_decimal || '').trim();
        const qty = decimalString(qtyRaw || '0');
        const uom = String(it.uom || '').trim();
        if (!Number.isInteger(itemId) || itemId <= 0) itemErrors.push(`Input row ${idx + 1}: select an item.`);
        if (!isStrictPositiveDecimal(qtyRaw)) itemErrors.push(`Input row ${idx + 1}: quantity must be a positive decimal.`);
        if (!uom) itemErrors.push(`Input row ${idx + 1}: UOM is required.`);
        return {
          item_id: itemId,
          quantity_decimal: qty,
          uom,
          optional: it.optional === true,
          sort: idx,
        };
      })
      .filter((it) => Number.isInteger(it.item_id) && it.item_id > 0 && Number(it.quantity_decimal) > 0 && it.uom);

    const errors = [];
    if (!nameVal) errors.push('Name is required.');
    if (!Number.isInteger(outItemId) || outItemId <= 0) errors.push('Choose an output item.');
    if (!isStrictPositiveDecimal(outQtyRaw)) errors.push('Output quantity must be a positive decimal.');
    errors.push(...itemErrors);
    // Intentional UI policy: require at least one component row even though backend permits empty items.
    if (cleanedItems.length === 0) errors.push('Add at least one input item with quantity and uom.');
    if (errors.length) throw new Error(errors.join(' '));

    const payload = {
      name: nameVal,
      output_item_id: outItemId,
      quantity_decimal: outQty,
      archived: !!_draft.archived,
      notes: (_draft.notes || '').trim() || null,
      items: cleanedItems,
    };
    if (outUom) payload.uom = outUom;
    return payload;
  }

  saveBtn.onclick = async () => {
    setStatus(status, '', 'neutral');
    let payload;
    try {
      payload = serializeDraft();
    } catch (err) {
      setStatus(status, err?.message || 'Please complete required fields.', 'error');
      return;
    }

    try {
      await ensureToken();
      const saved = _draft.id ? await RecipesAPI.update(_draft.id, payload) : await RecipesAPI.create(payload);
      _draft = normalizeRecipe(saved || (_draft.id ? await RecipesAPI.get(_draft.id) : saved));
      _activeId = _draft.id;
      await refreshData();
      renderList(leftPanel, editor);
      setStatus(status, 'Saved', 'success');
    } catch (e) {
      setStatus(status, formatRecipeError(e), 'error');
    }
  };

  deleteBtn.onclick = async () => {
    if (!_draft?.id) return;
    if (!confirm('Delete this recipe? This cannot be undone.')) return;
    setStatus(status, '', 'neutral');
    deleteBtn.disabled = true;
    const resetLabel = deleteBtn.textContent;
    deleteBtn.textContent = 'Deleting...';
    try {
      await ensureToken();
      await RecipesAPI.delete(_draft.id);
      await refreshData();
      _activeId = null;
      _draft = null;
      renderList(leftPanel, editor);
      renderEmpty(editor);
      setStatus(status, 'Deleted', 'success');
    } catch (e) {
      setStatus(status, (e?.detail?.message || e?.detail || e?.message || 'Delete failed'), 'error');
    } finally {
      deleteBtn.disabled = false;
      deleteBtn.textContent = resetLabel;
    }
  };

  actions.append(saveBtn, deleteBtn);
  editor.append(nameRow, outputRow, flagsRow, notes, itemsBox, actions, status);
}
