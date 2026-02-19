/* SPDX-License-Identifier: AGPL-3.0-or-later */
import { apiGet, apiPost } from "../api.js";

let _container = null;
let _root = null;
let _handlers = [];
let _state = {
  selectedRange: "30d",
  movements: [],
  amountBySourceId: new Map(),
};

function cleanupHandlers() {
  for (const off of _handlers) {
    try { off(); } catch (_) {}
  }
  _handlers = [];
}

function wire(el, event, fn) {
  el.addEventListener(event, fn);
  _handlers.push(() => el.removeEventListener(event, fn));
}

function todayYmd() {
  return new Date().toISOString().slice(0, 10);
}

function rangeToDates(rangeKey) {
  const now = new Date();
  const end = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const start = new Date(end);
  if (rangeKey === "7d") start.setDate(start.getDate() - 6);
  else if (rangeKey === "30d") start.setDate(start.getDate() - 29);
  else if (rangeKey === "90d") start.setDate(start.getDate() - 89);
  else if (rangeKey === "ytd") start.setMonth(0, 1);
  else if (rangeKey === "all") start.setFullYear(1970, 0, 1);
  return {
    from: start.toISOString().slice(0, 10),
    to: end.toISOString().slice(0, 10),
  };
}

function money(cents) {
  const n = Number(cents);
  if (!Number.isFinite(n)) return "$0.00";
  return `$${(n / 100).toFixed(2)}`;
}

function percent(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return "0.0%";
  return `${n.toFixed(1)}%`;
}

function setText(role, text) {
  const el = _root?.querySelector(`[data-role="${role}"]`);
  if (el) el.textContent = text;
}

function setStatus(message, bad = false) {
  const el = _root?.querySelector('[data-role="finance-status"]');
  if (!el) return;
  el.textContent = message || "";
  el.style.color = bad ? "var(--bad)" : "var(--muted)";
}

function renderMovements() {
  const body = _root?.querySelector('[data-role="finance-rows"]');
  if (!body) return;
  body.replaceChildren();

  const rows = (_state.movements || []).filter((m) => ["sold", "refund", "expense", "other_income"].includes(String(m.source_kind || "")));

  if (!rows.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = '<td colspan="5" class="muted">No finance events in this range.</td>';
    body.appendChild(tr);
    return;
  }

  for (const m of rows) {
    const tr = document.createElement("tr");
    tr.style.cursor = m.source_id ? "pointer" : "default";
    const amount = m.source_id ? _state.amountBySourceId.get(m.source_id) : null;
    const createdAt = String(m.created_at || "").replace("T", " ").slice(0, 19) || "—";
    tr.innerHTML = `
      <td>${createdAt || "—"}</td>
      <td>${m.source_kind || "—"}</td>
      <td>${amount == null ? "—" : money(amount)}</td>
      <td>${m.item_id == null ? "—" : String(m.item_id)}</td>
      <td>${m.source_id || "—"}</td>
    `;
    if (m.source_id) {
      wire(tr, "click", () => openDrawer(m.source_id));
    }
    body.appendChild(tr);
  }
}

async function loadAmountsForRows(rows) {
  _state.amountBySourceId = new Map();
  const seen = new Set();
  for (const row of rows) {
    const sid = row?.source_id;
    if (!sid || seen.has(sid)) continue;
    seen.add(sid);
    try {
      const trace = await apiGet(`/finance/cash-event/${encodeURIComponent(sid)}`);
      const amount = trace?.cash_event?.amount_cents;
      if (typeof amount === "number") _state.amountBySourceId.set(sid, amount);
    } catch (_) {
      // keep row amount as unavailable
    }
  }
}

async function refreshAll() {
  const { from, to } = rangeToDates(_state.selectedRange);
  setStatus("Loading…", false);
  try {
    const [profit, movementsResp] = await Promise.all([
      apiGet(`/finance/profit?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`),
      apiGet(`/ledger/movements?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}&limit=200`),
    ]);

    setText("gross", money(profit?.gross_revenue_cents));
    setText("refunds", money(profit?.refunds_cents));
    setText("net", money(profit?.net_revenue_cents));
    setText("cogs", money(profit?.cogs_cents));
    setText("gp", money(profit?.gross_profit_cents));
    setText("margin", percent(profit?.margin_percent));

    _state.movements = Array.isArray(movementsResp?.movements) ? movementsResp.movements : [];
    await loadAmountsForRows(_state.movements);
    renderMovements();

    setStatus(`Window: ${from} → ${to}`);
  } catch (err) {
    setStatus(`Load failed: ${err?.message || "unknown_error"}`, true);
    setText("gross", "$0.00");
    setText("refunds", "$0.00");
    setText("net", "$0.00");
    setText("cogs", "$0.00");
    setText("gp", "$0.00");
    setText("margin", "0.0%");
    _state.movements = [];
    renderMovements();
  }
}

