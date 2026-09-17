"""Vendored copy of the pure (hardware-independent) srne_ble decode logic.

Kept in sync with the top-level ``srne_ble`` package. Only the modules that do
NOT depend on ``bleak`` are vendored here (crc, protocol, controller,
discovery); the Home Assistant integration provides its own BLE transport via
``device.py`` using HA's Bluetooth stack.
"""
