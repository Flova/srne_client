"""Sensor platform for SRNE BLE."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SRNEConfigEntry
from .entity import SRNEEntity
from .srne.controller import CHARGE_STATE, ControllerData

CHARGE_STATE_OPTIONS = list(CHARGE_STATE.values())


@dataclass(frozen=True, kw_only=True)
class SRNESensorDescription(SensorEntityDescription):
    """Describes an SRNE sensor and how to read it from ControllerData."""

    value_fn: Callable[[ControllerData], float | int | str | None]


SENSORS: tuple[SRNESensorDescription, ...] = (
    SRNESensorDescription(
        key="battery_soc",
        translation_key="battery_soc",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.battery_soc,
    ),
    SRNESensorDescription(
        key="battery_voltage",
        translation_key="battery_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda d: d.battery_voltage,
    ),
    SRNESensorDescription(
        key="charging_current",
        translation_key="charging_current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda d: d.charging_current,
    ),
    SRNESensorDescription(
        key="charging_power",
        translation_key="charging_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.charging_power,
    ),
    SRNESensorDescription(
        key="pv_voltage",
        translation_key="pv_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda d: d.pv_voltage,
    ),
    SRNESensorDescription(
        key="pv_current",
        translation_key="pv_current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda d: d.pv_current,
    ),
    SRNESensorDescription(
        key="pv_power",
        translation_key="pv_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        # PV power isn't a register in this block; derive it from V x A.
        value_fn=lambda d: round(d.pv_voltage * d.pv_current),
    ),
    SRNESensorDescription(
        key="load_voltage",
        translation_key="load_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.load_voltage,
    ),
    SRNESensorDescription(
        key="load_current",
        translation_key="load_current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.load_current,
    ),
    SRNESensorDescription(
        key="load_power",
        translation_key="load_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.load_power,
    ),
    SRNESensorDescription(
        key="controller_temperature",
        translation_key="controller_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.controller_temperature,
    ),
    SRNESensorDescription(
        key="battery_temperature",
        translation_key="battery_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.battery_temperature,
    ),
    SRNESensorDescription(
        key="charging_state",
        translation_key="charging_state",
        device_class=SensorDeviceClass.ENUM,
        options=CHARGE_STATE_OPTIONS,
        # Guard against unexpected firmware codes so HA's ENUM check never errors.
        value_fn=lambda d: d.charging_state if d.charging_state in CHARGE_STATE_OPTIONS else None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SRNEConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(SRNESensor(coordinator, entry, desc) for desc in SENSORS)


class SRNESensor(SRNEEntity, SensorEntity):
    """A single decoded value from the controller."""

    entity_description: SRNESensorDescription

    def __init__(self, coordinator, entry, description: SRNESensorDescription) -> None:
        super().__init__(coordinator, entry)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.address}_{description.key}"

    @property
    def native_value(self) -> float | int | str | None:
        data = self.coordinator.data
        if data is None:
            return None
        return self.entity_description.value_fn(data)
