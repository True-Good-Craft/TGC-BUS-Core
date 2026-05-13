# SPDX-License-Identifier: AGPL-3.0-or-later
"""Static permission names and default role bundles for future auth."""

from __future__ import annotations

from types import MappingProxyType

PERMISSION_ADMIN_USERS = "admin.users"
PERMISSION_ADMIN_CONFIG = "admin.config"
PERMISSION_BACKUP_EXPORT = "backup.export"
PERMISSION_BACKUP_RESTORE = "backup.restore"
PERMISSION_FINANCE_READ = "finance.read"
PERMISSION_FINANCE_WRITE = "finance.write"
PERMISSION_INVENTORY_READ = "inventory.read"
PERMISSION_INVENTORY_WRITE = "inventory.write"
PERMISSION_MANUFACTURING_READ = "manufacturing.read"
PERMISSION_MANUFACTURING_RUN = "manufacturing.run"
PERMISSION_RECIPES_READ = "recipes.read"
PERMISSION_RECIPES_WRITE = "recipes.write"
PERMISSION_SYSTEM_RESTART = "system.restart"

OWNER_ROLE_KEY = "owner"
OPERATOR_ROLE_KEY = "operator"
VIEWER_ROLE_KEY = "viewer"

OWNER_PERMISSIONS = tuple(
    sorted(
        {
            PERMISSION_ADMIN_CONFIG,
            PERMISSION_ADMIN_USERS,
            PERMISSION_BACKUP_EXPORT,
            PERMISSION_BACKUP_RESTORE,
            PERMISSION_FINANCE_READ,
            PERMISSION_FINANCE_WRITE,
            PERMISSION_INVENTORY_READ,
            PERMISSION_INVENTORY_WRITE,
            PERMISSION_MANUFACTURING_READ,
            PERMISSION_MANUFACTURING_RUN,
            PERMISSION_RECIPES_READ,
            PERMISSION_RECIPES_WRITE,
            PERMISSION_SYSTEM_RESTART,
        }
    )
)

OPERATOR_PERMISSIONS = tuple(
    sorted(
        {
            PERMISSION_BACKUP_EXPORT,
            PERMISSION_FINANCE_READ,
            PERMISSION_FINANCE_WRITE,
            PERMISSION_INVENTORY_READ,
            PERMISSION_INVENTORY_WRITE,
            PERMISSION_MANUFACTURING_READ,
            PERMISSION_MANUFACTURING_RUN,
            PERMISSION_RECIPES_READ,
            PERMISSION_RECIPES_WRITE,
        }
    )
)

VIEWER_PERMISSIONS = tuple(
    sorted(
        {
            PERMISSION_FINANCE_READ,
            PERMISSION_INVENTORY_READ,
            PERMISSION_MANUFACTURING_READ,
            PERMISSION_RECIPES_READ,
        }
    )
)

DEFAULT_ROLE_BUNDLES = MappingProxyType(
    {
        OWNER_ROLE_KEY: OWNER_PERMISSIONS,
        OPERATOR_ROLE_KEY: OPERATOR_PERMISSIONS,
        VIEWER_ROLE_KEY: VIEWER_PERMISSIONS,
    }
)


def default_role_bundles() -> dict[str, tuple[str, ...]]:
    return {key: tuple(permissions) for key, permissions in DEFAULT_ROLE_BUNDLES.items()}


__all__ = [
    "DEFAULT_ROLE_BUNDLES",
    "OPERATOR_ROLE_KEY",
    "OWNER_ROLE_KEY",
    "PERMISSION_ADMIN_CONFIG",
    "PERMISSION_ADMIN_USERS",
    "PERMISSION_BACKUP_EXPORT",
    "PERMISSION_BACKUP_RESTORE",
    "PERMISSION_FINANCE_READ",
    "PERMISSION_FINANCE_WRITE",
    "PERMISSION_INVENTORY_READ",
    "PERMISSION_INVENTORY_WRITE",
    "PERMISSION_MANUFACTURING_READ",
    "PERMISSION_MANUFACTURING_RUN",
    "PERMISSION_RECIPES_READ",
    "PERMISSION_RECIPES_WRITE",
    "PERMISSION_SYSTEM_RESTART",
    "VIEWER_ROLE_KEY",
    "default_role_bundles",
]
