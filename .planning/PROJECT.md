# Clawdmeter — Windows Daemon Port

## What This Is

Clawdmeter is an ESP32-S3 desk monitor that shows your Claude Code usage
(session + weekly rate-limit utilization) on a small AMOLED display, driven by a
host daemon that polls the Anthropic API and pushes data over BLE. This project
**added a native Windows host daemon** (shipped v1.0) so the device stays
connected on Windows without depending on WSL. The host daemon lineup is now
macOS (Python), Linux (bash), and Windows (Python + `bleak` WinRT) — the Windows
daemon owns the Bluetooth adapter directly, runs from a login-startup system-tray
app, auto-reconnects through sleep/range/power-cycle drops, and survives
`wsl --shutdown`, replacing the old fragile BT-passthrough-to-WSL approach that
stole BLE from Windows and dropped the connection whenever WSL stopped.

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
- ✓ GATT custom data service confirmed UNENCRYPTED (no pairing / firmware change needed) — Validated in Phase 1: Foundation
- ✓ Windows-local OAuth token reader (`daemon/claude_usage_daemon_windows.py`, stdlib-only) reads the token from native-Windows credential paths and prints a redacted confirmation — Validated in Phase 1: Foundation (TOKEN-01; native-Windows end-to-end run pending manual confirmation)
- ✓ Native Windows daemon polls the Anthropic API and derives the `{s,sr,w,wr,st,ok}` session+weekly utilization payload (httpx-mocked unit tests) — Validated in Phase 2: Core Pipeline (POLL-01)
- ✓ Native Windows daemon scans/connects over BLE (`bleak` WinRT, `address_type="random"`, `use_cached_services=False`) and writes usage JSON to the GATT RX characteristic — Validated in Phase 2: Core Pipeline (BLE-01, BLE-02); confirmed on hardware (device left waiting screen, showed percentages)
- ✓ Daemon auto-reconnects after sleep / out-of-range / device drops with no user intervention (connect-retry wrapper + zombie-link break + split fast/slow backoff protecting the 120s SLA) — Validated in Phase 3: Resilience (BLE-03); SC#1–4 confirmed on hardware after the G-03-01 graceful-degradation fix — v1.0
- ✓ Daemon runs as a login-startup tray app (pystray status icon + Quit + error toast, `winreg` HKCU\Run autostart via `pythonw.exe`) — Validated in Phase 4: Tray & Autostart (APP-01) — v1.0
- ✓ Daemon is fully independent of WSL — `install-windows.ps1` bootstrap + static no-WSL-paths regression guard; SC#5 confirmed device connects/displays with WSL never launched and `wsl --shutdown` leaves the daemon undisturbed — Validated in Phase 4: Tray & Autostart (APP-02) — v1.0

### Active

<!-- This project's scope. Building toward these. Empty pending the next milestone — run /gsd:new-milestone to define v1.1. -->

(None — all v1.0 requirements shipped and validated. v2 candidates parked below.)

#### Parked for v2

- PyInstaller one-file Windows executable so the daemon installs without a Python environment (PKG-01)
- Windows Service / Scheduled Task run model for before-login operation (PKG-02)

### Out of Scope

<!-- Explicit boundaries. -->

- Firmware changes — the device side already works; only adjust if the GATT-encryption check forces it (see Key Decisions)
- Refactoring macOS/Linux daemons into a shared cross-platform codebase — deferred; Windows ships as its own daemon mirroring the macOS one
- Windows Service / Scheduled Task run models — rejected in favor of a login-startup tray app (lighter, visible status, sufficient for a desk monitor)
- Reaching the WSL-side token via `\\wsl$` or `wsl.exe` — avoided by installing Claude Code natively on Windows so the daemon reads a Windows-local token path
- New board support, UI changes, animation work — unrelated to this milestone

## Context

- **Shipped state (v1.0):** `daemon/claude_usage_daemon_windows.py` + `daemon/tray_windows.py`, `daemon/autostart_windows.py`, `daemon/icon_assets.py`, `install-windows.ps1`, and `daemon/README-windows.md`. ~1,061 LOC daemon/tray/autostart code, ~3,400 insertions across 16 daemon files incl. pytest suites. Stack: Python + `bleak` (WinRT) + `httpx` + `pystray` + `Pillow`. All 7 v1 requirements hardware-verified.
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
| Native Windows daemon (not BT passthrough to WSL) | Passthrough steals BLE from Windows and dies on WSL shutdown | ✓ Good — v1.0 daemon owns BLE on Windows; SC#5 confirmed it works with WSL stopped |
| Port the Python/macOS daemon, not the bash/Linux one | `bleak` WinRT backend + cross-platform `httpx` | ✓ Good — `poll_api`/`_extract_access_token` ported verbatim; WinRT recipe connected first try on hardware |
| Login-startup tray app (not Service/Scheduled Task) | Lighter setup, visible status, survives WSL shutdown | ✓ Good — pystray tray + `winreg` HKCU\Run autostart shipped (APP-01); Service/Task parked for v2 |
| Read native-Windows token (install Claude Code on Windows) | Avoids fragile `\\wsl$`/`wsl.exe` reaching; WSL-independent | ✓ Good — stdlib token reader with 3-path fallback; static no-WSL-paths guard enforces it |
| Verify GATT characteristics are unencrypted before building | Windows auto-bonds HID; encrypted chars would force manual pairing | ✓ Good — confirmed UNENCRYPTED in Phase 1; no pairing or firmware change needed |

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
*Last updated: 2026-06-02 after v1.0 (Windows Daemon) milestone — all 4 phases shipped, 7/7 v1 requirements delivered and hardware-verified (~1,061 LOC Windows daemon + tray/autostart). The Clawdmeter now stays connected on Windows independently of WSL. Next: run /gsd:new-milestone to scope v1.1.*
