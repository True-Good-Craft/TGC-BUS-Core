# UI Glowup Branch Notes (Phase 1 Audit)

Branch: fortheemperor  
Date: 2026-03-11  
Scope: Read-only authority audit of `core/ui/css/app.css`, `core/ui/shell.html`, and `core/ui/app.js`.

## 1) Styling Authority Map (Current State)

### Tokens
- Primary authority: `core/ui/css/app.css:3` (`:root` token block with `--bg`, `--surface`, `--border`, `--text`, accents, danger).
- Drift/secondary authority: `core/ui/shell.html:10` (`:root` redefines `--bg`, `--fg`, `--accent`, `--sidebar` in inline `<style>`).
- Token mismatch risk: `core/ui/css/app.css:54`, `core/ui/css/app.css:55`, `core/ui/css/app.css:85`, `core/ui/css/app.css:86` use `--border-color` and `--card-bg`, but these are not defined in app.css root token block.

### Shell / Layout
- Shared authority split:
- `core/ui/shell.html:12` body app frame layout (`display:flex;height:100vh`).
- `core/ui/shell.html:22` main region padding/scroll.
- `core/ui/css/app.css:19` body background/grid texture and base color.
- Result: shell/layout authority is mixed across app.css and shell inline style.

### Sidebar / Navigation
- In shell inline style:
- `core/ui/shell.html:13` sidebar surface/width/border.
- `core/ui/shell.html:15`-`core/ui/shell.html:21` tab/nav-group styles.
- `core/ui/shell.html:67` onward more sidebar/nav centering and hover rules.
- In canonical CSS:
- `core/ui/css/app.css:329`-`core/ui/css/app.css:401` brand, sidebar overflow, nav section styles.
- Result: sidebar/nav authority is duplicated and split.

### Cards
- Canonical candidate: `core/ui/css/app.css:37` `.card` base (surface/border/radius/shadow).
- Competing style: `core/ui/shell.html:23` `.card` redefined with different background/radius/no border.
- Runtime card injection: `core/ui/app.js:486` and `core/ui/app.js:648` insert `.card` via `innerHTML`, including inline sizing/margins.

### Forms
- Canonical baseline: `core/ui/css/app.css:127` inputs/select/textarea; `core/ui/css/app.css:223` form grid; `core/ui/css/app.css:414` inline check.
- Modal form structure in shell markup: `core/ui/shell.html:229` onward (`.field`, `.modal-footer`, etc.) with no complete centralized form-system mapping shown in shell style.
- Runtime inline form-related content: `core/ui/app.js:603` and welcome flow block `core/ui/app.js:647` onward.

### Buttons
- Canonical baseline: `core/ui/css/app.css:103` `button`, plus variants at `core/ui/css/app.css:107`, `core/ui/css/app.css:108`, `core/ui/css/app.css:270`, `core/ui/css/app.css:271`.
- Competing shell authority: `core/ui/shell.html:25` global `button`; `core/ui/shell.html:31` tabs button variant.
- Runtime-generated unclassed/partially classed buttons in app.js (`renderDemoBanner`, welcome template) rely on whichever global button styles currently win.

### Page-specific styling
- app.css includes many page/feature-specific rules:
- Inventory hard-targeting by data-role and nth-child columns: `core/ui/css/app.css:274`-`core/ui/css/app.css:313`.
- Legacy hiding rules: `core/ui/css/app.css:294`, `core/ui/css/app.css:297`.
- EULA onboarding: `core/ui/css/app.css:46`-`core/ui/css/app.css:75`.
- Shell also contains page-specific inline styles in markup, especially contacts and drawer headers: `core/ui/shell.html:181`-`core/ui/shell.html:190`, `core/ui/shell.html:306`-`core/ui/shell.html:307`.

## 2) Drift Inventory

### Inline CSS (direct blockers)
- Central inline stylesheet still active in shell: `core/ui/shell.html:9`.
- Element-level inline style attributes in shell:
- `core/ui/shell.html:124`, `core/ui/shell.html:181`, `core/ui/shell.html:182`, `core/ui/shell.html:185`, `core/ui/shell.html:188`-`core/ui/shell.html:190`, `core/ui/shell.html:210`, `core/ui/shell.html:306`, `core/ui/shell.html:307`.
- Runtime inline style attributes in JS templates:
- `core/ui/app.js:603`, `core/ui/app.js:648`-`core/ui/app.js:661`.

### Duplicated component styles
- Card base duplicated:
- app.css `.card`: `core/ui/css/app.css:37`.
- shell inline `.card`: `core/ui/shell.html:23`.
- Button base duplicated:
- app.css `button`: `core/ui/css/app.css:103`.
- shell inline `button`: `core/ui/shell.html:25`.
- Modal system overlap in naming/patterns:
- app.css `.modal`, `.modal-content`, `.modal-overlay`, `.modal-card`: `core/ui/css/app.css:174`, `core/ui/css/app.css:184`, `core/ui/css/app.css:250`, `core/ui/css/app.css:259`.
- shell defines modal behavior/parts again in inline style: `core/ui/shell.html:34`-`core/ui/shell.html:37`.
- Sidebar/nav overlap:
- shell inline `#sidebar`, `.nav-group`, tab styles: `core/ui/shell.html:13`-`core/ui/shell.html:21`, `core/ui/shell.html:67` onward.
- app.css nav section/brand/sidebar overflow: `core/ui/css/app.css:329` onward.

