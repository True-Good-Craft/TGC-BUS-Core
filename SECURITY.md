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

Current baseline configuration excludes only build/environment directories:

- `.venv`
- `build`
- `dist`

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
