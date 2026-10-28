"""Fan-speed control for the 352 X83."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import X83Entity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([X83SpeedNumber(hass.data[DOMAIN][entry.entry_id], entry)])


class X83SpeedNumber(X83Entity, NumberEntity):
    """Expose the six audited fan-speed levels without optimistic updates."""

    _attr_translation_key = "speed_control"
    _attr_native_min_value = 1
    _attr_native_max_value = 6
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "speed_control")

    @property
    def native_value(self) -> int | None:
        if self.coordinator.data is None:
            return None
        speed = self.coordinator.data.speed
        return speed if 1 <= speed <= 6 else None

    @property
    def available(self) -> bool:
        return bool(
            super().available
            and self.coordinator.data
            and self.coordinator.data.online
        )

    async def async_set_native_value(self, value: float) -> None:
        speed = int(value)
        if value != speed:
            raise HomeAssistantError("X83 fan speed must be a whole level")
        await self.coordinator.async_set_speed(speed)
