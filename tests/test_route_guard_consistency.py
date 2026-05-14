# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import ast
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

pytestmark = pytest.mark.api

REPO_ROOT = Path(__file__).resolve().parents[1]
SCOPED_ROUTE_FILES = (
    Path("core/api/routes/items.py"),
    Path("core/api/routes/ledger_api.py"),
    Path("core/api/routes/finance_api.py"),
    Path("core/api/routes/config.py"),
    Path("core/api/routes/update.py"),
    Path("core/api/routes/logs_api.py"),
    Path("core/api/routes/users.py"),
    Path("core/api/routes/recipes.py"),
    Path("core/api/routes/manufacturing.py"),
    Path("core/api/routes/vendors.py"),
    Path("core/api/routes/system_state.py"),
)
MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
TEST_SESSION_TOKEN = "route-guard-token"


class _ConfigStub:
    def model_dump(self) -> dict[str, object]:
        return {"ui": {"theme": "system"}}


def _name(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _route_methods(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    methods: set[str] = set()
    for decorator in node.decorator_list:
        call = decorator if isinstance(decorator, ast.Call) else None
        target = call.func if call is not None else decorator
        if isinstance(target, ast.Attribute):
            method = target.attr.upper()
            if method in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                methods.add(method)
    return methods


def _dependency_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    defaults = list(node.args.defaults) + [d for d in node.args.kw_defaults if d is not None]
    dependency_names: set[str] = set()
    for default in defaults:
        if not isinstance(default, ast.Call) or _name(default.func) != "Depends":
            continue
        dependency = default.args[0] if default.args else None
        if dependency is None:
            for keyword in default.keywords:
                if keyword.arg == "dependency":
                    dependency = keyword.value
                    break
        dependency_name = _name(dependency)
        if dependency_name is None and isinstance(dependency, ast.Call):
            dependency_name = _name(dependency.func)
        if dependency_name:
            dependency_names.add(dependency_name)
    return dependency_names


def _route_functions(relative_path: Path) -> list[tuple[str, set[str], set[str]]]:
    source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(relative_path))
    routes: list[tuple[str, set[str], set[str]]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        methods = _route_methods(node)
        if methods:
            routes.append((node.name, methods, _dependency_names(node)))
    return routes


def _require_test_token(request: Request) -> None:
    if request.cookies.get("bus_session") != TEST_SESSION_TOKEN:
        raise HTTPException(status_code=401, detail={"error": "unauthorized"})


def _dummy_session():
    yield object()


def _route_guard_user_context():
    from core.auth.dependencies import AuthUserContext
    from core.auth.permissions import ALL_PERMISSIONS, OWNER_ROLE_KEY

    return AuthUserContext(
        mode="unclaimed",
        user_id=None,
        username="route-guard-test",
        roles=(OWNER_ROLE_KEY,),
        permissions=ALL_PERMISSIONS,
    )


def _override_named_dependency(app: FastAPI, dependant, name: str, override) -> None:
    for child_dependant in getattr(dependant, "dependencies", ()):
        call = getattr(child_dependant, "call", None)
        if getattr(call, "__name__", None) == name:
            app.dependency_overrides[call] = override
        _override_named_dependency(app, child_dependant, name, override)


def _guard_test_app(monkeypatch: pytest.MonkeyPatch, *, allow_writes: bool) -> FastAPI:
    from core.api.routes import config as config_routes
    from core.api.routes import finance_api, ledger_api, logs_api
    from core.auth.dependencies import require_user
    from tgc.security import require_token_ctx

    app = FastAPI()
    app.state.allow_writes = allow_writes
    app.include_router(ledger_api.public_router, prefix="/app")
    app.include_router(ledger_api.router, prefix="/app")
    app.include_router(finance_api.router, prefix="/app")
    app.include_router(config_routes.router, prefix="/app")
    app.include_router(logs_api.public_router)
    app.include_router(logs_api.router)

    app.dependency_overrides[require_token_ctx] = _require_test_token
    app.dependency_overrides[require_user] = _route_guard_user_context
    for route in app.routes:
        dependant = getattr(route, "dependant", None)
        if dependant is not None:
            _override_named_dependency(app, dependant, "require_user", _route_guard_user_context)
    app.dependency_overrides[ledger_api.get_session] = _dummy_session
    app.dependency_overrides[finance_api.get_session] = _dummy_session
    app.dependency_overrides[logs_api.get_session] = _dummy_session
    monkeypatch.setattr(config_routes, "load_config", lambda: _ConfigStub())
    monkeypatch.setattr(config_routes, "save_config", lambda _payload: None)
    return app


def test_all_scoped_mutation_routes_have_route_local_token_and_write_guards() -> None:
    violations: list[str] = []
    for relative_path in SCOPED_ROUTE_FILES:
        for function_name, methods, dependencies in _route_functions(relative_path):
            if not methods.intersection(MUTATING_METHODS):
                continue
            missing: list[str] = []
            if "require_token_ctx" not in dependencies:
                missing.append("require_token_ctx")
            if not {"require_writes", "require_write_access"}.intersection(dependencies):
                missing.append("require_writes/require_write_access")
            if missing:
                violations.append(f"{relative_path}:{function_name} missing {missing}")

    assert not violations, "Sensitive mutations without explicit route-local guards:\n" + "\n".join(violations)


def test_all_scoped_read_routes_have_route_local_token_guards() -> None:
    violations: list[str] = []
    for relative_path in SCOPED_ROUTE_FILES:
        for function_name, methods, dependencies in _route_functions(relative_path):
            if "GET" not in methods:
                continue
            if "require_token_ctx" not in dependencies:
                violations.append(f"{relative_path}:{function_name} missing require_token_ctx")

    assert not violations, "Sensitive reads without explicit route-local token guards:\n" + "\n".join(violations)


def test_all_scoped_routes_have_route_local_permission_guards() -> None:
    violations: list[str] = []
    for relative_path in SCOPED_ROUTE_FILES:
        for function_name, methods, dependencies in _route_functions(relative_path):
            if not methods.intersection({"GET", "POST", "PUT", "PATCH", "DELETE"}):
                continue
            if "require_permission" not in dependencies:
                violations.append(f"{relative_path}:{function_name} missing require_permission")

    assert not violations, "Protected routes without explicit route-local permission guards:\n" + "\n".join(violations)


def test_anonymous_sensitive_reads_and_writes_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _guard_test_app(monkeypatch, allow_writes=True)
    cases = [
        ("get", "/app/ledger/history", {}),
        ("get", "/app/finance/summary", {"params": {"from": "2026-01-01", "to": "2026-01-31"}}),
        ("get", "/app/config", {}),
        ("get", "/app/logs", {}),
        ("post", "/app/stock/in", {"json": {"item_id": 1, "quantity_decimal": "1", "uom": "ea"}}),
        ("post", "/app/finance/expense", {"json": {"amount_cents": 1}}),
        ("post", "/app/config", {"json": {"ui": {"theme": "system"}}}),
    ]

    with TestClient(app) as anonymous_client:
        for method, path, kwargs in cases:
            response = getattr(anonymous_client, method)(path, **kwargs)
            assert response.status_code == 401, f"{method.upper()} {path}: {response.text}"


def test_writes_disabled_blocks_ledger_finance_and_config_mutations(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _guard_test_app(monkeypatch, allow_writes=False)
    headers = {"Cookie": f"bus_session={TEST_SESSION_TOKEN}"}
    with TestClient(app) as client:
        cases = [
            ("/app/stock/in", {"item_id": 1, "quantity_decimal": "1", "uom": "ea", "unit_cost_cents": 0}),
            ("/app/finance/expense", {"amount_cents": 1}),
            ("/app/config", {"ui": {"theme": "system"}}),
        ]
        for path, payload in cases:
            response = client.post(path, json=payload, headers=headers)
            assert response.status_code == 403, f"POST {path}: {response.text}"
            assert "writes_disabled" in response.text


def test_authenticated_config_flow_still_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _guard_test_app(monkeypatch, allow_writes=True)
    headers = {"Cookie": f"bus_session={TEST_SESSION_TOKEN}"}

    with TestClient(app) as client:
        get_response = client.get("/app/config", headers=headers)
        post_response = client.post("/app/config", json={"ui": {"theme": "system"}}, headers=headers)

    assert get_response.status_code == 200, get_response.text
    assert get_response.json() == {"ui": {"theme": "system"}}
    assert post_response.status_code == 200, post_response.text
    assert post_response.json() == {"ok": True, "restart_required": True}
