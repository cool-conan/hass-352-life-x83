import asyncio
import sys
import unittest
from pathlib import Path
from unittest import mock

HOME_ASSISTANT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOME_ASSISTANT_DIR))

from custom_components.life352_x83.client import (
    CLOSE_TIMEOUT_SECONDS,
    CONTROL_INTERVAL_SECONDS,
    X83CloudClient,
)
from custom_components.life352_x83.errors import (
    ControlStateNotConfirmedError,
    PowerStateNotConfirmedError,
)
from custom_components.life352_x83.protocol import (
    QUERY_DEVICE_ONLINE,
    DeviceProtocolFields,
    assemble_frame,
)


class FakeWriter:
    def __init__(self, drain_error=None, wait_closed=None):
        self.frames = []
        self.drain_error = drain_error
        self._wait_closed = wait_closed
        self.closed = False

    def write(self, frame):
        self.frames.append(frame)

    async def drain(self):
        if self.drain_error is not None:
            raise self.drain_error
        return None

    def is_closing(self):
        return self.closed

    def close(self):
        self.closed = True

    async def wait_closed(self):
        if self._wait_closed is not None:
            await self._wait_closed()
        return None


class ClientControlTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fields = DeviceProtocolFields(
            mac=bytes.fromhex("001122334455"),
            company_code=0xF1,
            device_type=0x02,
            auth_code=0x1234,
        )
        self.client = X83CloudClient("fixture-token", self.fields)
        self.client._reader = mock.sentinel.reader
        self.writer = FakeWriter()
        self.client._writer = self.writer

    def _state_frame(self, power, *, mode=1, speed=3, light=True):
        payload = bytearray(33)
        payload[0:3] = b"\x02\x5A\xA1"
        payload[3] = mode
        payload[4] = speed
        payload[7] = 0x00
        payload[8] = 0x00 if light else 0x11
        payload[9] = 0x00 if power else 0x11
        return assemble_frame(bytes(payload), 10, self.fields)

    async def test_power_control_is_three_rounds_at_150ms_and_uses_readback(self):
        with mock.patch.object(
            self.client, "_receive_frame", return_value=self._state_frame(True)
        ), mock.patch(
            "custom_components.life352_x83.client.asyncio.sleep", new=mock.AsyncMock()
        ) as sleep:
            result = await self.client.async_set_power(True)
        self.assertTrue(result.power)
        self.assertEqual(len(self.writer.frames), 6)
        self.assertEqual(
            [frame[16:] for frame in self.writer.frames[0::2]],
            [bytes.fromhex("01 A5 A0 5E 35 00 D8")] * 3,
        )
        self.assertEqual(
            [frame[16:] for frame in self.writer.frames[1::2]],
            [bytes.fromhex("01 A5 A0 50 50 00 00")] * 3,
        )
        self.assertEqual(
            sleep.await_args_list,
            [mock.call(CONTROL_INTERVAL_SECONDS), mock.call(CONTROL_INTERVAL_SECONDS)],
        )

    async def test_nonmatching_frames_never_create_optimistic_state(self):
        frames = [self._state_frame(False)] * 16
        with mock.patch.object(
            self.client, "_receive_frame", side_effect=frames
        ), mock.patch(
            "custom_components.life352_x83.client.asyncio.sleep", new=mock.AsyncMock()
        ):
            with self.assertRaises(PowerStateNotConfirmedError):
                await self.client.async_set_power(True)

    async def test_mode_speed_and_light_use_three_exact_rounds_and_readback(self):
        cases = (
            (
                "async_set_mode",
                5,
                self._state_frame(True, mode=5),
                bytes.fromhex("01 A5 A0 51 05 00 9B"),
            ),
            (
                "async_set_speed",
                6,
                self._state_frame(True, speed=6),
                bytes.fromhex("01 A5 A0 52 06 00 9D"),
            ),
            (
                "async_set_light",
                False,
                self._state_frame(True, light=False),
                bytes.fromhex("01 A5 A0 56 11 00 AC"),
            ),
        )
        for method_name, value, readback, expected_payload in cases:
            with self.subTest(method=method_name):
                self.writer.frames.clear()
                with mock.patch.object(
                    self.client, "_receive_frame", return_value=readback
                ), mock.patch(
                    "custom_components.life352_x83.client.asyncio.sleep",
                    new=mock.AsyncMock(),
                ):
                    result = await getattr(self.client, method_name)(value)
                self.assertIsNotNone(result)
                self.assertEqual(len(self.writer.frames), 6)
                self.assertEqual(
                    [frame[16:] for frame in self.writer.frames[0::2]],
                    [expected_payload] * 3,
                )
                self.assertEqual(
                    [frame[16:] for frame in self.writer.frames[1::2]],
                    [bytes.fromhex("01 A5 A0 50 50 00 00")] * 3,
                )

    async def test_new_controls_reject_nonmatching_readback(self):
        frames = [self._state_frame(True, mode=1, speed=1, light=True)] * 16
        with mock.patch.object(
            self.client, "_receive_frame", side_effect=frames
        ), mock.patch(
            "custom_components.life352_x83.client.asyncio.sleep", new=mock.AsyncMock()
        ):
            with self.assertRaises(ControlStateNotConfirmedError):
                await self.client.async_set_mode(5)

    async def test_explicit_offline_response_returns_online_false(self):
        offline = assemble_frame(
            bytes((QUERY_DEVICE_ONLINE, 0)), 11, self.fields
        )
        with mock.patch.object(
            self.client, "_wait_for_frame", return_value=offline
        ):
            state = await self.client.async_read_state()
        self.assertFalse(state.online)

    async def test_write_disconnect_enters_bounded_reconnect(self):
        broken = FakeWriter(ConnectionResetError("closed"))
        self.client._writer = broken
        healthy = FakeWriter()

        async def reconnect():
            self.client._reader = mock.sentinel.reconnected_reader
            self.client._writer = healthy

        with mock.patch.object(
            self.client,
            "_connect_locked",
            side_effect=reconnect,
        ) as connect, mock.patch.object(
            self.client,
            "_wait_for_frame",
            return_value=self._state_frame(True),
        ):
            state = await self.client.async_read_state()
        self.assertTrue(state.power)
        connect.assert_awaited_once()
        self.assertTrue(broken.closed)

    async def test_tls_close_handshake_is_bounded(self):
        never_closed = asyncio.Event()

        async def wait_forever():
            await never_closed.wait()

        writer = FakeWriter(wait_closed=wait_forever)
        with mock.patch(
            "custom_components.life352_x83.client.CLOSE_TIMEOUT_SECONDS", 0.001
        ):
            await asyncio.wait_for(self.client._close_writer(writer), timeout=0.1)

        self.assertTrue(writer.closed)
        self.assertEqual(CLOSE_TIMEOUT_SECONDS, 1.0)


if __name__ == "__main__":
    unittest.main()
