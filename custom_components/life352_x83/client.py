"""Bounded async client for one legacy 352 X83 TLS work session."""

from __future__ import annotations

import asyncio
import ssl
import time
from collections.abc import Callable

from .errors import (
    AuthenticationError,
    CannotConnectError,
    ControlStateNotConfirmedError,
    PowerStateNotConfirmedError,
    ProtocolError,
)
from .protocol import (
    ABNORMAL_LOGIN,
    GET_WORK_SERVER,
    JOIN_WORK_SERVER,
    MAX_FRAME_SIZE,
    DeviceProtocolFields,
    X83State,
    build_get_work_server_frame,
    build_join_work_server_frame,
    build_light_frame,
    build_mode_frame,
    build_power_frame,
    build_query_online_frame,
    build_read_state_frame,
    build_subscribe_device_event_frame,
    build_subscribe_online_frame,
    build_speed_frame,
    is_explicit_offline_response,
    parse_join_response,
    parse_state_frame,
    parse_work_server_response,
)

LOAD_BALANCER_HOST = "wifi.352air.com"
TCP_PORT = 11591
CONNECT_TIMEOUT_SECONDS = 8.0
RESPONSE_TIMEOUT_SECONDS = 6.0
MAX_SKIPPED_FRAMES = 16
CONTROL_INTERVAL_SECONDS = 0.150
CLOSE_TIMEOUT_SECONDS = 1.0


def verified_tls_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context


