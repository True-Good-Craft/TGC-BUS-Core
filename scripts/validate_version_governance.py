from __future__ import annotations

import re
import sys
from pathlib import Path

import tomllib


REPO_ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = REPO_ROOT / "core" / "version.py"
PYPROJECT_FILE = REPO_ROOT / "pyproject.toml"
SOT_FILE = REPO_ROOT / "SOT.md"
WIN_VERSION_FILE = REPO_ROOT / "scripts" / "_win_version_info.txt"

SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
INTERNAL_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$")


def read_version_constants() -> tuple[str | None, str | None]:
    text = VERSION_FILE.read_text(encoding="utf-8")
    version_match = re.search(r'^VERSION\s*=\s*"([^"]+)"\s*$', text, re.MULTILINE)
    internal_match = re.search(r'^INTERNAL_VERSION\s*=\s*"([^"]+)"\s*$', text, re.MULTILINE)
    return (
        version_match.group(1) if version_match else None,
        internal_match.group(1) if internal_match else None,
    )


def read_pyproject_version() -> str | None:
    data = tomllib.loads(PYPROJECT_FILE.read_text(encoding="utf-8"))
    project = data.get("project", {})
    version = project.get("version")
    return version if isinstance(version, str) else None


def read_sot_header_version() -> str | None:
    header_lines = SOT_FILE.read_text(encoding="utf-8").splitlines()[:8]
    for line in header_lines:
        match = re.search(r"\*\*Version:\*\*\s*v([0-9]+\.[0-9]+\.[0-9]+)\b", line)
        if match:
            return match.group(1)
    return None


def read_windows_version(label: str) -> str | None:
    text = WIN_VERSION_FILE.read_text(encoding="utf-8")
    match = re.search(rf"StringStruct\('{label}', '([^']+)'\)", text)
    return match.group(1) if match else None


def main() -> int:
    errors: list[str] = []

    version, internal_version = read_version_constants()
    if version is None:
        errors.append("core/version.py: failed to read VERSION.")
    elif not SEMVER_RE.fullmatch(version):
        errors.append(
            f"core/version.py: VERSION must be strict SemVer X.Y.Z, found {version!r}."
        )

    if internal_version is None:
        errors.append("core/version.py: failed to read INTERNAL_VERSION.")
    elif not INTERNAL_RE.fullmatch(internal_version):
        errors.append(
            "core/version.py: INTERNAL_VERSION must be X.Y.Z.R, "
            f"found {internal_version!r}."
        )

    pyproject_version = read_pyproject_version()
    if pyproject_version is None:
        errors.append("pyproject.toml: failed to read [project].version.")
    elif version is not None and pyproject_version != version:
        errors.append(
            "pyproject.toml: [project].version must match core/version.py VERSION "
            f"({version}), found {pyproject_version}."
        )

    sot_version = read_sot_header_version()
    if sot_version is None:
        errors.append("SOT.md: failed to read the header Version field.")
    elif version is not None and sot_version != version:
        errors.append(
            f"SOT.md: header version must be v{version}, found v{sot_version}."
        )

    for label in ("FileVersion", "ProductVersion"):
        windows_version = read_windows_version(label)
        if windows_version is None:
            errors.append(f"scripts/_win_version_info.txt: failed to read {label}.")
        elif version is not None and windows_version != version:
            errors.append(
                "scripts/_win_version_info.txt: "
                f"{label} must match core/version.py VERSION ({version}), found {windows_version}."
            )

    if errors:
        print("Version governance validation failed.", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(
        "Version governance validation passed: "
        f"VERSION={version}, INTERNAL_VERSION={internal_version}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())