# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from core.config.update_policy import validate_update_channel
from core.runtime import update_cache
from core.version import VERSION as CURRENT_VERSION

WINDOWS_HIDE = 0x08000000 if os.name == "nt" else 0
EXPECTED_PUBLISHER = "True Good Craft"
EXPECTED_SUBJECT_TOKENS = (
    "cn=true good craft",
    "o=true good craft",
)
ALLOWED_SIGNER_THUMBPRINTS: tuple[str, ...] = (
    "55474AA9A2D562022A6590D487045E069457F985",
)
AUTHENTICODE_SCRIPT = """
$path = $args[0]
try {
    $sig = Get-AuthenticodeSignature -LiteralPath $path -ErrorAction Stop
    $cert = $sig.SignerCertificate
    [pscustomobject]@{
        status = [string]$sig.Status
        status_message = [string]$sig.StatusMessage
        subject = if ($cert) { [string]$cert.Subject } else { "" }
        thumbprint = if ($cert) { [string]$cert.Thumbprint } else { "" }
    } | ConvertTo-Json -Compress
}
catch {
    Write-Error $_
    exit 1
}
""".strip()


class ExecutableTrustError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ExtractedExecutable:
    version: str
    channel: str
    extracted_dir: str
    exe_path: str
    sha256: str
    size_bytes: int | None


@dataclass(frozen=True)
class VerifiedExecutable:
    version: str
    channel: str
    extracted_dir: str
    exe_path: str
    sha256: str
    size_bytes: int | None
    publisher: str
    signer_subject: str
    signer_thumbprint: str | None
    verified_at: str


@dataclass(frozen=True)
class AuthenticodeProbe:
    status: str
    status_message: str
    subject: str
    thumbprint: str | None


class UpdateExecutableTrustService:
    def verify(
        self,
        artifact: Mapping[str, Any] | ExtractedExecutable,
        *,
        root: Path | None = None,
    ) -> VerifiedExecutable:
        validated = _coerce_extracted_executable(artifact)
        target_root = update_cache.ensure_cache_dirs(root)
        versions_root = update_cache.versions_dir(target_root)
        expected_dir = (versions_root / validated.version).resolve(strict=False)

        extracted_dir = _ensure_confined_directory(Path(validated.extracted_dir), expected_dir)
        exe_path = _ensure_confined_executable(Path(validated.exe_path), expected_dir)

        if not _is_windows_platform():
            raise ExecutableTrustError(
                "unsupported_platform",
                "Authenticode verification is only supported on Windows.",
            )

        probe = _probe_authenticode_signature(exe_path)
        publisher, signer_thumbprint = _enforce_signer_policy(probe)

        timestamp = _utc_now_iso()
        state = update_cache.read_state(target_root, active_version=CURRENT_VERSION)
        state["exe_verified"] = {
            "version": validated.version,
            "channel": validated.channel,
            "extracted_dir": str(extracted_dir),
            "exe_path": str(exe_path),
            "sha256": validated.sha256,
            "size_bytes": validated.size_bytes,
            "publisher": publisher,
            "signer_subject": probe.subject,
            "signer_thumbprint": signer_thumbprint,
            "verified": True,
            "verified_at": timestamp,
        }
        update_cache.write_state(state, target_root, active_version=CURRENT_VERSION)
        return VerifiedExecutable(
            version=validated.version,
            channel=validated.channel,
            extracted_dir=str(extracted_dir),
            exe_path=str(exe_path),
            sha256=validated.sha256,
            size_bytes=validated.size_bytes,
            publisher=publisher,
            signer_subject=probe.subject,
            signer_thumbprint=signer_thumbprint,
            verified_at=timestamp,
        )


