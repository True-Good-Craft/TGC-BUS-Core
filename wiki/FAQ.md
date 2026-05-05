> Status: Draft

# FAQ

## Is BUS Core cloud-based?

Draft answer: BUS Core is intended to be local-first rather than a cloud-first hosted service.

## Does it require an account?

Draft answer: local use is intended to work without a required cloud account. Final user-facing wording should stay aligned with canonical product docs.

## Can I run it locally?

Draft answer: yes, local operation is the main expected model.

## Can I run it in Docker?

Draft answer: yes, but Docker deployment is still beta/community-tested. See [Docker Install](Docker-Install.md).

## Where is my data stored?

Draft answer: this depends on how BUS Core is deployed. Docker users should review [Backups and Data Persistence](Backups-and-Data-Persistence.md). A fuller persistence audit is still pending.

## How do I back it up?

Draft answer: backup guidance is still being refined. Start with [Backups and Data Persistence](Backups-and-Data-Persistence.md) and verify your storage assumptions before relying on reset or update flows.

## Where do I report bugs?

Use [Bug Reports](Bug-Reports.md).