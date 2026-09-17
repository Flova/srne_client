"""Binary sensor platform for SRNE BLE."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SRNEConfigEntry
from .entity import SRNEEntity
from .srne.controller import ControllerData


@dataclass(frozen=True, kw_only=True)
class SRNEBinaryDescription(BinarySensorEntityDescription):
    is_on_fn: Callable[[ControllerData], bool]
    attrs_fn: Callable[[ControllerData], dict] | None = None


BINARY_SENSORS: tuple[SRNEBinaryDescription, ...] = (
    SRNEBinaryDescription(
        key="charging",
        translation_key="charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        is_on_fn=lambda d: d.charging_power > 0 or d.charging_current > 0,
    ),
    SRNEBinaryDescription(
        key="load",
        translation_key="load",
        device_class=BinarySensorDeviceClass.POWER,
        is_on_fn=lambda d: d.load_enabled,
    ),
    SRNEBinaryDescription(
        key="fault",
        translation_key="fault",
        device_class=BinarySensorDeviceClass.PROBLEM,
        is_on_fn=lambda d: bool(d.faults),
        attrs_fn=lambda d: {"faults": d.faults},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SRNEConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        SRNEBinarySensor(coordinator, entry, desc) for desc in BINARY_SENSORS
    )


class SRNEBinarySensor(SRNEEntity, BinarySensorEntity):
    entity_description: SRNEBinaryDescription

    def __init__(self, coordinator, entry, description: SRNEBinaryDescription) -> None:
        super().__init__(coordinator, entry)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.address}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data
        if data is None:
            return None
        return self.entity_description.is_on_fn(data)

    @property
    def extra_state_attributes(self) -> dict | None:
        data = self.coordinator.data
        if data is None or self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(data)
