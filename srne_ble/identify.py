"""Read and decode an SRNE device's identity (type / model / firmware).

Identity fields are read with small, targeted commands (each fits in a single
notification), rather than one large block:

    Device type          FF03 000B 0001   -> type code (low byte)
    Device specification FF03 000C 0008   -> product spec / model (ASCII)
    Software version     FF03 0014 0002   -> V{b1}.{b2}.{b3}
    Hardware version     FF03 0016 0002   -> V{b1}.{b2}.{b3}

Only the type read is required (it gates whether we treat the device as a
controller); model/version are best-effort.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from .crc import check_crc
from .discovery import device_type_name
from .protocol import build_read_holding

# Small, targeted identity commands.
CMD_DEVICE_TYPE = build_read_holding(0x000B, 0x0001)
CMD_DEVICE_SPEC = build_read_holding(0x000C, 0x0008)
CMD_SW_VERSION = build_read_holding(0x0014, 0x0002)
CMD_HW_VERSION = build_read_holding(0x0016, 0x0002)

# Device type codes we can decode as an MPPT charge controller.
CONTROLLER_TYPE_CODES = ("00", "01")

Request = Callable[[bytes], Awaitable[bytes]]


@dataclass
class DeviceIdentity:
    """Decoded device identity."""

    type_code: str            # e.g. "00"
    type_name: str            # e.g. "Controller"
    model: str = ""           # product spec, e.g. "MC2430N10"
    software_version: str = ""
    hardware_version: str = ""

    @property
    def is_controller(self) -> bool:
        return self.type_code in CONTROLLER_TYPE_CODES


def _response_data(frame: bytes) -> bytes:
    """Validate a Read-Holding response frame and return its data bytes."""
    if len(frame) < 5 or frame[1] & 0x80 or frame[1] != 0x03:
        raise ValueError(f"unexpected response: {frame.hex()}")
    byte_count = frame[2]
    end = 3 + byte_count
    if len(frame) < end + 2 or not check_crc(frame[:end + 2]):
        raise ValueError(f"bad frame: {frame.hex()}")
    return frame[3:end]


def parse_type(frame: bytes) -> str:
    """Type code = low byte of register 0x000B."""
    data = _response_data(frame)
    return f"{data[1]:02x}" if len(data) >= 2 else ""


def parse_spec(frame: bytes) -> str:
    """Model / product spec (ASCII), NUL/space stripped."""
    data = _response_data(frame)
    return data.decode("latin-1", "ignore").replace("\x00", "").strip()


def parse_version(frame: bytes) -> str:
    """Format a 2-register version block as V{b1}.{b2}.{b3}."""
    data = _response_data(frame)
    if len(data) < 4:
        return ""
    return f"V{data[1]}.{data[2]}.{data[3]}"


async def read_identity(request: Request) -> DeviceIdentity:
    """Read the identity via small commands using an async *request* callable.

    *request* sends a Modbus frame and returns the reassembled reply. Only the
    device-type read is required; model and versions are best-effort so a device
    that doesn't answer them still identifies.
    """
    type_code = parse_type(await request(CMD_DEVICE_TYPE))
    identity = DeviceIdentity(type_code=type_code, type_name=device_type_name(type_code))
    for cmd, attr, parse in (
        (CMD_DEVICE_SPEC, "model", parse_spec),
        (CMD_SW_VERSION, "software_version", parse_version),
        (CMD_HW_VERSION, "hardware_version", parse_version),
    ):
        try:
            setattr(identity, attr, parse(await request(cmd)))
        except Exception:  # noqa: BLE001 - optional field, ignore failures
            pass
    return identity
