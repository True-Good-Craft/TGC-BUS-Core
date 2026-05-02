# Copyright (C) 2025 BUS Core Authors
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "core"
PLUGS = ROOT / "plugins"

CORE_ID = "PolyForm-Noncommercial-1.0.0"
PLUG_ID = "Apache-2.0"

SKIP_DIRS = {".git", ".github", ".venv", "venv", "__pycache__", "dist", "build"}

HEADER = "# SPDX-License-Identifier: {spdx}\n# Copyright (c) True Good Craft\n"

def needs_header(text: str) -> bool:
    head = text.splitlines()[:5]
    return not any("SPDX-License-Identifier" in line for line in head)

def apply_headers(base: Path, spdx: str):
    if not base.exists(): return
    for p in base.rglob("*.py"):
        if any(part in SKIP_DIRS or part.startswith(".") for part in p.parts):
            continue
        try:
            t = p.read_text(encoding="utf-8")
        except Exception:
            continue
        if needs_header(t):
            p.write_text(HEADER.format(spdx=spdx) + "\n" + t, encoding="utf-8")

def main():
    apply_headers(CORE, CORE_ID)
    if PLUGS.exists():
        for sub in PLUGS.iterdir():
            if sub.is_dir() and not sub.name.startswith("_"):
                apply_headers(sub, PLUG_ID)
    print("SPDX headers applied.")

if __name__ == "__main__":
    main()
