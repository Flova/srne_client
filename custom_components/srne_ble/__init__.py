"""The SRNE solar charge controller (BLE) integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
from .coordinator import SRNECoordinator, SRNEConfigEntry

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: SRNEConfigEntry) -> bool:
    """Set up SRNE BLE from a config entry."""
    address = entry.unique_id or entry.data["address"]
    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    coordinator = SRNECoordinator(hass, entry, address, scan_interval)
    # Identify the module first so we never mis-parse a non-controller device.
    await coordinator.async_identify()
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_reload_on_options))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SRNEConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_shutdown()
    return unload_ok


async def _async_reload_on_options(hass: HomeAssistant, entry: SRNEConfigEntry) -> None:
    """Reload the entry when the scan interval option changes."""
    await hass.config_entries.async_reload(entry.entry_id)
