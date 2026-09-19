"""BLE transport for the SRNE integration, on top of Home Assistant's stack.

Uses ``bleak-retry-connector`` + HA's Bluetooth manager (rather than driving a
scanner directly) so it cooperates with every other BLE integration on the box.
The Modbus framing/decoding lives in the ``srne`` package.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional, Tuple

from bleak.backends.device import BLEDevice
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from .srne.charge import (
    charge_switch_command,
    charge_switch_read_command,
    is_write_ack,
    parse_charge_switch,
)
from .srne.controller import ControllerData, parse_realtime, realtime_request
from .srne.identify import DeviceIdentity, read_identity
from .srne.protocol import NOTIFY_CHAR_UUID, WRITE_CHAR_UUID, expected_response_length

_LOGGER = logging.getLogger(__name__)

# Give slow BLE bridges time to stream back the full ~75-byte reply in chunks.
RESPONSE_TIMEOUT = 8.0


class SRNEConnectionError(Exception):
    """Raised when the device cannot be reached or gives no valid reply."""


class SRNEBleDevice:
    """Talks to one SRNE controller, connecting per operation.

    The connection is opened for each poll/read/write and closed immediately
    after (see ``async_poll`` / ``async_identify``). BLE allows only one central
    connection at a time, so releasing between operations lets the phone app (or
    any other client) connect in the gaps instead of being locked out for as
    long as Home Assistant is running.
    """

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

    async def _connect(self, ble_device: BLEDevice) -> BleakClientWithServiceCache:
        client = await establish_connection(
            BleakClientWithServiceCache,
            ble_device,
            self._name,
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
                client = await self._connect(ble_device)

                async def _req(cmd: bytes) -> bytes:
                    return await self._request(client, cmd)

                return await read_identity(_req)
            except SRNEConnectionError:
                raise
            except Exception as exc:  # noqa: BLE001 - normalise transport errors
                raise SRNEConnectionError(str(exc)) from exc
            finally:
                await self.async_disconnect()

    async def async_poll(
        self, ble_device: BLEDevice
    ) -> Tuple[ControllerData, Optional[bool]]:
        """Read the real-time block and charge-switch state in one connection.

        Returns ``(ControllerData, charge_switch_on)``. The charge-switch read is
        best-effort: on failure it returns ``None`` for that value rather than
        failing the whole poll.
        """
        async with self._lock:
            try:
                client = await self._connect(ble_device)
                data = parse_realtime(await self._request(client, realtime_request()))
                charge_on: Optional[bool] = None
                try:
                    charge_on = parse_charge_switch(
                        await self._request(client, charge_switch_read_command())
                    )
                except Exception as exc:  # noqa: BLE001 - optional value
                    _LOGGER.debug("%s: charge-switch read failed: %s", self._name, exc)
                return data, charge_on
            except SRNEConnectionError:
                raise
            except Exception as exc:  # noqa: BLE001 - normalise transport errors
                raise SRNEConnectionError(str(exc)) from exc
            finally:
                await self.async_disconnect()

    async def async_set_charge_switch(self, ble_device: BLEDevice, on: bool) -> bool:
        """Enable/disable charging (register 0xDF00) and confirm the result.

        Writes the exact 0x06 command, checks the device's write acknowledgement,
        then reads the register back and requires it to match the requested
        state. Raises :class:`SRNEConnectionError` if either check fails, so a
        write is never reported as successful unless the device confirms it.
        """
        command = charge_switch_command(on)
        async with self._lock:
            try:
                client = await self._connect(ble_device)
                ack = await self._request(client, command)
                if not is_write_ack(ack, command):
                    raise SRNEConnectionError(
                        f"charge-switch write not acknowledged (sent {command.hex()}, "
                        f"got {ack.hex()})"
                    )
                state = parse_charge_switch(
                    await self._request(client, charge_switch_read_command())
                )
                if state != on:
                    raise SRNEConnectionError(
                        f"charge switch did not change (requested {'on' if on else 'off'}, "
                        f"reads {'on' if state else 'off'})"
                    )
                _LOGGER.debug("%s: charge switch set to %s", self._name, "on" if on else "off")
                return state
            except SRNEConnectionError:
                raise
            except Exception as exc:  # noqa: BLE001 - normalise transport errors
                raise SRNEConnectionError(str(exc)) from exc
            finally:
                await self.async_disconnect()

    async def async_disconnect(self) -> None:
        """Release the BLE connection so other clients (e.g. the phone app) can use it."""
        client, self._client = self._client, None
        if client is not None:
            try:
                await client.disconnect()
                _LOGGER.debug("%s: disconnected", self._name)
            except Exception:  # noqa: BLE001 - best-effort teardown
                pass
