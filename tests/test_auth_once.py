import sys
import unittest
from pathlib import Path
from unittest import mock

HOME_ASSISTANT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOME_ASSISTANT_DIR))

# The local system Python may have no Home Assistant dependencies. Stub only
# aiohttp's imported names in that environment, without polluting HA runtime tests.
try:
    import aiohttp  # noqa: F401
except ImportError:
    aiohttp = mock.MagicMock()
    aiohttp.ClientError = OSError
    aiohttp.ClientSession = object
    sys.modules["aiohttp"] = aiohttp

from custom_components.life352_x83 import auth
from custom_components.life352_x83.errors import AuthenticationError


class AuthenticationProcessBoundaryTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        auth._PASSWORD_LOGIN_ATTEMPTED = False

    def tearDown(self):
        auth._PASSWORD_LOGIN_ATTEMPTED = False

    async def test_second_password_attempt_in_process_is_blocked_before_http(self):
        first = auth.X83Authenticator(mock.MagicMock(), b"fixture")
        second = auth.X83Authenticator(mock.MagicMock(), b"fixture")
        with mock.patch.object(
            first, "_post_json", side_effect=AuthenticationError("rejected")
        ) as post:
            with self.assertRaises(AuthenticationError):
                await first.async_login_and_discover("shared", "password")
        post.assert_awaited_once()
        with mock.patch.object(second, "_post_json") as second_post:
            with self.assertRaisesRegex(AuthenticationError, "already attempted"):
                await second.async_login_and_discover("shared", "password")
        second_post.assert_not_called()

    async def test_empty_credentials_do_not_consume_process_login_attempt(self):
        empty = auth.X83Authenticator(mock.MagicMock(), b"fixture")
        with mock.patch.object(empty, "_post_json") as empty_post:
            with self.assertRaisesRegex(AuthenticationError, "required"):
                await empty.async_login_and_discover("", "")
        empty_post.assert_not_called()
        self.assertFalse(auth._PASSWORD_LOGIN_ATTEMPTED)

        valid = auth.X83Authenticator(mock.MagicMock(), b"fixture")
        with mock.patch.object(
            valid, "_post_json", side_effect=AuthenticationError("rejected")
        ) as valid_post:
            with self.assertRaises(AuthenticationError):
                await valid.async_login_and_discover("shared", "password")
        valid_post.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
