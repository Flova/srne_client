"""Tests for app-faithful device discovery / identification (no hardware)."""

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from srne_ble.discovery import (  # noqa: E402
    device_type_name,
    identify,
    name_matches,
    parse_ble_advdata,
    type_code_from_name,
)


def test_name_filter_matches_app_list():
    assert name_matches("BT-TH-161949")        # "BT-"
    assert name_matches("RNGRBP...")            # "RNG"
    assert name_matches("SRNE-XYZ")             # "SR"
    assert name_matches("BAT123")               # "BAT"
    assert not name_matches("MyHeadphones")
    assert not name_matches(None)


def test_type_code_from_name():
    assert type_code_from_name("BT00-1A2B3C") == "00"
    assert type_code_from_name("BT20-DEADBEEF") == "20"
    assert type_code_from_name("randomname") is None


def test_device_type_names():
    assert device_type_name("00") == "Controller"
    assert device_type_name("20") == "Inverter"
    assert device_type_name("40") == "Lithium battery"
    assert device_type_name("52") == "Shunt"
    assert device_type_name(None) == "Controller"     # app default


def test_parse_advdata_p_marker():
    # ASCII "P00MC2430;..." -> type 00, model MC2430
    payload = b"P00MC2430;extra"
    info = parse_ble_advdata(payload.hex())
    assert info["type"] == "00"
    assert info["devicespe"] == "MC2430"


def test_identify_from_manufacturer_data():
    # Reconstruct how bleak exposes it: first 2 bytes -> company id (LE), rest value
    payload = b"P00MC2430;"
    company_id = struct.unpack("<H", payload[:2])[0]
    manufacturer_data = {company_id: payload[2:]}
    dev = identify("AA:BB:CC:DD:EE:FF", "BT-TH-161949", -57, manufacturer_data)
    assert dev.type_code == "00"
    assert dev.type_name == "Controller"
    assert dev.model == "MC2430"
    assert "AA:BB:CC:DD:EE:FF" in dev.describe()
    assert "Controller" in dev.describe()


def test_identify_falls_back_to_name_code():
    dev = identify("11:22:33:44:55:66", "BT20-0A1B2C", -70, None)
    assert dev.type_code == "20"
    assert dev.type_name == "Inverter"
