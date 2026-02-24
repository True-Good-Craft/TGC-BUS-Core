/* SPDX-License-Identifier: AGPL-3.0-or-later */
/* core/ui/js/routes/home.js */
import { registerRoute } from "../router.js";
import { rawFetch } from "../api.js";

function ensureHomeStyles() {
  const id = "bus-home-styles";
  if (document.getElementById(id)) return;
  const css = `
  .bus-home { --bg:#1e1f22; --panel:#11151b; --panel2:#0f1318; --text:#e6e6e6; --muted:#a9b7c8;
    --line:#243041; --accent:#6aa9ff; --warn:#ffcc66; --good:#7ee787; --bad:#ff7b72;
    --shadow: 0 10px 25px rgba(0,0,0,.35); --radius:10px; --pad:18px; --max:1100px; }
  .bus-home{ background:var(--bg); color:var(--text); }
  .bus-home *{ box-sizing:border-box; }
  .bus-home a{ color:var(--accent); text-decoration:none; }
  .bus-home a:hover{ text-decoration:underline; }
  .bus-home .wrap{ max-width:var(--max); margin:0 auto; padding:28px 18px 60px; }
  .bus-home header{ display:flex; align-items:flex-start; justify-content:space-between; gap:16px; margin-bottom:18px; }
  .bus-home .brand h1{ margin:0; font-size:28px; letter-spacing:.2px; }
  .bus-home .brand p{ margin:8px 0 0; color:var(--muted); line-height:1.35; max-width:60ch; }
  .bus-home .meta{ text-align:right; color:var(--muted); font-size:13px; line-height:1.4;
    padding:10px 12px; border:1px solid var(--line); border-radius:10px; background:rgba(17,21,27,.55); min-width:220px; }
  .bus-home .meta code{ color:var(--text); background:rgba(255,255,255,.06); padding:2px 6px; border-radius:8px; }
  .bus-home .grid{ display:grid; grid-template-columns: 1.2fr .8fr; gap:16px; margin-top:16px; }
  @media (max-width: 920px){ .bus-home header{ flex-direction:column; } .bus-home .meta{ text-align:left; width:fit-content; } .bus-home .grid{ grid-template-columns:1fr; } }
  .bus-home .card{ background:linear-gradient(180deg, rgba(17,21,27,.9), rgba(15,19,24,.9)); border:1px solid var(--line);
    border-radius:var(--radius); box-shadow:var(--shadow); padding:var(--pad); }
  .bus-home .card h2{ margin:0 0 10px; font-size:16px; letter-spacing:.2px; }
  .bus-home .sub{ color:var(--muted); font-size:13px; margin:0 0 12px; line-height:1.45; }
  .bus-home .diagram{ border:1px dashed rgba(169,183,200,.35); border-radius:12px; background:rgba(0,0,0,.18); padding:12px; overflow:auto; }
  .bus-home pre{ margin:0; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono","Courier New", monospace;
    font-size:13px; line-height:1.45; color:#dbe7f7; white-space:pre; }
  .bus-home .list{ margin:10px 0 0; padding-left:18px; color:var(--muted); }
  .bus-home .list li{ margin:8px 0; }
  .bus-home .list strong{ color:var(--text); font-weight:600; }
  .bus-home .checklist{ display:flex; flex-direction:column; gap:10px; margin-top:12px; padding-left:0; list-style:none; }
  .bus-home .check{ display:flex; gap:10px; align-items:flex-start; padding:10px 12px; border-radius:12px;
    border:1px solid rgba(36,48,65,.75); background:rgba(0,0,0,.15); }
  .bus-home .dot{ width:10px; height:10px; border-radius:50%; margin-top:5px; background:rgba(126,231,135,.9); box-shadow:0 0 0 3px rgba(126,231,135,.12); flex:0 0 auto; }
  .bus-home .check p{ margin:0; color:var(--muted); line-height:1.35; }
  .bus-home .check p strong{ color:var(--text); }
  .bus-home .launchpad{ display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-top:10px; }
  @media (max-width: 520px){ .bus-home .launchpad{ grid-template-columns:1fr; } }
  .bus-home .btn{ display:flex; align-items:center; justify-content:space-between; gap:10px; padding:12px 12px; border-radius:10px;
    border:1px solid rgba(36,48,65,.85); background:rgba(0,0,0,.18); color:var(--text); text-decoration:none;
    transition: transform .06s ease, background .12s ease, border-color .12s ease; }
  .bus-home .btn:hover{ background: rgba(106,169,255,.10); border-color: rgba(106,169,255,.55); transform: translateY(-1px); text-decoration:none; }
  .bus-home .btn .label{ display:flex; align-items:center; gap:10px; font-weight:600; }
  .bus-home .btn .hint{ color: var(--muted); font-size:12px; }
  .bus-home .pill{ display:inline-block; padding:4px 8px; border-radius:999px; border:1px solid rgba(36,48,65,.85); background:rgba(255,255,255,.06); font-size:12px; color:var(--muted); }
  .bus-home .warn{ border-color: rgba(255,204,102,.45); background: rgba(255,204,102,.08); }
  .bus-home .warn strong{ color: var(--warn); }
  .bus-home .limits ul{ margin:10px 0 0; padding-left:18px; color:var(--muted); }
  .bus-home .limits li{ margin:8px 0; }
  .bus-home footer{ margin-top:16px; display:flex; flex-wrap:wrap; gap:10px; align-items:center; justify-content:space-between; color:var(--muted); font-size:13px; }
  .bus-home .links{ display:flex; flex-wrap:wrap; gap:12px; }
  .bus-home .kbd{ font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono","Courier New", monospace; font-size:12px;
    padding:2px 6px; border:1px solid rgba(36,48,65,.85); border-bottom-color:rgba(36,48,65,.95); border-radius:8px; background:rgba(0,0,0,.2); color:var(--text); }
  `;
  const style = document.createElement("style");
  style.id = id;
  style.textContent = css;
  document.head.appendChild(style);
}

