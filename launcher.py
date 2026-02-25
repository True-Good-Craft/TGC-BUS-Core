# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import os
import sys
import argparse
import ctypes
import logging
import copy
import threading
import time
import traceback
import webbrowser
from pathlib import Path

# --- 1. Dependency Guard ---
try:
    import requests
    import uvicorn
    from PIL import Image
    from core.api.http import build_app
    from core.config.manager import load_config
    from tgc.bootstrap_fs import DATA, LOGS
    from core.config.paths import APP_ROOT, STATE_DIR
except ImportError as e:
    print("!"*60)
    print(f"CRITICAL: Missing dependency - {e}")
    print("Please run: pip install -r requirements.txt")
    print("!"*60)
    try:
        input("Press Enter to exit...")
    except EOFError:
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


def _write_tray_failure_log(exc: Exception) -> Path:
    """Persist tray startup failure details to disk."""
    _ensure_runtime_dirs()
    log_path = LOGS / "tray_startup_error.log"
    details = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    log_path.write_text(
        f"[{timestamp}] Failed to initialize system tray.\n\n{details}",
        encoding="utf-8",
    )
    return log_path


def _show_tray_failure_message(log_path: Path) -> None:
    """Show a fail-loud message box when tray creation fails on Windows."""
    if os.name != "nt":
        return
    try:
        message = (
            "TGC BUS Core could not start the system tray icon and will now exit.\n\n"
            f"Details were written to:\n{log_path}"
        )
        ctypes.windll.user32.MessageBoxW(0, message, "TGC BUS Core Startup Error", 0x10)
    except Exception:
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
        except Exception:
            pass

def show_console():
    """Restores the console window."""
    if os.name == 'nt':
        try:
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 5) # SW_SHOW
                ctypes.windll.user32.SetForegroundWindow(hwnd)
        except Exception:
            pass

# --- 3. Browser Helper ---
def open_dashboard(port):
    """Opens dashboard in standard browser tab."""
    url = f"http://127.0.0.1:{port}/ui/shell.html#/home"
    webbrowser.open(url)

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

    if force_dev:
        print("--- DEV MODE: Console Visible ---")
        os.environ["BUS_DEV"] = "1" # Enforce strict SOT rule

        # IMPORTANT: Never enable uvicorn reload inside a frozen (PyInstaller) exe.
        # It will fork/loop endlessly.
        is_frozen = getattr(sys, "frozen", False)

        # Blocking Run with Reload (only from source, never from EXE)
        # NOTE: core.api.http initializes CORE on startup due to our fix
        uvicorn.run(
            "core.api.http:APP",
            host="127.0.0.1",
            port=args.port,
            reload=(not is_frozen),
            log_config=uvicorn_log_config,
        )
        return

    # C. PROD MODE: Stealth Default
    hide_console()

    # Load Config
    cfg = load_config()

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
        _show_tray_failure_message(log_path)
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
        _show_tray_failure_message(log_path)
        sys.exit(1)

if __name__ == "__main__":
    main()
