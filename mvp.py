#!/usr/bin/env python3
"""MVP CLI to talk to an SRNE solar controller over Bluetooth LE.

Run this on the Raspberry Pi (or any Linux box with a BLE adapter).

Examples
--------
    # 1. Find your device (note its address):
    python3 mvp.py scan

    # 2. Read the live data once:
    python3 mvp.py read --address AA:BB:CC:DD:EE:FF

    # 3. Poll continuously every 5 seconds:
    python3 mvp.py poll --address AA:BB:CC:DD:EE:FF --interval 5

    # 4. Read and dump every raw register (for exploring / debugging):
    python3 mvp.py read --address AA:BB:CC:DD:EE:FF --raw

Requires: pip install bleak  (see requirements.txt)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from srne_ble.controller import parse_realtime, realtime_request


async def cmd_scan(args: argparse.Namespace) -> int:
    from srne_ble.client import scan_srne

    print(f"Scanning for {args.timeout:.0f}s ...")
    devices = await scan_srne(timeout=args.timeout, show_all=args.all)
    if args.name:
        devices = [d for d in devices if args.name.upper() in (d.name or "").upper()]
    if not devices:
        print("No devices found. Is the controller powered and in range?")
        print("Tip: close the phone app (BLE allows one connection), or try --all.")
        return 1
    print(f"\nFound {len(devices)} device(s):")
    for d in devices:
        print("  " + d.describe())
    return 0


async def _read_once(address: str, raw: bool) -> int:
    from srne_ble.client import SRNEBLEClient

    async with SRNEBLEClient(address) as client:
        # Identity is advisory - never let it block the real-time read.
        try:
            identity = await client.read_identity()
            print(f"Device     : {identity.type_name} {identity.model} "
                  f"(sw {identity.software_version}, hw {identity.hardware_version})")
            if not identity.is_controller:
                print(f"Note: type {identity.type_code} is not an MPPT controller; "
                      "the values below may not apply.")
        except Exception as exc:  # noqa: BLE001 - advisory only
            print(f"Device     : (identity read failed: {exc})")

        frame = await client.request(realtime_request())
        data = parse_realtime(frame)
        print(data.summary())
        if raw:
            print(f"\nRaw realtime frame: {frame.hex()}")
            print("Raw registers:")
            for addr in sorted(data.registers):
                print(f"  0x{addr:04X} = 0x{data.registers[addr]:04X} "
                      f"({data.registers[addr]})")
    return 0


async def cmd_read(args: argparse.Namespace) -> int:
    return await _read_once(args.address, args.raw)


async def cmd_gatt(args: argparse.Namespace) -> int:
    """Dump the device's GATT services/characteristics (diagnostic)."""
    from bleak import BleakClient

    async with BleakClient(args.address) as client:
        print(f"GATT table for {args.address}:\n")
        for service in client.services:
            print(f"service {service.uuid}  ({service.description})")
            for char in service.characteristics:
                props = ",".join(char.properties)
                print(f"    char {char.uuid}  [{props}]")
    return 0


async def cmd_poll(args: argparse.Namespace) -> int:
    from srne_ble.client import SRNEBLEClient

    async with SRNEBLEClient(args.address) as client:
        while True:
            try:
                data = await client.read_controller()
                print("\033[2J\033[H", end="")  # clear screen
                print(f"SRNE controller @ {args.address}\n")
                print(data.summary())
            except Exception as exc:  # noqa: BLE001 - keep polling on transient errors
                print(f"read error: {exc}", file=sys.stderr)
            await asyncio.sleep(args.interval)


def build_parser() -> argparse.ArgumentParser:
    # A shared parent so -v/--verbose is accepted both before and after the
    # subcommand (e.g. `mvp.py read --address X -v`).
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-v", "--verbose", action="store_true", help="debug logging")

    p = argparse.ArgumentParser(description=__doc__, parents=[common],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("scan", parents=[common], help="discover nearby SRNE devices")
    s.add_argument("--timeout", type=float, default=8.0)
    s.add_argument("--all", action="store_true",
                   help="show every BLE device, not just SRNE ones")
    s.add_argument("--name", default=None,
                   help="only show devices whose name contains this text")
    s.set_defaults(func=cmd_scan)

    r = sub.add_parser("read", parents=[common], help="read the live controller data once")
    r.add_argument("--address", required=True, help="BLE MAC address of the device")
    r.add_argument("--raw", action="store_true", help="also dump raw register values")
    r.set_defaults(func=cmd_read)

    g = sub.add_parser("gatt", parents=[common],
                       help="dump the device's BLE services/characteristics")
    g.add_argument("--address", required=True)
    g.set_defaults(func=cmd_gatt)

    pl = sub.add_parser("poll", parents=[common], help="continuously read live data")
    pl.add_argument("--address", required=True)
    pl.add_argument("--interval", type=float, default=5.0)
    pl.set_defaults(func=cmd_poll)
    return p


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        return asyncio.run(args.func(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
