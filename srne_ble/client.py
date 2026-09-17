"""Async BLE transport for SRNE devices, built on `bleak`.

`bleak` runs on Linux (BlueZ), so this works on a Raspberry Pi, which is the
target for the eventual Home Assistant integration.

The client:

  1. connect to the device (GATT)
  2. subscribe to notifications on the notify characteristic (FFF1)
  3. write a Modbus RTU request to the write characteristic (FFD1, no response)
  4. reassemble the notification chunks into one Modbus frame and return it

`request()` is the core primitive; `read_controller()` is a convenience wrapper
that sends the real-time command and decodes the reply.
"""

from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

from . import protocol
from .controller import ControllerData, parse_realtime, realtime_request
from .discovery import DiscoveredDevice, identify, name_matches
from .identify import DeviceIdentity, read_identity

log = logging.getLogger("srne_ble")


class SRNEError(Exception):
    pass


async def scan(timeout: float = 8.0, name_prefix: Optional[str] = None) -> List[BLEDevice]:
    """Scan for BLE devices, optionally filtering by advertised-name prefix.

    SRNE BT modules typically advertise names beginning with ``BT``, or the
    controller model (e.g. ``ML4860``, ``MC2430``). Pass ``name_prefix=None``
    to list everything.
    """
    devices = await BleakScanner.discover(timeout=timeout)
    if name_prefix:
        prefix = name_prefix.upper()
        devices = [d for d in devices if (d.name or "").upper().startswith(prefix)]
    return devices


async def scan_srne(timeout: float = 8.0, show_all: bool = False) -> List[DiscoveredDevice]:
    """Discover and identify SRNE devices.

    Keeps only devices whose name matches the SRNE name filter (unless
    *show_all*), decodes the device type/model from the BLE advertisement, and
    returns :class:`DiscoveredDevice` objects sorted by signal strength.
    """
    found = await BleakScanner.discover(timeout=timeout, return_adv=True)
    devices: List[DiscoveredDevice] = []
    for address, (ble_dev, adv) in found.items():
        name = adv.local_name or ble_dev.name
        if not show_all and not name_matches(name):
            continue
        devices.append(identify(address, name, adv.rssi, adv.manufacturer_data))
    devices.sort(key=lambda d: (d.rssi is None, -(d.rssi or 0)))
    return devices


class SRNEBLEClient:
    """A connection to a single SRNE BLE device."""

    def __init__(self, address: str, response_timeout: float = 5.0):
        self.address = address
        self.response_timeout = response_timeout
        self._client: Optional[BleakClient] = None
        self._buffer = bytearray()
        self._expected_len = 0
        self._response: "Optional[asyncio.Future[bytes]]" = None
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> "SRNEBLEClient":
        await self.connect()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.disconnect()

    async def connect(self) -> None:
        self._client = BleakClient(self.address)
        await self._client.connect()
        await self._client.start_notify(protocol.NOTIFY_CHAR_UUID, self._on_notify)
        log.info("connected to %s", self.address)

    async def disconnect(self) -> None:
        if self._client is not None:
            try:
                await self._client.stop_notify(protocol.NOTIFY_CHAR_UUID)
            except Exception:  # noqa: BLE001 - best-effort teardown
                pass
            await self._client.disconnect()
            self._client = None

    def _on_notify(self, _char, data: bytearray) -> None:
        """Accumulate notification chunks and resolve when a full frame arrives."""
        if self._response is None or self._response.done():
            return
        self._buffer.extend(data)
        if self._expected_len and len(self._buffer) >= self._expected_len:
            frame = bytes(self._buffer[: self._expected_len])
            self._response.set_result(frame)

    async def request(self, command: bytes) -> bytes:
        """Send a Modbus *command* and return the reassembled reply frame.

        Serialised with a lock so overlapping requests don't mix notifications.
        """
        if self._client is None:
            raise SRNEError("not connected")
        async with self._lock:
            self._buffer = bytearray()
            self._expected_len = protocol.expected_response_length(command)
            loop = asyncio.get_running_loop()
            self._response = loop.create_future()

            await self._client.write_gatt_char(
                protocol.WRITE_CHAR_UUID, command, response=False
            )
            try:
                frame = await asyncio.wait_for(self._response, self.response_timeout)
            except asyncio.TimeoutError as exc:
                raise SRNEError(
                    f"no complete reply within {self.response_timeout}s "
                    f"(got {len(self._buffer)}/{self._expected_len} bytes: "
                    f"{self._buffer.hex()})"
                ) from exc
            finally:
                self._response = None
            return frame

    async def read_identity(self) -> DeviceIdentity:
        """Read the device identity (type/model/firmware version)."""
        return await read_identity(self.request)

    async def read_controller(self) -> ControllerData:
        """Poll and decode the controller real-time data block."""
        frame = await self.request(realtime_request())
        return parse_realtime(frame)