function closeDrawer() {
  const drawer = _root?.querySelector('[data-role="finance-drawer"]');
  if (!drawer) return;
  drawer.classList.add("hidden");
  drawer.setAttribute("aria-hidden", "true");
}

async function openDrawer(sourceId) {
  const drawer = _root?.querySelector('[data-role="finance-drawer"]');
  const body = _root?.querySelector('[data-role="finance-drawer-body"]');
  if (!drawer || !body) return;

  drawer.classList.remove("hidden");
  drawer.setAttribute("aria-hidden", "false");
  body.textContent = "Loading…";
  try {
    const trace = await apiGet(`/finance/cash-event/${encodeURIComponent(sourceId)}`);
    const ev = trace?.cash_event || {};
    const linked = Array.isArray(trace?.linked_movements) ? trace.linked_movements : [];

    const wrap = document.createElement("div");
    wrap.className = "stack";
    wrap.innerHTML = `
      <div class="kv"><span class="k">Kind</span><span class="v">${ev.kind || "—"}</span></div>
      <div class="kv"><span class="k">Amount</span><span class="v">${money(ev.amount_cents)}</span></div>
      <div class="kv"><span class="k">Source</span><span class="v">${ev.source_id || "—"}</span></div>
      <div class="kv"><span class="k">Created</span><span class="v">${ev.created_at || "—"}</span></div>
      <div class="kv"><span class="k">Computed COGS</span><span class="v">${money(trace?.computed_cogs_cents)}</span></div>
      <div class="kv"><span class="k">Net Profit</span><span class="v">${money(trace?.net_profit_cents)}</span></div>
      <h4 class="mt">Linked movements</h4>
    `;

    const list = document.createElement("ul");
    list.className = "list";
    for (const m of linked) {
      const li = document.createElement("li");
      li.textContent = `item=${m.item_id} qty=${m.qty_change} unit_cost_cents=${m.unit_cost_cents}`;
      list.appendChild(li);
    }
    if (!linked.length) {
      const li = document.createElement("li");
      li.textContent = "No linked movements";
      list.appendChild(li);
    }
    wrap.appendChild(list);

    body.replaceChildren(wrap);
  } catch (err) {
    body.textContent = `Failed to load details: ${err?.message || "unknown_error"}`;
  }
}

function closeExpenseModal() {
  const m = _root?.querySelector('[data-role="expense-modal"]');
  if (!m) return;
  m.classList.add("hidden");
  m.setAttribute("aria-hidden", "true");
}

function openExpenseModal() {
  const m = _root?.querySelector('[data-role="expense-modal"]');
  if (!m) return;
  m.classList.remove("hidden");
  m.setAttribute("aria-hidden", "false");
  const dateInput = _root?.querySelector('[name="expense-created-at"]');
  if (dateInput) dateInput.value = todayYmd();
}

async function submitExpense(evt) {
  evt.preventDefault();
  const form = evt.currentTarget;
  const amountRaw = form.querySelector('[name="expense-amount"]')?.value || "0";
  const category = form.querySelector('[name="expense-category"]')?.value || null;
  const notes = form.querySelector('[name="expense-notes"]')?.value || null;

  const amountNum = Number(amountRaw);
  if (!Number.isFinite(amountNum) || amountNum <= 0) {
    setStatus("Expense amount must be greater than zero.", true);
    return;
  }

  const amount_cents = Math.round(amountNum * 100);
  try {
    await apiPost("/finance/expense", { amount_cents, category, notes });
    closeExpenseModal();
    await refreshAll();
  } catch (err) {
    setStatus(`Expense save failed: ${err?.message || "unknown_error"}`, true);
  }
}

