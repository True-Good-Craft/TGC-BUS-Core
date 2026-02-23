// SPDX-License-Identifier: AGPL-3.0-or-later
import { apiGet, ensureToken } from '../api.js';
import { RecipesAPI } from '../api/recipes.js';

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

let _items = [];
let _recipes = [];
let _activeId = null;
let _draft = null;

function findItem(itemId) {
  return _items.find((i) => String(i.id) === String(itemId));
}

function decimalString(v) {
  const s = String(v ?? '').trim().replace(/,/g, '');
  if (s === '' || s === '.' || s === '-.') return '0';
  return s.startsWith('.') ? `0${s}` : s;
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
  return {
    id: data.id,
    name: data.name || '',
    output_item_id: data.output_item_id ?? null,
    quantity_decimal: data.quantity_decimal ? String(data.quantity_decimal) : '1',
    uom: data.uom || '',
    archived: data.archived === true || data.is_archived === true,
    notes: data.notes || '',
    items: (data.items || []).map((it, idx) => ({
      item_id: it.item_id ?? null,
      quantity_decimal: it.quantity_decimal != null ? String(it.quantity_decimal) : '',
      uom: it.uom || (it.item?.uom || ''),
      optional: it.optional === true || it.is_optional === true,
      sort: Number.isFinite(it.sort ?? it.sort_order) ? (it.sort ?? it.sort_order) : idx,
    })),
  };
}

async function refreshData() {
  _items = await apiGet('/app/items');
  _recipes = await RecipesAPI.list();
}

