# BUS Core Transparency Report

The BUS Core runtime is built for transparency and local control. This document summarises what the Core does at runtime, where data flows, and how operators can verify behaviour.

## Identity & Versioning

* **Core version**: `${VERSION}` (reported via `/health`).
* **Policy mode**: Loaded from `config/policy.json`. Default is `enforce` with deny-by-default rules.
* **Run identifier**: Every boot emits a unique `run_id` that appears in all API responses and logs.

## Runtime Surfaces

* **HTTP API** (localhost only): `/health`, `/plugins`, `/probe`, `/capabilities`, `/execTransform`, `/policy.simulate`, `/nodes.manifest.sync`, `/transparency.report`, `/logs`.
* **Plugin imports**: Guarded allowlist (`core.contracts.plugin_v2`, `core.services.conn_broker` (via compatibility shim `core.conn_broker`), `core.secrets`, `core.capabilities`). Any other `core.*` import fails at load time.
* **Sandbox**: Transform executions run in an ephemeral subprocess with a per-run temporary directory and a hard timeout.

## Journaling & Audit

* **Journal path**: `data/journal.log` (append-only JSONL). Each entry records `journal_id`, `intent`, hashes of inputs/proposals, policy version, and `prev_hash` for continuity.
* **Audit path**: `data/audit.log` (append-only JSONL). Contains hash-chained records of `commit`, `rollback`, and crash-recovery `replay` events.
* **Crash recovery**: On boot the Core rolls back any uncommitted journal entries and records the rollback in the audit log.

## Capabilities & Manifests

* Core signs capability manifests with an internal HMAC key stored under the local profile directory (`~/.tgc/state` or `%LOCALAPPDATA%\BUSCore\state`).
* `/capabilities` builds the manifest in-memory, returns it immediately, and writes to disk asynchronously (never blocks the request path).
* `/nodes.manifest.sync` validates signatures from remote peers but never writes without verification.

## Telemetry & Diagnostics

* **Telemetry**: Disabled. No network beacons, analytics, or background telemetry are emitted.
* **Diagnostics**: `logs/` contains per-run append-only logs. `/logs` returns the last 200 lines for local inspection only.
* **Policy simulator**: `/policy.simulate` offers an explicit alternative to legacy “dry-run” modes.

## Plugins

* Only configured plugins are exposed on `/plugins` and participate in `/probe`.
* Each plugin manifest declares `id`, `version`, `provides`, `requires`, `stages`, and `trust_tier` for transparency.
* Plugins never persist secrets. They access credentials through `core.secrets.Secrets`, which in turn prefers the OS keyring and falls back to an encrypted local store.

## Operator Checklist

1. Inspect `docs/DATA_LIFECYCLE.md` for retention and clearing procedures.
2. Review `config/policy.json` to understand allowed operations.
3. Start the server (`python -m uvicorn core.api.http:APP ...`) and confirm the startup trust banner.
4. Call `/transparency.report` and verify paths, telemetry status, and enabled plugins.
5. Use `python app.py config status` to review local paths.

This document, alongside the live `/transparency.report`, forms the disclosure package shipped with the Core.
