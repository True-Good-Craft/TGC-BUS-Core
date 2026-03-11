---
name: UI Pass
description: Help pass over UI
argument-hint: 
# tools: ['vscode', 'execute', 'read', 'agent', 'edit', 'search', 'web', 'todo'] # specify the tools this agent can use. If not set, all enabled tools are allowed.
---

<!-- Tip: Use /create-agent in chat to generate content with agent assistance -->

## Execution brief for Copilot agent — `fortheemperor`

Use this as the working instruction set inside VS Code.

---

# Branch

`fortheemperor`

# Mission

This branch is a **UI authority and standardization pass**.

The goal is to **establish one canonical styling system**, reduce visual drift, and make cards/pages consume shared UI rules instead of carrying ad hoc styling.

This is a **controlled glow-up pass**, not a feature branch.

---

# Primary objective

Create a calm, maintainable UI system where:

* styling authority lives in one canonical place
* shared cards/pages/forms/navigation use standardized classes and tokens
* inline style drift is reduced or removed
* page structure becomes more consistent
* the settings page becomes the first clean adoption target of that system

---

# Hard scope rules

## In scope

* CSS authority cleanup
* shared design tokens
* shared card/page/form/nav styling
* layout consistency improvements
* removal or migration of inline visual drift
* settings page structure and styling cleanup
* non-functional markup refactors needed to support standardized styling

## Out of scope

* backend behavior changes
* route/API changes
* config semantics changes
* feature additions
* changing business logic
* rewriting update-check behavior unless required by UI presentation and already supported by existing logic

If a change would alter application behavior beyond presentation or markup structure, stop and flag it instead of freelancing.

---

# Authority rules

## Canonical styling authority

`app.css` is the canonical visual authority.

## Non-canonical styling locations

`shell.html` may keep structure, but should not remain a long-term source of meaningful styling authority.

`app.js` should render semantic structure and shared class hooks, not invent one-off styling patterns.

## Principle

Pages should **compose** the design system, not invent their own.

---

# Working assumptions

Based on current repo structure:

* `app.css` already contains major theme/styling foundations
* `shell.html` still contains inline or local style drift
* `app.js` likely renders page markup and some runtime structure

Treat this branch as a **migration toward canonical styling**, not a full rewrite.

---

# Required operating style

Work **incrementally** and keep changes reviewable.

Do not do a giant all-files aesthetic rewrite.

Prefer small, coherent passes that each satisfy one clear purpose.

---

# Execution phases

## Phase 1 — Audit styling authority

Inspect and summarize where styling currently lives:

* canonical/shared styling in `app.css`
* inline/local styles in `shell.html`
* runtime markup/class patterns in `app.js`
* any page-specific one-off UI patterns that block standardization

Deliverable:

* short internal working summary in comments or notes
* identify what should migrate first

Do not start broad edits before understanding the split.

---

## Phase 2 — Strengthen canonical CSS system

Refactor `app.css` into clear sections if needed, and standardize or introduce reusable foundations:

### Add or normalize

* theme tokens
* background/surface layers
* border colors
* text hierarchy
* accent/status colors
* radius scale
* shadow scale
* spacing scale

### Standardize reusable components

* page shell/container
* page header
* section header
* content grid/split layouts
* card base + variants
* buttons
* inputs/selects/textareas
* checkbox rows / settings rows
* status/banners/help text

Deliverable:

* `app.css` becomes the clear visual authority

Do not over-engineer. Build only what current pages will actually use.

---

## Phase 3 — Migrate shared style authority out of `shell.html`

Move shared styling from `shell.html` into `app.css` in a controlled order:

1. global shell/frame
2. sidebar/navigation
3. card styling
4. form styling
5. remaining shared surface rules
6. page-specific leftovers only after shared rules are stable

Important:

* preserve behavior
* do not delete inline styles until the migrated CSS is confirmed in place
* reduce drift, do not create churn for its own sake

Deliverable:

* `shell.html` loses styling authority where practical
* `app.css` gains the canonical rules

---

## Phase 4 — Standardize structural class usage

Inspect `app.js` and normalize page markup toward shared wrappers and classes.

Target patterns like:

* page shell
* page header
* section/card wrappers
* consistent content spacing
* shared settings/form row patterns

Deliverable:

* markup becomes easier to style through the shared system
* fewer one-off class structures

Do not change application behavior.

---

## Phase 5 — Settings page first full adoption

Use the settings page as the first deliberate application of the standardized system.

### Desired result

* stronger hierarchy
* cleaner grouping
* consistent card treatment
* clearer spacing
* calmer top-level composition
* backup/restore grouped into a coherent lower operational section

### Directional structure

Top area:

* page title
* primary settings composition

Primary settings composition:

* left card: system / launcher / interface
* right card: updates / data management

Lower operational section:

* onboarding / administration if still needed
* full-width backup/restore management area

Do not invent new business logic.
Only restructure markup/styling around existing behavior.

---

## Phase 6 — Cleanup

After the first page is stable:

* remove dead selectors created by migration
* reduce duplicated rules
* normalize naming where low risk
* leave comments only where truly helpful

Do not do speculative cleanup unrelated to this branch.

---

# Quality bar

Every retained change should satisfy at least one of these:

* moves style toward canonical authority
* reduces duplication
* improves consistency
* improves hierarchy/scannability
* preserves behavior while improving structure
* makes future page adoption easier

If a change is only “looks cooler,” that is not enough.

---

# Change constraints

## Preserve

* existing feature behavior
* existing routes and interactions
* existing setting semantics unless already represented in UI logic
* existing backend integration points

## Avoid

* visual novelty for its own sake
* massive selector proliferation
* duplicate component classes that mean the same thing
* page-specific hacks when a shared component rule would solve it

---

# Expected deliverables

## Code deliverables

* improved `app.css` as canonical styling authority
* reduced inline style drift in `shell.html`
* cleaner shared class usage in `app.js`
* settings page aligned to the standardized system

## Documentation deliverable

Create or update a short working note such as:

`UI_GLOWUP_BRANCH_NOTES.md`

Include:

* branch purpose
* canonical styling authority
* migration rules
* completed passes
* known remaining drift

Keep it concise and operational.

---

# Recommended file organization in CSS

If helpful, organize `app.css` roughly like this:

```css
/* 1. Tokens */
/* 2. Base / reset */
/* 3. Shell layout */
/* 4. Navigation */
/* 5. Typography */
/* 6. Cards */
/* 7. Forms */
/* 8. Buttons */
/* 9. Status / utility */
/* 10. Page patterns */
/* 11. Settings page specifics */
/* 12. Responsive */
```

Do not force this if the current file structure already has a workable equivalent. The point is clarity and authority, not ceremony.

---

# Working method

Use small commits or logically separable edits.

Suggested sequence:

1. audit and note
2. token/foundation pass
3. shell/nav/card migration
4. form/layout standardization
5. settings page adoption
6. cleanup

At each step, prefer **reviewable diffs** over dramatic rewrites.

---

# Anti-drift rule

Before adding any new CSS rule or class, check:

1. Can an existing shared class solve this?
2. Can this be expressed as a variant of a canonical component?
3. Is this page inventing structure the system should own?

If yes, solve it at the system level first.

---

# Final instruction

Proceed as a disciplined UI systems lead, not a theme-hacker.

The win condition is not “one prettier page.”
The win condition is a **stable, canonical UI styling system** that makes future polish easy and future drift harder.


