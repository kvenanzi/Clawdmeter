# Roadmap: Clawdmeter — Windows Daemon Port

## Overview

Port the macOS Python daemon (`claude_usage_daemon.py`) to native Windows so the
Clawdmeter stays connected all the time without depending on WSL. Four phases
deliver the vertical MVP: a gate-check that de-risks the BLE encryption question
before writing a line of code, then the core API-to-BLE data pipeline, then
reconnect resilience, then the tray app shell that makes it a first-class login
startup experience independent of WSL.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Foundation** - GATT encryption gate-check + Windows credential reading + project scaffold (completed 2026-06-01)
- [x] **Phase 2: Core Pipeline** - BLE scan/connect/write + Anthropic API polling end-to-end (completed 2026-06-01)
- [ ] **Phase 3: Resilience** - Auto-reconnect after sleep, out-of-range, and device drop
- [ ] **Phase 4: Tray & Autostart** - System-tray icon + login startup + WSL independence verified

## Phase Details

### Phase 1: Foundation
**Goal**: The GATT encryption question is answered and the daemon can read a valid Windows-local OAuth token
**Mode:** mvp
**Depends on**: Nothing (first phase)
**Requirements**: TOKEN-01
**Success Criteria** (what must be TRUE):
  1. A reading of `firmware/src/ble.cpp` confirms whether RX/TX/REQ use plain `READ`/`WRITE`/`NOTIFY` or encrypted variants — result recorded in `.planning/notes/windows-daemon-port.md`
  2. A minimal `daemon/claude_usage_daemon_windows.py` skeleton exists with a `read_token()` function that successfully reads the OAuth token from the Windows-local `%APPDATA%\..\Local\Claude\.credentials.json` path (or equivalent native-Windows path) and returns the access token string
  3. Running the script on Windows with Claude Code installed natively prints the token expiry or a recognizable credential field without touching any WSL path
**Plans**: 2 plans
  - [x] 01-01-PLAN.md — Record GATT-encryption verdict + stand up pytest infra and the RED TOKEN-01 test suite
  - [x] 01-02-PLAN.md — Implement the Windows token reader (TDD) + redacted token/expiry output

### Phase 2: Core Pipeline
**Goal**: The daemon connects to the device over Windows BLE and the display updates with live Anthropic usage data
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: BLE-01, BLE-02, POLL-01
**Success Criteria** (what must be TRUE):
  1. Running the daemon script on Windows causes the Clawdmeter to exit its "waiting for data" bluetooth screen and show session + weekly percentages
  2. `BleakScanner.discover()` finds the device by name `"Claude Controller"` and `BleakClient` connects using `address_type="random"` and `use_cached_services=False`
  3. The daemon successfully writes a valid JSON payload to the GATT RX characteristic (`4c41555a-...0002`) and the device firmware parses it without nack
  4. Poll-to-display latency is under 10 seconds from daemon start with a warm token (matches macOS daemon behavior)
**Plans**: 3 plans
  - [x] 02-01-PLAN.md — TDD: port poll_api + pct/reset_minutes + compact-JSON payload (POLL-01) and add requirements-windows.txt
  - [x] 02-02-PLAN.md — BLE glue: scan_for_device, Session (REQ subscribe + RX write), connect_and_run + main run loop (BLE-01, BLE-02)
  - [x] 02-03-PLAN.md — Windows run doc + recorded on-hardware verification of SC#1-4
**UI hint**: yes

### Phase 3: Resilience
**Goal**: The daemon recovers from every expected disruption without user intervention
**Mode:** mvp
**Depends on**: Phase 2
**Requirements**: BLE-03
**Success Criteria** (what must be TRUE):
  1. Putting the PC to sleep and waking it causes the daemon to reconnect and push a fresh usage update within two poll cycles (120 seconds)
  2. Moving the device out of BLE range and back causes the daemon to reconnect automatically with no user action
  3. Powering the Clawdmeter off and back on causes the daemon to pick it back up on the next scan cycle
  4. The daemon never requires a restart to recover from any of the above scenarios
**Plans**: TBD

### Phase 4: Tray & Autostart
**Goal**: The daemon starts at Windows login, shows connection status in the system tray, and works entirely independently of WSL
**Mode:** mvp
**Depends on**: Phase 3
**Requirements**: APP-01, APP-02
**Success Criteria** (what must be TRUE):
  1. After installing the startup entry, the daemon launches automatically on Windows logon with no terminal window visible
  2. A system-tray icon is visible in the notification area; hovering or clicking it shows the current connection status (connected / scanning / error)
  3. Right-clicking the tray icon presents a Quit action that stops the daemon cleanly
  4. Stopping the WSL distro (`wsl --shutdown`) does not disconnect the Clawdmeter or cause any error in the daemon
  5. Starting a fresh Windows session (WSL never launched) results in the device connecting and displaying usage data normally
**Plans**: TBD
**UI hint**: yes

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 2/2 | Complete   | 2026-06-01 |
| 2. Core Pipeline | 3/3 | Complete   | 2026-06-01 |
| 3. Resilience | 0/TBD | Not started | - |
| 4. Tray & Autostart | 0/TBD | Not started | - |
