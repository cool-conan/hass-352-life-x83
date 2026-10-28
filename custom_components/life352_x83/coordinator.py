"""Data coordinator whose state only comes from X83 device-data frames."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import X83CloudClient
from .const import DOMAIN, UPDATE_INTERVAL
from .errors import Air352Error, AuthenticationError
from .protocol import X83State

_LOGGER = logging.getLogger(__name__)


class X83Coordinator(DataUpdateCoordinator[X83State]):
    """Serialize refresh and control through one X83 client."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: X83CloudClient
    ) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> X83State:
        try:
            return await self.client.async_read_state()
        except AuthenticationError as error:
            raise ConfigEntryAuthFailed from error
        except Air352Error as error:
            raise UpdateFailed("X83 state refresh failed") from error

    async def async_set_power(self, power: bool) -> None:
        await self._async_set_control(
            "power", lambda: self.client.async_set_power(power)
        )

    async def async_set_mode(self, mode: int) -> None:
        await self._async_set_control("mode", lambda: self.client.async_set_mode(mode))

    async def async_set_speed(self, speed: int) -> None:
        await self._async_set_control(
            "speed", lambda: self.client.async_set_speed(speed)
        )

    async def async_set_light(self, light: bool) -> None:
        await self._async_set_control(
            "light", lambda: self.client.async_set_light(light)
        )

    async def _async_set_control(
        self,
        control_name: str,
        run_control: Callable[[], Awaitable[X83State]],
    ) -> None:
        try:
            state = await run_control()
        except AuthenticationError as error:
            raise ConfigEntryAuthFailed from error
        except Air352Error as error:
            raise HomeAssistantError(
                f"X83 did not confirm the requested {control_name} state"
            ) from error
        # Client methods return only after a matching device-data frame.
        self.async_set_updated_data(state)
