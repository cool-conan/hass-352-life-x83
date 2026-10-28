"""UI configuration and explicit reauthentication for one shared X83 account."""

from __future__ import annotations

import hashlib
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .auth import X83Authenticator
from .const import CONF_AIR_TOKEN, DOMAIN, INTEGRATION_NAME
from .credentials import load_legacy_private_key
from .errors import AuthenticationError, CannotConnectError, ProtocolError
from .protocol import DeviceProtocolFields


def _schema(default_account: str = "") -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_USERNAME, default=default_account): TextSelector(
                TextSelectorConfig(
                    type=TextSelectorType.TEL,
                    autocomplete="username",
                )
            ),
            vol.Required(CONF_PASSWORD): TextSelector(
                TextSelectorConfig(
                    type=TextSelectorType.PASSWORD,
                    autocomplete="current-password",
                )
            ),
        }
    )


def _unique_id(fields: DeviceProtocolFields) -> str:
    return hashlib.sha256(fields.anonymous_id()).hexdigest()


class X83ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Create one entry from a user-initiated password login."""

    VERSION = 1

    async def _async_validate(
        self, user_input: dict[str, Any]
    ) -> tuple[str, DeviceProtocolFields]:
        private_key = await self.hass.async_add_executor_job(
            load_legacy_private_key, self.hass.config.config_dir
        )
        authenticator = X83Authenticator(
            async_get_clientsession(self.hass), private_key
        )
        return await authenticator.async_login_and_discover(
            user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
        )

    @staticmethod
    def _entry_data(
        account: str,
        token: str,
        fields: DeviceProtocolFields,
    ) -> dict[str, Any]:
        return {
            CONF_USERNAME: account.strip(),
            CONF_AIR_TOKEN: token,
            **fields.entry_data(),
        }

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                token, fields = await self._async_validate(user_input)
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except CannotConnectError:
                errors["base"] = "cannot_connect"
            except ProtocolError as error:
                if "private credential" in str(error):
                    errors["base"] = "missing_private_credentials"
                else:
                    errors["base"] = "invalid_device"
            except Exception:  # Home Assistant renders a generic, non-secret error.
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(_unique_id(fields))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=INTEGRATION_NAME,
                    data=self._entry_data(
                        user_input[CONF_USERNAME], token, fields
                    ),
                )
        return self.async_show_form(
            step_id="user", data_schema=_schema(), errors=errors
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> config_entries.ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                token, fields = await self._async_validate(user_input)
                if entry.unique_id != _unique_id(fields):
                    errors["base"] = "wrong_device"
                else:
                    return self.async_update_reload_and_abort(
                        entry,
                        data_updates=self._entry_data(
                            user_input[CONF_USERNAME],
                            token,
                            fields,
                        ),
                    )
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except CannotConnectError:
                errors["base"] = "cannot_connect"
            except ProtocolError as error:
                if "private credential" in str(error):
                    errors["base"] = "missing_private_credentials"
                else:
                    errors["base"] = "invalid_device"
            except Exception:
                errors["base"] = "unknown"
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=_schema(str(entry.data.get(CONF_USERNAME, ""))),
            errors=errors,
        )
