from pathlib import Path

import pytest

from core.utils.pathsafe import PathSafetyError, resolve_path_under_roots


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("raw_path", "expected_code"),
    [
        ("../escape.db.gcm", "path_out_of_roots"),
        ("..\\escape.db.gcm", "path_out_of_roots"),
        ("/etc/passwd", "path_out_of_roots"),
        (r"C:\Windows\System32\drivers\etc\hosts", "path_out_of_roots"),
        (r"\\server\share\file", "path_out_of_roots"),
        (r"\\?\C:\Windows\bad", "path_out_of_roots"),
        ("bad\x00name", "path_invalid"),
    ],
)
def test_resolve_path_under_roots_rejects_dangerous_inputs(tmp_path: Path, raw_path: str, expected_code: str) -> None:
    allowed_root = tmp_path / "exports"
    allowed_root.mkdir(parents=True)

    with pytest.raises(PathSafetyError, match=expected_code):
        resolve_path_under_roots(raw_path, [allowed_root])


def test_resolve_path_under_roots_accepts_valid_in_root_path(tmp_path: Path) -> None:
    allowed_root = tmp_path / "exports"
    nested_file = allowed_root / "nested" / "backup.db.gcm"
    nested_file.parent.mkdir(parents=True)

    resolved = resolve_path_under_roots("nested/backup.db.gcm", [allowed_root])

    assert resolved == nested_file.resolve(strict=False)


def test_path_sensitive_sinks_use_shared_resolved_path_helper() -> None:
    http_source = (REPO_ROOT / "core" / "api" / "http.py").read_text(encoding="utf-8")
    export_source = (REPO_ROOT / "core" / "utils" / "export.py").read_text(encoding="utf-8")

    assert 'subprocess.Popen(["explorer", "/select,", path])' not in http_source
    assert 'subprocess.Popen(["xdg-open", path])' not in http_source
    assert 'os.startfile(path)' not in http_source
    assert '_load_and_decrypt(Path(path), password)' not in export_source
    assert 'resolve_path_under_roots' in http_source
    assert 'resolve_path_under_roots' in export_source