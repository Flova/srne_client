"""Tests for the charge/discharge switch control (register 0xDF00).

Safety-critical: these lock down the exact write bytes and the guards that
prevent reporting an unconfirmed or wrong-register write as success.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from srne_ble.charge import (  # noqa: E402
    CHARGE_SWITCH_REGISTER,
    charge_switch_command,
    charge_switch_read_command,
    is_write_ack,
    parse_charge_switch,
)
from srne_ble.crc import append_crc  # noqa: E402


def test_register_is_df00():
    assert CHARGE_SWITCH_REGISTER == 0xDF00


def test_exact_write_bytes():
    # ON  = FF06 DF00 0001 + CRC ; OFF = FF06 DF00 0000 + CRC
    assert charge_switch_command(True).hex() == append_crc(bytes.fromhex("FF06DF000001")).hex()
    assert charge_switch_command(False).hex() == append_crc(bytes.fromhex("FF06DF000000")).hex()
    # Never touches any other register.
    assert charge_switch_command(True)[2:4] == bytes.fromhex("DF00")
    assert charge_switch_command(False)[2:4] == bytes.fromhex("DF00")


def test_exact_read_bytes():
    assert charge_switch_read_command().hex() == append_crc(bytes.fromhex("FF03DF000001")).hex()


def _read_response(value: int) -> bytes:
    return append_crc(bytes([0xFF, 0x03, 0x02, (value >> 8) & 0xFF, value & 0xFF]))


def test_parse_state():
    assert parse_charge_switch(_read_response(0x0001)) is True
    assert parse_charge_switch(_read_response(0x0000)) is False
    assert parse_charge_switch(_read_response(0x00FF)) is True  # any non-zero = on


def test_parse_rejects_bad_crc():
    frame = bytearray(_read_response(1))
    frame[-1] ^= 0xFF
    try:
        parse_charge_switch(bytes(frame))
    except ValueError:
        pass
    else:
        raise AssertionError("expected CRC rejection")


def test_write_ack_accepts_correct_echo():
    cmd = charge_switch_command(True)
    assert is_write_ack(cmd, cmd) is True  # device echoes the request


def test_write_ack_rejects_wrong_register_or_value():
    cmd_on = charge_switch_command(True)
    # Echo for a different register/value must not be accepted as our write.
    other = append_crc(bytes.fromhex("FF06E0030001"))
    assert is_write_ack(other, cmd_on) is False
    cmd_off = charge_switch_command(False)
    assert is_write_ack(cmd_off, cmd_on) is False  # value mismatch


def test_write_ack_rejects_exception_and_garbage():
    cmd = charge_switch_command(True)
    exception = append_crc(bytes([0xFF, 0x86, 0x02]))  # function|0x80 = error
    assert is_write_ack(exception, cmd) is False
    assert is_write_ack(b"\x00\x00", cmd) is False
    bad_crc = bytearray(cmd)
    bad_crc[-1] ^= 0xFF
    assert is_write_ack(bytes(bad_crc), cmd) is False
