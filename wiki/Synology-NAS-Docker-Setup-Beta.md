> Status: Community-Tested Beta Guide

# Synology NAS Docker Setup (Beta)

> This is a community-tested beta guide. It has been tested on one Synology environment and should be verified by additional users before being treated as final official documentation.

> The main BUS Core business database is persisted through `BUS_DB=/data/app.db`. Additional runtime state such as logs, journals, exports, config, secrets, session state, and future integration data should be audited before this guide is considered final.

This guide was developed and tested on Synology DSM `6.2.4-25556 Update 8`.

## DSM Version Caveat

- On DSM 6.x, Synology uses the `Docker` package and older Docker UI terminology.
- On DSM 7.x, Synology uses `Container Manager` and the names or screens may differ.
- The overall storage, user, environment-variable, and port-mapping ideas should still be similar, but they need wider verification.

## Overview

The key goals are:

1. Run BUS Core from the GHCR image `ghcr.io/true-good-craft/tgc-bus-core:latest`.
2. Persist the main database on Synology storage by mounting a host folder to `/data`.
3. Set `BUS_DB=/data/app.db`.
4. Avoid permission problems by using a dedicated Synology user and aligning folder ownership.

## Create A Dedicated BUS Core User

Create a dedicated Synology user for BUS Core rather than using an admin account.

Suggested flow:

1. In DSM, create a user such as `buscore`.
2. Grant that user access to the shared folder path you will use for persistent data.
3. Keep this user scoped to the minimum access needed for the BUS Core data location.

## Identify UID And GID

If you use SSH or Synology CLI tools, identify the numeric UID and GID for the BUS Core user.

Example:

```bash
id buscore
```

You will use these values to confirm folder ownership and permissions.

## Create The Persistent Storage Path

Create a persistent folder on Synology storage for BUS Core.

Example path:

```text
/volume1/docker/buscore
```

This folder is intended to back the container's `/data` mount.

## Set Folder Ownership And Permissions

Using Synology CLI access, set the folder ownership to the BUS Core user and ensure group-write access is preserved.

Example commands:

```bash
sudo chown -R buscore:users /volume1/docker/buscore
sudo chmod -R 775 /volume1/docker/buscore
sudo find /volume1/docker/buscore -type d -exec chmod g+s {} \;
```

What this does:

- `chown` assigns ownership to the dedicated BUS Core user and group.
- `chmod 775` allows owner and group read/write/execute access while keeping world access read/execute only.
- `g+s` on directories helps newly created files and directories inherit the group consistently.

Adjust the group name if your Synology setup uses a different group than `users`.

## Create The Container

Use the Synology Docker or Container Manager UI to create a container with these core values:

- Image: `ghcr.io/true-good-craft/tgc-bus-core:latest`
- Container port: `8765`
- Host port: `8765` or another port you intentionally choose
- Volume mount: your persistent Synology path mapped to `/data`
- Environment variable: `BUS_DB=/data/app.db`

If your Synology UI supports explicit user or advanced runtime settings, keep notes on what you chose so later testers can compare outcomes.

## Start BUS Core

After the container starts, open BUS Core in your browser.

Common URLs:

- `http://localhost:8765` if you are accessing it from the NAS host context
- `http://<synology-ip>:8765` from another machine on your LAN

## Update Flow

When testing updates, use a controlled recreate flow:

1. Pull or update the image `ghcr.io/true-good-craft/tgc-bus-core:latest`.
2. Stop the running BUS Core container.
3. Recreate or reset the container configuration while preserving the same persistent `/data` mount and `BUS_DB=/data/app.db` setting.
4. Start the new container.
5. Confirm that the expected database is still present.

Do not treat container reset or recreation as safe unless you have already verified what state is truly persisted.

## Troubleshooting

### Permission Problems

Symptoms:

- BUS Core cannot create or update `app.db`.
- The container starts but the database is missing or unwritable.

Checks:

- Confirm the host folder really maps to `/data`.
- Confirm the ownership matches the intended Synology user.
- Recheck `chown`, `chmod 775`, and directory `g+s` settings.

### Browser Access Problems

Symptoms:

- The container appears to be running but the UI does not load.

Checks:

- Confirm the host port is published.
- Confirm you are using the correct NAS IP or host name.
- Confirm no Synology firewall or reverse-proxy rule is blocking access.

### Missing Database Problems

Symptoms:

- The container appears to start fresh every time.
- Expected data is gone after recreate or update.

Checks:

- Confirm `BUS_DB=/data/app.db` is set.
- Confirm the host storage path is persistent and not a temporary container path.
- Confirm the mapped `/data` folder contains the expected SQLite files.
- Remember that SQLite sidecar files may also appear depending on runtime state.

## Beta Validation Request

If you test this on Synology, include these details in your feedback:

- DSM version
- Synology model
- Whether you used DSM 6.x Docker or DSM 7.x Container Manager
- Your storage mapping approach
- Any permission fixes required
- Whether BUS Core restarted cleanly after an image update