# Requirements: Clawdmeter — Windows Daemon Port

**Defined:** 2026-06-01
**Core Value:** The Clawdmeter stays connected on Windows, all the time, without the user thinking about it — independent of whether WSL is running.

## v1 Requirements

Requirements for the Windows daemon port. Each maps to roadmap phases.

### Token & Polling

- [ ] **TOKEN-01**: Daemon reads the Claude OAuth token from a native-Windows credentials path (no WSL/`\\wsl$` access)
- [ ] **POLL-01**: Daemon polls the Anthropic API and derives session + weekly rate-limit utilization, mirroring the macOS daemon's logic

### BLE Connectivity

- [ ] **BLE-01**: Daemon discovers and connects to the Clawdmeter over native Windows BLE using `bleak`'s WinRT backend (scan-first, connect by `BLEDevice`/address, `address_type="random"`, `use_cached_services=False`)
- [ ] **BLE-02**: Daemon writes usage JSON to the firmware's existing GATT data service (`4c41555a-...0001` RX characteristic) in the unchanged wire format the device expects
- [ ] **BLE-03**: Daemon auto-reconnects after sleep, out-of-range, or device drop with no user intervention (retry loop handling stale `is_connected` / `Unreachable`)

### Runtime & Lifecycle

- [ ] **APP-01**: Daemon runs as a login-startup app with a system-tray icon reflecting connection status and a quit action
- [ ] **APP-02**: Daemon operates fully independent of WSL — connects and stays connected with the WSL distro stopped

## v2 Requirements

Deferred to future work. Tracked but not in current roadmap.

### Packaging & Distribution

- **PKG-01**: One-file Windows executable (`pyinstaller`) for install without a Python environment
- **PKG-02**: Windows Service / Scheduled Task run model for before-login operation

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Firmware changes | Device side already works; only touch if the GATT-encryption check forces it |
| Refactor macOS/Linux daemons into one shared codebase | Deferred; Windows ships as its own daemon mirroring macOS |
| Bluetooth passthrough to WSL | The problem being solved — passthrough steals BLE from Windows and dies on WSL shutdown |
| Reaching the WSL-side token via `\\wsl$`/`wsl.exe` | Avoided by installing Claude Code natively on Windows |
| New board support / UI / animation work | Unrelated to this milestone |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| TOKEN-01 | Phase 1 | Pending |
| POLL-01 | Phase 2 | Pending |
| BLE-01 | Phase 2 | Pending |
| BLE-02 | Phase 2 | Pending |
| BLE-03 | Phase 3 | Pending |
| APP-01 | Phase 4 | Pending |
| APP-02 | Phase 4 | Pending |

**Coverage:**
- v1 requirements: 7 total
- Mapped to phases: 7
- Unmapped: 0 ✓

---
*Requirements defined: 2026-06-01*
*Last updated: 2026-06-01 after roadmap creation*
