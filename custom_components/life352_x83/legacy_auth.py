"""Pure old-352 RSA signing and encoded form helpers."""

from __future__ import annotations

import base64
import hashlib

from .errors import ProtocolError

OKHTTP_FORM_ENCODE_SET = " \"':;<=>@[]^`{}|/\\?#&!$(),~"


def _read_der_tlv(data: bytes, offset: int, expected_tag: int) -> tuple[bytes, int]:
    if offset >= len(data) or data[offset] != expected_tag:
        raise ProtocolError("old-352 signing key has an unexpected DER shape")
    offset += 1
    if offset >= len(data):
        raise ProtocolError("old-352 signing key has a truncated DER length")
    first = data[offset]
    offset += 1
    if first & 0x80:
        length_bytes = first & 0x7F
        if length_bytes == 0 or length_bytes > 4 or offset + length_bytes > len(data):
            raise ProtocolError("old-352 signing key has an invalid DER length")
        length = int.from_bytes(data[offset : offset + length_bytes], "big")
        offset += length_bytes
    else:
        length = first
    end = offset + length
    if end > len(data):
        raise ProtocolError("old-352 signing key has truncated DER content")
    return data[offset:end], end


def _parse_pkcs8_rsa_private_key(private_key_der: bytes) -> tuple[int, int]:
    outer, outer_end = _read_der_tlv(private_key_der, 0, 0x30)
    if outer_end != len(private_key_der):
        raise ProtocolError("old-352 signing key has trailing DER data")
    _, offset = _read_der_tlv(outer, 0, 0x02)
    algorithm, offset = _read_der_tlv(outer, offset, 0x30)
    if bytes.fromhex("06092a864886f70d010101") not in algorithm:
        raise ProtocolError("old-352 signing key is not RSA PKCS#8")
    private_key, offset = _read_der_tlv(outer, offset, 0x04)
    if offset != len(outer):
        raise ProtocolError("old-352 signing key has unexpected PKCS#8 fields")
    rsa_sequence, rsa_end = _read_der_tlv(private_key, 0, 0x30)
    if rsa_end != len(private_key):
        raise ProtocolError("old-352 RSA key has trailing data")
    integers: list[int] = []
    rsa_offset = 0
    while rsa_offset < len(rsa_sequence):
        integer, rsa_offset = _read_der_tlv(rsa_sequence, rsa_offset, 0x02)
        if not integer:
            raise ProtocolError("old-352 RSA key contains an empty integer")
        integers.append(int.from_bytes(integer, "big"))
    if len(integers) < 4 or integers[0] not in {0, 1}:
        raise ProtocolError("old-352 RSA private key is incomplete")
    modulus, private_exponent = integers[1], integers[3]
    if modulus.bit_length() < 1024 or private_exponent <= 1:
        raise ProtocolError("old-352 RSA private key is invalid")
    return modulus, private_exponent


def sha1withrsa_sign(private_key_der: bytes, message: str) -> str:
    """Match Java SHA1withRSA and Android Base64.DEFAULT output."""
    modulus, private_exponent = _parse_pkcs8_rsa_private_key(private_key_der)
    digest_info = bytes.fromhex("3021300906052b0e03021a05000414") + hashlib.sha1(
        message.encode("utf-8")
    ).digest()
    key_bytes = (modulus.bit_length() + 7) // 8
    padding_length = key_bytes - len(digest_info) - 3
    if padding_length < 8:
        raise ProtocolError("old-352 RSA key is too small for SHA1withRSA")
    encoded = b"\x00\x01" + (b"\xff" * padding_length) + b"\x00" + digest_info
    signature = pow(int.from_bytes(encoded, "big"), private_exponent, modulus).to_bytes(
        key_bytes, "big"
    )
    return base64.encodebytes(signature).decode("ascii")


def okhttp_form_encode_already_encoded(value: str) -> str:
    output: list[str] = []
    for character in value:
        codepoint = ord(character)
        if character in "\t\n\f\r":
            continue
        if character == "+":
            output.append("+")
            continue
        if (
            codepoint < 0x20
            or codepoint == 0x7F
            or codepoint >= 0x80
            or character in OKHTTP_FORM_ENCODE_SET
        ):
            output.extend(f"%{byte:02X}" for byte in character.encode("utf-8"))
        else:
            output.append(character)
    return "".join(output)


def build_legacy_device_list_body(token: str, signature: str) -> bytes:
    return "&".join(
        f"{okhttp_form_encode_already_encoded(key)}="
        f"{okhttp_form_encode_already_encoded(value)}"
        for key, value in (("token", token), ("sign", signature))
    ).encode("ascii")
