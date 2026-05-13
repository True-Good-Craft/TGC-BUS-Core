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


def test_shell_exposes_auth_and_security_mount_points() -> None:
    shell_html = (REPO_ROOT / "core" / "ui" / "shell.html").read_text(encoding="utf-8")

    assert 'data-role="auth-banner"' in shell_html
    assert 'data-role="auth-gate-screen"' in shell_html
    assert 'data-role="sidebar-auth-zone"' in shell_html
    assert 'href="#/security"' in shell_html
    assert 'data-role="security-root"' in shell_html


def test_auth_client_does_not_use_localstorage_for_authority() -> None:
    auth_js = (REPO_ROOT / "core" / "ui" / "js" / "auth.js").read_text(encoding="utf-8")

    assert "localStorage" not in auth_js
    for name in (
        "getAuthState",
        "setupOwner",
        "login",
        "logout",
        "getMe",
        "listUsers",
        "createUser",
        "updateUser",
        "disableUser",
        "enableUser",
        "resetPassword",
        "listRoles",
        "setUserRoles",
        "listSessions",
        "revokeSession",
        "listAudit",
    ):
        assert f"function {name}" in auth_js


def test_auth_ui_modules_do_not_store_secrets_or_authority() -> None:
    sensitive_terms = ("password", "recovery", "session", "token", "permission", "auth")
    for relative in (
        ("core", "ui", "app.js"),
        ("core", "ui", "js", "auth.js"),
        ("core", "ui", "js", "auth-ui.js"),
        ("core", "ui", "js", "security.js"),
    ):
        source = (REPO_ROOT / Path(*relative)).read_text(encoding="utf-8")
        for line in source.splitlines():
            if "localStorage" in line or "sessionStorage" in line:
                lowered = line.lower()
                assert not any(term in lowered for term in sensitive_terms), line


def test_recovery_codes_are_rendered_once_without_storage() -> None:
    auth_ui_js = (REPO_ROOT / "core" / "ui" / "js" / "auth-ui.js").read_text(encoding="utf-8")

    assert "renderRecoveryCodes" in auth_ui_js
    assert "result?.recovery_codes" in auth_ui_js
    assert "onContinue?.();" in auth_ui_js
    assert "localStorage" not in auth_ui_js
    assert "sessionStorage" not in auth_ui_js


def test_app_boot_checks_auth_state_before_protected_mount() -> None:
    app_js = (REPO_ROOT / "core" / "ui" / "app.js").read_text(encoding="utf-8")

    assert "await refreshAuthState();\n    if (!canMountNormalApp())" in app_js
    assert "showLoginGate();" in app_js
    assert "openClaimScreen" in app_js
    assert "#/security" in app_js


def test_security_ui_refreshes_auth_state_after_permission_sensitive_actions() -> None:
    app_js = (REPO_ROOT / "core" / "ui" / "app.js").read_text(encoding="utf-8")
    security_js = (REPO_ROOT / "core" / "ui" / "js" / "security.js").read_text(encoding="utf-8")

    assert "onAuthRefresh: refreshAuthState" in app_js
    assert "onLoginRequired: showLoginGate" in app_js
    assert "refreshAuthForSecurity" in security_js
    assert "refreshAfterSecurityMutation(root)" in security_js
    assert security_js.count("await refreshAfterSecurityMutation(root);") >= 3
    assert "error?.status === 401" in security_js
    assert "error?.status === 403" in security_js


def test_token_helper_accepts_claimed_mode_login_required() -> None:
    token_js = (REPO_ROOT / "core" / "ui" / "js" / "token.js").read_text(encoding="utf-8")

    assert "body?.error === 'login_required'" in token_js
    assert "_claimedModeNoLegacyToken = true" in token_js