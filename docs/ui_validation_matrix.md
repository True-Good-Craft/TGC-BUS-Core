# UI Validation Matrix (Manual)

This worksheet is for human execution after backend/UI deployment.
Do not mark a step pass unless network payload + UI behavior are both verified.

## Preconditions

- [ ] App is running and accessible.
- [ ] Browser devtools Network tab open and preserved logs enabled.
- [ ] Logged in with a user role that can perform inventory/manufacturing/finance actions.
- [ ] Test data available: at least one inventory item and one recipe.

---

## Inventory Validation

| Area | Steps | Expected Endpoint | Expected Payload Contract | Result | Notes |
|---|---|---|---|---|---|
| Create Item | Create a new count item from Inventory card. | `/app/items` | Item payload only; no qty legacy mutation keys. | ☐ Pass ☐ Fail | |
| Opening Batch (Add Item flow) | Enable opening batch, enter quantity + unit + cost, save. | `/app/stock/in` | `quantity_decimal` is string; `uom` present; no `qty`/`qty_base`/`quantity_int`. | ☐ Pass ☐ Fail | |
| Opening Batch cost-unit mismatch | Intentionally set different cost unit and item unit (if UI allows). | N/A or blocked | UI should block with validation error; no mutation call sent. | ☐ Pass ☐ Fail | |
| Stock In modal | Open existing item → Add Batch. Submit. | `/app/stock/in` | `item_id`, `quantity_decimal` (string), `uom`; no base conversions. | ☐ Pass ☐ Fail | |
| Stock Out (sold) | Execute stock-out with reason `sold` and price. | `/app/stock/out` | `quantity_decimal` string + `uom`; optional `sell_unit_price_cents`; no `qty`. | ☐ Pass ☐ Fail | |
| Stock Out (loss/theft/other) | Execute non-sold stock-out. | `/app/stock/out` | `quantity_decimal` string + `uom`; reason set; no `qty`. | ☐ Pass ☐ Fail | |
| Refund | Run refund flow from inventory UI. | Current behavior may vary | Document observed payload; check for base-unit semantics leakage (do not fix in this pass). | ☐ Pass ☐ Fail | |
| Edit Item | Edit metadata and save. | `/app/items/:id` | No unintended quantity mutation fields introduced. | ☐ Pass ☐ Fail | |

---

## Manufacturing Validation

| Area | Steps | Expected Endpoint | Expected Payload Contract | Result | Notes |
|---|---|---|---|---|---|
| Run recipe success | Select active recipe and click Run Production. | `/app/manufacture` | `recipe_id`, `quantity_decimal` (string), `uom`; no `output_qty`. | ☐ Pass ☐ Fail | |
| Run recipe shortage | Run with insufficient stock. | `/app/manufacture` | Structured shortage error surfaced in UI. | ☐ Pass ☐ Fail | |
| Ad-hoc manufacturing (if exposed) | Trigger ad-hoc flow (if present). | `/app/manufacture` | Output and component quantities use `quantity_decimal` + `uom`. | ☐ Pass ☐ Fail | |
| Recent runs list | Open manufacturing history panel. | Read-only history endpoint(s) | Entries render without base-int leakage in labels. | ☐ Pass ☐ Fail | |

---

## Finance Validation

| Area | Steps | Expected Behavior | Result | Notes |
|---|---|---|---|---|
| Profit report totals | Open finance/profit panel and compare revenue/COGS/margin with known test set. | Values render and update consistently. | ☐ Pass ☐ Fail | |
| Date filtering | Apply range/window filters and verify chart/table sync. | Correct filtered totals and stable UI state. | ☐ Pass ☐ Fail | |
| Regression spot-check | Navigate Inventory → Manufacturing → Finance repeatedly. | No stale state bleed or stale totals. | ☐ Pass ☐ Fail | |

---

## Ledger Validation

| Area | Steps | Expected Behavior | Result | Notes |
|---|---|---|---|---|
| Ledger history quantity display | Open ledger/history views used by UI. | Human-readable quantity format shown; no exposed base-int UX leakage. | ☐ Pass ☐ Fail | |
| Item-specific history | Filter by item where applicable. | Results align with recent stock in/out/manufacture activity. | ☐ Pass ☐ Fail | |

---

## Error Surface Audit

- [ ] Trigger validation error (empty quantity / invalid input) and verify clear, non-crashing message.
- [ ] Trigger backend structured error (e.g., shortage) and verify UI shows details without stack traces.
- [ ] Confirm no uncaught exceptions in browser console during inventory/manufacturing workflows.
- [ ] Confirm failed requests preserve form context (no forced route jumps).

## UI State Leakage Stress Navigation

Repeat 3–5 times:
1. Inventory → open modal → cancel.
2. Manufacturing → select recipe → do not run.
3. Finance → apply filter.
4. Return to Inventory and perform stock-out.

Checklist:
- [ ] No duplicate event handlers (single submit per click).
- [ ] No stale modal state reused incorrectly.
- [ ] No cross-card data contamination.
- [ ] No routing/lifecycle breakage observed.

---

## Sign-off

- Tester:
- Date:
- Environment:
- Commit SHA tested:
- Overall outcome: ☐ Pass ☐ Fail
- Follow-up issues:
