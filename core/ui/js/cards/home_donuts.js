// SPDX-License-Identifier: AGPL-3.0-or-later
// TGC BUS Core (Business Utility System Core)
// Copyright (C) 2025 True Good Craft
//
// This file is part of TGC BUS Core.
//
// TGC BUS Core is free software: you can redistribute it and/or modify
// it under the terms of the GNU Affero General Public License as
// published by the Free Software Foundation, either version 3 of the
// License, or (at your option) any later version.
//
// TGC BUS Core is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU Affero General Public License for more details.
//
// You should have received a copy of the GNU Affero General Public License
// along with TGC BUS Core.  If not, see <https://www.gnu.org/licenses/>.

import { apiGetJson } from '../token.js';

let activeType = null; // 'in' | 'out' | null
const STUB_NOTICE = 'Home transaction dashboard is placeholder only until the transactions module lands.';

function drawDonut(el, totalCents, categories, color) {
  if (!el) return;
  const size = 80, r = 32, cx = 40, cy = 40, strokeW = 12;
  el.innerHTML = '';
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox','0 0 80 80');
  const ring = document.createElementNS(svg.namespaceURI,'circle');
  ring.setAttribute('cx', cx); ring.setAttribute('cy', cy);
  ring.setAttribute('r', r); ring.setAttribute('fill','none');
  ring.setAttribute('stroke', color); ring.setAttribute('stroke-width', strokeW);
  svg.appendChild(ring);
  const total = Number(totalCents || 0);
  if (!total || !categories || !categories.length) { el.appendChild(svg); return; }
  let start = -90;
  categories.forEach(c => {
    const cents = Math.max(0, Number(c.amount_cents || 0));
    const frac = Math.max(0, Math.min(1, cents / total));
    const sweep = 360 * frac;
    if (sweep <= 0) return;
    const end = start + sweep;
    const path = document.createElementNS(svg.namespaceURI,'path');
    const large = sweep > 180 ? 1 : 0;
    const sx = cx + r * Math.cos(Math.PI * start/180);
    const sy = cy + r * Math.sin(Math.PI * start/180);
    const ex = cx + r * Math.cos(Math.PI * end/180);
    const ey = cy + r * Math.sin(Math.PI * end/180);
    path.setAttribute('d', `M ${sx} ${sy} A ${r} ${r} 0 ${large} 1 ${ex} ${ey}`);
    path.setAttribute('fill','none');
    path.setAttribute('stroke', color);
    path.setAttribute('stroke-width', strokeW);
    svg.appendChild(path);
    start = end;
  });
  el.appendChild(svg);
}

function formatCurrency(cents) {
  return `$${(Number(cents || 0) / 100).toFixed(2)}`;
}

async function fetchSummary() {
  return apiGetJson('/app/transactions/summary?window=30d');
}

async function fetchLast10() {
  const res = await apiGetJson('/app/transactions?limit=10');
  return {
    stub: !!res?.stub,
    items: res?.items || [],
  };
}

function setNetLine(text) {
  const netLine = document.querySelector('[data-role="net-30"]');
  if (netLine) netLine.textContent = text;
}

function renderStubDonuts() {
  const placeholder = '<div style="display:grid;place-items:center;height:100%;font-size:12px;text-align:center;color:#9ca3af;">Placeholder only</div>';
  const din  = document.querySelector('[data-role="donut-in"]');
  const dout = document.querySelector('[data-role="donut-out"]');
  if (din) din.innerHTML = placeholder;
  if (dout) dout.innerHTML = placeholder;
}

function renderStubTable() {
  const tbody = document.querySelector('[data-role="recent-transactions"] tbody');
  if (!tbody) return;
  tbody.innerHTML = `
    <tr>
      <td colspan="4" style="color:#9ca3af;text-align:center;">Transaction dashboard pending. Home data is placeholder only.</td>
    </tr>
  `;
}

async function render() {
  const sum = await fetchSummary();
  const recent = await fetchLast10();

  if (sum?.stub || recent.stub) {
    activeType = null;
    setNetLine(STUB_NOTICE);
    renderStubDonuts();
    renderStubTable();
    return;
  }

  const din  = document.querySelector('[data-role="donut-in"]');
  const dout = document.querySelector('[data-role="donut-out"]');
  const income = Number(sum?.income?.total_cents || 0);
  const expense = Number(sum?.expense?.total_cents || 0);

  setNetLine(`Net (Last 30 Days): ${formatCurrency(income - expense)}`);
  drawDonut(din, income, sum?.income?.categories, '#22c55e');
  drawDonut(dout, expense, sum?.expense?.categories, '#ef4444');
  await renderTable(recent.items);
}

async function renderTable(initialRows = null) {
  const tbody = document.querySelector('[data-role="recent-transactions"] tbody');
  if (!tbody) return;
  let rows = Array.isArray(initialRows) ? initialRows : (await fetchLast10()).items;
  if (activeType === 'in')  rows = rows.filter(r => r.type === 'revenue');
  if (activeType === 'out') rows = rows.filter(r => r.type === 'expense');
  tbody.innerHTML = '';
  for (const t of rows) {
    const amt = (Number(t.amount_cents || 0) / 100).toFixed(2);
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${t.date}</td><td>${t.type}</td><td>${amt}</td><td>${t.notes || ''}</td>`;
    tbody.appendChild(tr);
  }
}

function wireClicks() {
  const din  = document.querySelector('[data-role="donut-in"]');
  const dout = document.querySelector('[data-role="donut-out"]');
  if (din)  din.addEventListener('click',  async () => { activeType = (activeType === 'in'  ? null : 'in');  await renderTable(); });
  if (dout) dout.addEventListener('click', async () => { activeType = (activeType === 'out' ? null : 'out'); await renderTable(); });
}

document.addEventListener('DOMContentLoaded', async () => {
  wireClicks();
  try { await render(); } catch (_) {}
});

// Also re-render when routed back to home
window.addEventListener('hashchange', async () => {
  const route = (location.hash || '#/home').replace(/^#\/?/, '').split(/[\/?]/)[0] || 'home';
  if (route === 'home') { try { await render(); } catch (_) {} }
});