### One-off selectors and high-coupling selectors
- Data-role and nth-child coupled table layout (inventory): `core/ui/css/app.css:274`-`core/ui/css/app.css:313`.
- Legacy suppression selectors using `!important`: `core/ui/css/app.css:294`, `core/ui/css/app.css:297`.
- ID-specific styling (EULA, qty preview): `core/ui/css/app.css:50`, `core/ui/css/app.css:404`.

### Runtime markup/class patterns blocking standardization
- JS renders full HTML fragments with style attributes instead of class-only composition:
- `core/ui/app.js:647` (welcome host template with multiple inline styles).
- JS route handlers repeatedly toggle many screen nodes with manual `.hidden` mutations (`showContacts`, `showInventory`, `showManufacturing`, `showSettings`, `showLogs`, `showFinance`, `showRecipes`, `showNotFound`, `showRuns`, `showImport`, `showWelcome` starting around `core/ui/app.js:352` through `core/ui/app.js:729`).
- This creates structural inconsistency and makes page shell standardization harder because each route owns visibility details.

## 3) Recommended Lowest-Risk Migration Order (Toward app.css Authority)

1. Token alignment and safety
- In app.css, define missing token aliases (`--border-color`, `--card-bg`) to current values before moving rules.
- Keep visual output stable while preventing unresolved var fallbacks.

2. Freeze shell inline authority by migrating only duplicated globals first
- Migrate shell inline global primitives to app.css equivalents (body frame, `#sidebar`, `#main`, `.card`, global `button`, `.tabs` button).
- Do not remove shell rules until each migrated rule is confirmed in app.css with equal or stronger specificity.

3. Sidebar/navigation consolidation
- Consolidate shell sidebar/tab/nav-group rules into app.css under one nav section.
- Preserve existing class names/IDs and data-role hooks during this pass (no behavior changes).

4. Modal/drawer normalization
- Merge overlapping modal definitions into one canonical modal system in app.css, retaining current class hooks used by shell/app.js.
- Keep drawer visuals but move any remaining shell-owned drawer style into app.css.

5. Inline style attribute extraction from shell markup
- Replace shell element-level `style="..."` with semantic classes (contacts header row, table headers, recipes title, drawer header controls, version stamp).
- Add only minimal new classes needed; avoid restructuring DOM in this phase.

6. Runtime template cleanup in app.js (class hooks only)
- For welcome/demo templates, replace inline style attributes with reusable classes already defined in app.css.
- Keep route/render behavior exactly as-is.

7. Page-specific hard-coupling reduction (after shared system is stable)
- Inventory-specific nth-child/data-role selectors and legacy hide rules stay until shared table/card/form patterns are fully established.
- Then migrate to component-level classes and prune legacy selectors safely.

## Known Remaining Drift After Phase 1 (Expected)
- shell.html still owns a significant inline `<style>` block.
- app.js still injects inline-styled templates.
- app.css contains mixed global tokens plus page-specific/legacy selectors; authority exists but not yet exclusive.

## Phase 2A Update (Token Safety + Canonical Foundation)

Completed in `core/ui/css/app.css` only.

- Token issues fixed:
- Added safe legacy aliases in `:root`: `--border-color` and `--card-bg`.
- Added non-breaking foundation aliases/scales to support canonicalization without changing active behavior (`--surface-1`, `--surface-2`, `--text-muted`, radius/shadow tokens).
- Added explicit section headers to improve canonical authority readability: tokens, base, shell layout, navigation, cards, forms, buttons, utilities/status, page patterns, responsive.

- Undefined aliases resolved:
- `var(--border-color)` now resolves via `--border-color: var(--border)`.
- `var(--card-bg)` now resolves via `--card-bg: var(--surface)`.

- Remaining token-risk items for later:
- Duplicate/conflicting `:root` token authority still exists in `core/ui/shell.html` inline `<style>` and must be reconciled in later migration phases.
- Some hard-coded color literals remain in app.css and should eventually be mapped to canonical tokens once shared component migration is complete.

## Phase 2B Update (Shared Global Authority Migration)

Completed in `core/ui/css/app.css` and `core/ui/shell.html` only.

- Migrated rule groups to canonical authority in app.css:
- Shell/layout baseline: body frame (`display:flex`, sizing, font, background/color), global box sizing, `#sidebar` frame, `#main` content area.
- Sidebar/nav baseline: `#sidebar .sidebar-nav` list reset, top-level nav link box model/hover/active, `#sidebar .nav-group` baseline and centered submenu link treatment.
- Card baseline: `.card` and `.card h2` moved to app.css authority with current shell-equivalent values.
- Button baseline: base `button` and `button:hover` moved to app.css authority with current shell-equivalent values.

- Intentionally deferred shell style groups:
- Inline `:root` overrides in shell (`--bg`, `--fg`, `--accent`, `--sidebar`) left in place for now to avoid color-token regression during this pass.
- `.tab`, `.tabs`, `.tab-panel` styles left in shell for later nav/page-pattern consolidation.
- Modal/drawer rule block left in shell for Phase 3/4 style-system consolidation.
- `pre`, `.hidden`, `.brand-inline`, logo helper styles left in shell (not part of this shared-global migration slice).

