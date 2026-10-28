"""Read-only state sensors for the 352 X83."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfDensity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import X83Entity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [X83Pm25Sensor(coordinator, entry), X83SpeedSensor(coordinator, entry)]
    )


class X83Pm25Sensor(X83Entity, SensorEntity):
    _attr_translation_key = "pm25"
    _attr_device_class = SensorDeviceClass.PM25
    _attr_native_unit_of_measurement = UnitOfDensity.MICROGRAMS_PER_CUBIC_METER
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "pm25")

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.pm25 if self.coordinator.data else None

    @property
    def available(self) -> bool:
        return bool(
            super().available
            and self.coordinator.data
            and self.coordinator.data.online
        )


class X83SpeedSensor(X83Entity, SensorEntity):
    _attr_translation_key = "speed"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "speed")

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.speed if self.coordinator.data else None

    @property
    def available(self) -> bool:
        return bool(
            super().available
            and self.coordinator.data
            and self.coordinator.data.online
        )