function render() {
  const root = document.createElement("div");
  root.setAttribute("data-role", "finance-root");
  root.className = "stack";

  root.innerHTML = `
    <div class="card">
      <div class="row-compact" style="justify-content:space-between;align-items:center;">
        <h2 style="margin:0;">Finance</h2>
        <button class="btn" data-role="open-expense" type="button">Record Expense</button>
      </div>
      <div class="row-compact" style="margin-top:8px;gap:8px;flex-wrap:wrap;" data-role="range-buttons">
        <button class="btn" data-range="7d" type="button">7D</button>
        <button class="btn" data-range="30d" type="button">30D</button>
        <button class="btn" data-range="90d" type="button">90D</button>
        <button class="btn" data-range="ytd" type="button">YTD</button>
        <button class="btn" data-range="all" type="button">All</button>
      </div>
      <div class="muted" data-role="finance-status" style="margin-top:8px;"></div>
    </div>

    <div class="metric-grid">
      <div class="metric-card"><div class="muted">Gross Revenue</div><div data-role="gross">$0.00</div></div>
      <div class="metric-card"><div class="muted">Refunds</div><div data-role="refunds">$0.00</div></div>
      <div class="metric-card"><div class="muted">Net Revenue</div><div data-role="net">$0.00</div></div>
      <div class="metric-card"><div class="muted">COGS</div><div data-role="cogs">$0.00</div></div>
      <div class="metric-card"><div class="muted">Gross Profit</div><div data-role="gp">$0.00</div></div>
      <div class="metric-card"><div class="muted">Margin %</div><div data-role="margin">0.0%</div></div>
    </div>

    <div class="card">
      <h3 style="margin-top:0;">Cash Events</h3>
      <div class="table-wrap">
        <table>
          <thead>
            <tr><th>Date</th><th>Type</th><th>Amount</th><th>Item</th><th>Notes</th></tr>
          </thead>
          <tbody data-role="finance-rows"></tbody>
        </table>
      </div>
    </div>

    <aside data-role="finance-drawer" class="drawer hidden" aria-hidden="true" role="dialog" aria-label="Finance event details">
      <div class="drawer-backdrop" data-role="close-finance-drawer"></div>
      <div class="drawer-panel">
        <header class="drawer-header">
          <h3 style="margin:0;">Cash Event</h3>
          <button type="button" class="btn" data-role="close-finance-drawer">Close</button>
        </header>
        <section class="drawer-body" data-role="finance-drawer-body"></section>
      </div>
    </aside>

    <div data-role="expense-modal" class="modal hidden" aria-hidden="true">
      <div class="modal-backdrop" data-role="close-expense-modal"></div>
      <div class="modal-content">
        <h3 style="margin-top:0;">Record Expense</h3>
        <form data-role="expense-form" class="stack">
          <label>Amount (USD)<input name="expense-amount" type="number" step="0.01" min="0.01" required /></label>
          <label>Category<input name="expense-category" type="text" /></label>
          <label>Notes<textarea name="expense-notes"></textarea></label>
          <div class="row-compact" style="justify-content:flex-end;">
            <button class="btn" type="button" data-role="close-expense-modal">Cancel</button>
            <button class="btn" type="submit">Save</button>
          </div>
        </form>
      </div>
    </div>
  `;

  return root;
}

export async function mount(container) {
  if (!container) return;
  _container = container;
  _root = render();
  _container.replaceChildren(_root);

  const btns = _root.querySelectorAll("[data-range]");
  for (const btn of btns) {
    wire(btn, "click", async () => {
      _state.selectedRange = btn.getAttribute("data-range") || "30d";
      await refreshAll();
    });
  }

  const openExpense = _root.querySelector('[data-role="open-expense"]');
  if (openExpense) wire(openExpense, "click", openExpenseModal);

  for (const closer of _root.querySelectorAll('[data-role="close-expense-modal"]')) {
    wire(closer, "click", closeExpenseModal);
  }

  for (const closer of _root.querySelectorAll('[data-role="close-finance-drawer"]')) {
    wire(closer, "click", closeDrawer);
  }

  const form = _root.querySelector('[data-role="expense-form"]');
  if (form) wire(form, "submit", submitExpense);

  await refreshAll();
}

export function unmount() {
  cleanupHandlers();
  closeDrawer();
  closeExpenseModal();
  if (_container) _container.replaceChildren();
  _container = null;
  _root = null;
  _state = { selectedRange: "30d", movements: [], amountBySourceId: new Map() };
}
