#!/usr/bin/env python3
"""Offline decoder: turn a captured hex Modbus reply into readable values.

Useful for testing without hardware, or for decoding a captured frame.
No BLE required.

    python3 tools/decode_frame.py ff0346006400d2...<crc>
"""

from __future__ import annotations

import sys

sys.path.insert(0, ".")

from srne_ble.controller import parse_realtime  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: decode_frame.py <hex-frame>", file=sys.stderr)
        return 2
    hexstr = argv[1].replace(" ", "").replace(":", "")
    try:
        frame = bytes.fromhex(hexstr)
    except ValueError as exc:
        print(f"not valid hex: {exc}", file=sys.stderr)
        return 2
    data = parse_realtime(frame)
    print(data.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
