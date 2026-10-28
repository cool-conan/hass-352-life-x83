"""Home Assistant lifecycle for the 352-life integration."""

from __future__ import annotations

from typing import Any

from .const import CONF_AIR_TOKEN, DOMAIN, PLATFORMS
from .protocol import DeviceProtocolFields


async def async_setup_entry(hass: Any, entry: Any) -> bool:
    """Set up one X83 without performing a password login."""
    from homeassistant.exceptions import ConfigEntryAuthFailed

    from .client import X83CloudClient
    from .coordinator import X83Coordinator
    from .errors import AuthenticationError, ProtocolError

    try:
        fields = DeviceProtocolFields.from_entry_data(dict(entry.data))
        token = entry.data[CONF_AIR_TOKEN]
        if not isinstance(token, str) or not token:
            raise AuthenticationError("persisted old-352 session is missing")
    except (KeyError, AuthenticationError, ProtocolError) as error:
        raise ConfigEntryAuthFailed from error

    client = X83CloudClient(token, fields)
    coordinator = X83Coordinator(hass, entry, client)
    setup_succeeded = False
    try:
        await coordinator.async_config_entry_first_refresh()
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        setup_succeeded = True
        return True
    finally:
        if not setup_succeeded:
            await client.async_close()
            domain_data = hass.data.get(DOMAIN)
            if domain_data is not None:
                domain_data.pop(entry.entry_id, None)
                if not domain_data:
                    hass.data.pop(DOMAIN)


async def async_unload_entry(hass: Any, entry: Any) -> bool:
    """Unload platforms and close the single work-server stream."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.client.async_close()
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)
    return unloaded
