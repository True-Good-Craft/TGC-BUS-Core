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

  host.innerHTML = `
    <div class="card">
      <h2>Finance</h2>
      <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end;">
        <label>From<br/><input data-role="finance-from" type="date" value="${isoDate(fromDefault)}"></label>
        <label>To<br/><input data-role="finance-to" type="date" value="${isoDate(now)}"></label>
        <button data-role="finance-refresh" type="button">Refresh</button>
      </div>
      <div data-role="finance-summary" style="margin-top:12px;display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:8px;"></div>
      <div style="margin-top:14px;overflow:auto;">
        <table style="width:100%;border-collapse:collapse;">
          <thead>
            <tr>
              <th style="text-align:left;padding:8px;border-bottom:1px solid #333;">Date</th>
              <th style="text-align:left;padding:8px;border-bottom:1px solid #333;">Type</th>
              <th style="text-align:left;padding:8px;border-bottom:1px solid #333;">Amount</th>
              <th style="text-align:left;padding:8px;border-bottom:1px solid #333;">Details</th>
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
  const summaryEl = host.querySelector('[data-role="finance-summary"]');
  const txEl = host.querySelector('[data-role="finance-tx"]');

  function summaryTile(name, value) {
    return `<div style="border:1px solid #2f3541;padding:10px;border-radius:10px;background:#111318;"><div style="font-size:12px;color:#a4aabc;">${name}</div><div style="font-size:17px;font-weight:700;">${value}</div></div>`;
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
      <td style="padding:8px;border-bottom:1px solid #252a34;white-space:nowrap;">${escapeHtml(String(tx.created_at || "").slice(0, 19).replace("T", " "))}</td>
      <td style="padding:8px;border-bottom:1px solid #252a34;">${escapeHtml(tx.kind)}</td>
      <td style="padding:8px;border-bottom:1px solid #252a34;">${fmtMoney(tx.amount_cents || 0)}</td>
      <td style="padding:8px;border-bottom:1px solid #252a34;">${escapeHtml(detail)}</td>
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

    summaryEl.innerHTML = "<div>Loading...</div>";
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
      txEl.innerHTML = rows.length ? rows.map(txRow).join("") : '<tr><td colspan="4" style="padding:8px;">No transactions</td></tr>';
    } catch (_) {
      summaryEl.innerHTML = '<div style="color:#ff6b6b;">Finance report failed.</div>';
      txEl.innerHTML = '<tr><td colspan="4" style="padding:8px;color:#ff6b6b;">Failed to load transactions</td></tr>';
    }
  }

  refreshBtn?.addEventListener("click", refresh);
  refresh();
}
