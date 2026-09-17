"""Low-level SRNE BLE protocol constants and Modbus frame helpers.

See ``PROTOCOL.md`` for the protocol specification.

Transport summary
-----------------
The device (a BLE-to-serial bridge in the charge controller / BT module) speaks
**Modbus RTU wrapped in raw BLE GATT writes/notifications**:

* Write service      ``0000FFD0-0000-1000-8000-00805F9B34FB``
* Write characteristic ``0000FFD1-0000-1000-8000-00805F9B34FB``  (Write No Response)
* Notify service     ``0000FFF0-0000-1000-8000-00805F9B34FB``
* Notify characteristic ``0000FFF1-0000-1000-8000-00805F9B34FB`` (Notify)

A complete Modbus RTU request (slave address ``0xFF``, function ``0x03`` = Read
Holding Registers, CRC appended low-byte-first) is written to FFD1, and the
reply is delivered as one or more notifications on FFF1 that must be reassembled
into a single Modbus frame before the CRC is checked.
"""

from __future__ import annotations

from .crc import append_crc

# --- GATT UUIDs ------------------------------------------------------------
WRITE_SERVICE_UUID = "0000ffd0-0000-1000-8000-00805f9b34fb"
WRITE_CHAR_UUID = "0000ffd1-0000-1000-8000-00805f9b34fb"
NOTIFY_SERVICE_UUID = "0000fff0-0000-1000-8000-00805f9b34fb"
NOTIFY_CHAR_UUID = "0000fff1-0000-1000-8000-00805f9b34fb"

# Every device is addressed with the Modbus broadcast/wildcard slave id.
DEFAULT_SLAVE_ID = 0xFF

# Modbus function codes.
FUNC_READ_HOLDING = 0x03
FUNC_WRITE_SINGLE = 0x06


def build_read_holding(start_address: int, count: int, slave: int = DEFAULT_SLAVE_ID) -> bytes:
    """Build a Modbus RTU "Read Holding Registers" request frame.

    Example: ``build_read_holding(0x0100, 0x23)`` -> ``ff 03 01 00 00 23 10 31``
    (the controller real-time command).
    """
    payload = bytes(
        [
            slave & 0xFF,
            FUNC_READ_HOLDING,
            (start_address >> 8) & 0xFF,
            start_address & 0xFF,
            (count >> 8) & 0xFF,
            count & 0xFF,
        ]
    )
    return append_crc(payload)


def build_write_single(address: int, value: int, slave: int = DEFAULT_SLAVE_ID) -> bytes:
    """Build a Modbus RTU "Write Single Register" request frame (function 0x06)."""
    payload = bytes(
        [
            slave & 0xFF,
            FUNC_WRITE_SINGLE,
            (address >> 8) & 0xFF,
            address & 0xFF,
            (value >> 8) & 0xFF,
            value & 0xFF,
        ]
    )
    return append_crc(payload)


def expected_response_length(request: bytes) -> int:
    """Best-effort expected total byte length of the reply to *request*.

    Used by the notification reassembler so we know when a full frame has
    arrived. For Read Holding Registers the reply is:
        slave(1) + func(1) + byte_count(1) + data(byte_count) + crc(2)
    where ``byte_count == 2 * register_count``.
    """
    if len(request) < 6:
        raise ValueError("request too short")
    func = request[1]
    if func == FUNC_READ_HOLDING:
        count = (request[4] << 8) | request[5]
        return 3 + 2 * count + 2
    if func == FUNC_WRITE_SINGLE:
        # echo of the request
        return 8
    # Unknown: caller should fall back to a timeout.
    return 0