export async function mountRecipes() {
  await ensureToken();
  const container = document.querySelector('[data-tab-panel="recipes"]');
  if (!container) return;
  container.innerHTML = '';

  try {
    await refreshData();
  } catch {
    container.textContent = 'Failed to load recipes.';
    return;
  }

  const grid = el('div', { style: 'display:grid;grid-template-columns:1fr 2fr;gap:20px;min-height:calc(100vh - 160px);' });
  const listPanel = el('div', { class: 'card', style: 'overflow:auto;background:#1e1f22;border-radius:10px;border:1px solid #2f3136;' });
  const editorPanel = el('div', { class: 'card', style: 'overflow:auto;background:#1e1f22;border-radius:10px;border:1px solid #2f3136;' });

  grid.append(listPanel, editorPanel);
  container.append(grid);

  renderList(listPanel, editorPanel);
  renderEmpty(editorPanel);
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

  const header = el('div', { style: 'display:flex;justify-content:space-between;align-items:center;margin-bottom:12px' }, [
    el('h2', { text: 'Recipes', style: 'margin:0;' }),
    el('button', { class: 'btn primary small', text: '+ New', style: 'border-radius:10px;padding:8px 12px;' }),
  ]);
  header.lastChild.onclick = () => {
    _activeId = null;
    _draft = newRecipeDraft();
    renderEditor(editor, container);
  };

  const search = el('input', {
    type: 'search',
    placeholder: 'Filter…',
    style: 'width:100%;margin:6px 0 12px 0;padding:10px 12px;background:#2a2c30;border:1px solid #3a3d43;border-radius:10px;color:#e6e6e6',
  });
  const list = el('div', { style: 'display:flex;flex-direction:column;gap:8px' });

  const paint = (term = '') => {
    list.innerHTML = '';
    const q = term.trim().toLowerCase();
    _recipes
      .filter((r) => !q || String(r.name || '').toLowerCase().includes(q))
      .forEach((r) => {
        const row = el('div', {
          class: 'recipe-row',
          style: 'padding:10px 12px;background:#23262b;border-radius:10px;cursor:pointer;display:flex;justify-content:space-between;align-items:center;border:1px solid #2f3136;',
        }, [
          el('span', { text: r.name, style: 'color:#e6e6e6' }),
          el('span', { text: '→', style: 'color:#6b7280' }),
        ]);
        if (r.id === _activeId) row.style.background = '#2f333b';
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
  editor.append(el('div', { style: 'color:#666;text-align:center;margin-top:50px' }, 'Select a recipe to edit.'));
}

function renderEditor(editor, leftPanel) {
  editor.innerHTML = '';
  if (!_draft) {
    renderEmpty(editor);
    return;
  }

  const status = el('div', { style: 'min-height:18px;font-size:13px;margin-bottom:6px;color:#9ca3af' });

  const nameRow = el('div', { style: 'display:flex;gap:10px;align-items:center;margin-bottom:10px' });
  const nameInput = el('input', {
    type: 'text',
    value: _draft.name,
    style: 'flex:1;padding:10px 12px;background:#2a2c30;border:1px solid #3a3d43;border-radius:10px;color:#e6e6e6',
  });
  nameInput.addEventListener('input', () => { _draft.name = nameInput.value; });
  nameRow.append(el('label', { text: 'Name', style: 'width:90px;color:#cdd1dc' }), nameInput);

  const outputRow = el('div', { style: 'display:flex;gap:10px;align-items:center;margin-bottom:10px;flex-wrap:wrap' });
  const outSel = el('select', {
    id: 'recipe-output',
    style: 'flex:1;min-width:200px;padding:10px 12px;background:#2a2c30;border:1px solid #3a3d43;border-radius:10px;color:#e6e6e6',
  });
  outSel.append(el('option', { value: '', disabled: 'true', selected: _draft.output_item_id == null ? 'selected' : undefined }, '— Output Item —'));
  _items.forEach((i) => outSel.append(el('option', { value: String(i.id) }, i.name)));
  if (_draft.output_item_id != null) outSel.value = String(_draft.output_item_id);
  outSel.addEventListener('change', () => {
    const parsed = parseInt(outSel.value, 10);
    _draft.output_item_id = Number.isFinite(parsed) ? parsed : null;
    const outItem = findItem(_draft.output_item_id);
    _draft.uom = outItem?.uom || _draft.uom;
    outUomInput.value = _draft.uom || '';
  });

  const outQtyInput = el('input', {
    type: 'text',
    value: _draft.quantity_decimal || '1',
    style: 'width:120px;padding:10px 12px;background:#2a2c30;border:1px solid #3a3d43;border-radius:10px;color:#e6e6e6',
  });
  outQtyInput.addEventListener('input', () => { _draft.quantity_decimal = outQtyInput.value; });

  const outUomInput = el('input', {
    type: 'text',
    value: _draft.uom || '',
    style: 'width:100px;padding:10px 12px;background:#2a2c30;border:1px solid #3a3d43;border-radius:10px;color:#e6e6e6',
  });
  outUomInput.addEventListener('input', () => { _draft.uom = outUomInput.value; });

  outputRow.append(
    el('label', { text: 'Output', style: 'width:90px;color:#cdd1dc' }),
    outSel,
    outQtyInput,
    outUomInput,
  );

  const flagsRow = el('div', { style: 'display:flex;gap:16px;align-items:center;margin-bottom:10px' });
  const archivedToggle = el('input', { type: 'checkbox' });
  archivedToggle.checked = _draft.archived === true;
  archivedToggle.addEventListener('change', () => { _draft.archived = archivedToggle.checked; });
  flagsRow.append(archivedToggle, el('span', { text: 'Archived', style: 'color:#cdd1dc' }));

  const notes = el('textarea', {
    value: _draft.notes || '',
    placeholder: 'Notes',
    style: 'width:100%;min-height:80px;padding:10px 12px;background:#2a2c30;border:1px solid #3a3d43;border-radius:10px;color:#e6e6e6;margin-bottom:10px;',
  });
  notes.addEventListener('input', () => { _draft.notes = notes.value; });

  const itemsBox = el('div', { style: 'background:#23262b;padding:14px;border-radius:10px;border:1px solid #2f3136;margin-bottom:12px' });
  const itemsHeader = el('div', { style: 'display:flex;justify-content:space-between;align-items:center;margin-bottom:10px' }, [
    el('h4', { text: 'Input Items', style: 'margin:0;color:#e6e6e6' }),
    el('button', { class: 'btn small', text: '+ Add', style: 'border-radius:10px;padding:8px 12px;' }),
  ]);

  const table = el('table', { style: 'width:100%;border-collapse:collapse;background:#1e1f22;border:1px solid #2f3136;border-radius:10px;overflow:hidden;' });
  const thead = el('thead', { style: 'background:#202226' }, el('tr', {}, [
    el('th', { style: 'text-align:left;padding:10px;color:#e6e6e6' }, 'Item'),
    el('th', { style: 'text-align:right;padding:10px;color:#e6e6e6' }, 'Quantity'),
    el('th', { style: 'text-align:right;padding:10px;color:#e6e6e6' }, 'UOM'),
    el('th', { style: 'text-align:center;padding:10px;color:#e6e6e6' }, 'Optional'),
    el('th', { style: 'width:60px;text-align:right' }, ''),
  ]));
  const tbody = el('tbody');
  table.append(thead, tbody);

  function renderItemRows() {
    tbody.innerHTML = '';
    _draft.items.forEach((ri, idx) => {
      const row = el('tr', { style: 'border-bottom:1px solid #2f3136' });

      const itemSel = el('select', { style: 'width:100%;padding:8px 10px;background:#2a2c30;border:1px solid #3a3d43;border-radius:10px;color:#e6e6e6' });
      itemSel.append(el('option', { value: '', selected: ri.item_id == null ? 'selected' : undefined }, '— Select —'));
      _items.forEach((i) => itemSel.append(el('option', { value: String(i.id), selected: String(i.id) === String(ri.item_id) ? 'selected' : undefined }, i.name)));
      itemSel.addEventListener('change', () => {
        ri.item_id = itemSel.value ? Number(itemSel.value) : null;
        const meta = findItem(ri.item_id);
        if (meta?.uom) {
          ri.uom = meta.uom;
          uomInput.value = meta.uom;
        }
      });

      const qtyInput = el('input', {
        type: 'text',
        value: ri.quantity_decimal ?? '',
        style: 'width:120px;text-align:right;padding:8px 10px;background:#2a2c30;border:1px solid #3a3d43;border-radius:10px;color:#e6e6e6',
      });
      qtyInput.addEventListener('input', () => {
        ri.quantity_decimal = qtyInput.value;
      });

      const uomInput = el('input', {
        type: 'text',
        value: ri.uom ?? '',
        style: 'width:100px;padding:8px 10px;background:#2a2c30;border:1px solid #3a3d43;border-radius:10px;color:#e6e6e6',
      });
      uomInput.addEventListener('input', () => {
        ri.uom = uomInput.value;
      });

      const optBox = el('input', { type: 'checkbox' });
      optBox.checked = ri.optional === true;
      optBox.addEventListener('change', () => {
        ri.optional = optBox.checked;
      });

      const delBtn = el('button', { class: 'btn small', text: '✕', style: 'border-radius:10px;padding:6px 10px;' });
      delBtn.onclick = () => {
        _draft.items.splice(idx, 1);
        _draft.items = _draft.items.map((it, sidx) => ({ ...it, sort: sidx }));
        renderItemRows();
      };

      row.append(
        el('td', { style: 'padding:10px' }, itemSel),
        el('td', { style: 'padding:10px;text-align:right' }, qtyInput),
        el('td', { style: 'padding:10px;text-align:right' }, uomInput),
        el('td', { style: 'padding:10px;text-align:center' }, optBox),
        el('td', { style: 'padding:10px;text-align:right' }, delBtn),
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

  const actions = el('div', { style: 'display:flex;justify-content:space-between;gap:10px;align-items:center;margin-top:6px' });
  const saveBtn = el('button', { class: 'btn primary', text: 'Save Recipe', style: 'border-radius:10px;padding:10px 14px;' });
  const deleteBtn = el('button', {
    id: 'recipe-delete',
    class: 'btn',
    text: 'Delete',
    style: 'border-radius:10px;padding:10px 14px;background:#3a3d43;color:#e6e6e6;border:1px solid #2f3136',
  });
  deleteBtn.disabled = !_draft.id;

  function serializeDraft() {
    const nameVal = (_draft.name || '').trim();
    const outItemId = Number(_draft.output_item_id);
    const outQty = decimalString(_draft.quantity_decimal || '0');
    const outUom = String(_draft.uom || '').trim();

    const cleanedItems = (_draft.items || [])
      .map((it, idx) => ({
        item_id: Number(it.item_id),
        quantity_decimal: decimalString(it.quantity_decimal || '0'),
        uom: String(it.uom || '').trim(),
        optional: it.optional === true,
        sort: idx,
      }))
      .filter((it) => Number.isInteger(it.item_id) && it.item_id > 0 && Number(it.quantity_decimal) > 0 && it.uom);

    const errors = [];
    if (!nameVal) errors.push('Name is required.');
    if (!Number.isInteger(outItemId) || outItemId <= 0) errors.push('Choose an output item.');
    if (!outUom) errors.push('Output UOM is required.');
    if (Number(outQty) <= 0) errors.push('Output quantity must be positive.');
    if (cleanedItems.length === 0) errors.push('Add at least one input item with quantity and uom.');
    if (errors.length) throw new Error(errors.join(' '));

    return {
      name: nameVal,
      output_item_id: outItemId,
      quantity_decimal: outQty,
      uom: outUom,
      archived: !!_draft.archived,
      notes: (_draft.notes || '').trim() || null,
      items: cleanedItems,
    };
  }

  saveBtn.onclick = async () => {
    status.textContent = '';
    status.style.color = '#9ca3af';
    let payload;
    try {
      payload = serializeDraft();
    } catch (err) {
      status.textContent = err?.message || 'Please complete required fields.';
      status.style.color = '#ff6666';
      return;
    }

    try {
      await ensureToken();
      const saved = _draft.id ? await RecipesAPI.update(_draft.id, payload) : await RecipesAPI.create(payload);
      _draft = normalizeRecipe(saved || (_draft.id ? await RecipesAPI.get(_draft.id) : saved));
      _activeId = _draft.id;
      await refreshData();
      renderList(leftPanel, editor);
      status.textContent = 'Saved';
      status.style.color = '#4caf50';
    } catch (e) {
      status.textContent = (e?.data?.detail?.message || e?.message || 'Save failed');
      status.style.color = '#ff6666';
    }
  };

  deleteBtn.onclick = async () => {
    if (!_draft?.id) return;
    if (!confirm('Delete this recipe? This cannot be undone.')) return;
    status.textContent = '';
    status.style.color = '#9ca3af';
    deleteBtn.disabled = true;
    const resetLabel = deleteBtn.textContent;
    deleteBtn.textContent = 'Deleting…';
    try {
      await ensureToken();
      await RecipesAPI.delete(_draft.id);
      await refreshData();
      _activeId = null;
      _draft = null;
      renderList(leftPanel, editor);
      renderEmpty(editor);
      status.textContent = 'Deleted';
      status.style.color = '#4caf50';
    } catch (e) {
      status.textContent = (e?.detail?.message || e?.detail || e?.message || 'Delete failed');
      status.style.color = '#ff6666';
    } finally {
      deleteBtn.disabled = false;
      deleteBtn.textContent = resetLabel;
    }
  };

  actions.append(saveBtn, deleteBtn);
  editor.append(nameRow, outputRow, flagsRow, notes, itemsBox, actions, status);
}