- Remaining risky shell-owned styling:
- Shell still contains meaningful visual authority in inline `<style>` for tabs and modal/drawer systems.
- Shell `:root` token overrides still compete with app.css tokens and should be reconciled in a dedicated token unification pass.

## Phase 3A Update (Forms/Modal/Drawer/Helpers Authority Cleanup)

Completed in `core/ui/css/app.css` and `core/ui/shell.html` only.

- Migrated groups to app.css canonical authority:
- Modal baseline mechanics: `.modal.hidden`, `.modal.open`, `.modal .modal-backdrop`, `.modal .modal-dialog`.
- Drawer baseline mechanics and shared drawer content patterns: `.drawer`, `.drawer-panel`, `.drawer-header`, `.drawer-body`, `.drawer-body .kv`, `.drawer-body .list`, and related state selectors.
- Shared helper/utility groups: `.hidden`, `pre`, `.brand-inline`, `.small-dot-icon`, `.app-logo`, `.brand-nav`, `.hero-logo`, plus helper media rules for logo sizing.

- Deferred shell groups (intentionally left in inline style):
- Shell token overrides in `:root` (`--bg`, `--fg`, `--accent`, `--sidebar`).
- Tab/tabs/page-panel rules: `.tab`, `.tabs`, `.tabs button`, `.tabs button.active`, `.tab-panel`.
- `#sidebar h1` legacy heading rule (kept until sidebar/header normalization pass).

- Remaining shell-owned styling risk after this pass:
- Inline `<style>` still carries meaningful authority for token overrides and tabs behavior-coupled visuals.
- Until token overrides are reconciled, shell can still influence global color primitives ahead of app.css defaults.

## Phase 3B Update (app.js Inline Presentation Cleanup)

Completed in `core/ui/app.js` and `core/ui/css/app.css` only.

- Converted inline template groups:
- Welcome/onboarding runtime card wrapper styles converted to classes: `.welcome-card`, `.welcome-title`, `.welcome-body`, `.welcome-step`, `.welcome-actions`.
- EULA loading paragraph inline style converted to `.eula-loading`.
- `app.js` welcome/EULA template now uses class hooks instead of inline `style="..."` for these static presentation rules.

- Deferred runtime-presentational drift:
- Inline styles in static `shell.html` markup were intentionally not part of this pass (handled in separate shell migration phases).
- Non-inline runtime HTML blocks (for example demo banner/inline panel templates) were left unchanged because they are already class-based or not style-attribute driven.

- Remaining cleanup risk before settings-page adoption:
- App-level route rendering still relies on large `innerHTML` template blocks; while now cleaner, presentation ownership can still drift if new inline styles are added in JS.
- A guardrail/code-review rule is still needed to keep future runtime UI markup class-first and prevent reintroduction of inline style attributes.

## Phase 4A Update (Settings Page System Adoption)

Completed in `core/ui/js/cards/settings.js` and `core/ui/css/app.css`.

- Standardized settings structures:
- Settings renderer normalized to shared wrappers and hierarchy: `settings-shell`, `settings-page-header`, `settings-grid settings-grid--primary`, `settings-card`, `settings-save-row`, `settings-operational-section`.
- Primary settings grouped into stable cards: System, Updates, Interface, Data Management.
- Operational/recovery controls grouped into dedicated lower section cards: Onboarding and Administration.
- Form and control rows normalized to shared class patterns: `settings-label`, `settings-select`, `settings-stack`, `settings-check-row`, `settings-action-row`, `settings-help-text`, `settings-save-feedback`.
- Loading state moved from inline style to canonical class: `settings-loading`.

- Deferred settings drift:
- Dynamic feedback visibility still uses runtime style mutation (`save-feedback` opacity and update download button display) to avoid behavior risk in this pass.
- Existing admin block internals rendered by `mountAdmin` were not restyled here to avoid cross-component coupling.

- Remaining cleanup risk before visual polish pass:
- Settings visuals now use canonical structure/classes, but color/detail consistency can still be tuned later after broader token unification.
- A later polish pass should standardize button semantic variants and any admin sub-block styling once shared component variants are finalized.

## Phase 4B Update (Settings Visual Polish + Composition)

Completed in `core/ui/js/cards/settings.js` and `core/ui/css/app.css`.

- Visual improvements made:
- Strengthened top composition with a clearer settings header/kicker and section rhythm (`settings-page-header`, `settings-page-kicker`, section heads).
- Refined primary settings composition with better card spacing, card surface treatment, and tighter heading hierarchy.
- Improved action row and save row alignment to read as deliberate control bands, including divider rhythm before save/operational blocks.
- Elevated lower operational/recovery composition with its own section heading and calmer card cadence.
- Added responsive polish for smaller widths to keep spacing and header hierarchy stable.

- Deferred visual gaps:
- Admin internals mounted by `mountAdmin` remain visually independent and were not normalized in this pass.
- Color token deep-unification (replacing remaining hard-coded literals in settings-specific rules) is deferred to later token harmonization.

- Readiness for screenshot review:
- Settings page now has a stable, canonical class structure with a polished baseline hierarchy suitable for screenshot review and targeted visual QA.
- Remaining polish risks are localized to admin sub-block styling and token harmonization, not page composition.

