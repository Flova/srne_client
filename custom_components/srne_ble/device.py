"""BLE transport for the SRNE integration, on top of Home Assistant's stack.

Uses ``bleak-retry-connector`` + HA's Bluetooth manager (rather than driving a
scanner directly) so it cooperates with every other BLE integration on the box.
The Modbus framing/decoding lives in the ``srne`` package.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from bleak.backends.device import BLEDevice
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from .srne.controller import ControllerData, parse_realtime, realtime_request
from .srne.identify import DeviceIdentity, read_identity
from .srne.protocol import NOTIFY_CHAR_UUID, WRITE_CHAR_UUID, expected_response_length

_LOGGER = logging.getLogger(__name__)

# Give slow BLE bridges time to stream back the full ~75-byte reply in chunks.
RESPONSE_TIMEOUT = 8.0


class SRNEConnectionError(Exception):
    """Raised when the device cannot be reached or gives no valid reply."""


class SRNEBleDevice:
    """Owns a (re)connectable link to one SRNE controller."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._client: Optional[BleakClientWithServiceCache] = None
        self._lock = asyncio.Lock()
        self._buffer = bytearray()
        self._expected_len = 0
        self._response: "Optional[asyncio.Future[bytes]]" = None

    @property
    def connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    async def _ensure_connected(self, ble_device: BLEDevice) -> BleakClientWithServiceCache:
        if self._client is not None and self._client.is_connected:
            return self._client

        def _on_disconnect(_client: BleakClientWithServiceCache) -> None:
            _LOGGER.debug("%s: disconnected", self._name)
            self._client = None

        client = await establish_connection(
            BleakClientWithServiceCache,
            ble_device,
            self._name,
            disconnected_callback=_on_disconnect,
        )
        self._verify_notify_char(client)
        await client.start_notify(NOTIFY_CHAR_UUID, self._on_notify)
        self._client = client
        _LOGGER.debug("%s: connected", self._name)
        return client

    def _verify_notify_char(self, client: BleakClientWithServiceCache) -> None:
        """Confirm the expected notify characteristic is present, else explain."""
        found = {
            char.uuid.lower()
            for service in client.services
            for char in service.characteristics
        }
        for service in client.services:
            for char in service.characteristics:
                _LOGGER.debug(
                    "%s: GATT %s / %s props=%s",
                    self._name, service.uuid, char.uuid, char.properties,
                )
        if NOTIFY_CHAR_UUID not in found:
            msg = (
                f"notify characteristic {NOTIFY_CHAR_UUID} not present; device "
                f"exposes: {', '.join(sorted(found)) or 'nothing'}. The module may "
                "need pairing, or its GATT wasn't ready."
            )
            _LOGGER.warning("%s: %s", self._name, msg)
            raise SRNEConnectionError(msg)

    def _on_notify(self, _char, data: bytearray) -> None:
        if self._response is None or self._response.done():
            return
        self._buffer.extend(data)
        if self._expected_len and len(self._buffer) >= self._expected_len:
            self._response.set_result(bytes(self._buffer[: self._expected_len]))

    async def _request(self, client: BleakClientWithServiceCache, command: bytes) -> bytes:
        self._buffer = bytearray()
        self._expected_len = expected_response_length(command)
        loop = asyncio.get_running_loop()
        self._response = loop.create_future()
        try:
            await client.write_gatt_char(WRITE_CHAR_UUID, command, response=False)
            return await asyncio.wait_for(self._response, RESPONSE_TIMEOUT)
        except asyncio.TimeoutError as exc:
            raise SRNEConnectionError(
                f"no complete reply in {RESPONSE_TIMEOUT}s "
                f"(got {len(self._buffer)}/{self._expected_len} bytes)"
            ) from exc
        finally:
            self._response = None

    async def async_identify(self, ble_device: BLEDevice) -> DeviceIdentity:
        """Read and decode the device's identity (type/model/version)."""
        async with self._lock:
            try:
                client = await self._ensure_connected(ble_device)

                async def _req(cmd: bytes) -> bytes:
                    return await self._request(client, cmd)

                return await read_identity(_req)
            except SRNEConnectionError:
                raise
            except Exception as exc:  # noqa: BLE001 - normalise transport errors
                await self.async_disconnect()
                raise SRNEConnectionError(str(exc)) from exc

    async def async_poll(self, ble_device: BLEDevice) -> ControllerData:
        """Connect if needed, read the real-time block, and decode it."""
        async with self._lock:
            try:
                client = await self._ensure_connected(ble_device)
                frame = await self._request(client, realtime_request())
                return parse_realtime(frame)
            except SRNEConnectionError:
                raise
            except Exception as exc:  # noqa: BLE001 - normalise transport errors
                # Drop the client so the next poll reconnects cleanly.
                await self.async_disconnect()
                raise SRNEConnectionError(str(exc)) from exc

    async def async_disconnect(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            try:
                await client.disconnect()
            except Exception:  # noqa: BLE001 - best-effort teardown
                pass
