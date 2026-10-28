"""Pure protocol primitives reconstructed for the legacy 352 X83 path."""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import Any

from .errors import ProtocolError

FRAME_PREFIX = 0xA1
GET_WORK_SERVER = 0x81
JOIN_WORK_SERVER = 0x82
QUERY_DEVICE_ONLINE = 0x83
SUBSCRIBE_SERVER_EVENT = 0x86
ABNORMAL_LOGIN = 0x89
DEVICE_TO_APP = 0x02
MAX_FRAME_SIZE = 256

JOIN_WORK_SERVER_MARKER = bytes.fromhex("3335321C944E")
READ_STATE_PAYLOAD = bytes.fromhex("01 A5 A0 50 50 00 00")
POWER_ON_PAYLOAD = bytes.fromhex("01 A5 A0 5E 35 00 D8")
POWER_OFF_PAYLOAD = bytes.fromhex("01 A5 A0 5E 11 00 B4")
MODE_VALUES = frozenset({1, 2, 3, 5})
SPEED_VALUES = frozenset(range(1, 7))
LIGHT_ON_VALUE = 0x00
LIGHT_OFF_VALUE = 0x11


def _hex_int(value: object, byte_count: int) -> int:
    if not isinstance(value, str) or not re.fullmatch(
        rf"[0-9A-Fa-f]{{1,{byte_count * 2}}}", value
    ):
        raise ProtocolError("X83 legacy record has an invalid protocol field")
    return int(value, 16)


