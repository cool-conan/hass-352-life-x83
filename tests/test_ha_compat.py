import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

HOME_ASSISTANT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOME_ASSISTANT_DIR))

try:
    from homeassistant import loader
    from homeassistant.core import HomeAssistant
    from homeassistant.data_entry_flow import FlowResultType
    from homeassistant.helpers.selector import TextSelector, TextSelectorType
except ImportError as error:
    raise unittest.SkipTest("Home Assistant is not installed") from error

import custom_components.life352_x83 as integration_module
from custom_components.life352_x83 import binary_sensor, number, select, sensor, switch
from custom_components.life352_x83.config_flow import X83ConfigFlow, _schema
from custom_components.life352_x83.const import DOMAIN, PLATFORMS
from custom_components.life352_x83.coordinator import X83Coordinator
from custom_components.life352_x83.protocol import X83State


class HomeAssistantCompatibilityTest(unittest.IsolatedAsyncioTestCase):
    async def test_ha_loader_imports_component_and_all_platforms(self):
        self.assertEqual(DOMAIN, "life352_x83")
        hass = HomeAssistant(str(HOME_ASSISTANT_DIR))
        loader.async_setup(hass)
        integration = await loader.async_get_integration(hass, DOMAIN)
        component = await integration.async_get_component()
        platforms = await integration.async_get_platforms(PLATFORMS)

        self.assertEqual(component.__name__, "custom_components.life352_x83")
        self.assertEqual(set(platforms), set(PLATFORMS))
        self.assertEqual(integration.name, "352-life")
        self.assertEqual(str(integration.version), "1.0.0")
        self.assertTrue(integration.has_branding)
        self.assertEqual(X83ConfigFlow.VERSION, 1)
        self.assertNotIn("async_get_options_flow", X83ConfigFlow.__dict__)

    async def test_login_form_uses_supported_phone_and_password_selectors(self):
        schema = _schema()
        fields = {
            marker.schema: validator for marker, validator in schema.schema.items()
        }

        self.assertIsInstance(fields["username"], TextSelector)
        self.assertEqual(fields["username"].config["type"], TextSelectorType.TEL)
        self.assertIsInstance(fields["password"], TextSelector)
        self.assertEqual(
            fields["password"].config["type"], TextSelectorType.PASSWORD
        )

        flow = X83ConfigFlow()
        result = await flow.async_step_user()
        self.assertEqual(result["type"], FlowResultType.FORM)
        self.assertEqual(result["step_id"], "user")

    async def test_platform_setup_creates_entities_and_offline_is_representable(self):
        state = X83State(
            online=True,
            power=True,
            light=True,
            child_lock=False,
            mode=1,
            filter_type=1,
            speed=3,
            timer_hours=0,
            air_quality_level=1,
            pm25=12,
        )
        coordinator = SimpleNamespace(
            data=state,
            last_update_success=True,
            config_entry=SimpleNamespace(data={}),
        )
        entry = SimpleNamespace(entry_id="entry", unique_id="device")
        hass = SimpleNamespace(data={DOMAIN: {entry.entry_id: coordinator}})
        entities = []

        await switch.async_setup_entry(hass, entry, entities.extend)
        await select.async_setup_entry(hass, entry, entities.extend)
        await number.async_setup_entry(hass, entry, entities.extend)
        await sensor.async_setup_entry(hass, entry, entities.extend)
        await binary_sensor.async_setup_entry(hass, entry, entities.extend)

        self.assertEqual(len(entities), 7)
        self.assertTrue(entities[0].is_on)
        self.assertTrue(entities[0].available)
        self.assertTrue(entities[1].is_on)
        self.assertEqual(entities[2].current_option, "auto")
        self.assertEqual(entities[3].native_value, 3)
        self.assertEqual(entities[4].native_value, 12)
        self.assertEqual(entities[5].native_value, 3)
        self.assertTrue(entities[6].is_on)
        for entity in entities[:4]:
            self.assertTrue(entity.available)

        coordinator.data = X83State.offline()
        self.assertTrue(entities[0].available)
        for entity in entities[1:6]:
            self.assertFalse(entity.available)
        self.assertTrue(entities[6].available)
        self.assertFalse(entities[6].is_on)

    async def test_power_switch_stays_available_after_refresh_failure(self):
        coordinator = SimpleNamespace(
            data=X83State.offline(),
            last_update_success=False,
            config_entry=SimpleNamespace(data={}),
        )
        entry = SimpleNamespace(entry_id="entry", unique_id="device")
        entity = switch.X83PowerSwitch(coordinator, entry)

        self.assertTrue(entity.available)
        self.assertFalse(entity.is_on)

    async def test_all_controls_use_client_readback(self):
        hass = HomeAssistant(str(HOME_ASSISTANT_DIR))
        entry = SimpleNamespace(data={}, async_on_unload=lambda callback: None)
        initial = X83State(
            online=True,
            power=True,
            light=True,
            child_lock=False,
            mode=1,
            filter_type=1,
            speed=1,
            timer_hours=0,
            air_quality_level=1,
            pm25=12,
        )
        power_state = X83State(**{**initial.__dict__, "power": False})
        mode_state = X83State(**{**initial.__dict__, "mode": 2})
        speed_state = X83State(**{**initial.__dict__, "speed": 2})
        light_state = X83State(**{**initial.__dict__, "light": False})
        client = SimpleNamespace(
            async_set_power=mock.AsyncMock(return_value=power_state),
            async_set_mode=mock.AsyncMock(return_value=mode_state),
            async_set_speed=mock.AsyncMock(return_value=speed_state),
            async_set_light=mock.AsyncMock(return_value=light_state),
        )
        coordinator = X83Coordinator(hass, entry, client)
        coordinator.async_set_updated_data(initial)

        for method_name, client_method, expected, returned_state in (
            ("async_set_power", client.async_set_power, False, power_state),
            ("async_set_mode", client.async_set_mode, 2, mode_state),
            ("async_set_speed", client.async_set_speed, 2, speed_state),
            ("async_set_light", client.async_set_light, False, light_state),
        ):
            with self.subTest(method=method_name):
                await getattr(coordinator, method_name)(expected)

                client_method.assert_awaited_once_with(expected)
                self.assertIs(coordinator.data, returned_state)

    async def test_setup_failure_closes_client_and_removes_coordinator(self):
        fake_client = SimpleNamespace(async_close=mock.AsyncMock())
        fake_coordinator = SimpleNamespace(
            async_config_entry_first_refresh=mock.AsyncMock()
        )
        config_entries = SimpleNamespace(
            async_update_entry=mock.Mock(),
            async_forward_entry_setups=mock.AsyncMock(
                side_effect=ImportError("platform failed")
            ),
        )
        hass = SimpleNamespace(data={}, config_entries=config_entries)
        entry = SimpleNamespace(
            entry_id="entry",
            title="352-life",
            data={
                "air_token": "token",
                "device_mac": "001122334455",
                "company_code": 0xF1,
                "device_type": 0x02,
                "auth_code": 0x1234,
            },
        )

        with mock.patch(
            "custom_components.life352_x83.client.X83CloudClient",
            return_value=fake_client,
        ), mock.patch(
            "custom_components.life352_x83.coordinator.X83Coordinator",
            return_value=fake_coordinator,
        ), self.assertRaisesRegex(ImportError, "platform failed"):
            await integration_module.async_setup_entry(hass, entry)

        fake_client.async_close.assert_awaited_once()
        self.assertNotIn(DOMAIN, hass.data)

    async def test_setup_success_keeps_client(self):
        fake_client = SimpleNamespace(async_close=mock.AsyncMock())
        fake_coordinator = SimpleNamespace(
            async_config_entry_first_refresh=mock.AsyncMock()
        )
        config_entries = SimpleNamespace(
            async_update_entry=mock.Mock(),
            async_forward_entry_setups=mock.AsyncMock(),
        )
        hass = SimpleNamespace(data={}, config_entries=config_entries)
        entry = SimpleNamespace(
            entry_id="entry",
            title="352-life",
            data={
                "air_token": "token",
                "device_mac": "001122334455",
                "company_code": 0xF1,
                "device_type": 0x02,
                "auth_code": 0x1234,
            },
        )

        with mock.patch(
            "custom_components.life352_x83.client.X83CloudClient",
            return_value=fake_client,
        ), mock.patch(
            "custom_components.life352_x83.coordinator.X83Coordinator",
            return_value=fake_coordinator,
        ):
            result = await integration_module.async_setup_entry(hass, entry)

        self.assertTrue(result)
        self.assertIs(hass.data[DOMAIN][entry.entry_id], fake_coordinator)
        fake_client.async_close.assert_not_awaited()
        config_entries.async_update_entry.assert_not_called()


if __name__ == "__main__":
    unittest.main()
