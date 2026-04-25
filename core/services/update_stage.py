# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from core.config.manager import load_config
from core.runtime import update_cache
from core.services.update import UpdateCheckError, UpdateService
from core.services.update_artifact import ArtifactDownloadError, UpdateArtifactService
from core.services.update_exe_trust import ExecutableTrustError, UpdateExecutableTrustService
from core.services.update_extract import ArtifactExtractError, UpdateArtifactExtractService
from core.services.update_promote import UpdatePromotionError, UpdateReadyPromotionService
from core.version import VERSION as CURRENT_VERSION


@dataclass(frozen=True)
class UpdateStageResult:
    ok: bool
    status: str
    current_version: str
    latest_version: str | None
    exe_path: str | None
    restart_available: bool
    error_code: str | None
    error_message: str | None


_STAGE_LOCK = threading.Lock()


class UpdateStageService:
    def __init__(
        self,
        *,
        update_service: UpdateService,
        artifact_service: UpdateArtifactService | None = None,
        extract_service: UpdateArtifactExtractService | None = None,
        exe_trust_service: UpdateExecutableTrustService | None = None,
        promote_service: UpdateReadyPromotionService | None = None,
    ) -> None:
        self._update_service = update_service
        self._artifact_service = artifact_service or UpdateArtifactService()
        self._extract_service = extract_service or UpdateArtifactExtractService()
        self._exe_trust_service = exe_trust_service or UpdateExecutableTrustService()
        self._promote_service = promote_service or UpdateReadyPromotionService()

    def stage_from_config(self, *, root: Path | None = None) -> UpdateStageResult:
        cfg = load_config().updates
        return self.stage(manifest_url=cfg.manifest_url, channel=cfg.channel, root=root)

    def stage(self, *, manifest_url: str, channel: str, root: Path | None = None) -> UpdateStageResult:
        if not _STAGE_LOCK.acquire(blocking=False):
            return _failed(
                latest_version=None,
                code="stage_in_progress",
                message="An update staging operation is already running.",
            )
        try:
            return self._stage_locked(manifest_url=manifest_url, channel=channel, root=root)
        finally:
            _STAGE_LOCK.release()

    def _stage_locked(self, *, manifest_url: str, channel: str, root: Path | None) -> UpdateStageResult:
        latest_version: str | None = None
        try:
            release = self._update_service.select_release(manifest_url=manifest_url, channel=channel)
            latest_version = release.version

            if update_cache._parse_semver(release.version) <= update_cache._parse_semver(CURRENT_VERSION):
                return _failed(
                    latest_version=latest_version,
                    code="update_not_available",
                    message="No newer version is available.",
                )

            target_root = update_cache.ensure_cache_dirs(root)
            state = update_cache.read_state(target_root, active_version=CURRENT_VERSION)
            ready = state.get("verified_ready")
            if isinstance(ready, Mapping):
                ready_version = ready.get("version")
                ready_exe = ready.get("exe_path")
                if isinstance(ready_version, str) and isinstance(ready_exe, str) and update_cache._parse_semver(ready_version) >= update_cache._parse_semver(release.version):
                    return _success(latest_version=latest_version, exe_path=ready_exe)

            if not release.declared_sha256:
                return _failed(
                    latest_version=latest_version,
                    code="missing_declared_sha256",
                    message="Manifest declared sha256 is required for staging.",
                )

            downloaded = self._artifact_service.download_and_verify(release, root=target_root)
            extracted = self._extract_service.extract(downloaded, root=target_root)
            extracted_record = _resolve_extracted_record(
                extracted,
                update_cache.read_state(target_root, active_version=CURRENT_VERSION).get("extracted"),
            )
            if extracted_record is None:
                return _failed(
                    latest_version=latest_version,
                    code="missing_extracted_metadata",
                    message="Extracted update metadata is missing or incomplete.",
                )

            self._exe_trust_service.verify(extracted_record, root=target_root)
            promoted = self._promote_service.promote(
                update_cache.read_state(target_root, active_version=CURRENT_VERSION),
                root=target_root,
            )
            return _success(latest_version=latest_version, exe_path=promoted.exe_path)
        except UpdateCheckError as exc:
            return _failed(latest_version=latest_version, code=exc.code, message=exc.message)
        except ArtifactDownloadError as exc:
            return _failed(latest_version=latest_version, code=exc.code, message=exc.message)
        except ArtifactExtractError as exc:
            return _failed(latest_version=latest_version, code=exc.code, message=exc.message)
        except ExecutableTrustError as exc:
            return _failed(latest_version=latest_version, code=exc.code, message=exc.message)
        except UpdatePromotionError as exc:
            return _failed(latest_version=latest_version, code=exc.code, message=exc.message)
        except Exception:
            return _failed(
                latest_version=latest_version,
                code="update_stage_failed",
                message="Update staging failed.",
            )


def _success(*, latest_version: str | None, exe_path: str) -> UpdateStageResult:
    return UpdateStageResult(
        ok=True,
        status="verified_ready",
        current_version=CURRENT_VERSION,
        latest_version=latest_version,
        exe_path=exe_path,
        restart_available=True,
        error_code=None,
        error_message=None,
    )


def _failed(*, latest_version: str | None, code: str, message: str) -> UpdateStageResult:
    return UpdateStageResult(
        ok=False,
        status="failed",
        current_version=CURRENT_VERSION,
        latest_version=latest_version,
        exe_path=None,
        restart_available=False,
        error_code=code,
        error_message=message,
    )


def _resolve_extracted_record(extracted: Any, state_extracted: Any) -> dict[str, Any] | None:
    candidate = _coerce_extracted_record(extracted)
    if candidate is not None:
        return candidate
    return _coerce_extracted_record(state_extracted)


def _coerce_extracted_record(value: Any) -> dict[str, Any] | None:
    if isinstance(value, Mapping):
        candidate = dict(value)
    else:
        attrs = (
            "version",
            "channel",
            "artifact_path",
            "extracted_dir",
            "exe_path",
            "sha256",
            "size_bytes",
        )
        if not all(hasattr(value, attr) for attr in attrs):
            return None
        candidate = {attr: getattr(value, attr) for attr in attrs}

    required_non_empty = (
        "version",
        "channel",
        "artifact_path",
        "extracted_dir",
        "exe_path",
        "sha256",
    )
    for key in required_non_empty:
        raw = candidate.get(key)
        if not isinstance(raw, str) or not raw.strip():
            return None

    size_bytes = candidate.get("size_bytes")
    if size_bytes is not None and (type(size_bytes) is not int or size_bytes <= 0):
        return None

    return {
        "version": candidate["version"],
        "channel": candidate["channel"],
        "artifact_path": candidate["artifact_path"],
        "extracted_dir": candidate["extracted_dir"],
        "exe_path": candidate["exe_path"],
        "sha256": candidate["sha256"],
        "size_bytes": size_bytes,
    }
