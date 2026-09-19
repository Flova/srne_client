"""DataUpdateCoordinator that polls an SRNE controller over BLE."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryError,
    ConfigEntryNotReady,
    HomeAssistantError,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .device import SRNEBleDevice, SRNEConnectionError
from .srne.controller import ControllerData
from .srne.identify import DeviceIdentity

_LOGGER = logging.getLogger(__name__)

SRNEConfigEntry = ConfigEntry["SRNECoordinator"]


class SRNECoordinator(DataUpdateCoordinator[ControllerData]):
    """Polls the controller and shares the decoded snapshot with entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: SRNEConfigEntry,
        address: str,
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {address}",
            update_interval=timedelta(seconds=scan_interval),
            config_entry=entry,
        )
        self.address = address
        self.identity: DeviceIdentity | None = None
        # Last known charge/discharge switch state (None until first read). It is
        # read on demand (setup / after a toggle), never in the background poll.
        self.charge_switch_on: bool | None = None
        # When False, the integration has released the BLE connection so the
        # phone app can use it; polling is paused until it is turned back on.
        self.connection_enabled: bool = True
        self._device = SRNEBleDevice(name=entry.title or address)

    def _get_ble_device(self):
        ble_device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if ble_device is None:
            raise ConfigEntryNotReady(
                f"SRNE device {self.address} not found by any Bluetooth adapter "
                "(out of range, or the phone app is holding the connection)"
            )
        return ble_device

    async def async_identify(self) -> None:
        """Best-effort identity read; reject only a *confirmed* non-controller.

        Each module is checked individually, but identity is advisory: if the
        read fails we log and proceed (the real-time poll is the reachability
        gate), so a finicky handshake never blocks setup. We only refuse a
        device that successfully reports a non-controller type.
        """
        try:
            identity = await self._device.async_identify(self._get_ble_device())
        except (SRNEConnectionError, ValueError) as exc:
            _LOGGER.warning(
                "%s: could not read device identity (%s); continuing", self.address, exc
            )
            return

        if not identity.is_controller:
            raise ConfigEntryError(
                f"Device is a {identity.type_name} (type {identity.type_code}), "
                "which this integration does not support yet. Only MPPT charge "
                "controllers are implemented."
            )
        self.identity = identity
        _LOGGER.debug(
            "%s: identified model=%s sw=%s hw=%s",
            self.address, identity.model, identity.software_version,
            identity.hardware_version,
        )

    async def _async_update_data(self) -> ControllerData:
        # While the connection is released (for phone-app use), don't touch the
        # radio; keep the last known data so entities aren't torn down.
        if not self.connection_enabled:
            if self.data is not None:
                return self.data
            raise UpdateFailed("connection is turned off")
        try:
            ble_device = self._get_ble_device()
            data = await self._device.async_poll(ble_device)
        except ConfigEntryNotReady as exc:
            raise UpdateFailed(str(exc)) from exc
        except SRNEConnectionError as exc:
            raise UpdateFailed(str(exc)) from exc

        # After a (re)connect, read the charge switch once - it may have changed
        # while we were disconnected (e.g. toggled from the phone app).
        if self._device.consume_reconnected():
            try:
                self.charge_switch_on = await self._device.async_read_charge_switch(
                    ble_device
                )
            except SRNEConnectionError as exc:
                _LOGGER.debug("%s: charge-switch read after reconnect failed: %s",
                              self.address, exc)
        return data

    async def async_refresh_charge_switch(self) -> None:
        """Read the charge/discharge switch state on demand (not during polling)."""
        if not self.connection_enabled:
            return
        try:
            self.charge_switch_on = await self._device.async_read_charge_switch(
                self._get_ble_device()
            )
        except (SRNEConnectionError, ConfigEntryNotReady) as exc:
            _LOGGER.debug("%s: charge-switch read failed: %s", self.address, exc)
            return
        self.async_update_listeners()

    async def async_set_charge_switch(self, on: bool) -> None:
        """Turn charging on/off, confirm it, and refresh state.

        Raises on failure so Home Assistant surfaces it to the user instead of
        silently showing the wrong state.
        """
        if not self.connection_enabled:
            raise HomeAssistantError(
                "The Bluetooth connection is turned off; turn it on before changing charging."
            )
        try:
            self.charge_switch_on = await self._device.async_set_charge_switch(
                self._get_ble_device(), on
            )
        except (SRNEConnectionError, ConfigEntryNotReady) as exc:
            raise HomeAssistantError(f"Failed to set charging {'on' if on else 'off'}: {exc}") from exc
        self.async_update_listeners()

    async def async_set_connection(self, enabled: bool) -> None:
        """Turn HA's BLE connection on or off.

        Turning it off disconnects and pauses polling so the phone app (or any
        other client) can connect. Turning it on reconnects and resumes.
        """
        self.connection_enabled = enabled
        if enabled:
            await self.async_request_refresh()
        else:
            await self._device.async_disconnect()
        self.async_update_listeners()

    async def async_shutdown(self) -> None:
        await super().async_shutdown()
        await self._device.async_disconnect()
