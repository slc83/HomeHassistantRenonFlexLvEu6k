"""Sensor platform for the RENON FLEX Stick Logger."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
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
    "total_increasing": SensorStateClass.TOTAL_INCREASING,
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
    entities.append(
        RenonFlexBaseSensor(
            coordinator,
            entry,
            "power_active",
            device_class=SensorDeviceClass.POWER,
            unit="W",
            state_class=SensorStateClass.MEASUREMENT,
        )
    )
    entities.append(RenonFlexEstimatedPV1PowerSensor(coordinator, entry))
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
        if device_class == SensorDeviceClass.ENERGY:
            self._attr_suggested_display_precision = 3

    @property
    def available(self) -> bool:
        """A rejected measurement is unavailable even when other readings succeed."""
        return super().available and self.coordinator.data.get(self._key) is not None

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        data = self.coordinator.data
        if data is None:
            return None
        return data.get(self._key)


class RenonFlexSensor(RenonFlexBaseSensor):
    """A sensor mapped to one or two Modbus holding registers."""

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


class RenonFlexEstimatedPV1PowerSensor(RenonFlexBaseSensor):
    """Instantaneous DC power calculated from the same poll's PV1 voltage/current."""

    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:solar-power"

    def __init__(self, coordinator: RenonFlexCoordinator, entry: ConfigEntry) -> None:
        super().__init__(
            coordinator,
            entry,
            "power_pv1_estimated",
            device_class=SensorDeviceClass.POWER,
            unit="W",
            state_class=SensorStateClass.MEASUREMENT,
        )

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self.native_value is not None

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data
        if data is None:
            return None
        voltage, current = data.get("voltage_dc"), data.get("current_dc")
        if voltage is None or current is None:
            return None
        return round(voltage * current, 2)