async function setVersionInto(el) {
  try {
    const res = await rawFetch("/openapi.json", { credentials: "include" });
    const j = await res.json();
    if (j?.info?.version) {
      el.textContent = j.info.version;
      return;
    }
  } catch {}
  // Fallback: try shell header version if present
  const shell = document.querySelector('[data-role="ui-version"]');
  if (shell && shell.textContent.trim()) el.textContent = shell.textContent.trim();
}

function renderHome(root) {
  ensureHomeStyles();
  document.title = "BUS Core — Home";
  root.innerHTML = `
  <main class="bus-home" role="main">
    <div class="wrap">
      <header>
        <div class="brand">
          <h1>BUS Core</h1>
          <p>Local-first business core for small workshops. Tracks inventory, builds products, and calculates costs. No cloud. No subscriptions.</p>
        </div>
        <div class="meta" aria-label="Status">
          <div><span class="pill">Beta</span></div>
          <div style="margin-top:8px;">Version: <code id="bus-version">…</code></div>
          <div>Storage: <span class="kbd">Local</span></div>
          <div>Telemetry: <span class="kbd">Off</span></div>
        </div>
      </header>

      <section class="grid">
        <div class="card">
          <h2>How BUS-Core Thinks</h2>
          <p class="sub">If you understand this flow, you’ll stop fighting the app.</p>
          <div class="diagram" aria-label="BUS Core mental model diagram">
            <pre>Supplies  →  Blueprints  →  Assemblies / Products
   ↑             ↓                ↓
 Inventory     Costing         Pricing</pre>
          </div>
          <ul class="list">
            <li><strong>Supplies</strong> = raw materials &amp; consumables you buy.</li>
            <li><strong>Blueprints</strong> = recipes (what + how much).</li>
            <li><strong>Assemblies / Products</strong> = things you make or sell.</li>
            <li>Costs flow <strong>forward</strong>. Inventory flows <strong>down</strong>. Nothing is automatic magic.</li>
          </ul>
        </div>

        <div class="card">
          <h2>First-Time Setup</h2>
          <p class="sub">Do these in order. Don’t freestyle it.</p>
          <ol class="checklist">
            <li class="check"><span class="dot" aria-hidden="true"></span><p><strong>Add your Supplies</strong><br><span>name, unit, cost, starting quantity.</span></p></li>
            <li class="check"><span class="dot" aria-hidden="true"></span><p><strong>Create a Blueprint</strong><br><span>choose supplies + quantities.</span></p></li>
            <li class="check"><span class="dot" aria-hidden="true"></span><p><strong>Build an Assembly or Product</strong><br><span>costs are calculated from the blueprint.</span></p></li>
            <li class="check"><span class="dot" aria-hidden="true"></span><p><strong>Adjust Inventory</strong><br><span>stock in, consumption, corrections.</span></p></li>
          </ol>
          <div class="card warn" style="margin-top:12px; box-shadow:none;">
            <h2 style="margin-bottom:6px;">Reality Check</h2>
            <p class="sub" style="margin:0;"><strong>BUS-Core does not guess.</strong> If numbers are wrong, check your inputs.</p>
          </div>
        </div>
      </section>

      <section class="grid" style="margin-top:16px;">
        <div class="card">
          <h2>Common Tasks</h2>
          <p class="sub">Big buttons. No treasure hunt.</p>
          <nav class="launchpad" role="navigation" aria-label="Common tasks">
            <a class="btn" href="#/inventory" data-route="inventory">
              <span class="label">➕ Add Supply</span><span class="hint">Create material/consumable</span>
            </a>
            <a class="btn" href="#/recipes" data-route="recipes">
              <span class="label">🧱 Create Blueprint</span><span class="hint">Define recipe &amp; costs</span>
            </a>
            <a class="btn" href="#/runs" data-route="runs">
              <span class="label">🛠 Build Product</span><span class="hint">Assembly / finished good</span>
            </a>
            <a class="btn" href="#/inventory" data-route="inventory-adjust">
              <span class="label">📦 Adjust Inventory</span><span class="hint">Stock in / consume</span>
            </a>
            <a class="btn" href="#/contacts" data-route="contacts">
              <span class="label">👥 Manage Contacts</span><span class="hint">Customers / vendors</span>
            </a>
            <a class="btn" href="#/settings" data-route="settings">
              <span class="label">⚙️ Settings</span><span class="hint">Paths / export / admin</span>
            </a>
          </nav>
        </div>

        <div class="card limits">
          <h2>Known Limits (Beta)</h2>
          <p class="sub">This is here to build trust, not to scare you.</p>
          <ul>
            <li>No cloud sync</li>
            <li>No multi-user access</li>
            <li>No automatic backups (export manually)</li>
            <li>Database changes may require reset during beta</li>
          </ul>
          <div class="card" style="margin-top:12px; box-shadow:none;">
            <h2 style="margin-bottom:6px;">Data Safety</h2>
            <p class="sub" style="margin:0 0 10px;">All data is stored <strong>locally on this machine</strong>. Nothing is transmitted.</p>
            <p class="sub" style="margin:0;">If something breaks during beta:<br>1) Close BUS-Core<br>2) Delete local app data<br>3) Restart</p>
            <p class="sub" style="margin:10px 0 0;"><a href="#/settings">Where is my data stored?</a></p>
          </div>
        </div>
      </section>

      <footer>
        <div>BUS Core · Local-first · No cloud required</div>
        <div class="links" aria-label="Footer links">
          <a href="#/settings">Docs</a>
          <a href="#/settings">Bug Report</a>
          <a href="#/settings">Discord</a>
          <a href="#/settings">License</a>
        </div>
      </footer>
    </div>
  </main>`;
  // Version stamp inside the Home page
  const ver = root.querySelector("#bus-version");
  if (ver) setVersionInto(ver);
}

registerRoute("/home", (root) => {
  // Mount into the SPA app container
  const target = root || document.getElementById("app") || document.body;
  renderHome(target);
});
