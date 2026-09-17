"""DataUpdateCoordinator that polls an SRNE controller over BLE."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
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
        try:
            return await self._device.async_poll(self._get_ble_device())
        except ConfigEntryNotReady as exc:
            raise UpdateFailed(str(exc)) from exc
        except SRNEConnectionError as exc:
            raise UpdateFailed(str(exc)) from exc

    async def async_shutdown(self) -> None:
        await super().async_shutdown()
        await self._device.async_disconnect()
