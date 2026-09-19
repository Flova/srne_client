# SRNE Solar Controller (BLE) — Home Assistant integration

A local-polling Home Assistant integration for SRNE MPPT solar charge
controllers (e.g. the MC2430) over Bluetooth LE. It uses Home Assistant's own
Bluetooth stack, so it works with a Raspberry Pi's built-in adapter or any
supported ESPHome Bluetooth proxy.

See [`../../PROTOCOL.md`](../../PROTOCOL.md) for the protocol specification.

## Requirements

- Home Assistant **2024.8** or newer.
- A working Bluetooth adapter (the HA *Bluetooth* integration set up), **or** a
  Bluetooth proxy in range of the controller.
- The SRNE **phone app must be disconnected** — BLE allows only one connection
  at a time.

## Install

### Via HACS (custom repository)
1. HACS → ⋮ → *Custom repositories* → add `https://github.com/Flova/srne_client`
   as an **Integration**.
2. Install "SRNE Solar Controller (BLE)", then restart Home Assistant.

### Manually
Copy `custom_components/srne_ble/` into your HA config's `custom_components/`
directory and restart.

## Setup

Your controller is usually **auto-discovered** (HA shows a "SRNE …" discovered
device). Otherwise: *Settings → Devices & Services → Add Integration → SRNE
Solar Controller (BLE)* and pick it from the list.

The polling interval defaults to 30 s and can be changed in the integration's
*Configure* (options) dialog.

## Entities

| Entity | Register | Notes |
|--------|----------|-------|
| Battery charge (%) | 0x0100 | |
| Battery voltage (V) | 0x0101 | |
| Charging current (A) | 0x0102 | |
| Charging power (W) | 0x0109 | |
| Solar voltage (V) | 0x0107 | |
| Solar current (A) | 0x0108 | |
| Solar power (W) | derived | V × A |
| Load voltage / current / power | 0x0104–0x0106 | disabled by default |
| Controller temperature (°C) | 0x0103 hi | |
| Battery temperature (°C) | 0x0103 lo | |
| Charging state | 0x0120 | enum: not charging / mppt / boost / … |
| Charging active (binary) | derived | on when actively charging |
| Load output (binary) | 0x010A | |
| Fault (binary, problem) | 0x0121/0x0122 | `faults` attribute lists active faults |
| **Charging (switch)** | 0xDF00 | write control — see below |
| **Connection (switch)** | — | release/hold the BLE link — see below |

## Charging switch (write control)

The **Charging** switch turns the controller's charge/discharge switch on and
off (register `0xDF00`). This is the only write the integration performs, and it
is deliberately narrow:

- It writes *only* register `0xDF00` with value `1` (on) or `0` (off) — no other
  register can be written.
- Every change is confirmed twice before the switch reports success: the
  device's write acknowledgement is checked, and the register is read back and
  must match. If either check fails, Home Assistant surfaces an error and the
  switch keeps its previous state.

The switch state is read **on load and after each toggle** — not during the
background poll — so polling stays lightweight. It therefore also reflects a
change you make from the phone app the next time the integration reads it
(on reload, or after you toggle the switch).

## Bluetooth connection & using the phone app

The integration keeps a **persistent** BLE connection and reuses it across polls
(no reconnect each cycle), which stays fast with several devices or a high
polling rate.

BLE allows only one connection at a time, so to use the phone app, turn the
**Connection** switch **off**: Home Assistant disconnects and pauses polling,
freeing the controller. Turn it back **on** to reconnect and resume. (Disabling
the whole integration also releases the device.)

## Troubleshooting

- **Not discovered / "not found by any Bluetooth adapter"**: close the phone
  app, confirm the controller is in Bluetooth range, and that HA's Bluetooth
  integration is running. A USB BLE dongle or an ESPHome BT proxy near the
  controller helps a lot.
- **Frequent "no complete reply" errors**: the module is at the edge of range or
  contended. Increase the polling interval and improve signal.
- **"Characteristic … was not found" on setup**: the device's GATT wasn't ready
  (or the module needs pairing). Enable debug logging for
  `custom_components.srne_ble` — the log prints the full GATT table and the
  characteristics the device exposes.

## Per-device identification

On setup the integration reads each module's **identity block** (device type,
model, firmware version) and only proceeds if the module reports a **controller**
type — so a different device family (inverter, lithium battery, …) fails with a
clear message instead of being mis-decoded. The model and software/hardware
versions are shown on the HA device page. Each module is checked individually,
so mixing devices or firmware versions is handled per device.

## Scope

Covers the MPPT controller real-time block. History/energy totals, parameter
writes, and other device families are on the roadmap (commands are documented in
`PROTOCOL.md`).
