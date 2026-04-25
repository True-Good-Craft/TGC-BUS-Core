# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from dataclasses import fields
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from core.config.update_policy import ALLOWED_UPDATE_CHANNELS, DEFAULT_UPDATE_CHANNEL
from core.runtime.manifest_trust import canonicalize_manifest_payload
from core.services.update import ManifestRelease, UpdateService, _resolve_manifest_release

pytestmark = pytest.mark.unit

VALID_SHA256 = "a" * 64
VALID_SHA256_UPPER = "A" * 64
NON_STABLE_CHANNELS = tuple(channel for channel in ALLOWED_UPDATE_CHANNELS if channel != DEFAULT_UPDATE_CHANNEL)


@pytest.fixture(autouse=True)
def production_update_url_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUS_DEV", "0")
    monkeypatch.delenv("BUS_ALLOW_DEV_UPDATE_MANIFEST_URLS", raising=False)


def _latest(download_url: str = "https://example.test/download.zip", **extra: Any) -> dict[str, Any]:
    latest = {
        "version": "9.9.9",
        "release_notes_url": "https://example.test/release-notes",
        "size_bytes": 12345,
        "download": {
            "url": download_url,
            "sha256": VALID_SHA256,
            "size_bytes": 12345,
            "type": "zip",
            "platform": "windows-x64",
        },
    }
    latest.update(extra)
    return latest


def _check(manifest: Any, *, channel: str = DEFAULT_UPDATE_CHANNEL):
    service = UpdateService(fetch_manifest=lambda _url, _timeout: manifest)
    return service.check(manifest_url="https://example.test/manifest.json", channel=channel)


def _release(manifest: Any, *, channel: str = DEFAULT_UPDATE_CHANNEL) -> ManifestRelease:
    return _resolve_manifest_release(manifest, channel)


def _signed_envelope(payload: dict[str, Any], *, key_id: str = "test-manifest-key") -> tuple[dict[str, Any], dict[str, bytes]]:
    import base64

    private_key = Ed25519PrivateKey.generate()
    public_bytes = private_key.public_key().public_bytes(encoding=Encoding.Raw, format=PublicFormat.Raw)
    signature = private_key.sign(canonicalize_manifest_payload(payload))
    return (
        {
            "payload": payload,
            "signature": {
                "alg": "Ed25519",
                "key_id": key_id,
                "sig": base64.b64encode(signature).decode("ascii"),
            },
        },
        {key_id: public_bytes},
    )


def _signed_embedded_manifest(payload: dict[str, Any], *, key_id: str = "test-manifest-key") -> tuple[dict[str, Any], dict[str, bytes]]:
    import base64

    private_key = Ed25519PrivateKey.generate()
    public_bytes = private_key.public_key().public_bytes(encoding=Encoding.Raw, format=PublicFormat.Raw)
    signature = private_key.sign(canonicalize_manifest_payload(payload))
    manifest = dict(payload)
    manifest["signature"] = {
        "alg": "Ed25519",
        "key_id": key_id,
        "sig": base64.b64encode(signature).decode("ascii"),
    }
    return manifest, {key_id: public_bytes}


def test_stable_accepts_legacy_direct_manifest_shape():
    result = _check(
        {
            "version": "9.9.9",
            "download_url": "https://example.test/direct.zip",
            "release_notes_url": "https://example.test/release-notes",
            "sha256": VALID_SHA256,
            "size_bytes": 12345,
            "type": "zip",
            "platform": "windows-x64",
        }
    )

    assert result.error_code is None
    assert result.update_available is True
    assert result.download_url == "https://example.test/direct.zip"


def test_stable_accepts_current_canonical_latest_manifest_shape():
    result = _check(
        {
            "min_supported": "1.0.0",
            "latest": _latest("https://example.test/canonical.zip"),
            "history": [],
        }
    )

    assert result.error_code is None
    assert result.update_available is True
    assert result.download_url == "https://example.test/canonical.zip"


def test_signed_manifest_envelope_verifies_and_parses_normally():
    payload = {"latest": _latest("https://example.test/signed.zip")}
    envelope, trusted_keys = _signed_envelope(payload)
    service = UpdateService(fetch_manifest=lambda _url, _timeout: envelope, trusted_manifest_public_keys=trusted_keys)

    result = service.check(manifest_url="https://example.test/manifest.json", channel="stable")

    assert result.error_code is None
    assert result.update_available is True
    assert result.download_url == "https://example.test/signed.zip"


