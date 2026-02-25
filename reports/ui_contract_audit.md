# UI Contract Audit Report

- Timestamp (UTC): 2026-02-23T17:52:46Z
- Repo: /workspace/TGC-BUS-Core
- Search tool: rg
- Overall status: **PASS**

## Commands

```bash
rg -n "['\"]/api/" core/ui/js
rg -n "['\"]/ledger/" core/ui/js
rg -n "['\"]/manufacturing/" core/ui/js
rg -n "\bstock_in\b|manufacturing/run|ledger/movements" core/ui/js
rg -n "\bqty\b\s*:|\bqty_base\b\s*:|\bquantity_int\b\s*:|\boutput_qty\b\s*:|\bqty_required\b\s*:" core/ui/js
rg -n "\*1000\b|/1000\b|\bbaseQty\b|\bmultiplier\b" core/ui/js
rg -n "unit_cost_decimal" core/ui/js
rg -n "['\"]/app/stock/in['\"]" core/ui/js
rg -n "['\"]/app/stock/out['\"]" core/ui/js
rg -n "['\"]/app/purchase['\"]" core/ui/js
rg -n "['\"]/app/ledger/history['\"]" core/ui/js
rg -n "['\"]/app/manufacture['\"]" core/ui/js
```

## Forbidden endpoint strings found: ['"]/api/ (0)

No matches.

## Forbidden endpoint strings found: ['"]/ledger/ (0)

No matches.

## Forbidden endpoint strings found: ['"]/manufacturing/ (0)

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

### ['"]/app/stock/in['"] (1 matches)

PASS - all matches contained in core/ui/js/api/canonical.js

```text
core/ui/js/api/canonical.js:36:  return apiPost('/app/stock/in', payload);
```

### ['"]/app/stock/out['"] (1 matches)

PASS - all matches contained in core/ui/js/api/canonical.js

```text
core/ui/js/api/canonical.js:55:  return apiPost('/app/stock/out', payload);
```

### ['"]/app/purchase['"] (1 matches)

PASS - all matches contained in core/ui/js/api/canonical.js

```text
core/ui/js/api/canonical.js:69:  return apiPost('/app/purchase', payload);
```

### ['"]/app/ledger/history['"] (1 matches)

PASS - all matches contained in core/ui/js/api/canonical.js

```text
core/ui/js/api/canonical.js:79:  return apiGet(qs ? `/app/ledger/history?${qs}` : '/app/ledger/history');
```

### ['"]/app/manufacture['"] (2 matches)

PASS - all matches contained in core/ui/js/api/canonical.js

```text
core/ui/js/api/canonical.js:92:  return apiPost('/app/manufacture', payload);
core/ui/js/api/canonical.js:115:  return apiPost('/app/manufacture', payload);
```

## Summary

- Forbidden endpoint matches: 0
- Forbidden payload-key matches: 0
- Multiplier/base-conversion matches: 0
- Finance legacy-field matches: 0
- Canonical containment endpoint violations: 0
- Final result: **PASS**
