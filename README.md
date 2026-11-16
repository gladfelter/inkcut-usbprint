# inkcut-usbprint

An [Inkcut](https://github.com/inkcut/inkcut) transport for **USB printer-class
cutters that have no vendor driver and no print queue**.

Some desktop cutters enumerate as USB printer-class devices but leave Windows with
nothing to talk to: no driver installs, no COM port appears, and a print queue
accepts bytes and then fails to print them. The vendor's own application still
cuts, which proves the hardware is fine — it just talks to the USB interface
directly.

Inkcut's built-in transports cannot reach such a machine:

| Transport | Why it fails |
|---|---|
| **Printer** | there is no print queue to attach to |
| **Serial Port** | there is no COM port |
| **Raw device descriptor** | needs a path to a character device |

This plugin adds a fourth: open the USBPRINT device interface with `CreateFile`
and write HPGL to it with `WriteFile`, bypassing the spooler entirely.

## Requirements

Inkcut with external-plugin (entry point) loading, i.e. a build including
[PR #432](https://github.com/inkcut/inkcut/pull/432). Until that is in a release:

```bash
pip install git+https://github.com/inkcut/inkcut.git
pip install git+https://github.com/gladfelter/inkcut-usbprint.git
```

Windows only, for now: the interface enumeration and handle I/O are Win32 calls.
Importing the module on other platforms is inert, so it is safe to install
anywhere.

## Install

```bash
pip install git+https://github.com/gladfelter/inkcut-usbprint.git
```

Then restart Inkcut.

## Use

Device → **Configure device** → **Add** → choose **Monoprice / MakerCraft**, then:

| Tab | Value |
|---|---|
| Connection | **USB Print Interface** → your cutter's interface |
| Protocol | **HPGL** |

The driver is registered by this plugin, so the transport and the protocol are
already the only ones offered. If you press **Refresh** on the Connection tab and
the interface list is empty, the cutter is off, unplugged, or another program
(the vendor application) is holding it — the handle is opened exclusively.

## Does this apply to my cutter?

Symptoms that point at this plugin, in order of how cheap they are to check:

- The device appears in Device Manager as **`UNKNOWNPRINTER`**, or as a
  printer-class device with no driver.
- No **COM port** appears when you plug it in.
- Creating a print queue and sending a raw HPGL file results in the job failing
  with **"Win32 error code returned by the print processor: 87"** and
  **0 pages printed**, despite the spooler accepting the bytes.
- The vendor's software cuts fine.

To confirm the device exposes the interface this plugin uses, look for
`{28d78fad-5a12-11d1-ae5b-0000f803a8c2}` (GUID_DEVINTERFACE_USBPRINT) in:

```powershell
Get-PnpDevice -Class USB | Where-Object { $_.InstanceId -like '*<your-vid>*' }
```

## Verified against

| | |
|---|---|
| Machine | Monoprice MakerCraft Craft Cutter (rebranded SKYCUT) |
| Controller | reports as `SKY32 Vi`; no model or manufacturer string |
| USB | `VID_0483` / `PID_5750`, class 07/01/02 |
| Resolution | 40 HPGL units/mm (1016 per inch) |
| Protocols | HPGL, **absolute moves only** |

Verified on hardware: `CreateFile` + `WriteFile` to the interface drives the
machine, a full job writes and closes cleanly, and a pen test cuts in the right
place and orientation.

## Notes and limitations

- **Absolute moves only.** `PR` (relative) is accepted by the device and does
  nothing; the job must use `PU`/`PD`.
- **No homing and no limit switches** on this machine family. The origin is
  wherever the operator parks the head, and it survives only as long as the head
  is not moved and the machine is not power-cycled.
- **The carriage needs room at the right**, so the rightmost ~100 mm of the bed is
  unreachable on the 12" model. Set the driver width accordingly (`Custom` is
  enabled on the driver so the width is editable).
- **Reads are not implemented.** The interface is bidirectional but this transport
  only writes. The HPGL protocol never reads, so cutting is unaffected; status
  polling is not available.
- **Scale:** Inkcut's HPGL protocol assumes 1021 units/inch against the machine's
  1016, so expect roughly 0.5% oversize (200 mm measures ≈201 mm).

## Tests

```bash
pip install -e .[test]
pytest
```

The transport is tested against a fake OS layer, in the same style as Inkcut's
`tests/test_printer.py`, so the suite runs without a cutter attached and on any
platform.

## License

GPLv3, matching Inkcut. See `LICENSE`.