def test_embedded_signed_manifest_verifies_and_parses_normally():
    payload = {"latest": _latest("https://example.test/embedded.zip")}
    manifest, trusted_keys = _signed_embedded_manifest(payload)
    service = UpdateService(fetch_manifest=lambda _url, _timeout: manifest, trusted_manifest_public_keys=trusted_keys)

    result = service.check(manifest_url="https://example.test/manifest.json", channel="stable")

    assert result.error_code is None
    assert result.update_available is True
    assert result.download_url == "https://example.test/embedded.zip"


def test_embedded_signed_manifest_bad_signature_fails_closed():
    payload = {"latest": _latest("https://example.test/embedded.zip")}
    manifest, trusted_keys = _signed_embedded_manifest(payload)
    manifest["latest"]["download"]["url"] = "https://example.test/tampered.zip"
    service = UpdateService(fetch_manifest=lambda _url, _timeout: manifest, trusted_manifest_public_keys=trusted_keys)

    result = service.check(manifest_url="https://example.test/manifest.json", channel="stable")

    assert result.error_code == "bad_signature"
    assert result.update_available is False
    assert result.download_url is None


def test_signed_manifest_bad_signature_fails_closed():
    payload = {"latest": _latest("https://example.test/signed.zip")}
    envelope, trusted_keys = _signed_envelope(payload)
    envelope["payload"]["latest"]["version"] = "9.9.8"
    service = UpdateService(fetch_manifest=lambda _url, _timeout: envelope, trusted_manifest_public_keys=trusted_keys)

    result = service.check(manifest_url="https://example.test/manifest.json", channel="stable")

    assert result.error_code == "bad_signature"
    assert result.update_available is False
    assert result.download_url is None


def test_unsigned_manifest_fails_when_signed_manifest_is_required():
    service = UpdateService(
        fetch_manifest=lambda _url, _timeout: {"latest": _latest("https://example.test/unsigned.zip")},
        require_signed_manifest=True,
    )

    result = service.check(manifest_url="https://example.test/manifest.json", channel="stable")

    assert result.error_code == "missing_signature"
    assert result.update_available is False
    assert result.download_url is None


def test_signed_manifest_unknown_key_fails_closed():
    payload = {"latest": _latest("https://example.test/signed.zip")}
    envelope, _trusted_keys = _signed_envelope(payload, key_id="unknown")
    service = UpdateService(fetch_manifest=lambda _url, _timeout: envelope, trusted_manifest_public_keys={})

    result = service.check(manifest_url="https://example.test/manifest.json", channel="stable")

    assert result.error_code == "unknown_key_id"
    assert result.update_available is False
    assert result.download_url is None


def test_manifest_validation_runs_after_signed_manifest_unwrap():
    payload = {"latest": _latest("https://example.test/bad-sha.zip", download={"url": "https://example.test/bad-sha.zip", "sha256": "bad"})}
    envelope, trusted_keys = _signed_envelope(payload)
    service = UpdateService(fetch_manifest=lambda _url, _timeout: envelope, trusted_manifest_public_keys=trusted_keys)

    result = service.check(manifest_url="https://example.test/manifest.json", channel="stable")

    assert result.error_code == "invalid_manifest_sha256"
    assert result.update_available is False
    assert result.download_url is None


def test_signed_manifest_preserves_existing_channel_selection_behavior():
    payload = {
        "channels": {
            "stable": {"latest": _latest("https://example.test/stable.zip")},
            "partner-3dque": {"latest": _latest("https://example.test/partner.zip")},
        }
    }
    envelope, trusted_keys = _signed_envelope(payload)
    service = UpdateService(fetch_manifest=lambda _url, _timeout: envelope, trusted_manifest_public_keys=trusted_keys)

    result = service.check(manifest_url="https://example.test/manifest.json", channel="partner-3dque")

    assert result.error_code is None
    assert result.update_available is True
    assert result.download_url == "https://example.test/partner.zip"


def test_additive_metadata_does_not_break_current_latest_manifest_shape():
    result = _check(
        {
            "latest": _latest(
                "https://example.test/additive.zip",
                artifact_type="zip",
                publisher="True Good Craft",
                signer="True Good Craft Release Signing",
                download={
                    "url": "https://example.test/additive.zip",
                    "sha256": VALID_SHA256,
                    "size_bytes": 54321,
                    "signature_url": "https://example.test/additive.zip.sig",
                    "platform": "windows-x64",
                },
            )
        }
    )

    assert result.error_code is None
    assert result.update_available is True
    assert result.download_url == "https://example.test/additive.zip"


