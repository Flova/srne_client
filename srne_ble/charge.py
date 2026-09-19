"""Charge/discharge switch control (register 0xDF00).

This is the ONLY writable control in the library, deliberately kept narrow.

* Write: Modbus function 0x06 (write single register) to 0xDF00.
      value 1 -> charging enabled ("on")
      value 0 -> charging disabled ("off")
* Read state: function 0x03 read of 0xDF00; 0 = off, non-zero = on.

No other register is ever written. The write frame is built from a fixed
register constant and a boolean, so an arbitrary address/value cannot be sent.
Callers should confirm a write both by :func:`is_write_ack` (the device's write
response echoes the register + value it accepted) and by reading the state back
with :func:`parse_charge_switch`.
"""

from __future__ import annotations

from .crc import check_crc
from .protocol import FUNC_WRITE_SINGLE, build_read_holding, build_write_single

# The charge/discharge switch register. This module writes no other register.
CHARGE_SWITCH_REGISTER = 0xDF00


def charge_switch_command(on: bool) -> bytes:
    """Return the write frame that enables (*on*) or disables charging."""
    return build_write_single(CHARGE_SWITCH_REGISTER, 1 if on else 0)


def charge_switch_read_command() -> bytes:
    """Return the read frame for the charge-switch state register."""
    return build_read_holding(CHARGE_SWITCH_REGISTER, 1)


def _read_data(frame: bytes) -> bytes:
    """Validate a function-0x03 read response and return its data bytes."""
    if len(frame) < 5 or frame[1] & 0x80 or frame[1] != 0x03:
        raise ValueError(f"unexpected read response: {frame.hex()}")
    byte_count = frame[2]
    end = 3 + byte_count
    if len(frame) < end + 2 or not check_crc(frame[:end + 2]):
        raise ValueError(f"bad read frame: {frame.hex()}")
    return frame[3:end]


def parse_charge_switch(frame: bytes) -> bool:
    """Decode a charge-switch state read: True = on (register non-zero)."""
    data = _read_data(frame)
    if len(data) < 2:
        raise ValueError(f"short charge-switch response: {frame.hex()}")
    return ((data[0] << 8) | data[1]) != 0


def is_write_ack(frame: bytes, command: bytes) -> bool:
    """True only if *frame* confirms our exact 0x06 write of 0xDF00.

    A valid Modbus write response echoes the request (address, function,
    register, value). We require that echo to match the command we sent, so a
    malformed, error (function | 0x80), or mismatched response is rejected.
    """
    if len(frame) < 8 or len(command) < 6:
        return False
    if frame[1] != FUNC_WRITE_SINGLE:
        return False
    if not check_crc(frame):
        return False
    return frame[:6] == command[:6]
