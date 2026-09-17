"""Tests for the device identity handshake (small targeted reads)."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from srne_ble.crc import append_crc  # noqa: E402
from srne_ble.identify import (  # noqa: E402
    CMD_DEVICE_SPEC,
    CMD_DEVICE_TYPE,
    CMD_HW_VERSION,
    CMD_SW_VERSION,
    parse_spec,
    parse_type,
    parse_version,
    read_identity,
)


def response(data: bytes) -> bytes:
    """Build a Modbus read response frame carrying *data*."""
    return append_crc(bytes([0xFF, 0x03, len(data)]) + data)


def test_parse_type_low_byte():
    assert parse_type(response(bytes([0x20, 0x00]))) == "00"   # controller
    assert parse_type(response(bytes([0x00, 0x40]))) == "40"   # lithium battery


def test_parse_spec_ascii_stripped():
    raw = b"  MC2430N10\x00\x00\x00\x00\x00"
    assert parse_spec(response(raw)) == "MC2430N10"


def test_parse_version():
    assert parse_version(response(bytes([0x00, 0x01, 0x02, 0x03]))) == "V1.2.3"


def test_parse_rejects_bad_crc():
    frame = bytearray(response(bytes([0x20, 0x00])))
    frame[-1] ^= 0xFF
    try:
        parse_type(bytes(frame))
    except ValueError:
        pass
    else:
        raise AssertionError("expected CRC rejection")


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_read_identity_controller():
    replies = {
        CMD_DEVICE_TYPE: response(bytes([0x20, 0x00])),          # type 00
        CMD_DEVICE_SPEC: response(b"MC2430N10\x00\x00\x00\x00\x00\x00\x00"),
        CMD_SW_VERSION: response(bytes([0x00, 0x01, 0x02, 0x03])),
        CMD_HW_VERSION: response(bytes([0x00, 0x01, 0x00, 0x00])),
    }

    async def request(cmd):
        return replies[cmd]

    ident = _run(read_identity(request))
    assert ident.type_code == "00" and ident.is_controller
    assert ident.type_name == "Controller"
    assert ident.model == "MC2430N10"
    assert ident.software_version == "V1.2.3"
    assert ident.hardware_version == "V1.0.0"


def test_read_identity_is_resilient_to_optional_failures():
    async def request(cmd):
        if cmd == CMD_DEVICE_TYPE:
            return response(bytes([0x00, 0x00]))
        raise RuntimeError("device didn't answer optional field")

    ident = _run(read_identity(request))
    assert ident.type_code == "00" and ident.is_controller
    assert ident.model == ""            # optional reads failed, but identity still returns
    assert ident.software_version == ""
