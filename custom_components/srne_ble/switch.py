"""Switch platform for SRNE BLE: charge/discharge switch + BLE connection."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SRNEConfigEntry
from .entity import SRNEEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SRNEConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [SRNEChargeSwitch(coordinator, entry), SRNEConnectionSwitch(coordinator, entry)]
    )


class SRNEChargeSwitch(SRNEEntity, SwitchEntity):
    """Charge/discharge switch (register 0xDF00): turns charging on/off."""

    _attr_translation_key = "charging"
    _attr_icon = "mdi:battery-charging"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{coordinator.address}_charging"

    async def async_added_to_hass(self) -> None:
        """Read the switch state once on load (it isn't read during polling)."""
        await super().async_added_to_hass()
        if self.coordinator.charge_switch_on is None:
            self.hass.async_create_task(self.coordinator.async_refresh_charge_switch())

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.charge_switch_on is not None

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.charge_switch_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_charge_switch(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_charge_switch(False)


class SRNEConnectionSwitch(SRNEEntity, SwitchEntity):
    """Controls whether Home Assistant holds the BLE connection.

    Turn it off to release the controller so the phone app can connect (polling
    pauses); turn it on to reconnect and resume.
    """

    _attr_translation_key = "connection"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:bluetooth-connect"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{coordinator.address}_connection"

    @property
    def available(self) -> bool:
        # Always controllable, even while paused (so it can be turned back on).
        return True

    @property
    def is_on(self) -> bool:
        return self.coordinator.connection_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_connection(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_connection(False)
