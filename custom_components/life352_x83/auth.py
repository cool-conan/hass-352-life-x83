"""One-shot shared-account authentication and X83 discovery."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from aiohttp import ClientError, ClientSession

from .errors import AuthenticationError, CannotConnectError, ProtocolError
from .legacy_auth import build_legacy_device_list_body, sha1withrsa_sign
from .protocol import DeviceProtocolFields, is_x83_legacy_record

MX_HOST = "app.352air.com"
WIFI_HOST = "wifi.352air.com"
MX_APP_ID = "8d5018f2bc0f11ea8e6388e9fe5ac5b6"
LOGIN_PATH = "/api/v1/enduser/login"
LEGACY_LIST_DEVICES_PATH = "/api2/device/getDeviceList"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
HTTP_TIMEOUT_SECONDS = 20
_PASSWORD_LOGIN_ATTEMPTED = False
class X83Authenticator:
    """Allow one password login for one explicit UI flow submission."""

    def __init__(self, session: ClientSession, private_key: bytes) -> None:
        self._session = session
        self._private_key = private_key
        self._login_attempted = False

    async def _post_json(
        self,
        url: str,
        *,
        body: bytes,
        headers: dict[str, str],
        stage: str,
    ) -> dict[str, Any]:
        try:
            async with self._session.post(
                url,
                data=body,
                headers=headers,
                allow_redirects=False,
                timeout=HTTP_TIMEOUT_SECONDS,
            ) as response:
                if response.status in {401, 403}:
                    raise AuthenticationError(f"{stage}: authentication failed")
                if response.status != 200:
                    raise CannotConnectError(f"{stage}: HTTP request failed")
                raw = await response.content.read(MAX_RESPONSE_BYTES + 1)
        except AuthenticationError:
            raise
        except (ClientError, TimeoutError, OSError) as error:
            raise CannotConnectError(f"{stage}: network or TLS error") from error
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ProtocolError(f"{stage}: response is too large")
        try:
            result = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ProtocolError(f"{stage}: response is not JSON") from error
        if not isinstance(result, dict):
            raise ProtocolError(f"{stage}: response shape is invalid")
        return result

    async def async_login_and_discover(
        self, account: str, password: str
    ) -> tuple[str, DeviceProtocolFields]:
        global _PASSWORD_LOGIN_ATTEMPTED

        account = account.strip()
        if not account or not password:
            raise AuthenticationError("account and password are required")
        if self._login_attempted or _PASSWORD_LOGIN_ATTEMPTED:
            raise AuthenticationError(
                "this Home Assistant process already attempted one password login"
            )
        self._login_attempted = True
        _PASSWORD_LOGIN_ATTEMPTED = True

        timestamp = str(int(time.time()))
        sign = hashlib.md5(
            f"{MX_APP_ID}{LOGIN_PATH}{timestamp}".encode()
        ).hexdigest()
        login = await self._post_json(
            f"https://{MX_HOST}{LOGIN_PATH}",
            body=json.dumps(
                {"account": account, "password": password}, separators=(",", ":")
            ).encode(),
            headers={
                "Content-Type": "application/json;charset=utf-8",
                "User-Agent": "352Life/1.8.1",
                "ts": timestamp,
                "sign": sign,
            },
            stage="352 password login",
        )
        if str(login.get("code")) not in {"0", "200"}:
            raise AuthenticationError("352 password login was rejected")
        data = login.get("data")
        if not isinstance(data, dict):
            raise AuthenticationError("352 password login did not return a session")
        token = data.get("air_token")
        if not isinstance(token, str) or not token:
            raise AuthenticationError("352 password login did not return an old-device session")

        signature = sha1withrsa_sign(self._private_key, f"token={token}")
        listing = await self._post_json(
            f"https://{WIFI_HOST}{LEGACY_LIST_DEVICES_PATH}",
            body=build_legacy_device_list_body(token, signature),
            headers={
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "User-Agent": "352Life/1.8.1",
            },
            stage="old-352 device list",
        )
        devices = listing.get("data")
        if not isinstance(devices, list):
            raise ProtocolError("old-352 device list has an invalid response")
        candidates = [
            item for item in devices if isinstance(item, dict) and is_x83_legacy_record(item)
        ]
        if len(candidates) != 1:
            raise ProtocolError("shared account must contain exactly one X83")
        return token, DeviceProtocolFields.from_legacy_record(candidates[0])
