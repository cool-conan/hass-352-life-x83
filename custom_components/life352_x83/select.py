"""Operating-mode control for the 352 X83."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import X83Entity

MODE_TO_OPTION = {1: "auto", 2: "turbo", 3: "sleep", 5: "manual"}
OPTION_TO_MODE = {option: mode for mode, option in MODE_TO_OPTION.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([X83ModeSelect(hass.data[DOMAIN][entry.entry_id], entry)])


class X83ModeSelect(X83Entity, SelectEntity):
    """Expose protocol modes through stable user-facing options."""

    _attr_translation_key = "mode"
    _attr_options = list(OPTION_TO_MODE)

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "mode")

    @property
    def current_option(self) -> str | None:
        if self.coordinator.data is None:
            return None
        return MODE_TO_OPTION.get(self.coordinator.data.mode)

    @property
    def available(self) -> bool:
        return bool(
            super().available
            and self.coordinator.data
            and self.coordinator.data.online
        )

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_mode(OPTION_TO_MODE[option])
