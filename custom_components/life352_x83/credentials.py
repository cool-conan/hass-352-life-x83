"""Load the deployment-only legacy signing credential."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import stat
from pathlib import Path

from .errors import ProtocolError

PRIVATE_CREDENTIALS_RELATIVE_PATH = Path(".storage/life352_x83_private.json")
LEGACY_PRIVATE_KEY_SHA256 = (
    "c45d9bbabac3a712f24e0f58793d329e4858500dc5074c964d04f2591d0ddc1d"
)
MAX_CREDENTIAL_FILE_BYTES = 8192


def load_legacy_private_key(config_dir: str) -> bytes:
    """Read and verify a private deployment file without following symlinks."""
    path = Path(config_dir) / PRIVATE_CREDENTIALS_RELATIVE_PATH
    try:
        metadata = path.lstat()
    except OSError as error:
        raise ProtocolError("life352_x83 private credential file is missing") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ProtocolError("life352_x83 private credential must be a regular file")
    if metadata.st_mode & 0o077:
        raise ProtocolError("life352_x83 private credential permissions must be 0600")
    if metadata.st_size > MAX_CREDENTIAL_FILE_BYTES:
        raise ProtocolError("life352_x83 private credential file is too large")

    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
            raise ProtocolError("life352_x83 private credential changed while opening")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            raw = handle.read(MAX_CREDENTIAL_FILE_BYTES + 1)
    except OSError as error:
        raise ProtocolError("life352_x83 private credential cannot be read") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if len(raw) > MAX_CREDENTIAL_FILE_BYTES:
        raise ProtocolError("life352_x83 private credential file is too large")
    try:
        document = json.loads(raw)
        encoded = document["legacy_private_key_pkcs8_b64"]
        key = base64.b64decode(encoded, validate=True)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ProtocolError("life352_x83 private credential has an invalid format") from error
    if hashlib.sha256(key).hexdigest() != LEGACY_PRIVATE_KEY_SHA256:
        raise ProtocolError("life352_x83 private credential digest does not match")
    return key
