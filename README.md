# srne_client

Talk to an **SRNE solar charge controller** (e.g. the MC2430 MPPT series) over
**Bluetooth LE** from Python, with a Home Assistant integration for a Raspberry
Pi.

The protocol is **Modbus RTU wrapped in BLE GATT writes/notifications**. See
[`PROTOCOL.md`](PROTOCOL.md) for the full specification.

## What's here

```
custom_components/   Home Assistant integration (srne_ble) - see its README
srne_ble/            the library
  crc.py             Modbus CRC-16
  protocol.py        GATT UUIDs + Modbus frame builders
  controller.py      controller real-time register map + decoder -> ControllerData
  discovery.py       device discovery (name filter + type/model)
  client.py          async BLE transport (bleak) - scan / connect / request
scan.py              simple scanner: lists names, models & device types
mvp.py               runnable CLI: scan, read, poll
tools/decode_frame.py  decode a captured hex frame offline (no hardware)
tests/               CRC + decode + discovery unit tests (pytest, no hardware)
```

## Install

On the Raspberry Pi (Linux + BlueZ):

```bash
python3 -m pip install -r requirements.txt   # installs bleak
```

The decoding/CRC logic has **no dependencies** and can run anywhere; only the
live BLE transport needs `bleak`.

## Find your device

`scan.py` lists nearby devices — it keeps only devices whose name matches the
SRNE name filter (`BT-`, `BAT`, `OCS`, `SR`, `RNG`, `?`) and reads the **device
type and model out of the BLE advertisement**:

```bash
python3 scan.py                 # SRNE-only
python3 scan.py --all           # every BLE device, no filter
python3 scan.py --timeout 15    # scan longer
python3 scan.py --json          # machine-readable
```

```
Found 1 device(s)  [strongest signal first]:

  ADDRESS                RSSI   NAME                  DEVICE
  -----------------  --------   --------------------  ------------------------
  AA:BB:CC:DD:EE:FF   -57 dBm   BT-TH-161949          Controller / MC2430
```

The left column is the address you pass to `mvp.py read --address ...`. If your
device doesn't show up, close the phone app first — BLE allows only one
connection at a time.

## Quick start (the MVP)

```bash
# 1. Find your controller's BLE address (or use scan.py above)
python3 mvp.py scan

# 2. Read the live data once
python3 mvp.py read --address AA:BB:CC:DD:EE:FF

# 3. Continuously poll every 5 s
python3 mvp.py poll --address AA:BB:CC:DD:EE:FF --interval 5

# 4. First-connection sanity check — dump every raw register too
python3 mvp.py read --address AA:BB:CC:DD:EE:FF --raw
```

Example output:

```
Battery    :  13.5 V    98 %   +20 C
Charging   :  5.20 A     70 W   (mppt)
Solar (PV) :  18.2 V    3.10 A
Load       :  13.4 V    1.50 A     20 W   ON
Controller : +25 C
```

## Use as a library

```python
import asyncio
from srne_ble.client import SRNEBLEClient

async def main():
    async with SRNEBLEClient("AA:BB:CC:DD:EE:FF") as dev:
        data = await dev.read_controller()
        print(data.battery_voltage, data.charging_power)
        print(data.summary())

asyncio.run(main())
```

`ControllerData` exposes typed fields (`battery_soc`, `battery_voltage`,
`charging_current`, `pv_voltage`, `pv_current`, `charging_power`, `load_*`,
`controller_temperature`, `battery_temperature`, `charging_state`, `faults`, and
the raw `registers` dict).

## Testing without hardware

```bash
python3 -m pytest -q                       # unit tests
python3 tools/decode_frame.py ff0346...<crc>   # decode a captured frame
```

## Development: shared code & the HA component

The pure logic (`crc`, `protocol`, `controller`, `discovery`, `identify`) lives
once in `srne_ble/`. The Home Assistant component must be self-contained, so
those modules are **vendored** into `custom_components/srne_ble/srne/` by a
script — edit the originals, then run:

```bash
python3 scripts/sync_vendored.py     # refresh the vendored copy
```

`tests/test_vendored_sync.py` fails the test suite if the copy ever drifts, so
the duplication can't silently rot.

## Home Assistant integration

A ready-to-use custom integration lives in
[`custom_components/srne_ble/`](custom_components/srne_ble/README.md). It uses
Home Assistant's own Bluetooth stack (works with a Pi's adapter or an ESPHome BT
proxy), auto-discovers the controller, and exposes battery / solar / load /
temperature / charge-state sensors via a `DataUpdateCoordinator`. Install it
through HACS as a custom repository, or copy the folder into your HA
`custom_components/`.

## Roadmap

The realtime block is covered end to end (library, MVP, and HA integration).
Natural next steps:

1. History & cumulative-total registers (commands listed in `PROTOCOL.md`) —
   enables the HA energy dashboard (cumulative kWh).
2. Parameter reads/writes (load switch, charge settings) via function `0x06`.
3. Support other device families (inverters, BMS) — same transport, different
   command tables.

## Notes

Interoperability tooling for talking to your own SRNE device. Not affiliated
with SRNE. Validate the first live read with `--raw` before trusting derived
values.
