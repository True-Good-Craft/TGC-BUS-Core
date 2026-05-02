from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_admin_preview_renders_dynamic_values_without_innerhtml() -> None:
    admin_js = (REPO_ROOT / 'core' / 'ui' / 'js' / 'cards' / 'admin.js').read_text(encoding='utf-8')

    assert 'previewBox.innerHTML' not in admin_js
    assert 'renderPreview(previewBox, path, res.schema_version, counts);' in admin_js
    assert "previewBox.replaceChildren(" in admin_js
    assert "item.textContent = `${key}: ${value}`;" in admin_js
    assert "strong.textContent = `${label}:`;" in admin_js


def test_admin_preview_avoids_template_html_for_untrusted_fields() -> None:
    admin_js = (REPO_ROOT / 'core' / 'ui' / 'js' / 'cards' / 'admin.js').read_text(encoding='utf-8')

    assert '${path}</div>' not in admin_js
    assert '${res.schema_version' not in admin_js
    assert '<li>${k}: ${v}</li>' not in admin_js