## Phase 4C Update (Screenshot-Review Adjustment Pass)

Completed in `core/ui/css/app.css` (CSS-led, controlled corrections).

- Screenshot-driven corrections made:
- Softened container/card visual weight to reduce heavy stacking feel (lighter shadows and subtler card gradients).
- Locked primary settings grid to stable two-column composition on desktop with explicit single-column fallback on narrow widths.
- Improved checkbox row readability and update action-row balance by giving feedback text a flexible lane.
- Refined operational block separation cadence and tuned operational card treatment for calmer lower-section distinction.

- Remaining visible gaps:
- Administration subcontent still inherits its own internal styling and may need a dedicated follow-up alignment pass.
- Full token harmonization for remaining hard-coded settings shades is still pending.

- Baseline readiness:
- Settings page composition is now stable enough to serve as the visual baseline for extending the same canonical patterns across other pages.
- Additional changes should be incremental polish rather than structural rewrites.

## Vendors Drift Adoption Note

Completed in `core/ui/js/cards/vendors.js` and `core/ui/css/app.css` as a narrow, behavior-safe pass.

- Drift removed:
- Toast presentation moved from renderer-owned inline style mutations to canonical classes (`contacts-toast`, tone variants, hide transition class).
- Vendor badge opacity mutation replaced with class-based state variant (`contacts-chip--muted`).
- Expanded contact panel visibility switched from `style.display` writes to class toggles (`contacts-expanded.is-open`).
- Extended editor section visibility switched from `style.display` writes to class toggles (`contacts-extended-section.is-open`).

- Deferred items:
- None deferred in this vendors-only drift cleanup pass; all scoped hotspots from the prior audit were converted without changing behavior.

- Standardization status:
- `vendors.js` is now standardized for presentation ownership (class-based styling authority in `app.css`), with runtime behavior preserved.

## Manufacturing Drift Adoption Note

Completed in `core/ui/js/cards/manufacturing.js` and `core/ui/css/app.css` as a narrow, behavior-safe pass.

- Drift removed:
- Status color writes were replaced with canonical tone classes via `data-tone` on `mfg-status-msg` (`error`/`success`/`neutral`).
- Projection/table visibility switched from `style.display` writes to class-based visibility toggles using existing `hidden` utility class.
- Container-level presentational display write was removed.

- Deferred items:
- Dynamic `innerHTML` scaffold/row template paths in recent-runs rendering were intentionally not migrated in this pass to avoid behavior risk and keep scope narrow.

- Standardization status:
- `manufacturing.js` is now partially standardized. Core status/visibility presentation drift is removed, while dynamic template paths remain as a deferred cleanup item.

## Inventory Stage 1 Adoption Note

Completed in `core/ui/js/cards/inventory.js` and `core/ui/css/app.css` as a low-risk, presentation-only pass.

- Drift removed:
- Repeated modal shell inline styles were unified into canonical classes (`inventory-modal-card`, `inventory-modal-card--narrow`, `inventory-modal-card--wide`).
- Toast renderer inline style mutations were moved to canonical classes (`inventory-toast` with tone and hide variants).
- Notes/info block `cssText` presentation was replaced with reusable class-based markup (`inv-note`, `inv-note-title`, `inv-note-body`).

- Deferred items:
- Display-toggle paths remain deferred for later stages (per plan).
- Dynamic `innerHTML` select/option/template paths remain deferred.
- Transient border-color flash mutation remains deferred.

- Risk and standardization status:
- `inventory.js` remains heavy-risk for later stages due to dense behavior-coupled UI logic and deferred dynamic/visibility paths, but Stage 1 low-risk presentation drift is now removed.

## Inventory Stage 2 Adoption Note

Completed in `core/ui/js/cards/inventory.js` and `core/ui/css/app.css` as a narrow, low-risk layout pass.

- Drift removed:
- Inline form/layout micro-tweaks for quantity/cost wrappers were moved to reusable class-based utilities (`field-input-row`).
- Vendor select width micro-tweak was moved to class-based utility (`field-input-full`).
- Hinge button spacing micro-tweak was moved to class-based styling (`inventory-hinge`).

- Deferred items:
- Display-toggle paths remain deferred for Stage 3 (`style.display` visibility logic untouched).
- Dynamic `innerHTML` select/option/template paths remain deferred.
- Transient border-color flash mutation remains deferred.

- Stage 3 readiness:
- Inventory is now prepared for a focused Stage 3 display-toggle cleanup with reduced low-risk layout noise.

## Inventory Stage 3 Adoption Note

Completed in `core/ui/js/cards/inventory.js` as a medium-risk, behavior-preserving visibility pass.

- Visibility drift removed:
- Safe `style.display` visibility mutations were replaced with class toggles using existing `hidden` utility behavior for:
	- stock-out price row visibility
	- refund restock-cost row visibility
	- duplicate details kv rows
	- add/edit ledger details section visibility
	- quantity preview visibility in batch mode

- Deferred items:
- Dynamic `innerHTML` select/option/template paths remain deferred.
- Transient border-color flash mutation remains deferred.
- No additional visibility classes were introduced because the existing canonical `hidden` utility class was sufficient.

- Stage 4 readiness:
- Inventory is now ready for Stage 4 transient-state cleanup (border flash and any remaining behavior-coupled presentation state).

