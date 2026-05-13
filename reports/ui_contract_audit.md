# UI Contract Audit Report

- Timestamp (UTC): 2026-05-13T22:31:28Z
- Repo: D:\# Dev Test\BUSCore-Test\TGC-BUS-Core
- Search tool: rg
- Overall status: **PASS**

## Commands

```bash
rg -n "/api/" core/ui/js
rg -n "/ledger/" core/ui/js
rg -n "/manufacturing/" core/ui/js
rg -n "\bstock_in\b|manufacturing/run|ledger/movements" core/ui/js
rg -n "\bqty\b\s*:|\bqty_base\b\s*:|\bquantity_int\b\s*:|\boutput_qty\b\s*:|\bqty_required\b\s*:" core/ui/js
rg -n "\*1000\b|/1000\b|\bbaseQty\b|\bmultiplier\b" core/ui/js
rg -n "unit_cost_decimal" core/ui/js
rg -n "/app/stock/in" core/ui/js
rg -n "/app/stock/out" core/ui/js
rg -n "/app/purchase" core/ui/js
rg -n "/app/ledger/history" core/ui/js
rg -n "/app/manufacture" core/ui/js
rg -n "/auth/state|/auth/setup-owner|/auth/login|/auth/logout|/auth/me" core/ui/js
```

## Guard Scope Notes

- Forbidden endpoint and canonical containment checks are exact quoted endpoint searches to avoid regex quoting drift across shells.
- Payload-key and multiplier/base searches remain active. Known compatibility matches are narrowly excluded only for `core/ui/js/token.js` (imperial wrapper payload conversion) and `core/ui/js/cards/recipes.js` (recipe unit label state); new matches elsewhere fail the audit.
- Auth endpoint checks require `/auth/*` strings to live in `core/ui/js/auth.js`, keeping auth UI screens behind the small auth client instead of ad hoc endpoints.

## Forbidden endpoint strings found: /api/ (0)

No matches.

## Forbidden endpoint strings found: /ledger/ (0)

No matches.

## Forbidden endpoint strings found: /manufacturing/ (0)

No matches.

## Forbidden endpoint token patterns found (0)

No matches.

## Forbidden payload keys found (0)

No matches.

## Multiplier/base conversion logic found (0)

No matches.

## Finance suspicious legacy fields found (0)

No matches.

## Canonical endpoint containment check

### ["\']/app/stock/in["\'] (1 matches)

PASS - all matches contained in core/ui/js/api/canonical.js or the documented core/ui/js/token.js compatibility wrapper

```text
core/ui/js/api/canonical.js:42:  return apiPost('/app/stock/in', payload);
```

### ["\']/app/stock/out["\'] (2 matches)

PASS - all matches contained in core/ui/js/api/canonical.js or the documented core/ui/js/token.js compatibility wrapper

```text
core/ui/js/api/canonical.js:61:  return apiPost('/app/stock/out', payload);
core/ui/js/token.js:32:      const targets = ['/app/purchase', '/app/adjust', '/app/consume', '/app/stock/out'];
```

### ["\']/app/purchase["\'] (2 matches)

PASS - all matches contained in core/ui/js/api/canonical.js or the documented core/ui/js/token.js compatibility wrapper

```text
core/ui/js/api/canonical.js:88:  return apiPost('/app/purchase', payload);
core/ui/js/token.js:32:      const targets = ['/app/purchase', '/app/adjust', '/app/consume', '/app/stock/out'];
```

### ["\']/app/ledger/history["\'] (1 matches)

PASS - all matches contained in core/ui/js/api/canonical.js or the documented core/ui/js/token.js compatibility wrapper

```text
core/ui/js/api/canonical.js:98:  return apiGet(qs ? `/app/ledger/history?${qs}` : '/app/ledger/history');
```

### ["\']/app/manufacture["\'] (2 matches)

PASS - all matches contained in core/ui/js/api/canonical.js or the documented core/ui/js/token.js compatibility wrapper

```text
core/ui/js/api/canonical.js:111:  return apiPost('/app/manufacture', payload);
core/ui/js/api/canonical.js:134:  return apiPost('/app/manufacture', payload);
```

## Auth endpoint containment check

### /auth/state (1 matches)

PASS - all matches contained in core/ui/js/auth.js

```text
core/ui/js/auth.js:40:  return authRequest('/auth/state');
```

### /auth/setup-owner (1 matches)

PASS - all matches contained in core/ui/js/auth.js

```text
core/ui/js/auth.js:44:  return authRequest('/auth/setup-owner', 'POST', payload);
```

### /auth/login (1 matches)

PASS - all matches contained in core/ui/js/auth.js

```text
core/ui/js/auth.js:48:  return authRequest('/auth/login', 'POST', payload);
```

### /auth/logout (1 matches)

PASS - all matches contained in core/ui/js/auth.js

```text
core/ui/js/auth.js:52:  return authRequest('/auth/logout', 'POST', {});
```

### /auth/me (1 matches)

PASS - all matches contained in core/ui/js/auth.js

```text
core/ui/js/auth.js:56:  return authRequest('/auth/me');
```

## Summary

- Forbidden endpoint matches: 0
- Forbidden payload-key matches: 0
- Multiplier/base-conversion matches: 0
- Finance legacy-field matches: 0
- Canonical containment endpoint violations: 0
- Auth endpoint containment violations: 0
- Final result: **PASS**
