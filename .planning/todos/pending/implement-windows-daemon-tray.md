---
title: "Implement Windows daemon: bleak WinRT + login-startup tray app"
date: 2026-06-01
priority: medium
---

# Implement Windows daemon: bleak WinRT + login-startup tray app

Port the macOS daemon to a native Windows app so Clawdmeter stays connected
independently of WSL. Full context & research in
`.planning/notes/windows-daemon-port.md`. **Blocked-by:**
`verify-gatt-characteristics-unencrypted` (determines whether a manual pairing
step is needed).

## Scope

1. **Port the core loop** from `daemon/claude_usage_daemon.py` (Python +
   `bleak` + `httpx`) into a Windows-targeted daemon (e.g.
   `daemon/claude_usage_daemon_win.py` or a shared module with a platform
   branch).
2. **WinRT-friendly BLE:**
   - `BleakScanner.discover()` first, pass the `BLEDevice` to `BleakClient`.
   - `BleakClient(addr, use_cached_services=False)` — DIY firmware, GATT layout
     changes.
   - `address_type="random"` for the ESP32 NimBLE static-random address.
   - Retry loop around connect for post-sleep `Unreachable` / stale
     `is_connected`.
3. **Token:** read the native-Windows Claude OAuth credentials path (after the
   user installs Claude Code on Windows) instead of the WSL/Linux path.
4. **MAC cache:** Windows equivalent of `~/.config/claude-usage-monitor/`
   (e.g. `%APPDATA%\claude-usage-monitor\ble-address`), mirroring the macOS
   daemon's connect-by-name → cache-MAC → drop-on-failure resilience.
5. **Tray app:** system-tray icon (e.g. `pystray` + `Pillow`) showing
   connection status with a quit action.
6. **Autostart:** register to launch at logon (`shell:startup` `.lnk`, or a
   Run-key entry), running headless via `pythonw`/packaged exe.
7. **Packaging & docs:** decide `pyinstaller` one-file exe vs. raw Python; add
   a Windows section to the README / daemon docs.

## Acceptance

- Daemon launches at Windows logon, connects to Clawdmeter over native Windows
  BLE, polls the Anthropic API, pushes usage JSON, and **auto-reconnects** after
  sleep/range drops — all with WSL not running.
- Tray icon reflects connection state.
