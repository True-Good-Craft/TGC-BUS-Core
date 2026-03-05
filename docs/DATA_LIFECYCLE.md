# BUS Core Data Lifecycle

This document explains how BUS Core handles data, where it is stored, and how operators can clear or rotate it.

## Storage Locations

| Path | Purpose | Notes |
| ---- | ------- | ----- |
| `data/journal.log` | Write-ahead log (JSONL) | Append-only; records prepare phase details. |
| `data/audit.log` | Audit chain (JSONL) | Hash chained; records commit/rollback/replay events. |
| `logs/` | Runtime logs | Per-run file named `core_<run_id>.log`; `/logs` endpoint tails last 200 lines. |
| `data/session_token.txt` | Current session token | Regenerated on each boot; can be cleared via `config clear --what data`. |
| `~/.tgc/secrets` or `%LOCALAPPDATA%\BUSCore\secrets` | Encrypted secrets store | Managed by `core.secrets`; populated through `python app.py secrets set ...`. |
| `plugins/<id>/settings.json` | Optional read-only plugin settings | Never written by plugins; toggle read-only via `python app.py config settings-ro`. |
| `~/.tgc/state/system_manifest.json` | Last capability manifest | Written asynchronously by `/capabilities`. |

## Lifecycle Principles

1. **Core-owned writes only** – Plugins never write to disk. All stateful writes go through Core primitives.
2. **Two-phase writes** – `write()` and successful `transform()` calls record a journal entry before committing. Audit entries follow once commits/rollbacks resolve.
3. **Crash safety** – On startup, the journal manager rolls back any entry without an audit record and appends a `rollback` event.
4. **No telemetry** – Logs are local only; no remote upload or background diagnostics.
5. **Secrets in RAM** – Encryption keys are held in-memory; decrypted payloads are never written to disk.

## Retention & Rotation

* Journals and audits are retained until an operator deletes them. Suggested practice: archive after review, then remove with `python app.py config clear --what data`.
* Logs follow the same manual retention policy. Each boot creates a new file.
* Session tokens are regenerated automatically and stored in `data/session_token.txt` for CLI convenience.

## Operator Controls

* **Secrets** – Run `python app.py secrets set --plugin <id> --key <name>` to write secrets. Remove them with `python app.py config clear --what secrets`.
* **Data** – Run `python app.py config clear --what data` to clear journals, logs, and session tokens. This does not touch plugin settings.
* **Transparency** – `/transparency.report` summarises active paths, retention mode, and plugin state. `/policy.simulate` lets operators inspect policy outcomes without performing an action.

## Data Flow Overview

1. **Read**: Requests go through the policy engine; allowed reads return structured data and never write to disk.
2. **Transform**: Input is packaged into a sandboxed subprocess. The subprocess can only propose operations; it does not persist results. The Core records the proposal in the journal and surfaces it back to the caller.
3. **Write**: Not exposed over HTTP in BUS Core, but the primitive is available internally. It records to the journal, re-evaluates policy, and then commits with an audit record.
4. **Secrets**: Plugins retrieve secrets via `core.secrets.Secrets.get` on demand. They never cache or persist them.

For additional context, review `docs/TRANSPARENCY.md` and inspect the live transparency endpoints.
