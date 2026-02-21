// SPDX-License-Identifier: AGPL-3.0-or-later
// TGC BUS Core (Business Utility System Core)

import { apiGetJson } from '../token.js';

let activeType = null; // 'in' | 'out' | null
let _bound = false;
let _dinHandler = null;
let _doutHandler = null;

function drawDonut(el, totalCents, categories, color) {
  if (!el) return;
  const size = 80, r = 32, cx = 40, cy = 40, strokeW = 12;
  void size;
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
  categories.forEach((c) => {
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

async function fetchSummary() {
  return apiGetJson('/app/transactions/summary?window=30d');
}

async function fetchLast10() {
  const res = await apiGetJson('/app/transactions?limit=10');
  return res.items || [];
}

async function renderTable() {
  const tbody = document.querySelector('[data-role="recent-transactions"] tbody');
  if (!tbody) return;
  let rows = await fetchLast10();
  if (activeType === 'in') rows = rows.filter((r) => r.type === 'revenue');
  if (activeType === 'out') rows = rows.filter((r) => r.type === 'expense');
  tbody.innerHTML = '';
  for (const t of rows) {
    const amt = (Number(t.amount_cents || 0) / 100).toFixed(2);
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${t.date}</td><td>${t.type}</td><td>${amt}</td><td>${t.notes || ''}</td>`;
    tbody.appendChild(tr);
  }
}

export async function mount() {
  const din = document.querySelector('[data-role="donut-in"]');
  const dout = document.querySelector('[data-role="donut-out"]');
  if (!din || !dout) return;
  if (!_bound) {
    _dinHandler = async () => { activeType = (activeType === 'in' ? null : 'in'); await renderTable(); };
    _doutHandler = async () => { activeType = (activeType === 'out' ? null : 'out'); await renderTable(); };
    din.addEventListener('click', _dinHandler);
    dout.addEventListener('click', _doutHandler);
    _bound = true;
  }
  const sum = await fetchSummary();
  drawDonut(din, sum?.income?.total_cents, sum?.income?.categories, '#22c55e');
  drawDonut(dout, sum?.expense?.total_cents, sum?.expense?.categories, '#ef4444');
  await renderTable();
}

export function unmount() {
  const din = document.querySelector('[data-role="donut-in"]');
  const dout = document.querySelector('[data-role="donut-out"]');
  if (din && _dinHandler) din.removeEventListener('click', _dinHandler);
  if (dout && _doutHandler) dout.removeEventListener('click', _doutHandler);
  _bound = false;
  _dinHandler = null;
  _doutHandler = null;
}
