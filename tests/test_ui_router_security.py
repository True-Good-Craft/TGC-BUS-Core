from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_legacy_router_uses_allowlisted_route_resolution() -> None:
    router_js = (REPO_ROOT / "core" / "ui" / "js" / "router.js").read_text(encoding="utf-8")

    assert "const routes = Object.create(null);" in router_js
    assert "Object.prototype.hasOwnProperty.call(routes, path)" in router_js
    assert "const handler = resolveRoute(path);" in router_js
    assert "typeof handler === 'function'" in router_js
    assert "routes[path] || routes['/home']" not in router_js


def test_shell_still_uses_app_js_as_canonical_router() -> None:
    shell_html = (REPO_ROOT / "core" / "ui" / "shell.html").read_text(encoding="utf-8")

    assert '<script type="module" src="/ui/app.js' in shell_html