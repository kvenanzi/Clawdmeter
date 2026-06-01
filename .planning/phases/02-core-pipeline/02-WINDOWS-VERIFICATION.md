---
status: passed
phase: 02-core-pipeline
source: [02-03-PLAN.md]
verified: 2026-06-01
operator: kevin.venanzi@gmail.com
hardware: native Windows (PowerShell Core, .venv, files over \\wsl.localhost mount)
---

## Windows Hardware Verification — Phase 2: Core Pipeline

**Verified:** 2026-06-01
**Daemon run command:** `python .\daemon\claude_usage_daemon_windows.py`
**Device under test:** Clawdmeter (Waveshare AMOLED-2.16, BLE MAC 28:84:85:55:65:39)

Console output captured during the verified run (banner confirmed Windows daemon):

```
[17:18:18] === Claude Usage Tracker Daemon (BLE, Windows) ===
[17:18:18] Poll interval: 60s
[17:18:18] Scanning for 'Claude Controller' (8.0s)...
[17:18:18] Found: 28:84:85:55:65:39
[17:18:18] Connecting to 28:84:85:55:65:39...
[17:18:18] Connected
[17:18:37] Sending: {"s":46,"sr":11,"w":4,"wr":6281,"st":"allowed","ok":true}
[17:19:57] Sending: {"s":46,"sr":10,"w":4,"wr":6280,"st":"allowed","ok":true}
```

---

## Tests

### SC#1 — Device leaves waiting screen and shows session + weekly percentages

**Expected behavior:** Running the daemon on Windows causes the Clawdmeter to exit its
"waiting for data" bluetooth screen and display session utilization and weekly utilization
as percentages.

**Operator-reported result:** PASS. The Clawdmeter displayed fresh values sourced from
this Windows-daemon run — session 46% and weekly 4%. The device had previously been fed by
the macOS daemon ~3 minutes prior (17:15–17:16), so the device had already left its waiting
screen at that time; the operator confirmed the displayed values were FRESH values from
the Windows-daemon run (not stale from the macOS run). The waiting screen was not re-entered
between the macOS and Windows runs in this sequence.

---

### SC#2 — BleakScanner finds 'Claude Controller' and BleakClient connects with locked kwargs

**Expected behavior:** The scanner finds a BLE device named `"Claude Controller"` by name
(using `BleakScanner.find_device_by_name`, which returns a `BLEDevice` object), then
`BleakClient` connects to it using `address_type="random"` and `use_cached_services=False`
(the locked WinRT recipe from D-05; the ESP32/NimBLE static-random address type requires
this; `use_cached_services=False` prevents WinRT from serving a stale GATT cache after
firmware changes). No manual Bluetooth pairing required (GATT service is unencrypted — Phase 1 D-01).

**Operator-reported result:** PASS. Scan found the device at MAC 28:84:85:55:65:39;
`Connected` logged at the same second as scan start (17:18:18). Code uses
`BleakScanner.find_device_by_name` returning a `BLEDevice` and `BleakClient(device,
address_type="random", use_cached_services=False)`. No pairing prompt appeared.

---

### SC#3 — RX write parsed without nack

**Expected behavior:** The daemon writes a compact-JSON usage payload to the GATT RX
characteristic (`4c41555a-...0002`) using `write_gatt_char(..., response=False)`, and the
firmware parses it without responding with a nack. Evidence: the `Sending: {...}` log line
appears and the connection persists across multiple 60s poll cycles (a nack would appear
in the firmware serial output or cause a disconnect).

**Operator-reported result:** PASS. `Sending: {"s":46,"sr":11,"w":4,"wr":6281,"st":"allowed","ok":true}`
logged; connection persisted through a second poll at 17:19:57 with no nack or disconnect,
confirming the firmware accepted the compact-JSON RX write (`response=False`).

---

### SC#4 — first-paint under 10 seconds with a warm token

**Expected behavior:** From daemon launch to the device first displaying usage percentages
(first-paint), elapsed time is under 10 seconds with a warm (non-expired) OAuth token.

**Operator-reported result:** PASS WITH CAVEAT. Observed first-paint latency approximately
19 seconds: daemon launch / `Connected` at 17:18:18, first `Sending:` at 17:18:37 (~19s gap).
This exceeds the <10s target.

**Root cause and caveat (not a Windows-daemon-specific defect):** The ~19s gap is attributable
to the shared `poll_api()` HTTPS round-trip to `api.anthropic.com`, NOT to any Windows BLE
or WinRT overhead. BLE scan+connect itself was effectively instant (sub-second, within the
same 17:18:18 second). The macOS daemon (`claude_usage_daemon.py`) exhibited the same ~18s
connect-to-send gap in an immediately-prior run on the same network (Connected 17:14:45 →
Sending 17:15:03), confirming parity between the two daemons.

**Operator disposition:** SC#4 accepted as met-in-spirit. The Windows daemon achieves the
same first-paint latency as the macOS daemon on identical hardware and network conditions —
no Windows-specific regression exists. Deferred follow-up (not a Phase 2 blocker): profile
and optimize first `poll_api()` latency (e.g. warm TLS session / connection reuse) — candidate
for a future phase. No gap plan created.

---

## Summary

```
total:   4
passed:  4  (SC#4 passed with documented caveat — same latency as macOS daemon, deferred optimization)
issues:  0
gaps:    0
```

## Notes

- Token credential path: `%USERPROFILE%\.claude\.credentials.json` (native Windows — no WSL path).
  Token value redacted; expiry sourced from Phase 1 native-Windows verification (2026-06-01).
  No OAuth token or full credential content is embedded in this record (T-02-07 mitigation).
- Measurement confound: the macOS daemon had fed the device ~3 minutes prior to the Windows
  run, so the device had already left its waiting screen. The operator confirmed fresh
  session/weekly percentages were rendered during the Windows-daemon run.
- Multi-poll confirmation: two successive `Sending:` entries at 17:18:37 and 17:19:57
  confirm the 60s poll loop continued normally after first connect.
