import sys
import unittest
from pathlib import Path

HOME_ASSISTANT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOME_ASSISTANT_DIR))

from custom_components.life352_x83.errors import ProtocolError
from custom_components.life352_x83.protocol import (
    MODE_VALUES,
    POWER_OFF_PAYLOAD,
    POWER_ON_PAYLOAD,
    SPEED_VALUES,
    DeviceProtocolFields,
    assemble_frame,
    build_light_frame,
    build_mode_frame,
    build_power_frame,
    build_read_state_frame,
    build_speed_frame,
    parse_online_response,
    parse_state_frame,
    validate_light_frame,
    validate_mode_frame,
    validate_power_frame,
    validate_speed_frame,
)


class ProtocolTest(unittest.TestCase):
    def setUp(self):
        self.fields = DeviceProtocolFields(
            mac=bytes.fromhex("001122334455"),
            company_code=0xF1,
            device_type=0x02,
            auth_code=0x1234,
        )

    def _state_frame(self, power: bool = True) -> bytes:
        payload = bytearray(33)
        payload[0:3] = b"\x02\x5A\xA1"
        payload[3] = 0x12
        payload[4] = 3
        payload[5] = 2
        payload[6] = 1
        payload[7] = 0x11
        payload[8] = 0x00
        payload[9] = 0x00 if power else 0x11
        payload[12:14] = (35).to_bytes(2, "big")
        return assemble_frame(bytes(payload), 9, self.fields)

    def test_read_state_matches_audited_layout(self):
        frame = build_read_state_frame(self.fields, 0)
        self.assertEqual(
            frame,
            bytes.fromhex("A1040011223344550E000000F102123401A5A050500000"),
        )

    def test_both_power_payloads_require_exact_full_bytes(self):
        power_on = build_power_frame(self.fields, True, 1)
        power_off = build_power_frame(self.fields, False, 2)
        self.assertEqual(power_on[16:], POWER_ON_PAYLOAD)
        self.assertEqual(power_off[16:], POWER_OFF_PAYLOAD)
        validate_power_frame(power_on, self.fields, True)
        validate_power_frame(power_off, self.fields, False)
        corrupted = bytearray(power_off)
        corrupted[-1] = 0
        with self.assertRaises(ProtocolError):
            validate_power_frame(bytes(corrupted), self.fields, False)

    def test_mode_payloads_match_every_audited_value(self):
        expected = {
            1: "01 A5 A0 51 01 00 97",
            2: "01 A5 A0 51 02 00 98",
            3: "01 A5 A0 51 03 00 99",
            5: "01 A5 A0 51 05 00 9B",
        }
        self.assertEqual(set(expected), set(MODE_VALUES))
        for mode, payload_hex in expected.items():
            with self.subTest(mode=mode):
                frame = build_mode_frame(self.fields, mode, mode)
                self.assertEqual(frame[16:], bytes.fromhex(payload_hex))
                validate_mode_frame(frame, self.fields, mode)

    def test_speed_payloads_match_every_audited_value(self):
        expected = {
            1: "01 A5 A0 52 01 00 98",
            2: "01 A5 A0 52 02 00 99",
            3: "01 A5 A0 52 03 00 9A",
            4: "01 A5 A0 52 04 00 9B",
            5: "01 A5 A0 52 05 00 9C",
            6: "01 A5 A0 52 06 00 9D",
        }
        self.assertEqual(set(expected), set(SPEED_VALUES))
        for speed, payload_hex in expected.items():
            with self.subTest(speed=speed):
                frame = build_speed_frame(self.fields, speed, speed)
                self.assertEqual(frame[16:], bytes.fromhex(payload_hex))
                validate_speed_frame(frame, self.fields, speed)

    def test_light_payloads_match_both_audited_values(self):
        light_on = build_light_frame(self.fields, True, 1)
        light_off = build_light_frame(self.fields, False, 2)
        self.assertEqual(light_on[16:], bytes.fromhex("01 A5 A0 56 00 00 9B"))
        self.assertEqual(light_off[16:], bytes.fromhex("01 A5 A0 56 11 00 AC"))
        validate_light_frame(light_on, self.fields, True)
        validate_light_frame(light_off, self.fields, False)

    def test_new_controls_reject_out_of_range_or_mutated_frames(self):
        for builder, invalid in (
            (build_mode_frame, 0),
            (build_mode_frame, 4),
            (build_mode_frame, True),
            (build_mode_frame, 1.0),
            (build_speed_frame, 0),
            (build_speed_frame, 7),
            (build_speed_frame, True),
            (build_speed_frame, 1.0),
        ):
            with self.subTest(builder=builder.__name__, invalid=invalid):
                with self.assertRaises(ProtocolError):
                    builder(self.fields, invalid, 1)

        with self.assertRaises(ProtocolError):
            build_light_frame(self.fields, 1, 1)

        mode = bytearray(build_mode_frame(self.fields, 1, 1))
        mode[-1] ^= 0x01
        with self.assertRaises(ProtocolError):
            validate_mode_frame(bytes(mode), self.fields, 1)

        speed = bytearray(build_speed_frame(self.fields, 1, 1))
        speed[-4] = 0x51
        with self.assertRaises(ProtocolError):
            validate_speed_frame(bytes(speed), self.fields, 1)

        light = bytearray(build_light_frame(self.fields, True, 1))
        light[-3] = 0x11
        with self.assertRaises(ProtocolError):
            validate_light_frame(bytes(light), self.fields, True)

    def test_state_is_device_bound_and_not_optimistic(self):
        state = parse_state_frame(self._state_frame(power=True), self.fields)
        self.assertTrue(state.power)
        self.assertEqual(state.pm25, 35)
        other = DeviceProtocolFields(
            mac=bytes.fromhex("AABBCCDDEEFF"),
            company_code=0xF1,
            device_type=0x02,
            auth_code=0x1234,
        )
        with self.assertRaises(ProtocolError):
            parse_state_frame(self._state_frame(), other)

    def test_explicit_offline_response_is_preserved_and_device_bound(self):
        frame = assemble_frame(bytes((0x83, 0)), 10, self.fields)
        self.assertFalse(parse_online_response(frame, self.fields))
        online = assemble_frame(bytes((0x83, 1)), 11, self.fields)
        self.assertTrue(parse_online_response(online, self.fields))
        other = DeviceProtocolFields(
            mac=bytes.fromhex("AABBCCDDEEFF"),
            company_code=0xF1,
            device_type=0x02,
            auth_code=0x1234,
        )
        with self.assertRaises(ProtocolError):
            parse_online_response(frame, other)

    def test_only_device_type_02_is_accepted(self):
        with self.assertRaises(ProtocolError):
            DeviceProtocolFields(
                mac=self.fields.mac,
                company_code=0xF1,
                device_type=0x03,
                auth_code=0x1234,
            ).validate()

if __name__ == "__main__":
    unittest.main()
