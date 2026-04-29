# Security Policy

## Reporting a Vulnerability

Please report suspected vulnerabilities privately to project maintainers and include:

- Affected file(s) and function(s)
- Reproduction steps and required inputs
- Expected impact and trust boundary crossed
- Suggested fix or mitigation (optional)

Do not open public issues for unpatched security defects.

## Bandit Policy (BUS Core)

This repository uses Bandit to improve real security posture, not to force scanner-clean refactors.

Rules:

- Preserve canonical authority surfaces and API/runtime contracts.
- Prefer minimal diffs and behavior-preserving fixes.
- Avoid broad global skips.
- Use narrow suppressions only when findings are false positives or intentional fail-soft behavior.
- Suppressions must not replace real fixes when findings touch integrity-relevant boundary logic (for example, path-token or trust-boundary resolution paths).
- Compatibility-preserving security hardening may use old-read/new-write transitions when needed to avoid breaking valid standing state while strengthening new emissions.

Current CI security workflow: `.github/workflows/security-audit.yml`.

- Bandit runs on `core`, `tgc`, `scripts`, and `launcher.py`.
- Low-severity Bandit findings are reported in advisory mode.
- Medium and High Bandit findings fail CI.
- `pip-audit` runs against `requirements.txt` in advisory mode because the repository currently has range-based requirements rather than a fully pinned lockfile. This is visible evidence, not a silent skip; promote it to blocking once BUS Core has a stable audit input.

Current workflow exclusions are limited to tests, build/runtime outputs, virtual environments, caches, and local temporary tooling directories:

- `.venv`
- `build`
- `dist`
- `tests`
- `.pytest_cache`
- `.tmp_test_deps_*`
- `.tmp_localappdata_*`
- `.artifacts`

## Suppression Standard

Every suppression must be:

- Narrow: tied to a specific line or call site
- Justified: include an inline rationale
- Audited: recorded in `docs/security/remediation_audit_log.md`

Patterns that can be acceptable with narrow suppression:

- Controlled SQL fragments from internal allowlists/fixed keys
- Non-security hash usage for local identifiers
- Validated URL opens on fixed allowlisted endpoints
- Intentional cleanup/fail-soft exception handling
