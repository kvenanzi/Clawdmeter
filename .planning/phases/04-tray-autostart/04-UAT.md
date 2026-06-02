---
status: complete
phase: 04-tray-autostart
source:
  - 04-01-SUMMARY.md
  - 04-02-SUMMARY.md
  - 04-03-SUMMARY.md
started: 2026-06-02T17:54:16Z
updated: 2026-06-02T17:59:29Z
---

## Current Test

[testing complete]

## Tests

### 1. Tray icon appears at login (no console)
expected: After install + log out/in, the Clawdmeter icon appears in the notification area within ~10-15s, with NO console window. Task Manager shows pythonw.exe (not python.exe).
result: pass

### 2. Tray status reflects live state + last-update advances
expected: Hovering the icon shows a tooltip and right-clicking shows a menu header that reflect the real state — "Connected · last update HH:MM" when connected, "Scanning…" when searching. While connected, the "last update" time visibly advances each poll (~60s) rather than freezing.
result: pass

### 3. State-distinct icons (green / amber / red)
expected: The tray icon carries a corner bubble whose color matches state: green when Connected, amber while Scanning, red on Error. The three are visually distinguishable at notification-area size.
result: pass

### 4. Start-at-login toggle works
expected: Right-click menu → "Start at login" is a checkable item reflecting the current autostart state. Toggling it adds/removes the HKCU\Run "Clawdmeter" entry, and the checkmark updates to match. The setting persists across a reboot.
result: pass

### 5. Quit stops the daemon cleanly (Windows link persists)
expected: Right-click → Quit removes the tray icon promptly and leaves no pythonw.exe/python.exe process. The daemon disconnects its data connection cleanly (graceful). The device stays connected to Windows (bonded HID) and keeps showing last-synced usage — the intended point-in-time view.
result: pass

### 6. Daemon is independent of WSL
expected: With the daemon connected, running `wsl --shutdown` in a separate terminal does NOT disconnect or error the daemon. The tray stays Connected and the device keeps showing usage.
result: pass

### 7. Cold start — fresh reboot (WSL never launched) connects & shows usage
expected: After a full reboot, with WSL never opened, the tray auto-starts at login, connects, and the device shows session + weekly usage within ~60s. A transient network blip at boot must NOT show a false "token expired" toast.
result: pass

### 8. Error toast fires only on a genuine auth failure
expected: A notification "token expired — run claude login" fires once, only on an actual token rejection (HTTP 401/403). Transient failures (DNS/network not ready at boot, timeouts, rate limits, 5xx) do NOT trigger the toast.
result: pass

## Summary

total: 8
passed: 8
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none yet]
