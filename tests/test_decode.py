"""Controller real-time decode tests using synthetic Modbus frames."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from srne_ble.crc import append_crc  # noqa: E402
from srne_ble.controller import REALTIME_COUNT, REALTIME_START, parse_realtime  # noqa: E402


def build_frame(regs: dict) -> bytes:
    """Build a controller real-time reply frame from {address: word}."""
    data = bytearray()
    for i in range(REALTIME_COUNT):
        word = regs.get(REALTIME_START + i, 0)
        data += bytes([(word >> 8) & 0xFF, word & 0xFF])
    body = bytes([0xFF, 0x03, len(data)]) + bytes(data)
    return append_crc(body)


BASE = {
    0x0100: 100,      # SOC %
    0x0101: 135,      # 13.5 V
    0x0102: 520,      # 5.20 A
    0x0103: 0x1914,   # controller 25 C, battery 20 C
    0x0104: 134,      # load 13.4 V
    0x0105: 150,      # load 1.50 A
    0x0106: 20,       # load 20 W
    0x0107: 182,      # PV 18.2 V
    0x0108: 310,      # PV 3.10 A
    0x0109: 70,       # charge 70 W
    0x010A: 1,        # load ON
    0x0120: 0x0602,   # load status 0x06, charge state 0x02 (mppt)
}


def test_decode_basic_values():
    d = parse_realtime(build_frame(BASE))
    assert d.battery_soc == 100
    assert d.battery_voltage == 13.5
    assert d.charging_current == 5.20
    assert d.controller_temperature == 25
    assert d.battery_temperature == 20
    assert d.load_voltage == 13.4
    assert d.load_current == 1.50
    assert d.load_power == 20
    assert d.pv_voltage == 18.2
    assert d.pv_current == 3.10
    assert d.charging_power == 70
    assert d.load_enabled is True
    assert d.charging_state == "mppt"
    assert d.charging_state_code == 0x02
    assert d.faults == []


def test_negative_battery_temperature():
    regs = dict(BASE)
    regs[0x0103] = 0x19FB  # controller 25 C, battery -5 C (two's complement)
    d = parse_realtime(build_frame(regs))
    assert d.controller_temperature == 25
    assert d.battery_temperature == -5


def test_fault_bits():
    regs = dict(BASE)
    regs[0x0121] = 0x0400          # bit 10 -> BMS overcharge protection
    regs[0x0122] = 0x0010          # fault_value bit 20 -> load overcurrent
    d = parse_realtime(build_frame(regs))
    assert "BMS overcharge protection" in d.faults
    assert "load overcurrent" in d.faults
    assert d.fault_value == (0x0010 << 16) | 0x0400


def test_crc_rejected():
    frame = bytearray(build_frame(BASE))
    frame[-1] ^= 0xFF
    try:
        parse_realtime(bytes(frame))
    except ValueError as exc:
        assert "CRC" in str(exc)
    else:
        raise AssertionError("expected CRC failure")


def test_summary_renders():
    d = parse_realtime(build_frame(BASE))
    text = d.summary()
    assert "Battery" in text and "Solar" in text
