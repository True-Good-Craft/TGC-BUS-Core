# Bandit Remediation Audit Log

Date: 2026-04-23
Last documentation correction: 2026-04-24

## Entries

| File | Finding ID | Classification | Action Taken | Rationale |
| --- | --- | --- | --- | --- |
| `pyproject.toml` | policy baseline | DOCUMENTATION CORRECTION | No `[tool.bandit]` baseline is present in the current file; prior wording that claimed one was added was documentation drift | Do not claim Bandit exclusions or a pyproject Bandit baseline until the file actually contains one. |
| `core/api/http.py` | B608 | NARROW SUPPRESSION (EXACT-LINE RETAINED) | Removed inline `# nosec B608` for stale-check, re-ran Bandit on file, observed B608 at the same query line, then restored suppression on that exact line only | Query values remain parameterized with DB-API placeholders; scanner still flags dynamic placeholder assembly. |
| `core/ledger/health.py` | B608 | TRUE FIX | Replaced dynamic column interpolation with two static query variants (`qty` / `qty_stored`) | Removes string-formatted SQL while preserving existing runtime behavior and schema compatibility. |
| `core/utils/export.py` | B608 | NARROW SUPPRESSION | Added inline `# nosec B608` on table-count query | Table identifier comes from fixed internal dictionary keys only. |
| `core/reader/ids.py`, `core/reader/api.py`, `core/plans/commit.py`, `tests/test_reader_rid_security.py` | B324 | TRUE FIX + COMPATIBILITY HARDENING | Replaced active RID signature generation with hardened v2 generation (`local:v2:<sig32>:<payload>`), retained strict legacy read compatibility (`local:<sig10>:<payload>`), enforced strict fail-closed RID parsing/decoding/path checks, and tightened commit RID authority for present RID fields | Resolves integrity-relevant RID boundary weakness via real hardening without suppression/workarounds while preserving standing product compatibility for valid legacy values. |
| `plugins/notion/plugin.py` | B310 | TRUE FIX + NARROW SUPPRESSION | Added strict URL allowlist check (`https://api.notion.com`) and inline `# nosec B310` at `urlopen` | Runtime path now enforces scheme/host policy before network open; scanner warning is retained as documented suppression due generic `urlopen` rule. |

## Classification Notes (Current Snapshot)

- `core/api/http.py` still emits a Bandit `nosec encountered (B608), but no failed test` warning with the exact-line suppression in place; suppression is retained because removing it reproduces B608 at the same line.
- `pyproject.toml` currently contains project metadata only; Bandit configuration remains unset unless a future change adds `[tool.bandit]`.
- `B105` findings in provider/plugin response payload defaults are treated as FALSE POSITIVES unless a real secret literal is present.
- `B101` in tests is accepted test-scope noise.
- `B110/B112` are mostly intentional fail-soft/cleanup paths and require selective future cleanup, not blanket rewrites.
- `B603/B607/B404` around subprocess usage are context-dependent; current runtime patterns should be hardened only when trust-boundary input reaches command arguments.
- RID hardening verification completed with targeted commands: `python -m bandit -r core/reader/ids.py core/reader/api.py core/plans/commit.py core/organizer/api.py --exclude ./.venv,./build,./dist` and `pytest -q tests/test_reader_rid_security.py`.
