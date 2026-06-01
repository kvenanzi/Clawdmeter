---
title: Windows daemon port — approach & BLE research
date: 2026-06-01
context: exploration
---

# Windows daemon port — approach & BLE research

## Problem

Clawdmeter's host daemon ships for macOS (`daemon/claude_usage_daemon.py`,
Python + `bleak` + `httpx`) and Linux (`daemon/claude-usage-daemon.sh`, bash +
`bluetoothctl`/`busctl`/`curl`). There is no Windows daemon.

The user runs Claude Code inside **WSL**. Bluetooth on Windows is zero-sum:
passing the adapter through to WSL means Windows loses BLE, and when the WSL
distro shuts down the Clawdmeter connection dies. Goal: a **native Windows
daemon** that owns Bluetooth persistently and is independent of whether WSL is
running, so the device stays connected without the user thinking about it.

## Decisions from exploration (2026-06-01)

- **Native Windows daemon**, almost certainly a port of the existing
  `claude_usage_daemon.py` — `bleak` has a first-class Windows/WinRT backend and
  `httpx` is already cross-platform, so the macOS daemon is the right starting
  point (not the bash/Linux one).
- **Token source:** Claude OAuth token currently lives only in WSL
  (`~/.claude/.credentials.json` on the Linux side). User will **install Claude
  Code natively on Windows**, so the daemon reads a **Windows-local token path**
  directly — no `\\wsl$` reaching or `wsl.exe` shelling. This makes the daemon
  fully WSL-independent.
- **Run model: login-startup tray app.** Runs at Windows logon, optional
  system-tray icon for connection status / quit. Survives WSL shutdown; the
  "stops at logout" caveat is a non-issue for a desk monitor on an
  always-logged-in machine. Auto-reconnect covers sleep/range drops. (Windows
  Service and Scheduled Task were considered and rejected as heavier than needed.)

## BLE research findings (bleak / WinRT)

1. **The HID-held-device problem does NOT exist on Windows.** The ESP32
   advertises a custom GATT data service *and* a standard HID keyboard at once.
   On Linux/BlueZ you must `bluetoothctl disconnect` first; on macOS the port
   needed CoreBluetooth `retrieveConnectedPeripherals` (commit `18282e0`). On
   **WinRT the HID class driver and the GATT app share the same BLE link
   concurrently** — `BleakClient(address)` attaches to the existing OS
   connection transparently. Best practice: `BleakScanner.discover()` first,
   pass the returned `BLEDevice` to `BleakClient`.
2. **Encryption gate.** Windows auto-bonds HID keyboards. If the custom
   RX/TX/REQ characteristics require encryption/authentication, reads throw
   `Access Denied` until the device is manually paired in Windows settings
   (bleak issues #1291, #809). If the characteristics are **open** (typical for
   this firmware), bleak reads them with **no manual pairing**. → must verify in
   `firmware/src/ble.cpp` (see companion todo).
3. **`use_cached_services=False` is mandatory for DIY firmware.** WinRT caches
   the GATT table; after any firmware change the cached layout goes stale. Pass
   `BleakClient(addr, use_cached_services=False)`.
4. **Address type + post-sleep reconnect.** ESP32/NimBLE advertises a
   static-random address → pass `address_type="random"`. After the PC wakes,
   the OS may report stale `is_connected` or `Could not get GATT services:
   Unreachable` — wrap connect in a retry loop (recent bleak versions added
   internal retries for this).

Sources: bleak Windows backend & troubleshooting docs; bleak issues #367, #1291, #809.

## Open questions / next steps

- Confirm characteristics are unencrypted (de-risk gate — companion todo).
- Decide tray library (e.g. `pystray` + `Pillow`) and packaging
  (`pyinstaller` one-file exe vs. a `pythonw` + `.lnk` in `shell:startup`).
- Mirror the macOS daemon's discovery/cache/reconnect logic; the resolved-MAC
  cache lives under `~/.config/claude-usage-monitor/` on *nix — pick a Windows
  equivalent (e.g. `%APPDATA%\claude-usage-monitor\`).

## GATT encryption gate — verdict (D-01)

**Status: CONFIRMED UNENCRYPTED** — verified 2026-06-01 by reading
`firmware/src/ble.cpp` lines 185–199 directly.

The custom data-service characteristics (service UUID `4c41555a-…0001`) are
created with plain NimBLE property flags:

- **RX** (`…0002`): `NIMBLE_PROPERTY::WRITE | WRITE_NR` — no `_ENC` / `_AUTHEN` / `_AUTHOR`
- **TX** (`…0003`): `NIMBLE_PROPERTY::READ | NOTIFY` — plain
- **REQ** (`…0004`): `NIMBLE_PROPERTY::NOTIFY` — plain

The NimBLE library does define encrypted variants (`READ_ENC`, `WRITE_ENC`,
`READ_AUTHEN`, `WRITE_AUTHEN`, etc.) — they are used on the HID keyboard
characteristics but are absent from the custom data service.

**Consequence:** The Windows daemon needs no manual Bluetooth pairing and no
firmware change. The "encrypted characteristics" contingency from the BLE
research section above is closed.

*Satisfies Phase 1 Success Criterion #1.*
