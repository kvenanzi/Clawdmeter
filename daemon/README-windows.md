# Windows Setup and Run Guide

This guide covers running the Clawdmeter Windows daemon on native Windows hardware.
It includes the turnkey `install-windows.ps1` bootstrap (tray icon + login autostart),
the manual-run fallback, and how to manage or remove autostart.

---

## Prerequisites

| Requirement | Details |
|-------------|---------|
| **Native Windows** | Must run on real Windows — not WSL. The script prints a warning and BLE will not work under WSL. |
| **Python 3.11+** | Download from [python.org](https://www.python.org/downloads/) if not already installed. Ensure "Add python.exe to PATH" is checked during install. |
| **Claude Code installed** | Install Claude Code and complete `claude login` so credentials exist on disk. |
| **Clawdmeter powered on** | The device must be on and showing its Bluetooth waiting screen before the daemon starts. |

### Where are my credentials?

`claude login` writes the OAuth token to (first match wins):

1. `%USERPROFILE%\.claude\.credentials.json` — primary path (confirmed by Claude Code docs)
2. `%LOCALAPPDATA%\Claude\.credentials.json` — fallback
3. `%APPDATA%\Claude\.credentials.json` — fallback

The daemon probes these paths in order. You can also set `CLAUDE_CREDENTIALS_PATH` to an
absolute path or `CLAUDE_CONFIG_DIR` to a directory to override the search entirely.

> **Security note:** The credentials file contains your OAuth token. Never share its contents
> or embed it in scripts. The daemon reads it from disk and redacts it in all log output
> (e.g., `sk-ant-…XXXX`).

---

## Setup (one time)

Open a PowerShell terminal and `cd` to the repository root.

**1. Create a virtual environment**

```powershell
python -m venv .venv
```

**2. Activate it**

```powershell
.venv\Scripts\Activate.ps1
```

If you see a scripts-execution-policy error, run:
```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```
Then repeat the `Activate.ps1` step.

**3. Install dependencies**

```powershell
pip install -r daemon\requirements-windows.txt
```

This installs `bleak` (WinRT BLE) and `httpx` (async HTTP for the Anthropic API).

---

## Running the daemon

With the venv active and the Clawdmeter powered on:

```powershell
python daemon\claude_usage_daemon_windows.py
```

### Expected console output

```
[HH:MM:SS] === Claude Usage Tracker Daemon (BLE, Windows) ===
[HH:MM:SS] Poll interval: 60s
[HH:MM:SS] Scanning for 'Claude Controller' (8.0s)...
[HH:MM:SS] Found: XX:XX:XX:XX:XX:XX
[HH:MM:SS] Connecting to XX:XX:XX:XX:XX:XX...
[HH:MM:SS] Connected
[HH:MM:SS] Sending: {"s":42,"sr":180,"w":17,"wr":8820,"st":"active","ok":true}
```

- **No manual Bluetooth pairing is required.** The GATT data service is unencrypted; the
  daemon connects directly via `BleakScanner` + `BleakClient` with no Windows pairing dialog.
- After `Connected`, the daemon polls the Anthropic API immediately and sends the first
  payload within a few seconds of connect (warm token path). With a valid, non-expired token
  the device should leave its waiting screen and show session + weekly percentages within
  about 10 seconds of launch.
- The daemon then re-polls every 60 seconds while connected. If the device fires a refresh
  request (e.g., after a button press), an immediate re-poll occurs without waiting for the
  60-second interval.
- If the device disconnects or goes out of range, the daemon logs `Device disconnected` and
  re-scans automatically with exponential backoff (starting at 1 second, capped at 60 seconds).

### Stopping

Press **Ctrl+C** in the terminal. The daemon logs `Daemon stopping` and exits cleanly.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `Warning: running under Linux/WSL` | Running in WSL, not native Windows | Run from a native PowerShell or Command Prompt on Windows |
| `Scanning for 'Claude Controller'… Device not found` | Clawdmeter is off, out of range, or showing a non-Bluetooth screen | Power on the device and ensure it is on the Bluetooth waiting screen |
| `No token; skipping poll` | No credentials file found at any candidate path | Confirm `claude login` ran on this machine; check `%USERPROFILE%\.claude\.credentials.json` exists |
| `API HTTP 401` | Token expired | Re-run `claude login` in a terminal to refresh the token, then restart the daemon |
| `Connection failed` | WinRT BLE initialisation issue | Ensure Windows Bluetooth is on; try toggling Bluetooth off/on in Windows Settings |

---

## Tray icon, login autostart, and turnkey install

### One-command install (recommended)

Run this once from the repository root in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File install-windows.ps1
```

The script does four things in order and logs progress at each step:

1. Creates a Python virtual environment at `.venv`.
2. Installs dependencies from `daemon\requirements-windows.txt` (bleak, httpx, pystray, Pillow).
3. Registers the tray app to launch automatically at login via `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` — per-user, no admin required.
4. Launches the tray app immediately (headless — no console window).

The script downloads nothing from the internet. It only installs the packages listed in
the in-repo `daemon\requirements-windows.txt`.

### Tray icon and status

After install, the Clawdmeter icon appears in the Windows notification area:

| State | Icon bubble | Tooltip |
|-------|-------------|---------|
| Connected | green | `Connected · last update HH:MM` |
| Scanning | amber | `Scanning…` |
| Error | red | `Error: token expired — run claude login` |

Hover over the icon to see the current status tooltip. A notification fires once when the
daemon first enters the Error state (e.g. after a token expiry).

### Tray menu

Right-click the tray icon for the menu:

- **Status header** (non-clickable) — live status + last data sync time.
- **Start at login** (checkable toggle) — enables or disables autostart at runtime.
  Reflects the current registry state each time the menu opens.
- **Quit** — disconnects the BLE link cleanly and exits. No lingering process.

### Disabling or removing autostart

Use the tray menu toggle, or remove the registry value manually:

```powershell
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v Clawdmeter /f
```

### WSL independence

The daemon operates fully independently of WSL. The token is read from native Windows
credential paths (`%USERPROFILE%\.claude\.credentials.json` and fallbacks); BLE uses
the WinRT stack directly. Running `wsl --shutdown` does not affect the BLE link, and
the daemon starts correctly even in a fresh Windows session where WSL has never been
launched.

---

## What is NOT covered here

- PyInstaller / one-file `.exe` packaging — v2
- MAC-address cache / sleep-wake reconnect hardening — Phase 3
