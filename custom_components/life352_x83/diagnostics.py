"""Privacy-preserving diagnostics for the 352 X83 integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    state = coordinator.data
    return {
        "entry": {
            "version": entry.version,
            "state": entry.state.value,
            "title": "352-life",
        },
        "transport": {
            "kind": "legacy-cloud-tls-tcp",
            "certificate_verification": True,
            "password_login_on_entry_load": False,
            "automatic_password_relogin": False,
            "abnormal_login_frame_sent": False,
            "control_rounds": 3,
            "control_requires_device_readback": True,
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "state": None
            if state is None
            else {
                "online": state.online,
                "power": state.power,
                "light": state.light,
                "child_lock": state.child_lock,
                "mode": state.mode,
                "filter_type": state.filter_type,
                "speed": state.speed,
                "timer_hours": state.timer_hours,
                "air_quality_level": state.air_quality_level,
                "pm25": state.pm25,
            },
        },
    }