## Inventory Stage 4 Adoption Note

Completed in `core/ui/js/cards/inventory.js` and `core/ui/css/app.css` as a narrow transient-state cleanup.

- Transient-state drift removed:
- The remaining direct border-color validation flash mutation was replaced with a class-based transient state (`inventory-field-invalid`) applied/removed with the same 1500ms timing window.

- Limitations:
- The class-based replacement uses the existing JS timeout behavior and does not introduce debounce/coalescing for repeated rapid invalid triggers; this preserves existing behavior shape as closely as possible.

- Stage 5 readiness:
- Inventory is now ready for Stage 5 dynamic template path cleanup (`innerHTML` select/option/template rendering paths still deferred).

## Inventory Stage 5 Adoption Note

Completed in `core/ui/js/cards/inventory.js` as a controlled, partial dynamic-template cleanup.

- Safe template/presentation drift removed:
- Replaced static `typeSelect` option template `innerHTML` with node-based option creation.
- Replaced vendor default-option reset path from template `innerHTML` to node-based option rendering.
- Replaced stock-in unit option template string (`map().join('')`) with node-based option creation.

- Deferred as behavior-coupled or out-of-scope:
- Generic `innerHTML = ''` clearing paths used for fast list/reset behavior remain as-is.
- Broader dynamic table/detail rendering paths remain deferred to avoid behavior drift in data-shape-sensitive flows.

- Standardization status:
- `inventory.js` remains partially standardized. Major presentation drift has been reduced across staged passes, but dynamic rendering paths still include deferred behavior-sensitive areas.

## Dead-Module Cleanup Note

Completed as a tight removal pass with no active route/handler behavior changes.

- Files removed:
- `core/ui/js/cards/dev.js`
- `core/ui/js/cards/fixkit.js`
- `core/ui/js/cards/organizer.js`
- `core/ui/js/cards/tasks.js`
- `core/ui/js/cards/writes.js`

- Files intentionally deferred in this pass:
- `core/ui/js/cards/backup.js` (explicitly retained)
- `core/ui/js/cards/home_donuts.js` (deferred to legacy quarantine/removal pass)
- `core/ui/js/cards/tools.js` (deferred to legacy quarantine/removal pass)

- Remaining legacy quarantine candidates:
- `core/ui/js/cards/home_donuts.js`
- `core/ui/js/cards/tools.js`
- `core/ui/js/cards/backup.js` (ownership/retention decision still explicit and separate)

## Active Module and Legacy Status Snapshot

Current branch posture before parity remediation:

- Standardized for presentation authority: `settings.js`, `vendors.js`, `recipes.js`, `finance.js`, `logs.js`.
- Partially standardized: `inventory.js`, `manufacturing.js`.
- Legacy/orphan deferred by explicit decision: `home_donuts.js`, `tools.js`, `backup.js`.
- Removed dead modules in this branch: `dev.js`, `fixkit.js`, `organizer.js`, `tasks.js`, `writes.js`.

## Contract-to-Form Parity Audit

Phase 1 completed as read-only contract enforcement against API contract docs plus live backend validators and route handlers.

### Inventory

- Active UI surfaces and submit flows:
- Item create/edit modal save in `core/ui/js/cards/inventory.js`.
- Stock-out modal submit in `core/ui/js/cards/inventory.js`.
- Refund modal submit in `core/ui/js/cards/inventory.js`.
- Add-batch stock-in modal submit in `core/ui/js/cards/inventory.js`.
- Backing endpoints:
- `POST /app/items`, `PUT /app/items/{id}`, `DELETE /app/items/{id}`.
- `POST /app/stock/out`, `POST /app/stock/in`, `POST /app/finance/refund`.
- Parity status summary:
- Partial parity with high-risk drift in item quantity semantics and one sold-path guard.
- Exact mismatch summary:
- UI submits `quantity_decimal` on item create/edit, while backend item handlers only apply quantity through legacy `qty` or `qty_stored` paths.
- Create flow allows quantity intent that can be ignored unless opening batch stock-in is executed.
- Sold stock-out path lacks proactive non-count guard; backend can reject sold cash-event path for non-count dimensions.
- Optional cents handling in canonical helper may drop zero-valued `sell_unit_price_cents` due to optional-int normalization behavior.
- `vendor_id` may be submitted as a string and depends on backend loose dict coercion.
- Severity summary:
- Critical: item create/edit quantity parity drift.
- High: create-flow quantity intent mismatch; sold-reason non-count guard.
- Medium: optional cents handling; vendor_id coercion.
- Already correct and do not touch:
- Stock-out reason enum alignment with backend values.
- Refund conditional restock-cost logic parity.
- Stock-in and add-batch canonical payload shape using `quantity_decimal + uom`.

### Contacts

- Active UI surfaces and submit flows:
- Contact create/edit modal save and delete flows in `core/ui/js/cards/vendors.js`.
- Backing endpoints:
- `POST /app/contacts`, `PUT /app/contacts/{id}`, `PUT /app/vendors/{id}`.
- `DELETE /app/contacts/{id}`, `DELETE /app/vendors/{id}`, optional `cascade_children=true`.
- Parity status summary:
- Functional parity with backend facades, but stricter-than-backend client gating on contact fields.
- Exact mismatch summary:
- UI enforces email-or-phone requirement while backend only requires `name` on create.
- UI does not expose first-class organization assignment/creation controls though backend supports `is_org` and `organization_id`.
- Severity summary:
- High: stricter contact-required behavior than backend truth.
- Medium: missing org assignment surface parity.
- Already correct and do not touch:
- Name required on create.
- Cascade organization delete behavior wiring.
- Meta object submission shape for email/phone/address/notes.

