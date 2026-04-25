# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from core.runtime.manifest_trust import SIGNATURE_ALG

ManifestKeyStatus = Literal["active", "deprecated", "revoked"]


@dataclass(frozen=True)
class ManifestPublicKeyPolicy:
    key_id: str
    public_key: bytes
    algorithm: str = SIGNATURE_ALG
    status: ManifestKeyStatus = "active"


# No production manifest signing key has been provisioned yet.
# Future rotation model:
# 1. Add the new public key as active.
# 2. Publish manifests signed by the new key.
# 3. Mark the previous key deprecated while old clients migrate.
# 4. Revoke the previous key only after supported clients trust the replacement.
PRODUCTION_MANIFEST_PUBLIC_KEYS: tuple[ManifestPublicKeyPolicy, ...] = ()


def production_manifest_key_policies() -> tuple[ManifestPublicKeyPolicy, ...]:
    return PRODUCTION_MANIFEST_PUBLIC_KEYS


def active_manifest_public_keys(
    policies: tuple[ManifestPublicKeyPolicy, ...] | None = None,
) -> dict[str, bytes]:
    selected = production_manifest_key_policies() if policies is None else policies
    return {
        policy.key_id: policy.public_key
        for policy in selected
        if policy.status == "active" and policy.algorithm == SIGNATURE_ALG
    }