def test_validated_canonical_metadata_is_retained_as_manifest_declared_values():
    release = _release(
        {
            "latest": _latest(
                "https://example.test/metadata.zip",
                release_notes_url="https://example.test/notes",
                artifact_type="zip",
                publisher="True Good Craft",
                signer="True Good Craft Release Signing",
                download={
                    "url": "https://example.test/metadata.zip",
                    "sha256": VALID_SHA256,
                    "size_bytes": 54321,
                    "signature_url": "https://example.test/metadata.zip.sig",
                    "kind": "core",
                    "platform": "windows-x64",
                },
            )
        }
    )

    assert release == ManifestRelease(
        version="9.9.9",
        channel="stable",
        download_url="https://example.test/metadata.zip",
        declared_sha256=VALID_SHA256,
        declared_size_bytes=54321,
        release_notes_url="https://example.test/notes",
        artifact_type="zip",
        artifact_kind="core",
        platform="windows-x64",
        signature_url="https://example.test/metadata.zip.sig",
        publisher="True Good Craft",
        signer="True Good Craft Release Signing",
    )


def test_validated_legacy_direct_metadata_is_retained_as_manifest_declared_values():
    release = _release(
        {
            "version": "9.9.9",
            "download_url": "https://example.test/direct-metadata.zip",
            "sha256": VALID_SHA256_UPPER,
            "size_bytes": 22222,
            "release_notes_url": "https://example.test/direct-notes",
            "signature_url": "https://example.test/direct-metadata.zip.sig",
            "artifact_type": "zip",
            "artifact_kind": "core",
            "artifact_platform": "windows-x64",
            "publisher": "True Good Craft",
            "signer": "True Good Craft Release Signing",
        }
    )

    assert release.declared_sha256 == VALID_SHA256_UPPER
    assert release.declared_size_bytes == 22222
    assert release.release_notes_url == "https://example.test/direct-notes"
    assert release.signature_url == "https://example.test/direct-metadata.zip.sig"
    assert release.artifact_type == "zip"
    assert release.artifact_kind == "core"
    assert release.platform == "windows-x64"
    assert release.publisher == "True Good Craft"
    assert release.signer == "True Good Craft Release Signing"


def test_stable_prefers_top_level_latest_when_channels_are_also_present_for_backward_compatibility():
    result = _check(
        {
            "latest": _latest("https://example.test/top-level-stable.zip"),
            "channels": {
                "stable": {
                    "latest": _latest("https://example.test/channels-stable.zip"),
                },
                "partner-3dque": {
                    "latest": _latest("https://example.test/partner.zip"),
                },
            },
        }
    )

    assert result.error_code is None
    assert result.download_url == "https://example.test/top-level-stable.zip"


def test_future_manifest_with_top_level_latest_and_channels_uses_channel_entry_for_non_stable():
    result = _check(
        {
            "latest": _latest("https://example.test/public-stable.zip"),
            "channels": {
                "partner-3dque": {
                    "latest": _latest("https://example.test/partner.zip"),
                }
            },
        },
        channel="partner-3dque",
    )

    assert result.error_code is None
    assert result.download_url == "https://example.test/partner.zip"


def test_uppercase_sha256_is_accepted_when_present():
    result = _check(
        {
            "latest": _latest(
                "https://example.test/uppercase-sha.zip",
                download={
                    "url": "https://example.test/uppercase-sha.zip",
                    "sha256": VALID_SHA256_UPPER,
                    "size_bytes": 12345,
                },
            ),
        }
    )

    assert result.error_code is None
    assert result.download_url == "https://example.test/uppercase-sha.zip"


@pytest.mark.parametrize("channel", ALLOWED_UPDATE_CHANNELS)
def test_channels_object_accepts_each_allowed_channel(channel: str):
    result = _check(
        {
            "channels": {
                channel: {
                    "latest": _latest(f"https://example.test/{channel}.zip"),
                }
            }
        },
        channel=channel,
    )

    assert result.error_code is None
    assert result.update_available is True
    assert result.download_url == f"https://example.test/{channel}.zip"


@pytest.mark.parametrize("channel", ALLOWED_UPDATE_CHANNELS)
def test_top_level_keyed_channel_accepts_each_allowed_channel(channel: str):
    result = _check(
        {
            channel: {
                "latest": _latest(f"https://example.test/top-level-{channel}.zip"),
            }
        },
        channel=channel,
    )

    assert result.error_code is None
    assert result.update_available is True
    assert result.download_url == f"https://example.test/top-level-{channel}.zip"


@pytest.mark.parametrize("channel", NON_STABLE_CHANNELS)
def test_direct_channel_specific_manifest_accepts_non_stable_with_matching_metadata(channel: str):
    result = _check(
        {
            "channel": channel,
            "latest": _latest(f"https://example.test/direct-{channel}.zip"),
        },
        channel=channel,
    )

    assert result.error_code is None
    assert result.update_available is True
    assert result.download_url == f"https://example.test/direct-{channel}.zip"


