> Status: Draft

# Backups and Data Persistence

This page is a draft summary of what operators should currently treat as important persistence concerns.

## What Matters Most

The main BUS Core database is the critical durable business state.

For Docker-based setups, the primary persistence target should be:

```text
/data/app.db
```

## SQLite Sidecar Files

Depending on runtime state, SQLite sidecar files may also exist alongside the main database, including files such as WAL or SHM companions.

If those files exist during live operation, treat them as part of the active database state rather than as disposable clutter.

## Before You Rely On Reset Or Update Flows

Before relying on container reset, recreation, or update workflows, make sure you understand:

- where the database file is actually stored
- whether sidecar database files are present
- whether your backup or export process captures what you expect
- whether your storage mount remains attached after container changes

## Pending Audit Scope

Exact persistence requirements for non-database state are still pending audit.

That means operators should not yet assume a final answer for all BUS Core runtime state, including possible logs, journals, exports, config, secrets, session state, or future integration data.

## Current Practical Advice

- Persist `/data` when using Docker.
- Verify that `BUS_DB=/data/app.db` is set.
- Test restore assumptions before treating a reset or update flow as safe.
- Keep this page in draft status until the non-DB persistence surface is audited more completely.