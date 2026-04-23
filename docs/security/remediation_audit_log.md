# Bandit Remediation Audit Log

Date: 2026-04-23

## Entries

| File | Finding ID | Classification | Action Taken | Rationale |
| --- | --- | --- | --- | --- |
| `pyproject.toml` | policy baseline | TRUE FIX | Added `[tool.bandit]` with `exclude_dirs = [".venv", "build", "dist"]` | Required minimal scan baseline without broad skips. |
| `core/api/http.py` | B608 | NARROW SUPPRESSION (EXACT-LINE RETAINED) | Removed inline `# nosec B608` for stale-check, re-ran Bandit on file, observed B608 at the same query line, then restored suppression on that exact line only | Query values remain parameterized with DB-API placeholders; scanner still flags dynamic placeholder assembly. |
| `core/ledger/health.py` | B608 | TRUE FIX | Replaced dynamic column interpolation with two static query variants (`qty` / `qty_stored`) | Removes string-formatted SQL while preserving existing runtime behavior and schema compatibility. |
| `core/utils/export.py` | B608 | NARROW SUPPRESSION | Added inline `# nosec B608` on table-count query | Table identifier comes from fixed internal dictionary keys only. |
| `core/reader/ids.py` | B324 | HALTED / PENDING OPERATOR DECISION | Reverted prior automatic `usedforsecurity=False` annotation during correction pass | RID root signature participates in path resolution used by commit flow; trust/integrity-boundary ambiguity requires operator decision. |
| `plugins/notion/plugin.py` | B310 | TRUE FIX + NARROW SUPPRESSION | Added strict URL allowlist check (`https://api.notion.com`) and inline `# nosec B310` at `urlopen` | Runtime path now enforces scheme/host policy before network open; scanner warning is retained as documented suppression due generic `urlopen` rule. |

## Classification Notes (Current Snapshot)

- `core/api/http.py` still emits a Bandit `nosec encountered (B608), but no failed test` warning with the exact-line suppression in place; suppression is retained because removing it reproduces B608 at the same line.
- `B105` findings in provider/plugin response payload defaults are treated as FALSE POSITIVES unless a real secret literal is present.
- `B101` in tests is accepted test-scope noise.
- `B110/B112` are mostly intentional fail-soft/cleanup paths and require selective future cleanup, not blanket rewrites.
- `B603/B607/B404` around subprocess usage are context-dependent; current runtime patterns should be hardened only when trust-boundary input reaches command arguments.
