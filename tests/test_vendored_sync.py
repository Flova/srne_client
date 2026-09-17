"""Guard: the HA component's vendored modules must match the library source.

If this fails, run ``python3 scripts/sync_vendored.py`` to refresh the copy.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.sync_vendored import pairs  # noqa: E402


def test_vendored_modules_in_sync():
    stale = [
        dst.name
        for src, dst in pairs()
        if not dst.exists() or dst.read_bytes() != src.read_bytes()
    ]
    assert not stale, (
        f"vendored copies are stale: {stale}. "
        "Run: python3 scripts/sync_vendored.py"
    )
