"""Decode SRNE MPPT charge-controller real-time data.

The controller (device type ``00``, e.g. the MC24xx / ML series) is polled with
a single Modbus read of 35 holding registers starting at ``0x0100``:

    FF 03 01 00 00 23  + CRC   ==  build_read_holding(0x0100, 0x23)

The register map, scaling factors and fault-bit table are specified in
``PROTOCOL.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .crc import check_crc
from .protocol import build_read_holding

# The real-time poll for a controller (device type "00").
REALTIME_START = 0x0100
REALTIME_COUNT = 0x0023  # 35 registers -> 70 data bytes


def realtime_request() -> bytes:
    """Return the raw bytes of the controller real-time read command."""
    return build_read_holding(REALTIME_START, REALTIME_COUNT)


# Charging state, low byte of register 0x0120.
CHARGE_STATE = {
    0: "not charging",
    1: "activated",
    2: "mppt",
    3: "equalizing",
    4: "boost",
    5: "floating",
    6: "current limiting",
}

# Fault / warning bits of the combined 32-bit value (reg 0x0122 << 16 | 0x0121).
FAULT_BITS = {
    30: "charging MOS short circuit",
    29: "reverse MOS short circuit",
    28: "solar panels reverse connection",
    27: "solar panels working point overvoltage",
    26: "solar panels countercurrent",
    25: "overvoltage at photovoltaic input end",
    24: "short circuit at photovoltaic input end",
    23: "excessive photovoltaic input power",
    22: "battery temperature too high",
    21: "controller temperature too high",
    20: "load overcurrent",
    19: "load short circuit",
    18: "battery under-voltage warning",
    17: "battery overvoltage",
    16: "battery over-discharge",
    15: "load open circuit",
    14: "temperature sensing probe damaged",
    13: "capacitor overvoltage",
    12: "reverse battery connection",
    11: "battery low-temperature protection (charging stopped)",
    10: "BMS overcharge protection",
}


def _signed_byte(value: int) -> int:
    """8-bit two's-complement signed value."""
    return value - 256 if value > 127 else value


def decode_faults(fault_value: int) -> List[str]:
    """Return the list of active fault/warning descriptions for *fault_value*."""
    return [name for bit, name in FAULT_BITS.items() if fault_value & (1 << bit)]


@dataclass
class ControllerData:
    """Decoded controller real-time snapshot. Units: V, A, W, degrees C, %."""

    battery_soc: int                      # 0x0100  %
    battery_voltage: float                # 0x0101  V
    charging_current: float               # 0x0102  A
    controller_temperature: int           # 0x0103 hi byte  degrees C
    battery_temperature: int              # 0x0103 lo byte  degrees C
    load_voltage: float                   # 0x0104  V
    load_current: float                   # 0x0105  A
    load_power: int                       # 0x0106  W
    pv_voltage: float                     # 0x0107  V
    pv_current: float                     # 0x0108  A
    charging_power: int                   # 0x0109  W
    load_enabled: bool                    # 0x010A  on/off command
    charging_state: str                   # 0x0120 lo byte
    charging_state_code: int              # raw
    load_status_raw: int                  # 0x0120 hi byte
    faults: List[str] = field(default_factory=list)   # 0x0121/0x0122
    fault_value: int = 0                  # combined 32-bit fault register value
    registers: Dict[int, int] = field(default_factory=dict)  # addr -> raw word

    def summary(self) -> str:
        lines = [
            f"Battery    : {self.battery_voltage:5.1f} V   {self.battery_soc:3d} %"
            f"   {self.battery_temperature:+d} C",
            f"Charging   : {self.charging_current:5.2f} A   {self.charging_power:4d} W"
            f"   ({self.charging_state})",
            f"Solar (PV) : {self.pv_voltage:5.1f} V   {self.pv_current:5.2f} A",
            f"Load       : {self.load_voltage:5.1f} V   {self.load_current:5.2f} A"
            f"   {self.load_power:4d} W   {'ON' if self.load_enabled else 'OFF'}",
            f"Controller : {self.controller_temperature:+d} C",
        ]
        if self.faults:
            lines.append("Faults     : " + ", ".join(self.faults))
        return "\n".join(lines)


def _registers_from_frame(frame: bytes) -> Dict[int, int]:
    """Validate a Read-Holding response *frame* and return {address: word}."""
    if len(frame) < 5:
        raise ValueError(f"frame too short: {frame.hex()}")
    if frame[1] & 0x80:
        raise ValueError(f"modbus exception response: {frame.hex()}")
    if frame[1] != 0x03:
        raise ValueError(f"unexpected function code 0x{frame[1]:02x}")
    byte_count = frame[2]
    data = frame[3:3 + byte_count]
    if len(data) != byte_count:
        raise ValueError(
            f"truncated frame: got {len(data)} data bytes, expected {byte_count}"
        )
    if not check_crc(frame[:3 + byte_count + 2]):
        raise ValueError(f"CRC check failed: {frame.hex()}")
    words = {}
    for i in range(byte_count // 2):
        addr = REALTIME_START + i
        words[addr] = (data[2 * i] << 8) | data[2 * i + 1]
    return words


def parse_realtime(frame: bytes) -> ControllerData:
    """Parse a full controller real-time response frame into ``ControllerData``.

    *frame* is the reassembled Modbus reply to :func:`realtime_request`
    (``ff 03 46 ...``), including the trailing CRC.
    """
    r = _registers_from_frame(frame)

    def word(addr: int, default: Optional[int] = None) -> int:
        if addr not in r:
            if default is not None:
                return default
            raise ValueError(f"register 0x{addr:04x} missing from response")
        return r[addr]

    temp_word = word(0x0103)
    status_word = word(0x0120, 0)
    fault_value = (word(0x0122, 0) << 16) | word(0x0121, 0)

    return ControllerData(
        battery_soc=word(0x0100),
        battery_voltage=word(0x0101) / 10.0,
        charging_current=word(0x0102) / 100.0,
        controller_temperature=_signed_byte(temp_word >> 8),
        battery_temperature=_signed_byte(temp_word & 0xFF),
        load_voltage=word(0x0104) / 10.0,
        load_current=word(0x0105) / 100.0,
        load_power=word(0x0106),
        pv_voltage=word(0x0107) / 10.0,
        pv_current=word(0x0108) / 100.0,
        charging_power=word(0x0109),
        load_enabled=bool(word(0x010A, 0)),
        charging_state=CHARGE_STATE.get(status_word & 0xFF, f"unknown(0x{status_word & 0xFF:02x})"),
        charging_state_code=status_word & 0xFF,
        load_status_raw=status_word >> 8,
        faults=decode_faults(fault_value),
        fault_value=fault_value,
        registers=r,
    )
