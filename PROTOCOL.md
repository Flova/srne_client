# SRNE BLE protocol specification

This documents the Bluetooth Low Energy (BLE) protocol used to talk to SRNE
solar charge controllers (e.g. the **MC2430** MPPT series) over the built-in
Bluetooth module or an SRNE BT dongle.

## Transport: Modbus RTU over raw GATT

The device exposes a Nordic-UART-style pair of vendor services. A **complete
Modbus RTU frame** is written to the write characteristic, and the reply is
delivered as notifications on the notify characteristic.

| Role   | Service UUID | Characteristic UUID | Property |
|--------|--------------|---------------------|----------|
| Write  | `0000FFD0-0000-1000-8000-00805F9B34FB` | `0000FFD1-0000-1000-8000-00805F9B34FB` | Write **No Response** |
| Notify | `0000FFF0-0000-1000-8000-00805F9B34FB` | `0000FFF1-0000-1000-8000-00805F9B34FB` | Notify |

The client subscribes to notifications on `FFF1`, writes the framed command to
`FFD1` (write-without-response), then reassembles the notification chunks
(~20 bytes each) into one Modbus frame before checking the CRC.

## Modbus framing

* **Slave address**: `0xFF` (broadcast/wildcard) for every request.
* **Function**: `0x03` Read Holding Registers (reads); `0x06` Write Single Register.
* **CRC-16/Modbus**: polynomial `0xA001`, init `0xFFFF`, appended **low byte first**.

A read request is:

```
FF 03 <addr_hi> <addr_lo> <count_hi> <count_lo> <crc_lo> <crc_hi>
```

Example — the controller real-time read (`build_read_holding(0x0100, 0x23)`):

```
FF 03 01 00 00 23 10 31
```

## Discovery & device identification

Devices are found in two steps:

1. **Name filter** — a discovered device is kept only if its (local) name
   contains one of the substrings `BT-`, `BAT`, `OCS`, `SR`, `RNG`, `?`.
   Names are null-stripped and trimmed.

2. **Advertisement decode** — the device encodes an ASCII string in its BLE
   manufacturer-specific advertisement data:

   * `P<tt><model>;...` → `type = tt` (2-char type code), `model = <model>`
     (e.g. `P00MC2430;` → type `00`, model `MC2430`).
   * `Q...` → a user-set custom name.

   Names like `BT<tt>-XXXX` also embed the type code (`/BT([0-9A-F]{2})-/`).

The type code maps to a device family: `00`/`01` Controller, `03`/`04`/`05`/
`20`/`22`/`23`/`24` Inverter, `06` Battery protector, `31`/`34`/`35` DC charger,
`32`/`36`/`38` DC-DC charger, `39` DC-DC converter, `33` AC-DC charger, `40`/
`42`/`43` Lithium battery, `52` Shunt, `62`/`63`/`66`/`70` Master, `6a` DB
(default Controller). Implemented in `srne_ble/discovery.py`, surfaced by
`scan.py`.

## Device identity handshake

To identify a device individually before choosing a parser, read the identity
fields with **small, targeted commands** (each reply fits in a single BLE
notification):

| Command | Register | Field |
|---------|----------|-------|
| `FF03 000B 0001` | `0x000B` (low byte) | device type code |
| `FF03 000C 0008` | `0x000C` ×8 | product spec / model (ASCII), e.g. `MC2430N10` |
| `FF03 0014 0002` | `0x0014` ×2 | software version → `V{b1}.{b2}.{b3}` |
| `FF03 0016 0002` | `0x0016` ×2 | hardware version |

Implemented in `srne_ble/identify.py`. The type read is required (it decides
whether to treat the device as a controller); model/version are best-effort.
Identity is advisory — if the read fails, the integration logs it and proceeds
(the real-time poll is the reachability gate) rather than blocking.

## Controller real-time data (device type `00`)

An MPPT charge controller is polled with a single read of **35 holding
registers from `0x0100`** (`FF03 0100 0023`). Reply layout:
`FF 03 46 <70 data bytes> <crc>` (`0x46` = 70 = 35×2).

| Register | Field | Scale | Unit | Notes |
|----------|-------|-------|------|-------|
| `0x0100` | Battery SOC | ×1 | % | |
| `0x0101` | Battery voltage | ÷10 | V | |
| `0x0102` | Charging current | ÷100 | A | |
| `0x0103` | Controller temp (hi byte) + Battery temp (lo byte) | signed 8-bit each | °C | two's-complement |
| `0x0104` | DC load voltage | ÷10 | V | |
| `0x0105` | DC load current | ÷100 | A | |
| `0x0106` | DC load power | ×1 | W | |
| `0x0107` | Solar (PV) voltage | ÷10 | V | |
| `0x0108` | Solar (PV) current | ÷100 | A | |
| `0x0109` | Charging power | ×1 | W | |
| `0x010A` | DC load on/off command | ×1 | — | |
| `0x0120` | Load status (hi byte) + charging state (lo byte) | — | — | see below |
| `0x0121`–`0x0122` | Fault / warning bitmask (32-bit) | — | — | see below |

### Charging state (`0x0120` low byte)

`0` not charging, `1` activated, `2` MPPT, `3` equalizing, `4` boost,
`5` floating, `6` current-limiting.

### Fault / warning bits (`0x0121` + `0x0122`)

Combine as `(reg0x0122 << 16) | reg0x0121`; each set bit names a fault. The full
table is in `srne_ble/controller.py` (`FAULT_BITS`) — e.g. bit 30 = "charging
MOS short circuit", bit 20 = "load overcurrent", bit 16 = "battery
over-discharge".

## Other commands (not yet implemented)

For future expansion (history / totals / parameter writes):

* `FF03F00000 0A` … `FF03F006 000A` — 7-day history blocks.
* `FF0301320026` — multi-string MPPT data.
* `FF03012000 03` — cumulative totals (running days, total Wh in/out, …).
* `FF06DF00...` / `FF06E010...` — parameter writes (load switch, timers, etc.).

Other device families (inverters, DC chargers, lithium batteries, shunts, …)
use the same transport with different command sets and register maps.

## Notes

* Temperature uses two's-complement signed bytes (matters only for sub-zero
  readings; positive temperatures are unambiguous).
* Validate a first read on new hardware with `mvp.py read --raw`, which prints
  the raw frame and every decoded register.