@pytest.mark.parametrize("channel", NON_STABLE_CHANNELS)
@pytest.mark.parametrize(
    "manifest",
    [
        {"latest": _latest("https://example.test/public-stable.zip")},
        {"version": "9.9.9", "download_url": "https://example.test/public-stable.zip"},
    ],
)
def test_non_stable_channels_reject_channel_less_public_manifest(channel: str, manifest: dict[str, Any]):
    result = _check(manifest, channel=channel)

    assert result.error_code == "channel_not_found"
    assert result.update_available is False
    assert result.download_url is None


@pytest.mark.parametrize("channel", NON_STABLE_CHANNELS)
def test_non_stable_channels_reject_stable_only_channels_manifest(channel: str):
    result = _check(
        {
            "channels": {
                "stable": {
                    "latest": _latest("https://example.test/stable-only.zip"),
                }
            }
        },
        channel=channel,
    )

    assert result.error_code == "channel_not_found"
    assert result.download_url is None


def test_mismatched_channel_metadata_is_rejected():
    result = _check(
        {
            "channels": {
                "partner-3dque": {
                    "channel": "stable",
                    "latest": _latest("https://example.test/mismatch.zip"),
                }
            }
        },
        channel="partner-3dque",
    )

    assert result.error_code == "channel_mismatch"
    assert result.download_url is None


def test_partner_channel_accepts_explicit_channels_entry():
    result = _check(
        {
            "channels": {
                "partner-3dque": {
                    "channel": "partner-3dque",
                    "latest": _latest("https://example.test/partner.zip"),
                }
            }
        },
        channel="partner-3dque",
    )

    assert result.error_code is None
    assert result.download_url == "https://example.test/partner.zip"


@pytest.mark.parametrize(
    "sha256",
    [
        "abc123",
        "g" * 64,
        "a" * 63,
        123,
    ],
)
def test_invalid_sha256_is_rejected(sha256: Any):
    result = _check(
        {
            "latest": _latest(
                download={
                    "url": "https://example.test/bad-sha.zip",
                    "sha256": sha256,
                    "size_bytes": 12345,
                }
            )
        }
    )

    assert result.error_code == "invalid_manifest_sha256"
    assert result.download_url is None


@pytest.mark.parametrize("size_bytes", [0, -1, "12345", True])
def test_invalid_size_bytes_is_rejected(size_bytes: Any):
    result = _check({"latest": _latest(size_bytes=size_bytes)})

    assert result.error_code == "invalid_manifest_size"
    assert result.download_url is None


@pytest.mark.parametrize("release_notes_url", ["", "javascript:alert(1)", "file:///tmp/release", "https://"])
def test_invalid_release_notes_url_is_rejected(release_notes_url: str):
    result = _check({"latest": _latest(release_notes_url=release_notes_url)})

    assert result.error_code == "invalid_release_notes_url"
    assert result.download_url is None


def test_invalid_signature_url_is_rejected():
    result = _check(
        {
            "latest": _latest(
                download={
                    "url": "https://example.test/bad-signature.zip",
                    "signature_url": "javascript:alert(1)",
                }
            )
        }
    )

    assert result.error_code == "invalid_signature_url"
    assert result.download_url is None


@pytest.mark.parametrize(
    "download_url",
    [
        "",
        "javascript:alert(1)",
        "file:///tmp/release.zip",
        "http://example.test/download.zip",
        "https://127.0.0.1/download.zip",
    ],
)
def test_invalid_download_url_is_rejected(download_url: str):
    result = _check({"latest": _latest(download_url)})

    assert result.error_code == "invalid_download_url"
    assert result.download_url is None


@pytest.mark.parametrize("value", ["", "windows x64", " zip", 123])
def test_invalid_artifact_metadata_is_rejected(value: Any):
    result = _check(
        {
            "latest": _latest(
                download={
                    "url": "https://example.test/bad-artifact.zip",
                    "sha256": VALID_SHA256,
                    "size_bytes": 12345,
                    "platform": value,
                }
            )
        }
    )

    assert result.error_code == "invalid_artifact_metadata"
    assert result.download_url is None


def test_manual_download_url_response_shape_remains_six_fields():
    result = _check({"latest": _latest("https://example.test/manual.zip")})

    assert [field.name for field in fields(result)] == [
        "current_version",
        "latest_version",
        "update_available",
        "download_url",
        "error_code",
        "error_message",
    ]
    assert result.error_code is None
    assert result.update_available is True
    assert result.download_url == "https://example.test/manual.zip"
    assert not hasattr(result, "declared_sha256")