### Manufacturing

- Active UI surfaces and submit flows:
- Recipe run submit button in `core/ui/js/cards/manufacturing.js`.
- Backing endpoint:
- `POST /app/manufacture`.
- Parity status summary:
- Core submit shape parity is correct for recipe runs.
- Exact mismatch summary:
- UI hardcodes run quantity to `1` and does not expose positive quantity input even though backend supports arbitrary positive `quantity_decimal`.
- UI does not expose ad-hoc manufacturing payload path.
- Severity summary:
- Medium: missing quantity control parity.
- Low: ad-hoc path not surfaced.
- Already correct and do not touch:
- `recipe_id + quantity_decimal + uom` submit shape.
- Archived recipe prevention before submit.
- Server-side shortage error surfacing.

### Recipes

- Active UI surfaces and submit flows:
- Recipe create/update editor and delete flow in `core/ui/js/cards/recipes.js`.
- Backing endpoints:
- `POST /app/recipes`, `PUT /app/recipes/{id}`, `DELETE /app/recipes/{id}`.
- Parity status summary:
- Good v2 payload-shape alignment; validation strictness and UOM constraint parity remain incomplete.
- Exact mismatch summary:
- Output and component UOM are free-text in UI, but backend normalizes and rejects unsupported UOM for item dimension.
- Decimal validation is permissive and can allow malformed numeric text until backend rejection.
- UI requires at least one input item while backend model permits empty `items` list.
- Severity summary:
- High: free-text UOM parity drift.
- High: weak decimal pre-validation.
- Medium: stricter item-count requirement than backend.
- Already correct and do not touch:
- Uses `quantity_decimal`/`uom` v2 keys only.
- Legacy quantity keys are not sent.
- Archived and notes fields map correctly.

### Finance

- Active UI surfaces and submit flows:
- Finance route card in `core/ui/js/cards/finance.js` is read/report only.
- Backing endpoints used by this module:
- `GET /app/finance/summary`, `GET /app/finance/transactions`.
- Parity status summary:
- No active create/edit/write flow in this module to remediate under parity scope.
- Exact mismatch summary:
- None in write-flow scope.
- Severity summary:
- Not applicable for write parity.
- Already correct and do not touch:
- Keep finance route as read/report surface in parity remediation sequence.

### Settings/Admin

- Active UI surfaces and submit flows:
- Settings save flow in `core/ui/js/cards/settings.js`.
- Admin export/restore flow in `core/ui/js/cards/admin.js` mounted by settings.
- Backing endpoints:
- `POST /app/config`.
- `POST /app/db/export`, `GET /app/db/exports`, `POST /app/db/import/upload`, `POST /app/db/import/preview`, `POST /app/db/import/commit`.
- Parity status summary:
- Settings payload parity is strong; admin flow is functionally aligned with minor client-guard/error-clarity gaps.
- Exact mismatch summary:
- Export password relies primarily on HTML `required`; explicit JS guard is minimal.
- Import preview/commit known backend error codes are surfaced generically rather than field-actionable.
- Severity summary:
- Medium: admin guard and error-display clarity.
- Already correct and do not touch:
- Theme enum values map to backend literals.
- Launcher and updates boolean payload shape.
- Backup directory remains read-only UI reflection of backend config.

## Parity Remediation Plan

Execution order (fixed):

1. Inventory
2. Contacts
3. Manufacturing
4. Recipes
5. Finance
6. Settings/Admin only where contract-backed and needed

Planned remediation categories per module:

### 1. Inventory
- input type parity
- required/optional parity
- enum/options parity
- conditional logic parity
- pre-submit validation parity
- normalization/coercion parity
- error display parity

### 2. Contacts
- input type parity
- required/optional parity
- enum/options parity
- conditional logic parity
- pre-submit validation parity
- normalization/coercion parity
- error display parity

### 3. Manufacturing
- input type parity
- required/optional parity
- enum/options parity
- conditional logic parity
- pre-submit validation parity
- normalization/coercion parity
- error display parity

### 4. Recipes
- input type parity
- required/optional parity
- enum/options parity
- conditional logic parity
- pre-submit validation parity
- normalization/coercion parity
- error display parity

### 5. Finance
- input type parity
- required/optional parity
- enum/options parity
- conditional logic parity
- pre-submit validation parity
- normalization/coercion parity
- error display parity

### 6. Settings/Admin
- input type parity
- required/optional parity
- enum/options parity
- conditional logic parity
- pre-submit validation parity
- normalization/coercion parity
- error display parity

## Remediation Rules

- Fix one module at a time.
- Preserve backend/API behavior exactly.
- Do not change API contracts.
- Do not invent new business rules.
- UI becomes stricter only where backend truth requires it.
- Do not mix broad style cleanup into validation work unless needed for correct error-state display.
- Prefer partial, reviewable fixes over broad rewrites.

## Step 1 — Inventory Parity Remediation

Implementation-ready work package derived from completed Phase 1 audit.

