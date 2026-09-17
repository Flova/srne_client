"""Discover and identify SRNE devices from BLE advertisements.

Two steps:

1. **Name filter** - keep only advertised devices whose (local) name contains
   one of a small set of substrings (``DEFAULT_FILTER_LIST``): ``BT-``, ``BAT``,
   ``OCS``, ``SR``, ``RNG``, ``?``.

2. **Advertisement decode** - the device encodes an ASCII string in its BLE
   manufacturer-specific advertisement data, e.g. ``P00MC2430;...`` where ``P``
   is a marker, ``00`` is the device *type code* and ``MC2430`` is the *model
   spec*. The type code maps to a human name via ``DEVICE_TYPE_NAMES``.

All functions here are pure (no BLE), so they're unit-testable offline.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from typing import Dict, List, Optional

# Device-search name filter: keep names containing any of these.
DEFAULT_FILTER_LIST = ["BT-", "BAT", "OCS", "SR", "RNG", "?"]

# Device type code -> human name.
DEVICE_TYPE_NAMES = {
    "00": "Controller",
    "01": "Controller",
    "03": "Inverter",
    "04": "Inverter integrated machine",
    "05": "Inverter",
    "06": "Battery protector",
    "20": "Inverter",
    "22": "Inverter",
    "23": "Inverter",
    "24": "Inverter",
    "31": "DC charger",
    "32": "DC-DC charger",
    "33": "AC-DC Charger",
    "34": "DC charger",
    "35": "DC charger",
    "36": "DC-DC charger",
    "38": "DC-DC charger",
    "39": "DC-DC converter",
    "40": "Lithium battery",
    "42": "Lithium battery",
    "43": "Lithium battery",
    "52": "Shunt",
    "62": "Master",
    "63": "Master",
    "66": "Master",
    "70": "Master",
    "6a": "DB",
}

# Names like "BT02-1A2B3C" embed the type code as the two hex chars after "BT".
_BT_NAME_RE = re.compile(r"BT([0-9A-Fa-f]{2})-")


def device_type_name(type_code: Optional[str]) -> str:
    """Map a 2-char type code to a human name (defaults to 'Controller')."""
    if not type_code:
        return "Controller"
    return DEVICE_TYPE_NAMES.get(type_code.lower(), DEVICE_TYPE_NAMES.get(type_code, "Controller"))


def name_matches(name: Optional[str], filter_list: Optional[List[str]] = None) -> bool:
    """True if *name* contains any substring in *filter_list*."""
    if not name:
        return False
    for token in (filter_list if filter_list is not None else DEFAULT_FILTER_LIST):
        if token in name:
            return True
    return False


def type_code_from_name(name: Optional[str]) -> Optional[str]:
    """Extract the type code from a ``BT<XX>-...`` style name, if present."""
    if not name:
        return None
    m = _BT_NAME_RE.search(name)
    return m.group(1) if m else None


def parse_ble_advdata(advdata_hex: str) -> Dict[str, str]:
    """Decode the manufacturer advertisement payload.

    Returns ``{"type", "devicespe", "customername"}`` (any may be empty).
    *advdata_hex* is the manufacturer advertisement payload as a hex string.
    """
    out = {"type": "", "devicespe": "", "customername": ""}
    try:
        raw = bytes.fromhex(advdata_hex)
    except ValueError:
        return out
    if len(raw) <= 1:
        return out
    text = raw.decode("latin-1", "ignore")
    if len(text) > 2 and text[0] == "P":
        out["type"] = text[1:3]
        first = text.split(";")[0]
        out["devicespe"] = first[3:]
    elif len(text) > 3 and text[0] == "Q":
        # Custom name: bytes after the 3rd hex char.
        out["customername"] = bytes.fromhex(advdata_hex[3:]).decode("latin-1", "ignore")
    return out


def manufacturer_advdata_candidates(manufacturer_data: Dict[int, bytes]) -> List[str]:
    """Reconstruct ``advdata`` hex strings from bleak manufacturer data.

    bleak splits the 2-byte company id off as the dict key; the device packs
    ASCII across those bytes, so we rebuild ``le16(company_id) + value`` (and, as
    a fallback, the value alone) and let :func:`parse_ble_advdata` pick it up.
    """
    candidates: List[str] = []
    for company_id, value in manufacturer_data.items():
        candidates.append((struct.pack("<H", company_id & 0xFFFF) + value).hex())
        candidates.append(value.hex())
    return candidates


@dataclass
class DiscoveredDevice:
    """A discovered SRNE device with decoded identification."""

    address: str
    name: str
    rssi: Optional[int] = None
    type_code: Optional[str] = None
    type_name: str = "Controller"
    model: str = ""          # devicespe, e.g. "MC2430"
    custom_name: str = ""    # user-set name from advertisement, if any
    advdata: str = ""        # raw manufacturer advdata hex we decoded from

    def describe(self) -> str:
        label = self.type_name
        if self.model:
            label = f"{self.type_name} / {self.model}"
        rssi = f"{self.rssi:>4} dBm" if self.rssi is not None else "   ? dBm"
        name = self.custom_name or self.name or "(no name)"
        return f"{self.address}   {rssi}   {name:<20}  {label}"


def identify(address: str, name: Optional[str], rssi: Optional[int],
             manufacturer_data: Optional[Dict[int, bytes]] = None) -> DiscoveredDevice:
    """Build a :class:`DiscoveredDevice`, decoding type/model."""
    dev = DiscoveredDevice(address=address, name=(name or "").replace("\x00", "").strip(),
                           rssi=rssi)
    # Prefer the advertisement payload (has the model spec); fall back to name.
    for advdata in manufacturer_advdata_candidates(manufacturer_data or {}):
        info = parse_ble_advdata(advdata)
        if info["type"] or info["customername"]:
            dev.advdata = advdata
            if info["type"]:
                dev.type_code = info["type"]
                dev.type_name = device_type_name(info["type"])
                dev.model = info["devicespe"]
            if info["customername"]:
                dev.custom_name = info["customername"]
            break
    if dev.type_code is None:
        code = type_code_from_name(dev.name)
        if code:
            dev.type_code = code
            dev.type_name = device_type_name(code)
    return dev
