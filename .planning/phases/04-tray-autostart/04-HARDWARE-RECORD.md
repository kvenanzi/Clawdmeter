# Phase 4 — Hardware Verification Record (D-10 manual half)

**Purpose:** Operator-recorded on-hardware observations for SC#1–SC#5 (manual-only
verifications that cannot be proven by mocks or static analysis). Mirrors the Phase 1/2/3
D-06 hardware-record precedent.

**Instructions:** For each section below, perform the test steps on the target Windows PC
with the Clawdmeter device powered on. Fill in the "Observed:" line with what you actually
saw (not what you expected). Set "Result:" to PASS or FAIL. If any SC fails, describe the
failure in "Observed:" and report it rather than silently marking PASS.

---

## SC#1 — No-console logon launch

**Requirement:** APP-01 — the daemon launches automatically at login with no terminal window.

**Test steps:**
1. Run `powershell -ExecutionPolicy Bypass -File install-windows.ps1` from the repository root.
   Confirm it completes with no errors.
2. Log out of Windows and log back in.
3. Wait 10–15 seconds for startup programs to settle.
4. Check the notification area (system tray) for the Clawdmeter icon.
5. Check Task Manager (Details tab) for a `pythonw.exe` process — confirm there is no `python.exe` process or a visible black console window.

**Expected:** Tray icon present at logon. No console/terminal window visible. `pythonw.exe` (not `python.exe`) in Task Manager.

Observed: After signing out and back in, the tray icon started automatically with no cmd or PowerShell popup. (2026-06-02, after the SC#1 fix — autostart via base `pythonw` so the venv redirector no longer spawns a console.)

Result: PASS

---

## SC#2 — Tray icon visible; hover/click shows status

**Requirement:** APP-01 — tray icon visible with status on hover/click.

**Test steps:**
1. With the daemon running (from SC#1 or from a fresh `install-windows.ps1` run), locate the Clawdmeter icon in the notification area.
2. Hover over the icon. Note the tooltip text.
3. Right-click the icon to open the menu. Note the status header text at the top of the menu.
4. If the device is connected and data is flowing, confirm the status shows "Connected · last update HH:MM".
5. If the device is not yet found, confirm the status shows "Scanning…".
6. If a token error exists, confirm "Error: token expired — run claude login" appears and a notification fired.

**Expected:** Icon is visible. Tooltip and menu header reflect actual connection state (Connected/Scanning/Error). Each state is legible at notification-area size.

Observed: Tray icon visible. Hover/menu shows "Connected" with a last-update time, matching the live BLE link state. (2026-06-02)

Result: PASS

---

## SC#3 — Right-click → Quit stops daemon cleanly

**Requirement:** APP-01 — Quit action stops the daemon cleanly.

**Test steps:**
1. With the daemon running and (ideally) connected, right-click the tray icon.
2. Click "Quit" in the menu.
3. Observe the tray icon disappear.
4. Check Task Manager: confirm no `pythonw.exe` (or `python.exe`) process remains for Clawdmeter.
5. On the device side: the device is a **bonded BLE HID keyboard**, so Windows keeps the
   Bluetooth link and auto-reconnects it. By design the device **retains its last-synced
   usage** (a glanceable point-in-time view) and does NOT return to the waiting screen.
   Confirm it stays connected to Windows.
6. Optionally: check the console for `Stopping` (printed only after the loop's graceful
   `client.disconnect()` runs) and a clean exit.

**Expected (revised 2026-06-02):** Tray icon disappears promptly. No lingering
`pythonw.exe`/`python.exe` process. The daemon releases its GATT data connection cleanly
(console prints `Stopping`). The **Windows BLE/HID link intentionally persists** — the
device stays connected to Windows and keeps showing the last usage (point-in-time view).
Clean exit (no crash).

> **Criterion revision rationale:** The original "device returns to waiting screen"
> expectation assumed Quit drops the BLE link. The firmware enables bonding
> (`setSecurityAuth(true,false,true)`) and is an HID keyboard, so Windows maintains the
> link for the physical buttons and auto-reconnects the bonded device. Per operator
> decision (2026-06-02), keeping the connection — and the last-usage point-in-time view —
> after Quit is the desired behavior. Native Windows pairing is now a documented
> prerequisite (see `daemon/README-windows.md` → "Pair the device").

Observed: Right-click → Quit removed the tray icon promptly; no `python.exe`/`pythonw.exe`
remained in Task Manager. Console logged `Stopping` (graceful `client.disconnect()` ran —
previously this was skipped because the daemon thread was killed before the `finally`). The
device stayed connected to Windows and retained its last usage, as intended. (2026-06-02,
after the graceful-shutdown fix: `_on_quit` now joins the daemon thread and the poll loop
wakes immediately on stop.)

Result: PASS

---

## SC#4 — `wsl --shutdown` does not disconnect or error the daemon

**Requirement:** APP-02 — daemon operates fully independent of WSL.

**Test steps:**
1. Start the daemon (via tray or `install-windows.ps1`) and confirm the device is connected (tray shows green/Connected).
2. In a separate PowerShell terminal, run `wsl --shutdown`.
3. Wait 10–15 seconds. Observe the tray icon and status.
4. If the daemon logs to a visible console (or via the tray status), check for any error messages.
5. Check the device screen — confirm it still shows usage data and has not dropped to the waiting screen.

**Expected:** Tray remains Connected (green). No error logged. Device screen continues to show usage data. The BLE link is unaffected by WSL shutdown.

Observed:

Result: PASS/FAIL

---

## SC#5 — Fresh Windows session (WSL never launched) connects and shows usage

**Requirement:** APP-02 — daemon connects and shows usage in a fresh session where WSL has never been launched.

**Test steps:**
1. Fully reboot the Windows PC.
2. After login, do NOT open WSL, a WSL terminal, or any WSL-dependent application.
3. Confirm the daemon started automatically at login (from the HKCU\Run autostart registered in SC#1). Check the tray icon.
4. Wait for the device to connect (allow up to 60 seconds for initial scan + BLE connect).
5. Once the tray shows Connected, verify the device screen shows session and weekly usage percentages (not a waiting screen).
6. Note the approximate time from login to first data shown on the device.

**Expected:** Daemon starts without WSL. Device connects and shows usage data within ~60 seconds. WSL never needs to be launched for the daemon to function.

Observed:

Result: PASS/FAIL

---

*Record created by the executor (pre-seeded). Observations must be filled by the operator on real Windows hardware. Do not fabricate results.*