### Issue A: Item create/edit quantity parity problem
- Severity: Critical.
- Likely files: `core/ui/js/cards/inventory.js`.
- Fix type: payload shaping and conditional logic.
- Work type: payload shaping parity.
- Checklist:
- Align item save payload with backend-accepted quantity fields or remove misleading quantity submission path from item create/edit payload.
- Ensure quantity mutations occur only through contract-aligned stock mutation endpoints when required.

### Issue B: Create-flow quantity intent mismatch
- Severity: High.
- Likely files: `core/ui/js/cards/inventory.js`.
- Fix type: UI validation and conditional logic.
- Work type: UI validation plus conditional logic parity.
- Checklist:
- Prevent UI from implying opening quantity is persisted when opening batch is disabled.
- Make create-path behavior explicit and contract-aligned before submit.

### Issue C: Sold-reason and non-count item guard
- Severity: High.
- Likely files: `core/ui/js/cards/inventory.js`, optionally `core/ui/js/api/canonical.js` for guard-compatible payload semantics.
- Fix type: conditional logic.
- Work type: conditional logic parity.
- Checklist:
- Add proactive client guard for sold cash-event path on non-count items to mirror backend rejection behavior.
- Keep reasons enum unchanged.

### Issue D: Optional cents/value handling issue
- Severity: Medium.
- Likely files: `core/ui/js/api/canonical.js`, `core/ui/js/cards/inventory.js`.
- Fix type: normalization/coercion.
- Work type: normalization/coercion parity.
- Checklist:
- Review optional int normalization behavior for sell price and other optional cents values so backend-intended semantics are preserved.

### Issue E: vendor_id coercion issue
- Severity: Medium.
- Likely files: `core/ui/js/cards/inventory.js`.
- Fix type: payload shaping.
- Work type: normalization/coercion parity.
- Checklist:
- Coerce `vendor_id` to integer or omit when empty.
- Avoid relying on backend loose dict assignment for type cleanup.

### Known-correct inventory behaviors that must not be disturbed
- Stock-out reason enum alignment.
- Refund conditional restock-cost logic.
- Stock-in and add-batch canonical `quantity_decimal + uom` payload shape.

## Next Pass Activation Note

Next active implementation pass should begin with Inventory parity remediation. Read-audit findings are complete. Code changes for parity remediation have not started yet.

## Step 1 Progress Update (Inventory)

Step 1 implementation has started with narrow code changes in inventory submission logic and canonical payload handling.

- Completed in this pass:
- Item create/edit quantity parity: removed `quantity_decimal` from item metadata create/update payload path in UI so quantity is no longer silently implied through unsupported item fields.
- Create-flow quantity intent mismatch: added guard to block non-zero opening quantity when "Add opening batch now" is disabled.
- Sold reason non-count guard: added client-side block/message for `reason=sold` on non-count items before submit.
- Optional cents handling: canonical optional cents normalization updated to preserve explicit zero-valued cents for non-negative cents fields.
- Vendor ID coercion: inventory save payload now coerces vendor selection to integer or omits it when empty/invalid.

- Known-correct behaviors preserved:
- Stock-out reason enum options unchanged.
- Refund conditional restock-cost logic unchanged.
- Stock-in and add-batch canonical `quantity_decimal + uom` shape unchanged.

- Remaining for Step 1 completion:
- No additional Step 1 issue buckets remain open; next pass should validate behavior and then proceed to Step 2 (Contacts).

## Step 2 Progress Update (Contacts)

Step 2 implementation has started with a narrow contacts parity pass in `core/ui/js/cards/vendors.js`.

- Completed in this pass:
- Removed strict client requirement for email-or-phone; UI now only enforces backend-required `name` on create/update.
- Added contract-backed organization controls in editor: `is_org` toggle and parent `organization_id` selection path.
- Removed redundant role forcing from contact payload; backend now derives `role` from `is_vendor` as intended.

- Known constraints and intentionally deferred behavior:
- Clearing `organization_id` explicitly is still constrained by backend update serialization (`exclude_none=True`), so this pass focuses on safe set/omit behavior rather than force-clear semantics.
- No API contract or backend behavior changes were made.

## Step 3 Progress Update (Manufacturing)

Step 3 implementation has started with a narrow manufacturing parity pass in `core/ui/js/cards/manufacturing.js`.

- Completed in this pass:
- Quantity input parity gap: added explicit output quantity input for recipe runs; submit now sends validated positive `quantity_decimal` instead of hard-coded `1`.
- Projection parity: projection rows now scale component/output quantities based on requested output quantity relative to recipe base output quantity.
- Structured shortage/error display parity: manufacturing errors now parse structured `insufficient_stock` details and render concise, readable shortage summaries.

- Decision and scope constraints applied:
- Recipe-only UI remains intentional in this pass; ad-hoc manufacturing UI is not implemented.

- Known constraints and intentionally deferred behavior:
- Ad-hoc manufacturing surface remains deferred by branch scope decision.
- No API contract or backend behavior changes were made.

## Step 4 Progress Update (Recipes)

Step 4 implementation has started with a narrow recipes parity pass in `core/ui/js/cards/recipes.js`.

