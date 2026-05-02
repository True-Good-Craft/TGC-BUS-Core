// SPDX-License-Identifier: AGPL-3.0-or-later

export function quantityValueOnly(source) {
  const toNumeric = (value) => {
    if (value == null || typeof value === 'object') return null;
    const match = String(value).match(/-?\d+(?:\.\d+)?/);
    if (!match) return null;
    const parsed = Number(match[0]);
    return Number.isFinite(parsed) ? parsed : null;
  };
  if (source == null) return null;
  if (typeof source !== 'object') return toNumeric(source);
  return toNumeric(source.qty ?? source.quantity ?? source.value);
}

export function formatOnHandDisplay(item, { fallback = '—', allowLegacyFallbacks = true } = {}) {
  const stockOnHandValue = quantityValueOnly(item?.stock_on_hand_display);
  if (stockOnHandValue != null && stockOnHandValue !== '') {
    return String(stockOnHandValue);
  }
  if (item?.quantity_decimal != null) {
    return String(item.quantity_decimal);
  }
  const quantityDisplayValue = quantityValueOnly(item?.quantity_display);
  if (quantityDisplayValue != null && quantityDisplayValue !== '') {
    return String(quantityDisplayValue);
  }
  if (!allowLegacyFallbacks) {
    return fallback;
  }
  const quantityValue = quantityValueOnly(item?.quantity);
  if (quantityValue != null && quantityValue !== '') {
    return String(quantityValue);
  }
  if (item?.qty != null && item.qty !== '') {
    return String(item.qty);
  }
  return fallback;
}
