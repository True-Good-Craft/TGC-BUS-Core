// SPDX-License-Identifier: AGPL-3.0-or-later
import { rawFetch } from "../api.js";

function fmtMoney(cents) {
  return `$${(Number(cents || 0) / 100).toFixed(2)}`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function isoDate(date) {
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

export function mountFinance() {
  const host = document.querySelector('[data-role="finance-root"]');
  if (!host) return;

  const now = new Date();
  const fromDefault = new Date(now);
  fromDefault.setDate(now.getDate() - 30);

  host.classList.add('finance-shell');
  host.innerHTML = `
    <div class="card finance-card">
      <h2>Finance</h2>
      <div class="finance-controls">
        <label class="finance-field">From<br/><input class="finance-input" data-role="finance-from" type="date" value="${isoDate(fromDefault)}"></label>
        <label class="finance-field">To<br/><input class="finance-input" data-role="finance-to" type="date" value="${isoDate(now)}"></label>
        <button class="finance-refresh-btn" data-role="finance-refresh" type="button">Refresh</button>
        <button class="finance-refresh-btn" data-role="finance-export" type="button">Export CSV</button>
      </div>
      <div data-role="finance-summary" class="finance-summary-grid"></div>
      <div class="finance-table-wrap">
        <table class="finance-table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Type</th>
              <th>Amount</th>
              <th>Details</th>
            </tr>
          </thead>
          <tbody data-role="finance-tx"></tbody>
        </table>
      </div>
    </div>
  `;

  const fromInput = host.querySelector('[data-role="finance-from"]');
  const toInput = host.querySelector('[data-role="finance-to"]');
  const refreshBtn = host.querySelector('[data-role="finance-refresh"]');
  const exportBtn = host.querySelector('[data-role="finance-export"]');
  const summaryEl = host.querySelector('[data-role="finance-summary"]');
  const txEl = host.querySelector('[data-role="finance-tx"]');

  function summaryTile(name, value) {
    return `<div class="finance-summary-tile"><div class="finance-summary-name">${name}</div><div class="finance-summary-value">${value}</div></div>`;
  }

  function txRow(tx) {
    let detail = tx.source_id || tx.category || tx.notes || tx.status || "-";
    if (tx.kind === "sale") {
      const cogs = tx.cogs_cents != null ? fmtMoney(tx.cogs_cents) : "-";
      const gp = tx.gross_profit_cents != null ? fmtMoney(tx.gross_profit_cents) : "-";
      detail = `COGS: ${cogs} · Gross Profit: ${gp}`;
    } else if (tx.kind === "manufacturing_run") {
      detail = `Output: ${tx.output_qty_decimal || "0"} ${tx.output_uom || ""}`.trim();
    } else if (tx.kind === "purchase_inferred") {
      detail = `Qty: ${tx.quantity_decimal || "0"} ${tx.uom || ""} · Unit Cost: ${fmtMoney(tx.unit_cost_cents || 0)}`.trim();
    }
    return `<tr>
      <td class="finance-td finance-td-date">${escapeHtml(String(tx.created_at || "").slice(0, 19).replace("T", " "))}</td>
      <td class="finance-td">${escapeHtml(tx.kind)}</td>
      <td class="finance-td">${fmtMoney(tx.amount_cents || 0)}</td>
      <td class="finance-td">${escapeHtml(detail)}</td>
    </tr>`;
  }

  function sumEaQty(units) {
    return (Array.isArray(units) ? units : []).reduce((acc, row) => {
      if (row?.uom !== "ea") return acc;
      const n = Number(row?.quantity_decimal ?? 0);
      return Number.isFinite(n) ? acc + n : acc;
    }, 0);
  }

  function formatQty(value) {
    const n = Number(value || 0);
    if (!Number.isFinite(n)) return "0";
    return Number.isInteger(n) ? String(n) : n.toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
  }

  async function refresh() {
    const from = fromInput?.value;
    const to = toInput?.value;
    if (!from || !to) return;

    summaryEl.innerHTML = "<div class=\"finance-loading\">Loading...</div>";
    txEl.innerHTML = "";

    try {
      const [summaryRes, txRes] = await Promise.all([
        rawFetch(`/app/finance/summary?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`, { credentials: "include" }),
        rawFetch(`/app/finance/transactions?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}&limit=100`, { credentials: "include" }),
      ]);
      const summary = await summaryRes.json();
      const txPayload = await txRes.json();
      if (!summaryRes.ok || !txRes.ok) throw new Error("finance_load_failed");

      summaryEl.innerHTML = [
        summaryTile("Gross Sales", fmtMoney(summary.gross_sales_cents)),
        summaryTile("Returns", fmtMoney(summary.returns_cents)),
        summaryTile("Net Sales", fmtMoney(summary.net_sales_cents)),
        summaryTile("COGS", fmtMoney(summary.cogs_cents)),
        summaryTile("Gross Profit", fmtMoney(summary.gross_profit_cents)),
        summaryTile("Expenses", fmtMoney(summary.expenses_cents)),
        summaryTile("Net Profit", fmtMoney(summary.net_profit_cents)),
        summaryTile("Runs", String(summary.runs_count || 0)),
        summaryTile("Produced Items", String((summary.units_produced || []).length)),
        summaryTile("Produced Qty (count items only)", formatQty(sumEaQty(summary.units_produced))),
        summaryTile("Sold Items", String((summary.units_sold || []).length)),
        summaryTile("Sold Qty (count items only)", formatQty(sumEaQty(summary.units_sold))),
      ].join("");

      const rows = Array.isArray(txPayload.transactions) ? txPayload.transactions : [];
      txEl.innerHTML = rows.length
        ? rows.map(txRow).join("")
        : '<tr><td colspan="4" class="finance-td finance-empty">No transactions</td></tr>';
    } catch (_) {
      summaryEl.innerHTML = '<div class="finance-error">Finance report failed.</div>';
      txEl.innerHTML = '<tr><td colspan="4" class="finance-td finance-error">Failed to load transactions</td></tr>';
    }
  }

  function exportCsv() {
    const params = new URLSearchParams();
    params.set("profile", "generic");
    if (fromInput?.value) params.set("from", fromInput.value);
    if (toInput?.value) params.set("to", toInput.value);
    window.open(`/app/finance/export.csv?${params.toString()}`, "_blank", "noopener");
  }

  if (host._financeRefreshHandler) {
    document.removeEventListener("bus:finance-refresh", host._financeRefreshHandler);
  }
  host._financeRefreshHandler = () => {
    if (!document.body.contains(host)) {
      document.removeEventListener("bus:finance-refresh", host._financeRefreshHandler);
      host._financeRefreshHandler = null;
      return;
    }
    void refresh();
  };
  document.addEventListener("bus:finance-refresh", host._financeRefreshHandler);

  refreshBtn?.addEventListener("click", refresh);
  exportBtn?.addEventListener("click", exportCsv);
  refresh();
}
