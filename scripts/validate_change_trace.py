from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path, PurePosixPath


REPO_ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_FILES = {
    "CHANGELOG.md",
    "SOT.md",
    "README.md",
    "01_SYSTEM_MAP.md",
    "02_API_AND_UI_CONTRACT_MAP.md",
    "03_DATA_CONFIG_AND_STATE_MODEL.md",
    "04_SECURITY_TRUST_AND_OPERATIONS.md",
    "05_RELEASE_UPDATE_AND_DEPLOYMENT_FLOW.md",
    "API_CONTRACT.md",
}
DOC_ONLY_ROOTS = {"docs", "license"}
CONTROL_EXTENSIONS = {".py", ".ps1", ".yml", ".yaml", ".toml", ".spec", ".js", ".html", ".css"}
CONTROL_PREFIXES = ("core/", "scripts/", ".github/workflows/")


def run_git(*args: str, allow_failure: bool = False) -> list[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 and not allow_failure:
        stderr = result.stderr.strip() or "git command failed"
        raise RuntimeError(f"git {' '.join(args)} failed: {stderr}")
    output = result.stdout.strip()
    return [line.strip() for line in output.splitlines() if line.strip()]


def normalize_paths(paths: list[str]) -> list[str]:
    normalized = set()
    for path in paths:
        candidate = path.replace("\\", "/")
        if candidate.startswith("./"):
            candidate = candidate[2:]
        if candidate:
            normalized.add(candidate)
    return sorted(normalized)


def collect_changed_files(base_ref: str | None) -> list[str]:
    if base_ref:
        return normalize_paths(run_git("diff", "--name-only", f"{base_ref}...HEAD"))

    changed = set(run_git("diff", "--name-only", "HEAD"))
    changed.update(run_git("diff", "--name-only", "--cached", "HEAD"))
    changed.update(run_git("ls-files", "--others", "--exclude-standard"))
    return normalize_paths(list(changed))


def is_doc_only(path: str) -> bool:
    if path in EXCLUDED_FILES:
        return True
    parts = PurePosixPath(path).parts
    return bool(parts) and parts[0] in DOC_ONLY_ROOTS


def is_control_surface(path: str) -> bool:
    if is_doc_only(path):
        return False
    if path == "launcher.py":
        return True
    if path.startswith(CONTROL_PREFIXES):
        return True
    return PurePosixPath(path).suffix.lower() in CONTROL_EXTENSIONS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enforce changelog/version traceability for control-surface changes."
    )
    parser.add_argument(
        "--base-ref",
        help="Optional git base ref or commit. When provided, validates the diff from base-ref to HEAD.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        changed_files = collect_changed_files(args.base_ref)
    except RuntimeError as exc:
        print(f"Change-trace validation failed: {exc}", file=sys.stderr)
        return 1

    control_files = [path for path in changed_files if is_control_surface(path)]
    if not control_files:
        scope = f" relative to {args.base_ref}...HEAD" if args.base_ref else " relative to HEAD"
        print(f"No code/control-surface changes detected{scope}.")
        return 0

    missing = []
    if "CHANGELOG.md" not in changed_files:
        missing.append("CHANGELOG.md")
    if "core/version.py" not in changed_files:
        missing.append("core/version.py")

    if missing:
        print("Version governance violation.", file=sys.stderr)
        print("Code/control surfaces changed:", file=sys.stderr)
        for path in control_files:
            print(f"- {path}", file=sys.stderr)
        print("This repository requires traceability for meaningful repo changes:", file=sys.stderr)
        print("- CHANGELOG.md must be updated in the same diff.", file=sys.stderr)
        print("- core/version.py must be updated in the same diff.", file=sys.stderr)
        print("- INTERNAL_VERSION must be bumped for meaningful repo changes.", file=sys.stderr)
        print("Missing required file changes:", file=sys.stderr)
        for path in missing:
            print(f"- {path}", file=sys.stderr)
        return 1

    print("Change-trace validation passed: control-surface changes include CHANGELOG.md and core/version.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())