- Completed in this pass:
- Free-text UOM parity gap: replaced output/component free-text UOM inputs with item-compatible UOM selects.
- Numeric validation parity: strengthened output/component quantity validation to strict positive-decimal checks before submit.
- Output UOM required-vs-default behavior: output UOM is no longer hard-required client-side; payload omits `uom` when empty so backend default behavior remains authoritative.
- Backend error display parity: safe structured parsing added for array/object/string backend error details.

- Decision and scope constraints applied:
- The "at least one component" requirement is intentionally retained as a UI policy guard and is now explicitly documented.

- Known constraints and intentionally deferred behavior:
- No API contract or backend behavior changes were made.
- No broad UOM-system expansion beyond item-compatible select restriction was performed.

## Recipes Follow-up Validation Notes

- Count UOM label clarification:
- UI keeps both `mc` and `ea` as distinct allowed count units.
- `mc` is relabeled in recipe UOM selectors to `mc (1/1000 ea)` for operator clarity while preserving the submitted value.

- Count UOM presentation policy update:
- `mc` is now treated as internal-only for recipe UI selectors and is hidden from user-facing choices.
- Recipe UI presents operator-facing count units (`ea`) and maps count presentation accordingly while preserving backend/storage authority.

- Deferred authority reconciliation:
- UI unit helper count-base modeling and backend/SOT count-base authority are not yet fully reconciled.
- This remains a separate follow-up audit/remediation item and is not changed in this pass.

- Deferred recursion validation test:
- A self-referential recipe test was masked by stock/batch failure before recursion/self-reference validation could be conclusively observed.
- Run a controlled follow-up test with sufficient stock so recursion/self-dependency validation path can be isolated from inventory shortage failures.

## Branch Freeze / Closure Snapshot

### Completed in fortheemperor

- UI styling authority migration to `core/ui/css/app.css` as canonical visual system authority.
- Shared shell/navigation/cards/forms/button/status standardization passes completed and settings page adopted as first full-system target.
- Dead UI module removals completed for `dev.js`, `fixkit.js`, `organizer.js`, `tasks.js`, and `writes.js`.
- Contract-to-form parity remediation completed for Inventory, Contacts, Manufacturing, and Recipes scoped issues.
- Recipes UI count-unit presentation policy updated so internal `mc` is hidden in user-facing selectors.

### Deferred / Follow-on

- Small settings/admin pass for contract-backed guard/error-display polish.
- Update-check display/settings logic adjustment pass.
- Legacy/quarantine resolution for `home_donuts.js`, `tools.js`, and explicit `backup.js` ownership decision.
- Unit-authority reconciliation follow-up: `core/ui/js/lib/units.js` count-base model vs backend/SOT canonical count base.
- Controlled recursion/self-reference recipe validation test with non-shortage stock conditions.

### Next Workstream

- Step 5 (Finance) and Step 6 (Settings/Admin where contract-backed and needed) remain next in sequence, with deferred items above to be tracked as post-parity follow-on work.

## Deferred Follow-on Progress — Step B (Update-check Policy/UI Relocation)

- Completed in this pass:
- Sidebar now owns update awareness surface (bottom-left zone): always-visible version, update status text, manual `Check now`, and conditional download action.
- Settings update controls were simplified to one user-facing policy toggle: `Enable automatic update checks`.
- Redundant split startup-check control was removed from Settings UI.
- Automatic update checks are default-on unless explicitly disabled (`updates.enabled !== false`).
- Existing update-check mechanism/endpoint/manifest parsing was preserved.

- Scheduling policy wired:
- Automatic check runs on launch when automatic checks are enabled.
- While app stays open, re-check runs when last successful check age exceeds 24 hours.

- Scope guard honored:
- No internal update network call mechanics, endpoint usage, response handling, or manifest interpretation logic was changed.

## Deferred Follow-on Bugfix Note — Settings Update Policy Persistence

- Fixed misleading update-policy persistence in `core/ui/js/cards/settings.js` save payload.
- Compatibility field `updates.check_on_startup` is retained for legacy compatibility, but now mirrors `updates.enabled` so persisted config cannot contain contradictory state (`enabled=false` with `check_on_startup=true`).
- Settings save still writes only the intended settings subset (`ui`, `launcher`, `updates`) and does not mutate unrelated config sections such as `dev`.

## Final Cleanup Pass — fortheemperor

- `dev.writes_enabled` default truth:
- Config-model default now reflects fresh-install truth (`true`) so default/public model authority no longer implies writes-disabled on first persistence when no explicit value is set.
- Persisted explicit values still override as expected (`false` remains authoritative when present).

- Obsolete `close_to_tray` active ownership removed:
- Removed from active Settings UI controls, load wiring, and settings-save payload.
- Launcher behavior settings in active ownership now only expose and persist `auto_start_in_tray`.

- Theme control stubbed honestly:
- Theme selector is now disabled and system-only in active UI, with explicit deferred messaging.
- No fake active theme choice remains in settings-save behavior.

- Sidebar branding strengthened:
- Top sidebar brand now includes a deliberate logo-under-title mark container using existing `/ui/Logo.png` asset.
- Spacing/hierarchy and container treatment were tuned for stronger BUS Core identity while preserving navigation/update-zone behavior.

- Deferred leftovers (explicit):
- `core/ui/js/lib/units.js` count-base authority reconciliation remains deferred.
- Controlled self-reference recipe validation test remains deferred.