@dataclass(frozen=True)
class DeviceProtocolFields:
    """Only the fields needed to address one X83 protocol session."""

    mac: bytes
    company_code: int
    device_type: int
    auth_code: int

    @classmethod
    def from_legacy_record(cls, device: dict[str, Any]) -> "DeviceProtocolFields":
        mac_source = device.get("macAddress")
        if not isinstance(mac_source, str):
            raise ProtocolError("X83 legacy record has no MAC field")
        mac_hex = re.sub(r"[^0-9A-Fa-f]", "", mac_source)
        if len(mac_hex) != 12:
            raise ProtocolError("X83 legacy record has an invalid MAC field")
        fields = cls(
            mac=bytes.fromhex(mac_hex),
            company_code=_hex_int(device.get("companyCode"), 1),
            device_type=_hex_int(device.get("deviceType"), 1),
            auth_code=_hex_int(device.get("authCode"), 2),
        )
        fields.validate()
        return fields

    @classmethod
    def from_entry_data(cls, data: dict[str, Any]) -> "DeviceProtocolFields":
        try:
            fields = cls(
                mac=bytes.fromhex(data["device_mac"]),
                company_code=int(data["company_code"]),
                device_type=int(data["device_type"]),
                auth_code=int(data["auth_code"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ProtocolError("stored X83 protocol fields are invalid") from error
        fields.validate()
        return fields

    def validate(self) -> None:
        if len(self.mac) != 6:
            raise ProtocolError("X83 MAC field has an invalid length")
        if self.device_type != 0x02:
            raise ProtocolError("legacy candidate is not the APK X83 protocol type")
        if not 0 <= self.company_code <= 0xFF:
            raise ProtocolError("X83 company field is outside one byte")
        if not 0 <= self.auth_code <= 0xFFFF:
            raise ProtocolError("X83 auth field is outside two bytes")

    def entry_data(self) -> dict[str, int | str]:
        return {
            "device_mac": self.mac.hex(),
            "company_code": self.company_code,
            "device_type": self.device_type,
            "auth_code": self.auth_code,
        }

    def anonymous_id(self) -> bytes:
        return (
            self.mac
            + bytes((self.company_code, self.device_type))
            + self.auth_code.to_bytes(2, "big")
        )


@dataclass(frozen=True)
class X83State:
    online: bool
    power: bool
    light: bool
    child_lock: bool
    mode: int
    filter_type: int
    speed: int
    timer_hours: int
    air_quality_level: int
    pm25: int

    @classmethod
    def offline(cls) -> X83State:
        """Represent an explicit device-offline response without stale readings."""
        return cls(
            online=False,
            power=False,
            light=False,
            child_lock=False,
            mode=0,
            filter_type=0,
            speed=0,
            timer_hours=0,
            air_quality_level=0,
            pm25=0,
        )


def is_x83_legacy_record(device: dict[str, Any]) -> bool:
    try:
        return _hex_int(device.get("deviceType"), 1) == 0x02
    except ProtocolError:
        return False


def assemble_frame(
    payload: bytes,
    protocol_index: int,
    fields: DeviceProtocolFields | None = None,
) -> bytes:
    if not payload or len(payload) + 7 > 0xFF:
        raise ProtocolError("legacy TCP payload has an invalid length")
    if not 0 <= protocol_index <= 0x7FFF:
        raise ProtocolError("legacy TCP protocol index is outside the audited range")
    frame = bytearray(16 + len(payload))
    frame[0] = FRAME_PREFIX
    frame[8] = len(payload) + 7
    frame[10:12] = protocol_index.to_bytes(2, "big")
    if fields is not None:
        fields.validate()
        frame[1] = 0x04
        frame[2:8] = fields.mac
        frame[12] = fields.company_code
        frame[13] = fields.device_type
        frame[14:16] = fields.auth_code.to_bytes(2, "big")
    frame[16:] = payload
    return bytes(frame)


def build_get_work_server_frame(protocol_index: int) -> bytes:
    return assemble_frame(bytes((GET_WORK_SERVER,)), protocol_index)


def build_join_work_server_frame(token: str, protocol_index: int) -> bytes:
    try:
        token_bytes = token.encode("utf-8")
    except UnicodeError as error:
        raise ProtocolError("old-352 token is not valid UTF-8") from error
    if not token_bytes or len(token_bytes) > 0xFF:
        raise ProtocolError("old-352 token has an invalid legacy length")
    payload = (
        bytes((JOIN_WORK_SERVER, len(JOIN_WORK_SERVER_MARKER)))
        + JOIN_WORK_SERVER_MARKER
        + bytes((0xFF, len(token_bytes)))
        + token_bytes
    )
    return assemble_frame(payload, protocol_index)


def build_subscribe_online_frame(
    fields: DeviceProtocolFields, protocol_index: int
) -> bytes:
    return assemble_frame(
        bytes((SUBSCRIBE_SERVER_EVENT, 1, 0x84, 0)), protocol_index, fields
    )


def build_subscribe_device_event_frame(
    fields: DeviceProtocolFields, protocol_index: int
) -> bytes:
    return assemble_frame(
        bytes((SUBSCRIBE_SERVER_EVENT, 1, DEVICE_TO_APP, 0)),
        protocol_index,
        fields,
    )


def build_query_online_frame(
    fields: DeviceProtocolFields, protocol_index: int
) -> bytes:
    return assemble_frame(bytes((QUERY_DEVICE_ONLINE,)), protocol_index, fields)


def build_read_state_frame(
    fields: DeviceProtocolFields, protocol_index: int
) -> bytes:
    return assemble_frame(READ_STATE_PAYLOAD, protocol_index, fields)


def build_power_frame(
    fields: DeviceProtocolFields, power: bool, protocol_index: int
) -> bytes:
    payload = POWER_ON_PAYLOAD if power else POWER_OFF_PAYLOAD
    frame = assemble_frame(payload, protocol_index, fields)
    validate_power_frame(frame, fields, power)
    return frame


def _build_control_payload(opcode: int, value: int) -> bytes:
    body = bytes((0xA5, 0xA0, opcode, value, 0x00))
    return bytes((0x01,)) + body + bytes((sum(body) & 0xFF,))


def build_mode_frame(
    fields: DeviceProtocolFields, mode: int, protocol_index: int
) -> bytes:
    if type(mode) is not int or mode not in MODE_VALUES:
        raise ProtocolError("X83 mode is outside the audited control values")
    frame = assemble_frame(_build_control_payload(0x51, mode), protocol_index, fields)
    validate_mode_frame(frame, fields, mode)
    return frame


def build_speed_frame(
    fields: DeviceProtocolFields, speed: int, protocol_index: int
) -> bytes:
    if type(speed) is not int or speed not in SPEED_VALUES:
        raise ProtocolError("X83 speed is outside the audited control values")
    frame = assemble_frame(_build_control_payload(0x52, speed), protocol_index, fields)
    validate_speed_frame(frame, fields, speed)
    return frame


def build_light_frame(
    fields: DeviceProtocolFields, light: bool, protocol_index: int
) -> bytes:
    if type(light) is not bool:
        raise ProtocolError("X83 light state is not boolean")
    value = LIGHT_ON_VALUE if light else LIGHT_OFF_VALUE
    frame = assemble_frame(_build_control_payload(0x56, value), protocol_index, fields)
    validate_light_frame(frame, fields, light)
    return frame


def _validated_payload(frame: bytes, fields: DeviceProtocolFields) -> bytes:
    if len(frame) < 17 or frame[0] != FRAME_PREFIX:
        raise ProtocolError("legacy cloud response has an invalid header")
    if frame[8] + 9 != len(frame):
        raise ProtocolError("legacy cloud response has an invalid length")
    if frame[2:8] != fields.mac:
        raise ProtocolError("legacy cloud response belongs to another device")
    if frame[12] != fields.company_code or frame[13] != fields.device_type:
        raise ProtocolError("legacy cloud response has a different device type")
    if int.from_bytes(frame[14:16], "big") != fields.auth_code:
        raise ProtocolError("legacy cloud response auth field does not match")
    return frame[16:]


def validate_power_frame(
    frame: bytes, fields: DeviceProtocolFields, power: bool
) -> None:
    payload = _validated_payload(frame, fields)
    expected = POWER_ON_PAYLOAD if power else POWER_OFF_PAYLOAD
    if payload != expected:
        raise ProtocolError("X83 frame is not the exact allowed power payload")


def _validate_control_frame(
    frame: bytes,
    fields: DeviceProtocolFields,
    expected_payload: bytes,
    control_name: str,
) -> None:
    if _validated_payload(frame, fields) != expected_payload:
        raise ProtocolError(
            f"X83 frame is not the exact allowed {control_name} payload"
        )


def validate_mode_frame(
    frame: bytes, fields: DeviceProtocolFields, mode: int
) -> None:
    if type(mode) is not int or mode not in MODE_VALUES:
        raise ProtocolError("X83 mode is outside the audited control values")
    _validate_control_frame(
        frame, fields, _build_control_payload(0x51, mode), "mode"
    )


def validate_speed_frame(
    frame: bytes, fields: DeviceProtocolFields, speed: int
) -> None:
    if type(speed) is not int or speed not in SPEED_VALUES:
        raise ProtocolError("X83 speed is outside the audited control values")
    _validate_control_frame(
        frame, fields, _build_control_payload(0x52, speed), "speed"
    )


def validate_light_frame(
    frame: bytes, fields: DeviceProtocolFields, light: bool
) -> None:
    if type(light) is not bool:
        raise ProtocolError("X83 light state is not boolean")
    value = LIGHT_ON_VALUE if light else LIGHT_OFF_VALUE
    _validate_control_frame(
        frame, fields, _build_control_payload(0x56, value), "light"
    )


def parse_state_frame(frame: bytes, fields: DeviceProtocolFields) -> X83State:
    payload = _validated_payload(frame, fields)
    if len(payload) != 33 or payload[0:3] != b"\x02\x5A\xA1":
        raise ProtocolError("legacy cloud response is not an X83 state frame")
    if payload[7] not in {0x00, 0x11}:
        raise ProtocolError("X83 child-lock state is outside the audited values")
    if payload[8] not in {0x00, 0x11}:
        raise ProtocolError("X83 light state is outside the audited values")
    if payload[9] not in {0x00, 0x11}:
        raise ProtocolError("X83 power state is outside the audited values")
    return X83State(
        online=True,
        power=payload[9] == 0x00,
        light=payload[8] == 0x00,
        child_lock=payload[7] == 0x11,
        mode=payload[3] & 0x0F,
        filter_type=(payload[3] & 0xF0) >> 4,
        speed=payload[4],
        timer_hours=payload[5],
        air_quality_level=payload[6],
        pm25=int.from_bytes(payload[12:14], "big"),
    )


def parse_online_response(frame: bytes, fields: DeviceProtocolFields) -> bool:
    """Parse a device-bound 0x83 online response, including explicit offline."""
    payload = _validated_payload(frame, fields)
    if len(payload) != 2 or payload[0] != QUERY_DEVICE_ONLINE:
        raise ProtocolError("legacy cloud response is not an X83 online response")
    if payload[1] not in {0, 1}:
        raise ProtocolError("legacy cloud returned an unknown X83 online state")
    return payload[1] == 1


def is_explicit_offline_response(
    frame: bytes, fields: DeviceProtocolFields
) -> bool:
    try:
        return not parse_online_response(frame, fields)
    except ProtocolError:
        return False


def is_state_frame(frame: bytes, fields: DeviceProtocolFields) -> bool:
    try:
        parse_state_frame(frame, fields)
    except ProtocolError:
        return False
    return True


def parse_work_server_response(frame: bytes) -> tuple[str, int]:
    if (
        len(frame) < 23
        or frame[0] != FRAME_PREFIX
        or frame[8] + 9 != len(frame)
        or not frame[1] & 0x02
        or frame[16] != GET_WORK_SERVER
    ):
        raise ProtocolError("legacy cloud returned an invalid work-server response")
    address = ipaddress.IPv4Address(frame[17:21])
    port = int.from_bytes(frame[21:23], "big")
    if not address.is_global or not 1024 <= port <= 65535:
        raise ProtocolError("legacy cloud returned an unsafe work-server endpoint")
    return str(address), port


def parse_join_response(frame: bytes) -> bool:
    return bool(
        len(frame) >= 18
        and frame[1] & 0x02
        and frame[16] == JOIN_WORK_SERVER
        and frame[17] == 0
    )
