"""CRC and frame-builder tests, checked against known-good protocol vectors."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from srne_ble.crc import append_crc, check_crc, crc16  # noqa: E402
from srne_ble.protocol import build_read_holding  # noqa: E402


def test_crc_matches_known_command():
    # "FF0301000023" -> "FF03010000231031"
    frame = append_crc(bytes.fromhex("FF0301000023"))
    assert frame.hex() == "ff03010000231031"


def test_more_commands():
    # "ff03010A0063" -> CRC "31c3"
    assert append_crc(bytes.fromhex("ff03010A0063")).hex() == "ff03010a006331c3"
    # "FF0301010001" -> "c1e8"
    assert append_crc(bytes.fromhex("FF0301010001")).hex() == "ff0301010001c1e8"


def test_build_read_holding_controller_realtime():
    assert build_read_holding(0x0100, 0x23).hex() == "ff03010000231031"


def test_check_crc_roundtrip():
    frame = append_crc(bytes.fromhex("FF0301000023"))
    assert check_crc(frame)
    assert not check_crc(frame[:-1] + b"\x00")


def test_crc16_value():
    assert crc16(bytes.fromhex("FF0301000023")) == 0x3110
