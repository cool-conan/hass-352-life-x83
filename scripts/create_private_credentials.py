#!/usr/bin/env python3
"""Create the deployment-only X83 signing credential from the audited APK."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
import zipfile
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from custom_components.life352_x83.errors import ProtocolError  # noqa: E402
from custom_components.life352_x83.legacy_auth import sha1withrsa_sign  # noqa: E402

APK_SHA256 = "8748c78c74f0c8f2447b309fb6ba3744414689cfcf7424d5b101c1839e264c2c"
LEGACY_PRIVATE_KEY_SHA256 = (
    "c45d9bbabac3a712f24e0f58793d329e4858500dc5074c964d04f2591d0ddc1d"
)
AUDITED_DEX_SHA256 = {
    "classes.dex": "1f1189cfbe97c0099593b77d28c0db6ade0633a66713efd36d123a493f185724",
    "classes3.dex": "4a4ddada638b4f65802b64d83e53a0ee1d715b76e134129b6b2de4169750b0a3",
}
DEFAULT_OUTPUT = REPOSITORY_ROOT / "private/life352_x83_private.json"


class CredentialBuildError(RuntimeError):
    """Safe error that never includes private credential contents."""


def find_default_apk() -> Path | None:
    """Find the audited 352Life APK in the current user's Downloads folder."""
    downloads = Path.home() / "Downloads"
    matches = sorted(downloads.glob("106_b618c0534310679518f15a32c28eec37*.apk"))
    return matches[0] if matches else None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        raise CredentialBuildError(
            "APK or audited DEX carrier cannot be read"
        ) from None
    return digest.hexdigest()


def read_audited_dex_entries(apk_path: Path) -> dict[str, bytes]:
    """Accept only the exact audited APK or exact two-DEX transfer carrier."""
    artifact_digest = _sha256_file(apk_path)
    try:
        with zipfile.ZipFile(apk_path) as archive:
            if artifact_digest == APK_SHA256:
                names = [
                    name
                    for name in archive.namelist()
                    if name.startswith("classes") and name.endswith(".dex")
                ]
                return {name: archive.read(name) for name in names}

            entries = {name: archive.read(name) for name in AUDITED_DEX_SHA256}
    except (OSError, zipfile.BadZipFile, KeyError):
        raise CredentialBuildError(
            "artifact is neither the audited APK nor its DEX carrier"
        ) from None

    for name, expected_digest in AUDITED_DEX_SHA256.items():
        if hashlib.sha256(entries[name]).hexdigest() != expected_digest:
            raise CredentialBuildError(f"audited DEX digest mismatch: {name}")
    return entries


def extract_legacy_private_key(apk_path: Path) -> bytes:
    """Extract the audited PKCS#8 key in memory without printing its contents."""
    candidate_pattern = re.compile(
        rb"(?<![0-9A-Fa-f])[0-9A-Fa-f]{1000,6000}(?![0-9A-Fa-f])"
    )
    for dex_bytes in read_audited_dex_entries(apk_path).values():
        for candidate in candidate_pattern.findall(dex_bytes):
            if len(candidate) % 2:
                continue
            decoded = bytes.fromhex(candidate.decode("ascii"))
            if hashlib.sha256(decoded).hexdigest() != LEGACY_PRIVATE_KEY_SHA256:
                continue
            try:
                sha1withrsa_sign(decoded, "credential validation")
            except ProtocolError as error:
                raise CredentialBuildError(
                    "audited signing key has an invalid PKCS#8 structure"
                ) from error
            return decoded
    raise CredentialBuildError(
        "audited old-352 signing key was not found in the APK"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apk", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    apk_path = args.apk or find_default_apk()
    if apk_path is None:
        print("error: audited APK was not found", file=sys.stderr)
        return 2
    try:
        private_key = extract_legacy_private_key(apk_path.expanduser())
    except CredentialBuildError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    output = args.output.expanduser().resolve()
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(output.parent, 0o700)
    document = {
        "format": 1,
        "legacy_private_key_pkcs8_b64": base64.b64encode(private_key).decode("ascii"),
    }
    try:
        descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        print(
            "error: output already exists; remove it explicitly before regenerating",
            file=sys.stderr,
        )
        return 2
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(document, handle, separators=(",", ":"))
        handle.write("\n")
    print(f"created private credential: {output}")
    print("copy it to /config/.storage/life352_x83_private.json with mode 0600")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
