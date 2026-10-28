"""Shared entity metadata."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import X83Coordinator


class X83Entity(CoordinatorEntity[X83Coordinator]):
    """Base entity for the single configured X83."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: X83Coordinator, entry: ConfigEntry, suffix: str
    ) -> None:
        super().__init__(coordinator)
        device_id = entry.unique_id or entry.entry_id
        self._attr_unique_id = f"{device_id}_{suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            manufacturer="352",
            model="X83",
            name="352-life X83",
        )
