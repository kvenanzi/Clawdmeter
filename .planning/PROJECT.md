# Clawdmeter — Windows Daemon Port

## What This Is

Clawdmeter is an ESP32-S3 desk monitor that shows your Claude Code usage
(session + weekly rate-limit utilization) on a small AMOLED display, driven by a
host daemon that polls the Anthropic API and pushes data over BLE. This project
adds a **native Windows host daemon** so the device stays connected on Windows
without depending on WSL — today the only host daemons are macOS (Python) and
Linux (bash), and a Windows user running Claude Code in WSL must pass the
Bluetooth adapter through to WSL, which steals BLE from Windows and drops the
Clawdmeter connection whenever WSL shuts down.

## Core Value

The Clawdmeter stays connected on Windows, all the time, without the user
thinking about it — independent of whether WSL is running.

## Requirements

### Validated

<!-- Existing capabilities inferred from the codebase (already shipped). -->

- ✓ ESP32-S3 firmware renders usage/splash/bluetooth screens across 3 board ports — existing
- ✓ Firmware exposes a custom BLE GATT data service (`4c41555a-...0001`, RX/TX/REQ) plus a standard HID keyboard — existing
- ✓ macOS host daemon (`daemon/claude_usage_daemon.py`, Python + `bleak` + `httpx`) polls the Anthropic API and pushes usage JSON over BLE — existing
- ✓ Linux host daemon (`daemon/claude-usage-daemon.sh`, bash + `bluetoothctl`/`busctl`/`curl`) — existing
- ✓ Daemon resilience pattern: connect-by-name → cache resolved MAC → drop cache + bluez entry on failure; ESP-triggered refresh requests — existing

### Active

<!-- This project's scope. Building toward these. -->

- [ ] Native Windows host daemon that reads the Windows-local Claude OAuth token and polls the Anthropic API
- [ ] Daemon connects to Clawdmeter over native Windows BLE (`bleak` WinRT backend) and pushes usage JSON to the GATT data service
- [ ] Daemon auto-reconnects after sleep / out-of-range / device drops, with no user intervention
- [ ] Daemon runs as a login-startup tray app showing connection status with a quit action
- [ ] Daemon is fully independent of WSL — works with the WSL distro stopped

### Out of Scope

<!-- Explicit boundaries. -->

- Firmware changes — the device side already works; only adjust if the GATT-encryption check forces it (see Key Decisions)
- Refactoring macOS/Linux daemons into a shared cross-platform codebase — deferred; Windows ships as its own daemon mirroring the macOS one
- Windows Service / Scheduled Task run models — rejected in favor of a login-startup tray app (lighter, visible status, sufficient for a desk monitor)
- Reaching the WSL-side token via `\\wsl$` or `wsl.exe` — avoided by installing Claude Code natively on Windows so the daemon reads a Windows-local token path
- New board support, UI changes, animation work — unrelated to this milestone

## Context

- **Token source:** Claude OAuth credentials currently live only inside WSL
  (`~/.claude/.credentials.json`). The user will install Claude Code natively on
  Windows so the daemon reads a Windows-local token path directly — making the
  daemon WSL-independent.
- **Run model:** login-startup tray app. Runs at Windows logon; survives WSL
  shutdown. The "stops at logout" caveat is acceptable for a desk monitor on an
  always-logged-in machine. Auto-reconnect covers sleep/range drops.
- **Starting point:** port the macOS `claude_usage_daemon.py` (Python + `bleak` +
  `httpx`), not the Linux bash daemon — `bleak` has a first-class Windows/WinRT
  backend and `httpx` is already cross-platform.
- **BLE research findings (from `/gsd-explore`, see `.planning/notes/windows-daemon-port.md`):**
  1. The HID-held-device problem that hit macOS (commit `18282e0`, `retrieveConnected`)
     does **not** exist on Windows — WinRT lets the HID driver and the GATT app
     share the same link; `BleakClient(address)` attaches transparently.
  2. Windows auto-bonds HID keyboards; if the custom characteristics require
     encryption, reads throw `Access Denied` until manually paired. Must verify
     the characteristics are open (see todo).
  3. `use_cached_services=False` is mandatory for DIY firmware (WinRT caches the
     GATT table across firmware changes).
  4. ESP32/NimBLE advertises a static-random address → `address_type="random"`;
     wrap connect in a retry loop for post-sleep `Unreachable`.
- Prior exploration artifacts: `.planning/notes/windows-daemon-port.md`,
  `.planning/todos/pending/verify-gatt-characteristics-unencrypted.md`,
  `.planning/todos/pending/implement-windows-daemon-tray.md`.

## Constraints

- **Platform**: Target is Windows 10/11 native (not WSL) — must own Bluetooth and survive WSL shutdown.
- **Tech stack**: Python + `bleak` (WinRT) + `httpx`, mirroring the macOS daemon, for code parity and reuse.
- **Compatibility**: Must speak the existing firmware GATT protocol unchanged (service `4c41555a-...0001`, RX/TX/REQ characteristics) — no firmware changes if avoidable.
- **Dependency**: Requires Claude Code installed natively on Windows for a Windows-local token path.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Native Windows daemon (not BT passthrough to WSL) | Passthrough steals BLE from Windows and dies on WSL shutdown | — Pending |
| Port the Python/macOS daemon, not the bash/Linux one | `bleak` WinRT backend + cross-platform `httpx` | — Pending |
| Login-startup tray app (not Service/Scheduled Task) | Lighter setup, visible status, survives WSL shutdown | — Pending |
| Read native-Windows token (install Claude Code on Windows) | Avoids fragile `\\wsl$`/`wsl.exe` reaching; WSL-independent | — Pending |
| Verify GATT characteristics are unencrypted before building | Windows auto-bonds HID; encrypted chars would force manual pairing | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-06-01 after initialization*
