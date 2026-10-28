import base64
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HOME_ASSISTANT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOME_ASSISTANT_DIR))

from custom_components.life352_x83 import credentials, legacy_auth
from custom_components.life352_x83.errors import ProtocolError


class AuthAndCredentialsTest(unittest.TestCase):
    def test_okhttp_encoded_form_matches_apk_semantics(self):
        body = legacy_auth.build_legacy_device_list_body(
            "token-value", "A+B/C=\nSECOND+LINE==\n"
        )
        self.assertEqual(
            body,
            b"token=token-value&sign=A+B%2FC%3DSECOND+LINE%3D%3D",
        )

    def test_private_file_must_be_0600_and_digest_bound(self):
        key = b"private-fixture"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / credentials.PRIVATE_CREDENTIALS_RELATIVE_PATH
            path.parent.mkdir()
            path.write_text(
                json.dumps(
                    {
                        "legacy_private_key_pkcs8_b64": base64.b64encode(key).decode()
                    }
                ),
                encoding="utf-8",
            )
            os.chmod(path, 0o600)
            with mock.patch.object(
                credentials,
                "LEGACY_PRIVATE_KEY_SHA256",
                hashlib.sha256(key).hexdigest(),
            ):
                self.assertEqual(credentials.load_legacy_private_key(directory), key)
            os.chmod(path, 0o644)
            with self.assertRaisesRegex(ProtocolError, "0600"):
                credentials.load_legacy_private_key(directory)

    def test_malformed_rsa_key_is_rejected(self):
        with self.assertRaises(ProtocolError):
            legacy_auth.sha1withrsa_sign(b"not-a-key", "token=value")


if __name__ == "__main__":
    unittest.main()
