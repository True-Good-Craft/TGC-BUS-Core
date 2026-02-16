/* SPDX-License-Identifier: AGPL-3.0-or-later */
import { ensureToken } from "../token.js";

export { mountDashboard };

function formatCents(cents) {
  const value = Number(cents);
  if (!Number.isFinite(value)) return "$0.00";
  return `$${(value / 100).toFixed(2)}`;
}

function formatPercent(p) {
  const value = Number(p);
  if (!Number.isFinite(value)) return "0.0%";
  return `${value.toFixed(1)}%`;
}

function dashboardHost() {
  return document.querySelector('[data-role="home-screen"]') || document.querySelector('#app') || document.body;
}

function ensureDashboardStyles() {
  const id = "bus-dashboard-styles";
  if (document.getElementById(id)) return;
  const style = document.createElement("style");
  style.id = id;
  style.textContent = `
    .bus-dashboard{display:grid;gap:12px}
    .bus-dashboard h1{margin:0 0 6px;font-size:24px}
    .bus-dashboard .muted{color:#a9b7c8;font-size:13px}
    .bus-dashboard .cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-top:12px}
    .bus-dashboard .metric{background:#242424;padding:14px;border-radius:10px;border:1px solid #2f3540}
    .bus-dashboard .metric .label{font-size:12px;color:#a9b7c8;margin-bottom:6px}
    .bus-dashboard .metric .value{font-size:20px;font-weight:700;line-height:1.2}
    .bus-dashboard .metric .sub{font-size:13px;color:#a9b7c8;margin-top:4px}
  `;
  document.head.appendChild(style);
}

function renderLoading(root) {
  root.innerHTML = `
    <section class="bus-dashboard" data-state="loading">
      <h1>Dashboard</h1>
      <div class="cards">
        <article class="metric"><div class="label">Loading...</div><div class="value">Loading...</div></article>
        <article class="metric"><div class="label">Loading...</div><div class="value">Loading...</div></article>
        <article class="metric"><div class="label">Loading...</div><div class="value">Loading...</div></article>
        <article class="metric"><div class="label">Loading...</div><div class="value">Loading...</div></article>
        <article class="metric"><div class="label">Loading...</div><div class="value">Loading...</div></article>
        <article class="metric"><div class="label">Loading...</div><div class="value">Loading...</div></article>
      </div>
    </section>
  `;
}

function renderError(root, err) {
  const message = err instanceof Error ? err.message : "Unknown error";
  root.innerHTML = `
    <section class="bus-dashboard" data-state="error">
      <h1>Dashboard</h1>
      <div class="metric">
        <div class="value">Dashboard unavailable</div>
        <div class="sub">${message}</div>
      </div>
    </section>
  `;
}

function renderOk(root, data) {
  root.innerHTML = `
    <section class="bus-dashboard" data-state="ok">
      <h1>Dashboard</h1>
      <div class="muted">${data?.window?.start || ""} to ${data?.window?.end || ""}</div>
      <div class="cards">
        <article class="metric"><div class="label">Inventory Value</div><div class="value">${formatCents(data.inventory_value_cents)}</div></article>
        <article class="metric"><div class="label">Units Produced</div><div class="value">${Number.isFinite(Number(data.units_produced)) ? Number(data.units_produced) : 0}</div></article>
        <article class="metric"><div class="label">Gross Revenue</div><div class="value">${formatCents(data.gross_revenue_cents)}</div></article>
        <article class="metric"><div class="label">Net Revenue</div><div class="value">${formatCents(data.net_revenue_cents)}</div></article>
        <article class="metric"><div class="label">COGS</div><div class="value">${formatCents(data.cogs_cents)}</div></article>
        <article class="metric"><div class="label">Gross Profit + Margin</div><div class="value">${formatCents(data.gross_profit_cents)}</div><div class="sub">(${formatPercent(data.margin_percent)})</div></article>
      </div>
    </section>
  `;
}

async function mountDashboard() {
  ensureDashboardStyles();
  document.title = "BUS Core — Dashboard";
  const root = dashboardHost();
  renderLoading(root);
  try {
    const token = await ensureToken();
    const res = await fetch("/app/dashboard/summary", {
      method: "GET",
      credentials: "include",
      headers: { "X-Session-Token": token },
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data?.error || data?.message || `HTTP ${res.status}`);
    renderOk(root, data || {});
  } catch (err) {
    renderError(root, err);
  }
}
