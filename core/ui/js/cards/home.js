/* SPDX-License-Identifier: AGPL-3.0-or-later */
import { rawFetch } from '../api.js';

function mountHome() { return renderHome(); }
export { mountHome as default, mountHome };

async function setVersionInto(el) {
  try {
    const res = await rawFetch('/openapi.json', { credentials: 'include' });
    const j = await res.json();
    if (j?.info?.version) {
      el.textContent = j.info.version;
      return;
    }
  } catch {}

  const shell = document.querySelector('[data-role="ui-version"]');
  if (shell && shell.textContent.trim()) {
    el.textContent = shell.textContent.trim();
    return;
  }
  el.textContent = 'unknown';
}

function hostRoot() {
  return document.querySelector('[data-role="home-screen"]')
    || document.querySelector('#app')
    || document.querySelector('#page')
    || document.querySelector('[data-role="page"]')
    || document.querySelector('main')
    || document.body;
}

function renderHome() {
  document.title = 'BUS Core - Home';
  const root = hostRoot();
  if (!root) return;

  // Home owns its own internal card layout; avoid inheriting legacy screen-level card shell.
  root.classList.remove('card');
  root.classList.add('home-screen-host');

  root.innerHTML = `
  <div class="bus-home" role="main">
    <div class="bus-home-wrap">

      <header class="bus-home-header">
        <div class="bus-home-brand">
          <h1>BUS Core</h1>
          <p>Local-first business core for small workshops. Tracks inventory, builds products, and calculates costs. No cloud. No subscriptions.</p>
        </div>
        <div class="bus-home-meta" aria-label="Status">
          <div class="bus-home-meta-row">Version: <code id="bus-version">...</code></div>
          <div class="bus-home-meta-row">Storage: <span class="bus-home-kbd">Local</span></div>
          <div class="bus-home-meta-row">Telemetry: <span class="bus-home-kbd">Off</span></div>
        </div>
      </header>

      <section class="bus-home-grid bus-home-grid--top">
        <div class="card bus-home-card">
          <h2>How BUS Core Thinks</h2>
          <p class="bus-home-sub">If you understand this flow, you'll stop fighting the app.</p>
          <div class="bus-home-diagram" aria-label="BUS Core mental model diagram">
            <pre>Supplies  ->  Blueprints  ->  Assemblies / Products
   ^             v                v
 Inventory     Costing         Pricing</pre>
          </div>
          <ul class="bus-home-list">
            <li><strong>Supplies</strong> = raw materials and consumables you buy.</li>
            <li><strong>Blueprints</strong> = recipes (what + how much).</li>
            <li><strong>Assemblies / Products</strong> = things you make or sell.</li>
            <li>Costs flow <strong>forward</strong>. Inventory flows <strong>down</strong>. Nothing is automatic magic.</li>
          </ul>
        </div>

        <div class="card bus-home-card">
          <h2>First-Time Setup</h2>
          <p class="bus-home-sub">Do these in order. Don't freestyle it.</p>
          <ol class="bus-home-checklist">
            <li class="bus-home-check"><span class="bus-home-dot" aria-hidden="true"></span><p><strong>Add your Supplies</strong><br><span>name, unit, cost, starting quantity.</span></p></li>
            <li class="bus-home-check"><span class="bus-home-dot" aria-hidden="true"></span><p><strong>Create a Blueprint</strong><br><span>choose supplies + quantities.</span></p></li>
            <li class="bus-home-check"><span class="bus-home-dot" aria-hidden="true"></span><p><strong>Build an Assembly or Product</strong><br><span>costs are calculated from the blueprint.</span></p></li>
            <li class="bus-home-check"><span class="bus-home-dot" aria-hidden="true"></span><p><strong>Adjust Inventory</strong><br><span>stock in, consumption, corrections.</span></p></li>
          </ol>
          <div class="bus-home-callout bus-home-callout--warn">
            <h2>Reality Check</h2>
            <p class="bus-home-sub"><strong>BUS Core does not guess.</strong> If numbers are wrong, check your inputs.</p>
          </div>
        </div>
      </section>

      <section class="bus-home-grid bus-home-grid--bottom">
        <div class="card bus-home-card">
          <h2>Common Tasks</h2>
          <p class="bus-home-sub">Big buttons. No treasure hunt.</p>
          <nav class="bus-home-launchpad" role="navigation" aria-label="Common tasks">
            <a class="bus-home-btn" href="#/inventory" data-route="inventory"><span class="bus-home-btn-label">Add Supply</span><span class="bus-home-btn-hint">Create material/consumable</span></a>
            <a class="bus-home-btn" href="#/recipes" data-route="recipes"><span class="bus-home-btn-label">Create Blueprint</span><span class="bus-home-btn-hint">Define recipe and costs</span></a>
            <a class="bus-home-btn" href="#/runs" data-route="runs"><span class="bus-home-btn-label">Build Product</span><span class="bus-home-btn-hint">Assembly / finished good</span></a>
            <a class="bus-home-btn" href="#/inventory" data-route="inventory-adjust"><span class="bus-home-btn-label">Adjust Inventory</span><span class="bus-home-btn-hint">Stock in / consume</span></a>
            <a class="bus-home-btn" href="#/contacts" data-route="contacts"><span class="bus-home-btn-label">Manage Contacts</span><span class="bus-home-btn-hint">Customers / vendors</span></a>
            <a class="bus-home-btn" href="#/settings" data-route="settings"><span class="bus-home-btn-label">Settings</span><span class="bus-home-btn-hint">Paths / export / admin</span></a>
          </nav>
        </div>

        <div class="card bus-home-card bus-home-limits">
          <h2>Known Limits</h2>
          <p class="bus-home-sub">This is here to build trust, not to scare you.</p>
          <ul>
            <li>No cloud sync</li>
            <li>No multi-user access</li>
            <li>No automatic backups (export manually)</li>
            <li>Database changes may require reset during pre-1.0 release</li>
          </ul>
          <div class="bus-home-callout">
            <h2>Data Safety</h2>
            <p class="bus-home-sub">All data is stored <strong>locally on this machine</strong>. Nothing is transmitted.</p>
            <p class="bus-home-sub">If something breaks during pre-1.0 release:<br>1) Close BUS Core<br>2) Delete local app data<br>3) Restart</p>
            <p class="bus-home-sub"><a href="#/settings">Where is my data stored?</a></p>
          </div>
        </div>
      </section>

      <footer class="bus-home-footer">
        <div>BUS Core - Local-first - No cloud required</div>
        <div class="bus-home-links" aria-label="Footer links">
          <a href="#/settings">Docs</a>
          <a href="#/settings">Bug Report</a>
          <a href="#/settings">Discord</a>
          <a href="#/settings">License</a>
        </div>
      </footer>

    </div>
  </div>`;

  const ver = root.querySelector('#bus-version');
  if (ver) setVersionInto(ver);
}
