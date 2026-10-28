"""Sensor platform for the RENON FLEX Stick Logger."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfEnergy,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import const
from .coordinator import RenonFlexCoordinator

PARALLEL_UPDATES = 0

DEVICE_CLASSES = {
    "power": SensorDeviceClass.POWER,
    "voltage": SensorDeviceClass.VOLTAGE,
    "current": SensorDeviceClass.CURRENT,
    "energy": SensorDeviceClass.ENERGY,
}

STATE_CLASSES = {
    "measurement": SensorStateClass.MEASUREMENT,
    "total": SensorStateClass.TOTAL,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor entities for a config entry."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        RenonFlexSensor(coordinator, entry, reg) for reg in const.REGISTERS
    ]
    entities.append(RenonFlexStateSensor(coordinator, entry))
    entities.append(RenonFlexEnergySensor(coordinator, entry))
    async_add_entities(entities)


class RenonFlexBaseSensor(CoordinatorEntity[RenonFlexCoordinator], SensorEntity):
    """Base for all sensors exposed by the integration."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: RenonFlexCoordinator,
        entry: ConfigEntry,
        key: str,
        *,
        device_class: SensorDeviceClass | None = None,
        unit: str | None = None,
        state_class: SensorStateClass | None = None,
    ) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{entry.entry_id}-{key}"
        self._attr_translation_key = key
        self._attr_device_info = {
            "identifiers": {(const.DOMAIN, entry.entry_id)},
            "manufacturer": const.MANUFACTURER,
            "model": const.MODEL,
            "name": const.DEVICE_NAME,
        }
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit
        self._attr_state_class = state_class

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        data = self.coordinator.data
        if data is None:
            return None
        return data.get(self._key)


class RenonFlexSensor(RenonFlexBaseSensor):
    """A sensor mapped to a single Modbus holding register."""

    def __init__(
        self,
        coordinator: RenonFlexCoordinator,
        entry: ConfigEntry,
        reg: const.Register,
    ) -> None:
        super().__init__(
            coordinator,
            entry,
            reg.key,
            device_class=DEVICE_CLASSES.get(reg.device_class),
            unit=reg.unit,
            state_class=STATE_CLASSES.get(reg.state_class),
        )


class RenonFlexStateSensor(RenonFlexBaseSensor):
    """Inverter state (off / standby / working / fault)."""

    def __init__(
        self,
        coordinator: RenonFlexCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, entry, const.STATE_KEY)
        self._attr_device_class = SensorDeviceClass.ENUM
        self._attr_options = [*const.STATE_MAP.values(), "unknown"]


class RenonFlexEnergySensor(RenonFlexBaseSensor):
    """Energy produced today, estimated by integrating the active power."""

    def __init__(
        self,
        coordinator: RenonFlexCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(
            coordinator,
            entry,
            const.ENERGY_KEY,
            device_class=SensorDeviceClass.ENERGY,
            unit=UnitOfEnergy.KILO_WATT_HOUR,
            state_class=SensorStateClass.TOTAL_INCREASING,
        )
        self._attr_suggested_display_precision = 3
