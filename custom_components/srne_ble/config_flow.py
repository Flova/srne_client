"""Config flow for the SRNE BLE integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)
from .coordinator import SRNEConfigEntry
from .srne.discovery import DiscoveredDevice, identify, name_matches


def _label(dev: DiscoveredDevice) -> str:
    name = dev.custom_name or dev.name or "SRNE device"
    model = f" - {dev.model}" if dev.model else ""
    return f"{name}{model} ({dev.address})"


class SRNEConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SRNE BLE."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered: DiscoveredDevice | None = None
        self._discovered_devices: dict[str, DiscoveredDevice] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle a device discovered by the Bluetooth integration."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._discovered = identify(
            discovery_info.address,
            discovery_info.name,
            discovery_info.rssi,
            discovery_info.manufacturer_data,
        )
        self.context["title_placeholders"] = {"name": _label(self._discovered)}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm a single discovered device."""
        assert self._discovered is not None
        if user_input is not None:
            return self._create_entry(self._discovered)
        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": _label(self._discovered)},
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick from discovered devices or reject if none present."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self._create_entry(self._discovered_devices[address])

        current = self._async_current_ids()
        for info in async_discovered_service_info(self.hass, connectable=True):
            if info.address in current or info.address in self._discovered_devices:
                continue
            if not name_matches(info.name):
                continue
            self._discovered_devices[info.address] = identify(
                info.address, info.name, info.rssi, info.manufacturer_data
            )

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(
                        {
                            addr: _label(dev)
                            for addr, dev in self._discovered_devices.items()
                        }
                    )
                }
            ),
        )

    def _create_entry(self, dev: DiscoveredDevice) -> ConfigFlowResult:
        title = dev.custom_name or dev.name or f"SRNE {dev.address}"
        return self.async_create_entry(
            title=title,
            data={
                CONF_ADDRESS: dev.address,
                "model": dev.model,
                "device_type": dev.type_name,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: SRNEConfigEntry) -> "SRNEOptionsFlow":
        return SRNEOptionsFlow()


class SRNEOptionsFlow(OptionsFlow):
    """Handle the scan-interval option."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(
                        cv.positive_int, vol.Range(min=MIN_SCAN_INTERVAL)
                    )
                }
            ),
        )