class X83CloudClient:
    """Own one serialized work-server stream and never perform password login."""

    def __init__(self, token: str, fields: DeviceProtocolFields) -> None:
        if not token:
            raise AuthenticationError("persisted old-352 session is missing")
        self._token = token
        self._fields = fields
        self._context = verified_tls_context()
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()
        self._protocol_index = 0

    def _next_index(self) -> int:
        result = self._protocol_index
        self._protocol_index = (self._protocol_index + 1) & 0x7FFF
        return result

    async def _open_verified(
        self, host: str, port: int
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        try:
            return await asyncio.wait_for(
                asyncio.open_connection(
                    host,
                    port,
                    ssl=self._context,
                    server_hostname=LOAD_BALANCER_HOST,
                ),
                timeout=CONNECT_TIMEOUT_SECONDS,
            )
        except (OSError, ssl.SSLError, asyncio.TimeoutError) as error:
            raise CannotConnectError(
                "legacy cloud TLS connection or certificate verification failed"
            ) from error

    async def _receive_frame(
        self, reader: asyncio.StreamReader, timeout: float = RESPONSE_TIMEOUT_SECONDS
    ) -> bytes:
        deadline = time.monotonic() + timeout
        try:
            prefix = await asyncio.wait_for(
                reader.readexactly(9), timeout=max(0.05, timeout)
            )
            total_length = prefix[8] + 9
            if prefix[0] != 0xA1 or not 17 <= total_length <= MAX_FRAME_SIZE:
                raise ProtocolError("legacy cloud returned an invalid frame header")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise asyncio.TimeoutError
            suffix = await asyncio.wait_for(
                reader.readexactly(total_length - 9), timeout=max(0.05, remaining)
            )
        except (asyncio.IncompleteReadError, ConnectionError, OSError) as error:
            raise CannotConnectError("legacy cloud connection closed early") from error
        except asyncio.TimeoutError as error:
            raise CannotConnectError("legacy cloud response timed out") from error
        frame = prefix + suffix
        if frame[16] == ABNORMAL_LOGIN:
            raise AuthenticationError("legacy cloud rejected the persisted session")
        return frame

    async def _drain_writer(self, writer: asyncio.StreamWriter) -> None:
        """Normalize a write-side disconnect into the bounded retry path."""
        try:
            await writer.drain()
        except (ConnectionError, OSError, ssl.SSLError) as error:
            writer.close()
            raise CannotConnectError(
                "legacy cloud connection closed while sending"
            ) from error

    async def _wait_for_frame(
        self,
        reader: asyncio.StreamReader,
        predicate: Callable[[bytes], bool],
        response_name: str,
    ) -> bytes:
        deadline = time.monotonic() + RESPONSE_TIMEOUT_SECONDS
        for _ in range(MAX_SKIPPED_FRAMES):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            frame = await self._receive_frame(reader, remaining)
            if predicate(frame):
                return frame
        raise CannotConnectError(
            f"legacy cloud did not return the expected {response_name} response"
        )

    async def _close_locked(self) -> None:
        writer = self._writer
        self._reader = None
        self._writer = None
        if writer is not None:
            await self._close_writer(writer)

    async def _close_writer(self, writer: asyncio.StreamWriter) -> None:
        """Close a TLS stream without letting its shutdown handshake hang HA."""
        writer.close()
        try:
            await asyncio.wait_for(
                writer.wait_closed(), timeout=CLOSE_TIMEOUT_SECONDS
            )
        except (asyncio.TimeoutError, ConnectionError, OSError, ssl.SSLError):
            pass

    async def _get_work_endpoint(self) -> tuple[str, int]:
        reader, writer = await self._open_verified(LOAD_BALANCER_HOST, TCP_PORT)
        try:
            writer.write(build_get_work_server_frame(self._next_index()))
            await self._drain_writer(writer)
            response = await self._wait_for_frame(
                reader,
                lambda frame: len(frame) > 16 and frame[16] == GET_WORK_SERVER,
                "work-server",
            )
            return parse_work_server_response(response)
        finally:
            await self._close_writer(writer)

    async def _connect_locked(self) -> None:
        await self._close_locked()
        host, port = await self._get_work_endpoint()
        reader, writer = await self._open_verified(host, port)
        self._reader = reader
        self._writer = writer
        try:
            writer.write(build_join_work_server_frame(self._token, self._next_index()))
            await self._drain_writer(writer)
            response = await self._wait_for_frame(
                reader,
                lambda frame: len(frame) > 16 and frame[16] == JOIN_WORK_SERVER,
                "join",
            )
            if not parse_join_response(response):
                raise AuthenticationError("legacy cloud refused the persisted session")
            writer.write(build_subscribe_online_frame(self._fields, self._next_index()))
            writer.write(
                build_subscribe_device_event_frame(self._fields, self._next_index())
            )
            await self._drain_writer(writer)
        except Exception:
            await self._close_locked()
            raise

    async def _ensure_connected_locked(self) -> None:
        if self._reader is None or self._writer is None or self._writer.is_closing():
            await self._connect_locked()

    async def _read_state_locked(self) -> X83State:
        await self._ensure_connected_locked()
        assert self._reader is not None
        assert self._writer is not None
        self._writer.write(build_query_online_frame(self._fields, self._next_index()))
        self._writer.write(build_read_state_frame(self._fields, self._next_index()))
        await self._drain_writer(self._writer)
        frame = await self._wait_for_frame(
            self._reader,
            lambda candidate: self._try_parse_state(candidate) is not None
            or is_explicit_offline_response(candidate, self._fields),
            "X83 state",
        )
        if is_explicit_offline_response(frame, self._fields):
            return X83State.offline()
        return parse_state_frame(frame, self._fields)

    def _try_parse_state(self, frame: bytes) -> X83State | None:
        try:
            return parse_state_frame(frame, self._fields)
        except ProtocolError:
            return None

    async def async_read_state(self) -> X83State:
        """Read state, reconnecting at most once with the persisted token."""
        async with self._lock:
            for attempt in range(2):
                try:
                    return await self._read_state_locked()
                except AuthenticationError:
                    await self._close_locked()
                    raise
                except CannotConnectError:
                    await self._close_locked()
                    if attempt:
                        raise
            raise CannotConnectError("bounded X83 state read failed")

    async def async_set_power(self, power: bool) -> X83State:
        """Set power and return only a matching device-data readback."""
        async with self._lock:
            return await self._set_control_locked(
                lambda protocol_index: build_power_frame(
                    self._fields, power, protocol_index
                ),
                lambda state: state.power is power,
                "power",
                PowerStateNotConfirmedError,
            )

    async def async_set_mode(self, mode: int) -> X83State:
        """Set the raw protocol mode and require matching device-data."""
        async with self._lock:
            return await self._set_control_locked(
                lambda protocol_index: build_mode_frame(
                    self._fields, mode, protocol_index
                ),
                lambda state: state.mode == mode,
                "mode",
            )

    async def async_set_speed(self, speed: int) -> X83State:
        """Set fan speed and require matching device-data."""
        async with self._lock:
            return await self._set_control_locked(
                lambda protocol_index: build_speed_frame(
                    self._fields, speed, protocol_index
                ),
                lambda state: state.speed == speed,
                "speed",
            )

    async def async_set_light(self, light: bool) -> X83State:
        """Set display light and require matching device-data."""
        async with self._lock:
            return await self._set_control_locked(
                lambda protocol_index: build_light_frame(
                    self._fields, light, protocol_index
                ),
                lambda state: state.light is light,
                "light",
            )

    async def _set_control_locked(
        self,
        build_control: Callable[[int], bytes],
        matches: Callable[[X83State], bool],
        control_name: str,
        error_type: type[ControlStateNotConfirmedError] = ControlStateNotConfirmedError,
    ) -> X83State:
        """Send exactly three control/read rounds, then require device readback."""
        await self._ensure_connected_locked()
        assert self._reader is not None
        assert self._writer is not None
        try:
            for round_index in range(3):
                self._writer.write(build_control(self._next_index()))
                self._writer.write(
                    build_read_state_frame(self._fields, self._next_index())
                )
                await self._drain_writer(self._writer)
                if round_index < 2:
                    await asyncio.sleep(CONTROL_INTERVAL_SECONDS)

            deadline = time.monotonic() + RESPONSE_TIMEOUT_SECONDS
            for _ in range(MAX_SKIPPED_FRAMES):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                frame = await self._receive_frame(self._reader, remaining)
                state = self._try_parse_state(frame)
                if state is not None and matches(state):
                    return state
        except (AuthenticationError, CannotConnectError, ProtocolError):
            await self._close_locked()
            raise
        raise error_type(
            f"X83 device-data frame did not confirm the requested {control_name} state"
        )

    async def async_close(self) -> None:
        async with self._lock:
            await self._close_locked()
