# Phase 4: Tray & Autostart - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-02
**Phase:** 4-Tray & Autostart
**Areas discussed:** Tray icon states & art, Tray menu actions, Autostart mechanism & install, WSL-independence verification

---

## Tray icon states & art

### How many connection states?

| Option | Description | Selected |
|--------|-------------|----------|
| 3 states (matches SC#2) | Connected / Scanning / Error | ✓ |
| 4 states | Connected / Scanning / Disconnected / Error | |
| 2 states | Connected / Not connected | |

**User's choice:** 3 states. Scanning covers searching + reconnecting; Error covers token/BLE failures.

### How are states visually distinguished?

| Option | Description | Selected |
|--------|-------------|----------|
| Color-tinted brand icon + tooltip | One recolored icon per state + tooltip | ✓ (refined) |
| Distinct icon art per state + tooltip | Three separate icon images | |
| Single icon, tooltip only | One unchanging icon, tooltip text only | |

**User's choice:** Refinement of option 1 — a single Clawdmeter icon kept in the normal Anthropic Claude (brand) color, with a small colored bubble in the corner indicating state. Base mark never changes; corner badge does.

### Source asset for the base icon?

| Option | Description | Selected |
|--------|-------------|----------|
| Derive from firmware logo.h | Convert the 80×80 RGB565 brand logo to PNG | ✓ |
| Use a claudepix mascot frame | A 20×20 pixel-art creature frame | |
| I'll provide a PNG/SVG | User supplies a brand asset | |

**User's choice:** Derive from `firmware/src/logo.h`. Corner status bubble drawn programmatically.

### Toast on state change, or silent?

| Option | Description | Selected |
|--------|-------------|----------|
| Silent — icon only | Bubble + tooltip only, no popups | |
| Toast on error only | Popup only when entering Error | ✓ |
| Toast on every transition | Notify on connect/disconnect/error | |

**User's choice:** Toast on Error state only.

---

## Tray menu actions

### What's in the right-click menu?

| Option | Description | Selected |
|--------|-------------|----------|
| Status line + Quit | Status header + Quit | |
| Status + Start-at-login toggle + Quit | Adds checkable autostart toggle | ✓ |
| Full: status + log + autostart + Quit | + Open log | |
| Quit only | Bare minimum (SC#3) | |

**User's choice:** Status header + "Start at login" toggle + Quit. Autostart is controlled from the menu.

### Status header detail level?

| Option | Description | Selected |
|--------|-------------|----------|
| State + reason | "Connected" / "Scanning…" / "Error: …" | ✓ (combined) |
| State + last-sync time | "Connected · last update 14:32" | ✓ (combined) |
| State + live usage % | "Connected · session 42% / week 17%" | |

**User's choice:** State + reason + last-sync time. Live usage % rejected (out of scope — device screen shows it).

---

## Autostart mechanism & install

### Autostart mechanism?

| Option | Description | Selected |
|--------|-------------|----------|
| shell:startup .lnk shortcut | .lnk in Startup folder | |
| HKCU Run-key entry | winreg Run value | |
| You decide | Planner picks | ✓ |

**User's choice:** You decide. CONTEXT leans stdlib-only (Run-key) to avoid a new dependency.

### First-time setup UX?

| Option | Description | Selected |
|--------|-------------|----------|
| install-windows.ps1 bootstrap | venv + deps + launch; user flips toggle | |
| Updated docs only | Manual steps in README | |
| Script also auto-enables autostart | venv + deps + register autostart + launch | ✓ |

**User's choice:** install-windows.ps1 that does venv + deps AND registers autostart immediately, then launches. Menu toggle disables/re-enables afterward.

### Tray library?

| Option | Description | Selected |
|--------|-------------|----------|
| pystray + Pillow | Mature, dynamic icons, menus, toasts | |
| infi.systray | Lighter, Windows-only, weaker dynamic icons | |
| You decide | Planner/research picks | ✓ |

**User's choice:** You decide. CONTEXT leans pystray + Pillow (covers dynamic bubble + menu + toast).

---

## WSL-independence verification

### How to prove WSL independence (SC#4-5)?

| Option | Description | Selected |
|--------|-------------|----------|
| Hardware record + static guard | Manual record + no-WSL-paths unit test | ✓ (Claude's call) |
| Manual hardware record only | Documented hardware test, no code | |
| Record + startup self-check log | Record + log resolved token path | |

**User's choice:** You decide. CONTEXT adopts hardware record + static no-WSL-paths unit guard (mirrors Phase 3 D-06 split).

---

## Claude's Discretion

- Threading/concurrency model (asyncio loop vs. tray main thread; status/last-sync hand-off; Quit join).
- Autostart mechanism (.lnk vs HKCU Run-key) — lean stdlib Run-key.
- Tray library — lean pystray + Pillow.
- Exact brand hex + corner-bubble size/placement (derive from logo.h).
- Precise Error-state triggers beyond token/auth.
- WSL-verification approach selected by Claude: hardware record + static guard.

## Deferred Ideas

- PyInstaller one-file .exe packaging → v2 (PKG-01).
- Windows Service / Scheduled Task run model → v2 (PKG-02).
- Usage percentages in the tray → out of scope (device screen shows them).
- Active Win32 power/session-event wake detection → rejected Phase 3 (D-02).
- Startup self-check log of resolved token path → considered, not adopted as a test.
