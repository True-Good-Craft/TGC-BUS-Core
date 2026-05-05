> Status: User Guide

# BUS Core Wiki

BUS Core is a local-first, open-source shop operations tool for small makers, workshops, and owner-operators.

This wiki is for user help, setup guides, beta testing, and common workflows. It is not the engineering source of truth. Canonical engineering truth remains in the main repository documentation, including `/docs`, `SOT.md`, and the existing governance files.

## How This Wiki Publishes

- Edit `/wiki/*.md` in the main repository.
- On push to `main`, GitHub Actions publishes the `/wiki` folder to the GitHub Wiki.
- The GitHub Wiki must be initialized manually once by creating a Home page in the GitHub UI before automatic publishing will work reliably.

## Main Pages

- [Getting Started](Getting-Started.md)
- [Windows Install](Windows-Install.md)
- [Docker Install](Docker-Install.md)
- [Synology NAS Docker Setup (Beta)](Synology-NAS-Docker-Setup-Beta.md)
- [Backups and Data Persistence](Backups-and-Data-Persistence.md)
- [Beta Testing Guide](Beta-Testing-Guide.md)
- [Bug Reports](Bug-Reports.md)
- [Feature Requests](Feature-Requests.md)
- [FAQ](FAQ.md)

## What This Wiki Is For

- Getting BUS Core running locally on supported or community-tested setups.
- Helping beta testers understand what feedback is useful.
- Giving operators a simple place to start before they need deeper engineering docs.
- Collecting common setup questions, bug-report details, and feature-request context.

## What This Wiki Is Not

- It is not the release, schema, API, or governance authority.
- It should not overstate support status or deployment guarantees.
- It should not replace the repository's canonical engineering documents.