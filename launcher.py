# SPDX-License-Identifier: AGPL-3.0-or-later
"""Canonical native entrypoint for BUS Core."""

from __future__ import annotations

import os
import sys
import argparse
import ctypes
import logging
import copy
import atexit
import threading
import time
import traceback
import re
import subprocess
import webbrowser
from pathlib import Path
from typing import Any, Callable

# --- 1. Dependency Guard ---
try:
    import uvicorn
    from PIL import Image
    from core.appdata.paths import resolve_db_path
    from core.config.manager import load_config
    from core.runtime import update_cache
    from core.version import VERSION as CURRENT_VERSION
    from tgc.bootstrap_fs import DATA, LOGS
    from core.config.paths import APP_ROOT, STATE_DIR
    from core.runtime.instance_lock import (
        InstanceLock,
        InstanceOwnershipError,
        acquire_db_owner_lock,
    )
except ImportError as e:
    print("!"*60)
    print(f"CRITICAL: Missing dependency - {e}")
    print("Please run: pip install -r requirements.txt")
    print("!"*60)
    try:
        input("Press Enter to exit...")
    except EOFError:  # Optional console prompt; dependency failure exit remains authoritative.
        pass
    sys.exit(1)

try:
    import pystray
except ImportError:
    print("!"*60)
    print("CRITICAL: Missing dependency - pystray")
    print("Please run: pip install -r requirements.txt")
    print("!"*60)
    sys.exit(1)
except Exception:
    # Ignore runtime errors during import (e.g. X11 missing)
    pystray = None

logger = logging.getLogger(__name__)
_SEMVER_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def _write_launcher_log(message: str) -> None:
    _ensure_runtime_dirs()
    log_path = LOGS / "launcher.log"
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(f"[{timestamp}] {message}\n")


def _startup_log(message: str) -> None:
    logger.info(message)
    try:
        _write_launcher_log(message)
    except Exception:  # Best-effort launcher log; startup continues if log path is unavailable.
        pass


def _write_tray_failure_log(exc: Exception) -> Path:
    """Persist launcher failure details to disk."""
    _ensure_runtime_dirs()
    log_path = LOGS / "launcher.log"
    details = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(f"[{timestamp}] Failed to initialize system tray.\n\n{details}\n")
    return log_path


def _show_tray_failure_message(exc: Exception, log_path: Path) -> None:
    """Show a fail-loud message box when tray creation fails on Windows."""
    if os.name != "nt":
        return
    try:
        message = (
            "TGC BUS Core could not start the system tray icon and will now exit.\n\n"
            f"Error: {exc}\n\n"
            f"Details were written to:\n{log_path}"
        )
        ctypes.windll.user32.MessageBoxW(0, message, "TGC BUS Core Startup Error", 0x10)
    except Exception:  # Optional Windows UI notification; tray startup failure still exits.
        pass


def _ensure_standard_streams() -> None:
    """Ensure streams exist for windowed executable environments."""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


def _uvicorn_log_config_no_tty() -> dict:
    """Disable uvicorn color auto-detection to avoid isatty() on missing TTY streams."""
    config = copy.deepcopy(uvicorn.config.LOGGING_CONFIG)
    for formatter_name in ("default", "access"):
        formatter = config.get("formatters", {}).get(formatter_name)
        if formatter is not None:
            formatter["use_colors"] = False
    return config

def _ensure_runtime_dirs() -> None:
    for path in (DATA, LOGS):
        path.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        (APP_ROOT / "secrets").mkdir(parents=True, exist_ok=True)
        STATE_DIR.mkdir(parents=True, exist_ok=True)

# --- 2. Window Management (Stealth Mode) ---
def hide_console():
    """Vanishes the console window."""
    if os.name == 'nt':
        try:
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 0) # SW_HIDE
        except Exception:  # Optional Windows console control; hidden mode remains best-effort.
            pass

def show_console():
    """Restores the console window."""
    if os.name == 'nt':
        try:
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 5) # SW_SHOW
                ctypes.windll.user32.SetForegroundWindow(hwnd)
        except Exception:  # Optional Windows console control; showing console remains best-effort.
            pass

# --- 3. Browser Helper ---
def open_dashboard(port):
    """Opens dashboard in standard browser tab."""
    url = f"http://127.0.0.1:{port}/ui/shell.html"
    webbrowser.open(url)


def acquire_launcher_db_lock(port: int) -> InstanceLock:
    db_path = Path(resolve_db_path())
    return acquire_db_owner_lock(db_path, app_root=APP_ROOT, port=port, export_env=True)


