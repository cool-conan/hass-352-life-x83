"""Power and display-light switches for the 352 X83."""

from __future__ import annotations

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
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
        [X83PowerSwitch(coordinator, entry), X83LightSwitch(coordinator, entry)]
    )


class X83PowerSwitch(X83Entity, SwitchEntity):
    """Expose power without optimistic updates."""

    _attr_translation_key = "power"
    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "power")

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.power if self.coordinator.data else None

    @property
    def available(self) -> bool:
        # Keep the recovery action reachable after a transient refresh failure
        # or an explicit offline response. The client still requires real
        # device-data readback before changing the state.
        return self.coordinator.data is not None

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_set_power(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_set_power(False)


class X83LightSwitch(X83Entity, SwitchEntity):
    """Expose the display light without optimistic updates."""

    _attr_translation_key = "light"
    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "light")

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.light if self.coordinator.data else None

    @property
    def available(self) -> bool:
        return bool(
            super().available
            and self.coordinator.data
            and self.coordinator.data.online
        )

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_set_light(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_set_light(False)