def _coerce_extracted_executable(artifact: Mapping[str, Any] | ExtractedExecutable) -> ExtractedExecutable:
    if isinstance(artifact, ExtractedExecutable):
        return artifact
    if not isinstance(artifact, Mapping):
        raise ExecutableTrustError("invalid_extracted_state", "Executable verification requires extracted update metadata.")

    version = artifact.get("version")
    if not isinstance(version, str) or not update_cache.SEMVER_PATTERN.fullmatch(version):
        raise ExecutableTrustError("invalid_extracted_state", "Extracted version must be strict SemVer.")

    channel = validate_update_channel(artifact.get("channel"))
    extracted_dir = artifact.get("extracted_dir")
    if not isinstance(extracted_dir, str) or not extracted_dir.strip():
        raise ExecutableTrustError("invalid_extracted_dir", "Extracted directory must be a non-empty string.")

    exe_path = artifact.get("exe_path")
    if not isinstance(exe_path, str) or not exe_path.strip():
        raise ExecutableTrustError("invalid_exe_path", "Executable path must be a non-empty string.")

    sha256 = artifact.get("sha256")
    if not isinstance(sha256, str) or not update_cache.re.fullmatch(r"[A-Fa-f0-9]{64}", sha256):
        raise ExecutableTrustError("invalid_extracted_state", "Extracted sha256 must be 64 hex characters.")

    size_bytes = artifact.get("size_bytes")
    if size_bytes is not None and (type(size_bytes) is not int or size_bytes <= 0):
        raise ExecutableTrustError("invalid_extracted_state", "Extracted size_bytes must be null or a positive integer.")

    return ExtractedExecutable(
        version=version,
        channel=channel,
        extracted_dir=extracted_dir,
        exe_path=exe_path,
        sha256=sha256.lower(),
        size_bytes=size_bytes,
    )


def _ensure_confined_directory(path: Path, expected_dir: Path) -> Path:
    if not path.is_absolute():
        raise ExecutableTrustError("invalid_extracted_dir", "Extracted directory must be absolute.")
    resolved_path = path.resolve(strict=False)
    if resolved_path != expected_dir:
        raise ExecutableTrustError("invalid_extracted_dir", "Extracted directory must match updates\\versions\\<version>.")
    return resolved_path


def _ensure_confined_executable(path: Path, expected_dir: Path) -> Path:
    if not path.is_absolute():
        raise ExecutableTrustError("invalid_exe_path", "Executable path must be absolute.")

    resolved_path = path.resolve(strict=False)
    try:
        resolved_path.relative_to(expected_dir)
    except ValueError as exc:
        raise ExecutableTrustError("invalid_exe_path", "Executable path must stay inside the extracted version directory.") from exc

    if resolved_path.suffix.lower() != ".exe":
        raise ExecutableTrustError("invalid_exe_path", "Executable path must end with .exe.")
    if not resolved_path.exists() or not resolved_path.is_file():
        raise ExecutableTrustError("invalid_exe_path", "Executable path does not exist.")
    return resolved_path


def _is_windows_platform() -> bool:
    return os.name == "nt"


def _probe_authenticode_signature(exe_path: Path) -> AuthenticodeProbe:
    command = [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        AUTHENTICODE_SCRIPT,
        str(exe_path),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
            creationflags=WINDOWS_HIDE,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ExecutableTrustError("signature_check_failed", "Authenticode verification tool execution failed.") from exc

    if completed.returncode != 0:
        raise ExecutableTrustError("signature_check_failed", "Authenticode verification returned a tool error.")

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ExecutableTrustError("signature_check_failed", "Authenticode verification returned invalid output.") from exc

    if not isinstance(payload, dict):
        raise ExecutableTrustError("signature_check_failed", "Authenticode verification returned an invalid payload.")

    status = str(payload.get("status", "")).strip()
    status_message = str(payload.get("status_message", "")).strip()
    subject = str(payload.get("subject", "")).strip()
    thumbprint_value = _normalize_thumbprint(payload.get("thumbprint"))
    thumbprint = thumbprint_value or None

    return AuthenticodeProbe(
        status=status,
        status_message=status_message,
        subject=subject,
        thumbprint=thumbprint,
    )


def _enforce_signer_policy(probe: AuthenticodeProbe) -> tuple[str, str | None]:
    if probe.status.lower() != "valid":
        raise ExecutableTrustError("invalid_signature", "Executable Authenticode signature is not valid.")

    normalized_subject = probe.subject.lower()
    if not any(token in normalized_subject for token in EXPECTED_SUBJECT_TOKENS):
        raise ExecutableTrustError("wrong_publisher", "Executable signer subject does not match the expected publisher.")

    normalized_allowed = {_normalize_thumbprint(value) for value in ALLOWED_SIGNER_THUMBPRINTS}
    if probe.thumbprint is None:
        raise ExecutableTrustError("untrusted_signer", "Executable signer thumbprint is missing.")
    if probe.thumbprint not in normalized_allowed:
        raise ExecutableTrustError("untrusted_signer", "Executable signer thumbprint is not trusted.")

    return EXPECTED_PUBLISHER, probe.thumbprint


def _normalize_thumbprint(value: Any) -> str:
    if value is None:
        return ""
    return "".join(str(value).split()).lower()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")