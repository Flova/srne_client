"""Switch platform for SRNE BLE - the charge/discharge switch."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SRNEConfigEntry
from .entity import SRNEEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SRNEConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([SRNEChargeSwitch(entry.runtime_data, entry)])


class SRNEChargeSwitch(SRNEEntity, SwitchEntity):
    """Charge/discharge switch (register 0xDF00): turns charging on/off."""

    _attr_translation_key = "charging"
    _attr_icon = "mdi:battery-charging"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{coordinator.address}_charging"

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
