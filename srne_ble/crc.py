"""Modbus RTU CRC-16 helpers.

Standard Modbus CRC-16 (polynomial 0xA001, init 0xFFFF). The two CRC bytes are
appended to a frame low-byte-first, as Modbus RTU requires (LSB, then MSB).
"""

from __future__ import annotations

# 0xA001 == 40961 is the reversed (LSB-first) Modbus polynomial.
_POLY = 0xA001


def crc16(data: bytes) -> int:
    """Return the 16-bit Modbus CRC of *data* as an integer."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ _POLY
            else:
                crc >>= 1
    return crc & 0xFFFF


def crc16_bytes(data: bytes) -> bytes:
    """Return the CRC of *data* as 2 bytes in Modbus append order (LSB, MSB)."""
    crc = crc16(data)
    return bytes([crc & 0xFF, (crc >> 8) & 0xFF])


def append_crc(payload: bytes) -> bytes:
    """Append the Modbus CRC to *payload* and return the full frame."""
    return payload + crc16_bytes(payload)


def check_crc(frame: bytes) -> bool:
    """Return True if the trailing 2 bytes of *frame* are a valid CRC."""
    if len(frame) < 3:
        return False
    body, crc = frame[:-2], frame[-2:]
    return crc16_bytes(body) == crc
