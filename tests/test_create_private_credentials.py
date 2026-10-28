import importlib.util
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest import mock

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPOSITORY_ROOT / "scripts/create_private_credentials.py"
SPEC = importlib.util.spec_from_file_location("create_private_credentials", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("could not load create_private_credentials.py")
script = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = script
SPEC.loader.exec_module(script)


class CreatePrivateCredentialsTest(unittest.TestCase):
    def test_default_output_is_private_and_repository_relative(self):
        self.assertEqual(
            script.DEFAULT_OUTPUT,
            REPOSITORY_ROOT / "private/life352_x83_private.json",
        )

    def test_invalid_artifact_fails_without_creating_output(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "invalid.apk"
            output = Path(directory) / "credential.json"
            artifact.write_bytes(b"not an APK")

            with redirect_stderr(StringIO()), mock.patch.object(
                sys,
                "argv",
                [
                    str(SCRIPT_PATH),
                    "--apk",
                    str(artifact),
                    "--output",
                    str(output),
                ],
            ):
                result = script.main()

            self.assertEqual(result, 2)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
