# Running Tests

## Full suite
```bash
pytest -q
```

## Layers (markers)
```bash
pytest -q -m unit
pytest -q -m api
pytest -q -m integration
```

## Strictness checks
```bash
pytest -q --strict-markers
pytest -q -W error::DeprecationWarning
```

## Marker meaning
- `unit`: isolated logic tests, no app server startup required.
- `api`: route contract tests through `TestClient` + isolated test DB.
- `integration`: cross-component flows (DB + filesystem journal/backup behavior).
- `smoke`: optional top-level user-journey checks.
- `slow`: optional long-running tests.

## Runtime target
Typical local runtime target is under ~30 seconds on a warm environment.
