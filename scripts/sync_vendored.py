#!/usr/bin/env python3
"""Copy the pure-logic modules into the Home Assistant component (vendoring).

The HA custom component must be self-contained (it can't import the top-level
``srne_ble`` package), so the hardware-independent modules are vendored under
``custom_components/srne_ble/srne/``. This script is the single source of that
copy: edit the originals in ``srne_ble/`` and run this to refresh the vendored
files. ``tests/test_vendored_sync.py`` fails if they ever drift.

    python3 scripts/sync_vendored.py          # copy
    python3 scripts/sync_vendored.py --check   # verify only (exit 1 if stale)
"""

from __future__ import annotations

import sys
from pathlib import Path

# Modules that are safe to vendor (no bleak / no Home Assistant imports).
VENDORED_MODULES = ("crc.py", "protocol.py", "controller.py", "discovery.py", "identify.py")

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "srne_ble"
DST = ROOT / "custom_components" / "srne_ble" / "srne"


def pairs():
    return [(SRC / name, DST / name) for name in VENDORED_MODULES]


def check() -> bool:
    ok = True
    for src, dst in pairs():
        if not dst.exists() or dst.read_bytes() != src.read_bytes():
            print(f"STALE: {dst.relative_to(ROOT)} differs from {src.relative_to(ROOT)}")
            ok = False
    return ok


def sync() -> None:
    DST.mkdir(parents=True, exist_ok=True)
    for src, dst in pairs():
        dst.write_bytes(src.read_bytes())
        print(f"copied {src.relative_to(ROOT)} -> {dst.relative_to(ROOT)}")


def main(argv: list[str]) -> int:
    if "--check" in argv:
        return 0 if check() else 1
    sync()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
