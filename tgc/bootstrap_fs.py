# SPDX-License-Identifier: AGPL-3.0-or-later
# Compatibility shim for legacy imports:
#   from tgc.bootstrap_fs import DATA, LOGS, ensure_first_run, TOKEN_FILE
# Uses canonical paths from this repo; no behavior change beyond directory creation.

from __future__ import annotations

from pathlib import Path

from core.config.paths import APP_DIR, APP_ROOT, DATA_DIR, STATE_DIR  # canonical %LOCALAPPDATA%\BUSCore


# DATA points at the canonical data dir used by the app
DATA: Path = DATA_DIR
DATA.mkdir(parents=True, exist_ok=True)

# LOGS lives alongside data within the app root
LOGS: Path = APP_DIR / "logs"
LOGS.mkdir(parents=True, exist_ok=True)

# Session token file (kept where http.py expects it)
TOKEN_FILE: Path = DATA / "session_token.txt"


def ensure_first_run() -> dict:
    """
    Materialize required runtime folders and return a serializable summary
    used by core/bootstrap reporting.
    """
    # Ensure canonical dirs exist (idempotent)
    root = APP_DIR
    sec = APP_ROOT / "secrets"
    st = STATE_DIR
    LOGS.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)

    return {
        "app_root": str(root.resolve()),
        "data": str(DATA.resolve()),
        "logs": str(LOGS.resolve()),
        "secrets": str(sec.resolve()),
        "state": str(st.resolve()),
    }
