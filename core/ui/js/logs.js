import { apiGet } from "./api.js";

let _cursor = null;
let _loading = false;

function rowEl(ev) {
  const dt = new Date(ev.ts);
  const dateStr = dt.toLocaleDateString();
  const timeStr = dt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

  let summary = "";
  if (ev.domain === "inventory") {
    const sign = (ev.qty_change ?? 0) >= 0 ? "+" : "";
    summary = `${ev.kind} • item #${ev.item_id} • ${sign}${ev.qty_change} ea`;
  } else if (ev.domain === "manufacturing") {
    const name = ev.recipe_name || (ev.recipe_id != null ? `Recipe #${ev.recipe_id}` : "ad-hoc");
    summary = `run • ${name} • x${ev.output_qty}`;
  } else if (ev.domain === "recipes") {
    summary = `${ev.kind} • ${ev.recipe_name || `(id ${ev.recipe_id})`}`;
  } else {
    summary = ev.kind || ev.domain || "event";
  }

  const row = document.createElement("div");
  row.className = "logs-row";

  const when = document.createElement("div");
  when.className = "logs-col when";
  when.textContent = `${dateStr} ${timeStr}`;

  const domain = document.createElement("div");
  domain.className = "logs-col domain";
  domain.textContent = String(ev.domain ?? "");

  const summaryCol = document.createElement("div");
  summaryCol.className = "logs-col summary";
  summaryCol.textContent = summary;

  row.append(when, domain, summaryCol);
  return row;
}

async function fetchMore(root) {
  if (_loading) return;
  _loading = true;
  try {
    const url = _cursor
      ? `/app/logs?limit=200&cursor_id=${encodeURIComponent(_cursor)}`
      : "/app/logs?limit=200";

    const { events, next_cursor_id } = await apiGet(url);
    const body = root.querySelector('[data-role="logs-body"]');
    const more = root.querySelector('[data-role="logs-more"]');
    if (!body) return;

    if (!events || !events.length) {
      if (!body.children.length) {
        body.innerHTML = "";
        const empty = document.createElement("div");
        empty.className = "logs-empty";
        empty.textContent = "No logs.";
        body.append(empty);
      }
      if (more) more.classList.add("hidden");
      return;
    }

    const frag = document.createDocumentFragment();
    events.forEach((ev) => frag.appendChild(rowEl(ev)));
    body.appendChild(frag);

    _cursor = next_cursor_id || null;
    if (more) {
      more.classList.toggle("hidden", !_cursor);
    }
  } finally {
    _loading = false;
  }
}

export function mountLogsPage(root) {
  root.classList.add("logs-shell");
  root.innerHTML = `
    <div class="card logs-card">
      <div class="card-title logs-title">Logs</div>
      <div class="logs-wrap">
        <div class="logs-head"><div>Date/Time</div><div>Domain</div><div>Summary</div></div>
        <div class="logs-scroller" data-role="logs-scroll">
          <div data-role="logs-body"></div>
          <div data-role="logs-more" class="logs-load">Load older…</div>
        </div>
      </div>
    </div>
  `;

  const more = root.querySelector('[data-role="logs-more"]');
  if (more) {
    more.addEventListener("click", () => {
      void fetchMore(root);
    });
  }

  const sc = root.querySelector('[data-role="logs-scroll"]');
  if (sc) {
    sc.addEventListener("scroll", () => {
      if (!_cursor) return;
      if (sc.scrollTop + sc.clientHeight >= sc.scrollHeight - 10) {
        void fetchMore(root);
      }
    });
  }

  _cursor = null;
  _loading = false;
  const body = root.querySelector('[data-role="logs-body"]');
  if (body) body.innerHTML = "";

  fetchMore(root).catch(() => {
    const firstLoadBody = root.querySelector('[data-role="logs-body"]');
    if (firstLoadBody && !firstLoadBody.children.length) {
      const err = document.createElement("div");
      err.className = "logs-empty";
      err.textContent = "Failed to load logs (endpoint unavailable).";
      firstLoadBody.append(err);
    }
  });
}
