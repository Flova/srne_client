"""Shared base entity for SRNE BLE."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import SRNECoordinator


class SRNEEntity(CoordinatorEntity[SRNECoordinator]):
    """Base entity tying all sensors to one controller device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SRNECoordinator, entry) -> None:
        super().__init__(coordinator)
        address = coordinator.address
        identity = coordinator.identity
        model = (
            (identity.model if identity and identity.model else None)
            or entry.data.get("model")
            or (identity.type_name if identity else None)
            or "Solar Charge Controller"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, address)},
            connections={(CONNECTION_BLUETOOTH, address)},
            manufacturer=MANUFACTURER,
            model=model,
            name=entry.title,
            sw_version=identity.software_version if identity else None,
            hw_version=identity.hardware_version if identity else None,
        )

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data is not None
