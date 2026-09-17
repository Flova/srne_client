"""Constants for the SRNE BLE integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "srne_ble"

# Config / options keys
CONF_SCAN_INTERVAL: Final = "scan_interval"

DEFAULT_SCAN_INTERVAL: Final = 30  # seconds
MIN_SCAN_INTERVAL: Final = 5

MANUFACTURER: Final = "SRNE"
