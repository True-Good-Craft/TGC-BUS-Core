# BUS Core Test Plan (Coverage Matrix)

## Scope
This plan documents **business invariants and API contracts** covered by the suite, and explicitly omits low-value checks.

## What we test
- **Inventory / Ledger invariants**
  - FIFO consumption behavior.
  - Positive/negative adjustments and shortage envelopes.
  - Purchase creates inventory batch and journal entry.
- **Manufacturing invariants**
  - Atomic transaction rollback on failure.
  - Fail-fast insufficient-stock behavior.
  - Costing calculations and output batch cost.
  - Journal append failures do not roll back committed DB work.
  - Manufacturing movements never set oversold flag.
- **Finance v1 contracts**
  - Sale records cash event and links movement source IDs.
  - Refund validation (restock requires cost/related context).
  - Refund without restock records cash-only event.
  - Profit-window bounds are correct.
- **Backup / restore invariants**
  - Export artifact integrity and naming.
  - Preview rejects incompatible schema.
  - Commit restores DB and archives journals.
- **Contacts API**
  - Read/create/filter contract behavior.
- **Plugin discovery security guard**
  - Internal-core imports are rejected.
  - Non-plugin interfaces are ignored.
- **Indexing helpers (unit)**
  - Master index and sheets index logic with fake clients/adapters.

## What we intentionally do NOT test
- Framework internals (FastAPI/SQLAlchemy internals).
- Third-party SDK behavior (Google/Notion libraries themselves).
- Redundant permutations that assert identical invariants.
- Incidental log strings and unrelated implementation details.

## Coverage matrix
| Feature / invariant | Primary tests |
|---|---|
| FIFO adjustment correctness + shortage detail | `tests/adjustments/test_fifo_adjustments.py` |
| Inventory journaling + purchase/stock-out contract | `tests/journal/test_inventory_journal.py` |
| Manufacturing atomic rollback | `tests/manufacturing/test_atomic_success.py` |
| Manufacturing fail-fast error contract | `tests/manufacturing/test_fail_fast.py` |
| Manufacturing costing math | `tests/manufacturing/test_costing.py` |
| Manufacturing journal append no-rollback behavior | `tests/manufacturing/test_journal_ordering.py` |
| Manufacturing oversell guard | `tests/manufacturing/test_no_oversell.py` |
| Manufacturing smoke flow (high-level) | `tests/smoke/test_manufacturing_flow.py` |
| Error envelope shape normalization | `tests/api/test_error_shapes.py` |
| Manufacturing run request contract validation | `tests/api/test_manufacturing_run_contract.py` |
| Finance linkage/refund/profit contracts | `tests/api/test_finance_v1.py` |
| Backup export/restore round-trip | `tests/backup/test_export.py`, `tests/backup/test_restore.py`, `tests/backup/test_smoke_backup_restore.py` |
| Contacts API behavior | `tests/test_contacts.py` |
| Plugin import guard / non-plugin rejection | `tests/test_plugin_import_guard.py` |
| Master index/sheets index helper logic | `tests/test_master_index.py`, `tests/test_sheets_index.py` |
| DB path env handling | `tests/test_db_paths.py` |
