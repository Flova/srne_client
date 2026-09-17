"""srne_ble - a small Python library to talk to SRNE solar controllers over BLE.

See ``PROTOCOL.md`` for the protocol specification.
"""

from .controller import ControllerData, parse_realtime, realtime_request
from .discovery import (
    DEFAULT_FILTER_LIST,
    DEVICE_TYPE_NAMES,
    DiscoveredDevice,
    device_type_name,
    identify,
    name_matches,
    parse_ble_advdata,
)
from .protocol import (
    NOTIFY_CHAR_UUID,
    NOTIFY_SERVICE_UUID,
    WRITE_CHAR_UUID,
    WRITE_SERVICE_UUID,
    build_read_holding,
    build_write_single,
)

__all__ = [
    "ControllerData",
    "parse_realtime",
    "realtime_request",
    "DiscoveredDevice",
    "identify",
    "name_matches",
    "parse_ble_advdata",
    "device_type_name",
    "DEFAULT_FILTER_LIST",
    "DEVICE_TYPE_NAMES",
    "build_read_holding",
    "build_write_single",
    "WRITE_SERVICE_UUID",
    "WRITE_CHAR_UUID",
    "NOTIFY_SERVICE_UUID",
    "NOTIFY_CHAR_UUID",
]

# `client` (SRNEBLEClient / scan) is intentionally NOT imported here so that the
# offline decoding logic can be used without `bleak` installed. Import it via
# `from srne_ble.client import SRNEBLEClient, scan`.

__version__ = "0.1.0"
