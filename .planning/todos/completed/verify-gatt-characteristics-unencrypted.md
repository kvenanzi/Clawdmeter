---
title: Verify ESP32 custom GATT characteristics are unencrypted
date: 2026-06-01
priority: high
---

# Verify ESP32 custom GATT characteristics are unencrypted

**De-risk gate for the Windows daemon port** (see
`.planning/notes/windows-daemon-port.md`).

Windows auto-bonds HID keyboards. If the custom data-service characteristics
(RX `...0002`, TX `...0003`, REQ `...0004` on service `4c41555a-...0001`)
require encryption/authentication, `bleak` reads/writes throw `Access Denied`
on Windows until the device is manually paired in Bluetooth settings. If they
are **open**, the Windows daemon connects with zero manual pairing.

## Task

- Inspect `firmware/src/ble.cpp` — check the NimBLE characteristic flag macros
  used when creating RX/TX/REQ. Confirm they use plain
  `READ`/`WRITE`/`NOTIFY` and **not** the `_ENC`/`_AUTHEN`/`_AUTHOR` encrypted
  variants.
- If unencrypted: note it; the Windows port needs no pairing step.
- If encrypted: decide whether to (a) drop encryption on the data service
  (HID stays bonded regardless), or (b) document a one-time "pair in Windows
  settings" step in the Windows daemon setup.

## Acceptance

A definitive yes/no on whether the custom data service requires bonding on
Windows, recorded back in the Windows-port note.
