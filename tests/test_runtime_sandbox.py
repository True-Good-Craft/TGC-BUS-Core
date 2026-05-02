from __future__ import annotations

import io
import json
import subprocess
import sys

import pytest

from core.runtime import sandbox, sandbox_runner


class _FakePlugin:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object], dict[str, object]]] = []

    def plan_transform(self, fn: str, input_data: dict[str, object], *, limits: dict[str, object]) -> dict[str, object]:
        self.calls.append((fn, input_data, limits))
        return {"fn": fn, "input": input_data, "limits": limits}


@pytest.mark.parametrize(
    ("plugin_id", "fn"),
    [
        ("calc.exe", "cmd /c whoami"),
        ("powershell -NoProfile -Command Write-Host pwned", "python -c print(1)"),
        (r"C:\Program Files\Bad App\tool.exe", "--extra-argv=--danger"),
        ("cmd /c echo injected", "&& rm -rf /"),
    ],
)
def test_run_transform_never_places_user_strings_in_subprocess_argv(
    monkeypatch: pytest.MonkeyPatch,
    plugin_id: str,
    fn: str,
) -> None:
    captured: dict[str, object] = {}

    def _fake_run(*args, **kwargs):
        captured["command"] = args[0]
        captured["input"] = kwargs["input"]
        captured["timeout"] = kwargs["timeout"]
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout=b'{"proposal": {"ok": true}}', stderr=b"")

    monkeypatch.setattr("core.runtime.sandbox.subprocess.run", _fake_run)

    result = sandbox.run_transform(plugin_id, fn, {"input": {"value": 1}, "limits": {"rows": 5}}, timeout=999)

    assert result == {"proposal": {"ok": True}}
    assert captured["command"] == [sandbox.sys.executable, "-m", "core.runtime.sandbox_runner"]
    assert captured["timeout"] == 30.0

    command_text = " ".join(captured["command"])
    assert plugin_id not in command_text
    assert fn not in command_text

    stdin_payload = json.loads(captured["input"].decode("utf-8"))
    assert stdin_payload["plugin_id"] == plugin_id
    assert stdin_payload["fn"] == fn
    assert stdin_payload["payload"] == {"input": {"value": 1}, "limits": {"rows": 5}}


def test_sandbox_runner_executes_transform_from_stdin_request(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_plugin = _FakePlugin()
    stdin = io.StringIO(
        json.dumps(
            {
                "plugin_id": "trusted_plugin",
                "fn": "normalize",
                "payload": {"input": {"value": 7}, "limits": {"rows": 1}},
            }
        )
    )
    stdout = io.StringIO()

    monkeypatch.setattr("core.runtime.sandbox_runner._load_plugin", lambda plugin_id: fake_plugin)
    monkeypatch.setattr("sys.stdin", stdin)
    monkeypatch.setattr("sys.stdout", stdout)

    exit_code = sandbox_runner.main([])

    assert exit_code == 0
    assert fake_plugin.calls == [("normalize", {"value": 7}, {"rows": 1})]
    assert json.loads(stdout.getvalue()) == {
        "proposal": {
            "fn": "normalize",
            "input": {"value": 7},
            "limits": {"rows": 1},
        }
    }


def test_sandbox_runner_rejects_malformed_stdin_request(monkeypatch: pytest.MonkeyPatch) -> None:
    stdin = io.StringIO("{not-json")
    stdout = io.StringIO()
    stderr = io.StringIO()

    monkeypatch.setattr("sys.stdin", stdin)
    monkeypatch.setattr("sys.stdout", stdout)
    monkeypatch.setattr("sys.stderr", stderr)

    exit_code = sandbox_runner.main([])

    assert exit_code == 2
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == "sandbox_invalid_request"


@pytest.mark.parametrize(
    ("requested", "expected"),
    [
        (0, 0.5),
        (999, 30.0),
    ],
)
def test_run_transform_clamps_timeout_bounds(monkeypatch: pytest.MonkeyPatch, requested: float, expected: float) -> None:
    captured: dict[str, object] = {}

    def _fake_run(*args, **kwargs):
        captured["timeout"] = kwargs["timeout"]
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout=b'{"proposal": {}}', stderr=b"")

    monkeypatch.setattr("core.runtime.sandbox.subprocess.run", _fake_run)

    result = sandbox.run_transform("trusted_plugin", "normalize", {"input": {}, "limits": {}}, timeout=requested)

    assert result == {"proposal": {}}
    assert captured["timeout"] == expected


def test_run_transform_rejects_non_numeric_timeout() -> None:
    with pytest.raises(sandbox.SandboxError, match="sandbox_invalid_timeout"):
        sandbox.run_transform("trusted_plugin", "normalize", {"input": {}, "limits": {}}, timeout=float("nan"))