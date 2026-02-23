// SPDX-License-Identifier: AGPL-3.0-or-later

import { apiGet, apiPost } from '../api.js';

function toDecimalString(value) {
  const raw = String(value ?? '').trim().replace(/,/g, '');
  if (!raw || raw === '.' || raw === '-.') return '0';
  return raw.startsWith('.') ? `0${raw}` : raw;
}

function normalizeOptionalInt(value) {
  if (value === undefined || value === null || value === '') return undefined;
  const parsed = Math.trunc(Number(value));
  return Number.isInteger(parsed) && parsed > 0 ? parsed : undefined;
}

function normalizeOptionalString(value) {
  if (value === undefined || value === null) return undefined;
  const normalized = String(value).trim();
  return normalized === '' ? undefined : normalized;
}

export function stockIn({ item_id, quantity_decimal, uom, unit_cost_cents, source_id } = {}) {
  const payload = {
    item_id: Math.trunc(Number(item_id)),
    quantity_decimal: toDecimalString(quantity_decimal),
    uom: String(uom || ''),
  };

  const unitCost = normalizeOptionalInt(unit_cost_cents);
  if (unitCost !== undefined) payload.unit_cost_cents = unitCost;

  const sourceId = normalizeOptionalString(source_id);
  if (sourceId !== undefined) payload.source_id = sourceId;

  return apiPost('/app/stock/in', payload);
}

export function stockOut({ item_id, quantity_decimal, uom, reason, note, record_cash_event, sell_unit_price_cents } = {}) {
  const payload = {
    item_id: Math.trunc(Number(item_id)),
    quantity_decimal: toDecimalString(quantity_decimal),
    uom: String(uom || ''),
    reason: String(reason || ''),
  };

  const normalizedNote = normalizeOptionalString(note);
  if (normalizedNote !== undefined) payload.note = normalizedNote;

  if (record_cash_event !== undefined) payload.record_cash_event = !!record_cash_event;

  const sellPrice = normalizeOptionalInt(sell_unit_price_cents);
  if (sellPrice !== undefined) payload.sell_unit_price_cents = sellPrice;

  return apiPost('/app/stock/out', payload);
}

export function purchase({ item_id, quantity_decimal, uom, unit_cost_cents, source_id } = {}) {
  const payload = {
    item_id: Math.trunc(Number(item_id)),
    quantity_decimal: toDecimalString(quantity_decimal),
    uom: String(uom || ''),
    unit_cost_cents: Math.trunc(Number(unit_cost_cents)),
  };

  const sourceId = normalizeOptionalString(source_id);
  if (sourceId !== undefined) payload.source_id = sourceId;

  return apiPost('/app/purchase', payload);
}

export function ledgerHistory({ item_id, limit } = {}) {
  const params = new URLSearchParams();
  const itemId = normalizeOptionalInt(item_id);
  const cap = normalizeOptionalInt(limit);
  if (itemId !== undefined) params.set('item_id', String(itemId));
  if (cap !== undefined) params.set('limit', String(cap));
  const qs = params.toString();
  return apiGet(qs ? `/app/ledger/history?${qs}` : '/app/ledger/history');
}

export function manufactureRecipe({ recipe_id, quantity_decimal, uom, notes } = {}) {
  const payload = {
    recipe_id: Math.trunc(Number(recipe_id)),
    quantity_decimal: toDecimalString(quantity_decimal),
    uom: String(uom || ''),
  };

  const normalizedNotes = normalizeOptionalString(notes);
  if (normalizedNotes !== undefined) payload.notes = normalizedNotes;

  return apiPost('/app/manufacture', payload);
}

export function manufactureAdhoc({ output_item_id, quantity_decimal, uom, components, notes } = {}) {
  const payload = {
    output_item_id: Math.trunc(Number(output_item_id)),
    quantity_decimal: toDecimalString(quantity_decimal),
    uom: String(uom || ''),
    components: Array.isArray(components)
      ? components
          .map((component) => ({
            item_id: Math.trunc(Number(component?.item_id)),
            quantity_decimal: toDecimalString(component?.quantity_decimal),
            uom: String(component?.uom || ''),
            is_optional: !!component?.is_optional,
          }))
          .filter((component) => Number.isInteger(component.item_id) && component.item_id > 0 && component.uom)
      : [],
  };

  const normalizedNotes = normalizeOptionalString(notes);
  if (normalizedNotes !== undefined) payload.notes = normalizedNotes;

  return apiPost('/app/manufacture', payload);
}
