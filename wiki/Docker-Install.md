> Status: Beta Guide

# Docker Install

Docker deployment is still beta and community-tested. Treat this as a practical starting point rather than final production documentation.

## Core Settings

- Image: `ghcr.io/true-good-craft/tgc-bus-core:latest`
- Port: `8765`
- Persistent mount: `/data`
- Database environment variable: `BUS_DB=/data/app.db`

## Basic Container Requirements

Your container setup should:

1. Pull `ghcr.io/true-good-craft/tgc-bus-core:latest`.
2. Publish container port `8765` to a host port you control.
3. Mount persistent storage to `/data`.
4. Set `BUS_DB=/data/app.db` so the main SQLite database stays on persistent storage.

## Open The UI

- Local host: `http://localhost:8765`
- Other machine on your network, if you intentionally expose the port: `http://<host-ip>:8765`

## Synology Users

If you are testing on Synology NAS, use the Synology-specific guide instead of treating this page as sufficient:

- [Synology NAS Docker Setup (Beta)](Synology-NAS-Docker-Setup-Beta.md)

## Persistence Warning

Do not rely on container stop, reset, or update flows until you have confirmed your persistent storage mapping and backup approach.

## Beta Note

Docker deployment is still a beta/community-tested path. If you hit friction, document it in the [Beta Testing Guide](Beta-Testing-Guide.md) and [Bug Reports](Bug-Reports.md).