def _parse_semver(raw: str) -> tuple[int, int, int] | None:
    match = _SEMVER_PATTERN.fullmatch(raw)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def _current_executable_path() -> Path | None:
    executable = getattr(sys, "executable", None)
    if not executable:
        return None
    try:
        return Path(executable).resolve(strict=False)
    except Exception:
        return None


def _verified_ready_candidate(
    *,
    state: dict[str, Any],
    cache_root: Path,
    current_version: str,
    current_executable: Path | None,
) -> dict[str, str] | None:
    ready = state.get("verified_ready")
    if not isinstance(ready, dict):
        _startup_log("[launcher] verified_ready not present; continuing current version.")
        return None

    version = ready.get("version")
    exe_path_value = ready.get("exe_path")
    if not isinstance(version, str) or not isinstance(exe_path_value, str) or not exe_path_value.strip():
        _startup_log("[launcher] verified_ready invalid/incomplete; continuing current version.")
        return None

    candidate_semver = _parse_semver(version)
    current_semver = _parse_semver(current_version)
    if candidate_semver is None or current_semver is None or candidate_semver <= current_semver:
        _startup_log("[launcher] verified_ready present but not newer; continuing current version.")
        return None

    candidate_exe = Path(exe_path_value).resolve(strict=False)
    if not candidate_exe.exists() or not candidate_exe.is_file():
        _startup_log("[launcher] verified_ready executable missing; continuing current version.")
        return None

    versions_root = update_cache.versions_dir(cache_root).resolve(strict=False)
    expected_dir = (versions_root / version).resolve(strict=False)
    try:
        candidate_exe.relative_to(expected_dir)
    except ValueError:
        _startup_log("[launcher] verified_ready executable path is outside versions/<version>; continuing current version.")
        return None

    if current_executable is not None and candidate_exe == current_executable:
        _startup_log("[launcher] verified_ready executable matches current executable; continuing current version.")
        return None

    return {"version": version, "exe_path": str(candidate_exe)}


def _ask_windows_use_verified(version: str) -> bool:
    if os.name != "nt":
        return False
    try:
        prompt = f"A verified newer BUS Core version is ready. Run version {version} now?"
        MB_YESNO = 0x4
        MB_ICONQUESTION = 0x20
        IDYES = 6
        result = ctypes.windll.user32.MessageBoxW(0, prompt, "TGC BUS Core Update", MB_YESNO | MB_ICONQUESTION)
        return result == IDYES
    except Exception:
        return False


def _decide_verified_launch_action(
    *,
    verified_launch_policy: str,
    candidate: dict[str, str] | None,
    ask_user: Callable[[str], bool],
) -> tuple[str, dict[str, str] | None]:
    if candidate is None:
        return "current", None

    policy = (verified_launch_policy or "ask").strip().lower()
    if policy == "current_only":
        _startup_log("[launcher] verified_ready present but policy is current_only; continuing current version.")
        return "current", None
    if policy == "always_newest":
        _startup_log(f"[launcher] verified_ready selected by policy always_newest (version {candidate['version']}).")
        return "launch", candidate

    if os.name != "nt":
        _startup_log("[launcher] verified_ready available; ask policy defaults to current on non-Windows.")
        return "current", None

    if ask_user(candidate["version"]):
        _startup_log(f"[launcher] verified_ready selected by user prompt (version {candidate['version']}).")
        return "launch", candidate

    _startup_log("[launcher] verified_ready prompt declined; continuing current version.")
    return "current", None


def _launch_verified_executable(*, exe_path: str, port: int, force_dev: bool) -> bool:
    command = [exe_path, "--port", str(port)]
    if force_dev:
        command.append("--dev")
    try:
        subprocess.Popen(command)  # noqa: S603
        return True
    except Exception as exc:
        _startup_log(f"[launcher] verified launch failed ({exc}); continuing current version.")
        return False


def _maybe_handoff_to_verified_ready(*, verified_launch_policy: str, port: int, force_dev: bool) -> bool:
    cache_root = update_cache.cache_root()
    state = update_cache.read_state(cache_root, active_version=CURRENT_VERSION)
    candidate = _verified_ready_candidate(
        state=state,
        cache_root=cache_root,
        current_version=CURRENT_VERSION,
        current_executable=_current_executable_path(),
    )
    action, selection = _decide_verified_launch_action(
        verified_launch_policy=verified_launch_policy,
        candidate=candidate,
        ask_user=_ask_windows_use_verified,
    )
    if action != "launch" or selection is None:
        return False

    launched = _launch_verified_executable(exe_path=selection["exe_path"], port=port, force_dev=force_dev)
    if launched:
        _startup_log(f"[launcher] handoff launched verified version {selection['version']}; exiting bootstrap process.")
    return launched


