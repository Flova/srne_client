#!/usr/bin/env python3
"""Simple SRNE device scanner - shows names, models and device types.

Discovers nearby Bluetooth LE devices and identifies SRNE gear: it keeps
devices whose name matches the SRNE name filter and reads the device *type* and
*model* out of the BLE advertisement.

Usage
-----
    python3 scan.py                 # SRNE-only
    python3 scan.py --all           # show every BLE device (no name filter)
    python3 scan.py --timeout 15    # scan longer
    python3 scan.py --json          # machine-readable output

Requires: pip install bleak
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from srne_ble.discovery import DEFAULT_FILTER_LIST, identify, name_matches


async def run(timeout: float, show_all: bool, as_json: bool) -> int:
    from bleak import BleakScanner

    if not as_json:
        scope = "all BLE devices" if show_all else f"SRNE devices ({', '.join(DEFAULT_FILTER_LIST)})"
        print(f"Scanning {timeout:.0f}s for {scope} ...\n")

    # return_adv=True gives us the advertisement data (name, RSSI, manufacturer).
    found = await BleakScanner.discover(timeout=timeout, return_adv=True)

    devices = []
    for address, (ble_dev, adv) in found.items():
        name = adv.local_name or ble_dev.name
        if not show_all and not name_matches(name):
            continue
        devices.append(
            identify(address, name, adv.rssi, adv.manufacturer_data)
        )

    devices.sort(key=lambda d: (d.rssi is None, -(d.rssi or 0)))  # strongest first

    if as_json:
        print(json.dumps([d.__dict__ for d in devices], indent=2))
        return 0 if devices else 1

    if not devices:
        print("No matching devices found.")
        print("Tips: power the controller, close the phone app (BLE allows one")
        print("connection), move closer, or try --all / --timeout 15.")
        return 1

    print(f"Found {len(devices)} device(s)  [strongest signal first]:\n")
    print(f"  {'ADDRESS':<17}  {'RSSI':>8}   {'NAME':<20}  DEVICE")
    print(f"  {'-'*17}  {'-'*8}   {'-'*20}  {'-'*24}")
    for d in devices:
        print("  " + d.describe())
    print("\nConnect with:  python3 mvp.py read --address <ADDRESS>")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--all", action="store_true", dest="show_all",
                   help="show every BLE device, not just SRNE ones")
    p.add_argument("--timeout", type=float, default=8.0, help="scan duration (s)")
    p.add_argument("--json", action="store_true", help="output JSON")
    args = p.parse_args()
    try:
        return asyncio.run(run(args.timeout, args.show_all, args.json))
    except KeyboardInterrupt:
        return 130
    except ModuleNotFoundError:
        print("bleak is not installed. Run: pip install -r requirements.txt",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