def _exit_already_running(exc: InstanceOwnershipError) -> None:
    db_path = getattr(exc, "db_path", None) or Path(resolve_db_path())
    user_message = (
        "BUS Core is already running.\n\n"
        f"Database:\n{db_path}\n\n"
        "Close the existing BUS Core window before starting another copy."
    )
    log_message = str(exc)
    if not log_message.startswith("BUS Core is already running for this database."):
        log_message = f"BUS Core is already running for this database. {log_message}"
    print(user_message)
    try:
        _write_launcher_log(log_message)
    except Exception:  # Best-effort launcher log; already-running exit remains authoritative.
        pass
    sys.exit(2)


# --- 4. Main Execution ---
def main():
    _ensure_runtime_dirs()
    _ensure_standard_streams()
    uvicorn_log_config = _uvicorn_log_config_no_tty()

    # A. Parse Explicit Command
    parser = argparse.ArgumentParser()
    parser.add_argument("--dev", action="store_true", help="Run in Developer Mode (Visible Console)")
    parser.add_argument("--port", type=int, default=8765, help="Port to run on")
    # Parse known args to tolerate extra args if any
    args, unknown = parser.parse_known_args()

    # B. Determine Mode
    # "No command = no devmode" -> Defaults to False
    force_dev = args.dev or os.environ.get("BUS_DEV") == "1"

    try:
        launcher_lock = acquire_launcher_db_lock(args.port)
    except InstanceOwnershipError as exc:
        _exit_already_running(exc)
    atexit.register(launcher_lock.release)

    cfg = load_config()
    if _maybe_handoff_to_verified_ready(
        verified_launch_policy=cfg.updates.verified_launch_policy,
        port=args.port,
        force_dev=force_dev,
    ):
        sys.exit(0)

    if force_dev and not getattr(sys, "frozen", False):
        print("--- DEV MODE: Console Visible ---")
        os.environ["BUS_DEV"] = "1" # Enforce strict SOT rule

        # IMPORTANT: Never enable uvicorn reload inside a frozen (PyInstaller) exe.
        # It will fork/loop endlessly.
        is_frozen = getattr(sys, "frozen", False)

        # Blocking Run with Reload (only from source, never from EXE)
        # NOTE: core.api.http initializes CORE on startup due to our fix
        uvicorn.run(
            "core.api.http:create_app",
            host="127.0.0.1",
            port=args.port,
            reload=(not is_frozen),
            log_config=uvicorn_log_config,
            factory=True,
        )
        return

    # C. PROD MODE: Stealth Default
    hide_console()

    is_frozen = getattr(sys, "frozen", False)
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    logo_path = base / "core" / "ui" / "Logo.png"
    logger.debug("Tray icon base path resolved (frozen=%s): %s", is_frozen, logo_path)
    try:
        icon_image = Image.open(logo_path)
    except Exception as exc:
        logger.warning("Unable to load tray icon from %s: %s", logo_path, exc)
        icon_image = Image.new('RGB', (64, 64), color=(73, 109, 137))

    # Threaded Server
    from core.api.http import build_app

    app_instance, _ = build_app()

    server = uvicorn.Server(
        uvicorn.Config(
            app_instance,
            host="127.0.0.1",
            port=args.port,
            log_level="error",
            log_config=uvicorn_log_config,
        )
    )

    def run_server():
        # log_level error to keep console clean (even if hidden)
        server.run()

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    # Auto-Launch (Delayed)
    if not cfg.launcher.auto_start_in_tray:
        def launch():
            time.sleep(1.5)
            open_dashboard(args.port)
        threading.Thread(target=launch, daemon=True).start()

    if pystray is None:
        err = RuntimeError("pystray is unavailable in this environment")
        log_path = _write_tray_failure_log(err)
        _show_tray_failure_message(err, log_path)
        sys.exit(1)

    def on_quit(icon, item):
        server.should_exit = True
        server.force_exit = True
        icon.stop()
        server_thread.join(timeout=5)
        sys.exit(0)

    try:
        menu = pystray.Menu(
            pystray.MenuItem("Open Dashboard", lambda i,t: open_dashboard(args.port)),
            pystray.MenuItem("Show Console", lambda i,t: show_console()),
            pystray.MenuItem("Quit BUS Core", on_quit)
        )

        icon = pystray.Icon("BUS Core", icon_image, "TGC BUS Core", menu)
        icon.run()
    except Exception as exc:
        server.should_exit = True
        server.force_exit = True
        log_path = _write_tray_failure_log(exc)
        _show_tray_failure_message(exc, log_path)
        sys.exit(1)

if __name__ == "__main__":
    main()




