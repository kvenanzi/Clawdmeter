# Milestone v1.0 — Project Summary

**Milestone:** Windows Daemon
**Generated:** 2026-06-02
**Status:** SHIPPED & ARCHIVED
**Purpose:** Team onboarding and project review

---

## 1. Project Overview

**Clawdmeter** is an ESP32-S3 desk monitor that shows your Claude Code usage
(session + weekly rate-limit utilization) on a small AMOLED display, driven by a
host daemon that polls the Anthropic API and pushes data to the device over BLE.

**This milestone added a native Windows host daemon** so the device stays
connected on Windows without depending on WSL. The host-daemon lineup is now:

- **macOS** — Python (`bleak` + `httpx`)
- **Linux** — bash (`bluetoothctl`/`busctl`/`curl`)
- **Windows (new in v1.0)** — Python (`bleak` WinRT backend + `httpx`)

The new Windows daemon owns the Bluetooth adapter directly, runs from a
login-startup system-tray app, auto-reconnects through sleep/range/power-cycle
drops, and survives `wsl --shutdown` — replacing the old fragile
BT-passthrough-to-WSL approach that stole BLE from Windows and dropped the
connection whenever WSL stopped.

**Core value:** The Clawdmeter stays connected on Windows, all the time, without
the user thinking about it — independent of whether WSL is running.

**Status:** All 4 phases shipped. All 7 v1 requirements delivered and
**hardware-verified** on real devices. ~1,061 LOC of daemon/tray/autostart code
(+ ~3,000 LOC of tests). Next step: `/gsd:new-milestone` to scope v1.1.

---

## 2. Architecture & Technical Decisions

The Windows daemon is a **standalone mirror of the macOS daemon**, not a shared
cross-platform refactor. It speaks the firmware's existing GATT wire protocol
unchanged. Key choices:

- **Decision:** Native Windows daemon (not Bluetooth passthrough to WSL)
  - **Why:** Passthrough steals BLE from Windows and dies on WSL shutdown — the
    exact failure this milestone fixes.
  - **Phase:** Pre-planning / Project decision

- **Decision:** Port the Python/macOS daemon, not the bash/Linux one
  - **Why:** `bleak` has a first-class Windows/WinRT backend and `httpx` is
    already cross-platform. `poll_api()` and `_extract_access_token()` were
    copied **verbatim** (D-08, D-07) for parity and low risk.
  - **Phase:** Phase 1 / Phase 2

- **Decision:** Read a native-Windows OAuth token (install Claude Code on Windows)
  - **Why:** Avoids fragile `\\wsl$`/`wsl.exe` reaching into the WSL filesystem;
    keeps the daemon WSL-independent. Stdlib-only token reader with a 3-path
    fallback + `CLAUDE_CREDENTIALS_PATH` env override.
  - **Phase:** Phase 1 (TOKEN-01)

- **Decision:** Locked WinRT connect recipe
  - **Why:** DIY firmware needs `use_cached_services=False` (WinRT caches the
    GATT table across firmware changes); ESP32/NimBLE uses a static-random
    address → `address_type="random"`; scan-first then pass the `BLEDevice`.
  - **Phase:** Phase 2 (BLE-01, D-05)

- **Decision:** Passive wake detection — no Win32 power events
  - **Why:** The existing 5s tick loop already observes the dead link after wake
    and reconnects within the 120s SLA. Avoids a `pywin32` dependency and
    event-loop plumbing for marginal gain.
  - **Phase:** Phase 3 (D-02)

- **Decision:** Stateless scan-every-cycle — no MAC-address cache
  - **Why:** An ~8s scan-by-name fits comfortably in the 120s reconnect SLA and
    naturally survives the device acquiring a new address. The macOS
    HID-invisibility problem that forced a cache there does not exist on Windows.
  - **Phase:** Phase 3 (D-04)

- **Decision:** Login-startup tray app (not a Windows Service / Scheduled Task)
  - **Why:** Lighter setup, visible status, survives WSL shutdown. pystray status
    icon + `winreg` HKCU\Run autostart via `pythonw.exe` (headless). Service/Task
    parked for v2.
  - **Phase:** Phase 4 (APP-01)

- **Gate decision:** Verify GATT characteristics are unencrypted before building
  - **Why:** Windows auto-bonds HID keyboards; if the custom characteristics
    required encryption, reads would throw `Access Denied` until manually paired.
    Confirmed UNENCRYPTED — no pairing, no firmware change needed.
  - **Phase:** Phase 1 (the de-risk gate)

**Stack:** Python · `bleak` (WinRT) · `httpx` · `pystray` · `Pillow` · stdlib
`winreg` · pytest.

---

## 3. Phases Delivered

| Phase | Name | Status | One-Liner |
|-------|------|--------|-----------|
| 1 | Foundation | ✅ Complete (2026-06-01) | Closed the GATT-encryption gate (UNENCRYPTED → no pairing) and stood up a stdlib Windows-local OAuth token reader. |
| 2 | Core Pipeline | ✅ Complete (2026-06-01) | End-to-end API→BLE pipeline: poll Anthropic, derive the `{s,sr,w,wr,st,ok}` payload, scan/connect over WinRT, write to the GATT RX characteristic. Confirmed on hardware. |
| 3 | Resilience | ✅ Complete (2026-06-02) | Auto-reconnect after sleep / out-of-range / power-cycle with no restart: connect-retry wrapper, zombie-link break, split fast/slow backoff protecting a 120s SLA. |
| 4 | Tray & Autostart | ✅ Complete (2026-06-02) | Login-startup system-tray app (pystray + `winreg` autostart), turnkey `install-windows.ps1`, and verified WSL independence via a static no-WSL-paths guard. |

Phases executed strictly in order 1 → 2 → 3 → 4. All 12 plans complete.

---

## 4. Requirements Coverage

All 7 v1 requirements delivered and hardware-verified (7/7 ✓):

- ✅ **TOKEN-01** — Reads the Claude OAuth token from a native-Windows path (no WSL access) — *Phase 1*
- ✅ **POLL-01** — Polls the Anthropic API and derives session + weekly utilization, mirroring macOS — *Phase 2*
- ✅ **BLE-01** — Discovers/connects over WinRT (`address_type="random"`, `use_cached_services=False`) — *Phase 2*
- ✅ **BLE-02** — Writes usage JSON to the firmware's existing GATT RX characteristic, unchanged wire format — *Phase 2*
- ✅ **BLE-03** — Auto-reconnects after sleep / out-of-range / device drop with no user intervention — *Phase 3*
- ✅ **APP-01** — Runs as a login-startup tray app with a status icon and Quit action — *Phase 4*
- ✅ **APP-02** — Operates fully independent of WSL — connects with the WSL distro stopped — *Phase 4*

**Parked for v2:**
- **PKG-01** — PyInstaller one-file Windows executable (install without a Python environment)
- **PKG-02** — Windows Service / Scheduled Task run model for before-login operation

*No formal milestone audit was run; coverage rests on per-phase verification and
on-hardware UAT records (see Tech Debt).*

---

## 5. Key Decisions Log

| ID | Decision | Phase | Rationale |
|----|----------|-------|-----------|
| D-01 (P1) | GATT characteristics are UNENCRYPTED | 1 | `ble.cpp` §185–199: plain NimBLE flags, no `_ENC`/`_AUTHEN` — no pairing, no firmware change |
| D-02/03/08 (P1) | Priority-ordered token path search + env override; copy `_extract_access_token` verbatim | 1 | First-hit-wins file search; don't import the macOS module (runs Keychain code) |
| D-05 (P2) | Locked WinRT connect recipe | 2 | `BLEDevice` + `address_type="random"` + `use_cached_services=False` |
| D-06 (P2) | Include REQ refresh subscription | 2 | Full macOS parity — device-initiated refresh |
| D-07/08 (P2) | Copy poll/write logic verbatim; compact-JSON payload | 2 | Wire-contract parity, MTU efficiency |
| D-01 (P3) | Connect-retry wrapper (3 tries / 2s) | 3 | Defeats post-wake `Unreachable` / stale `is_connected` |
| D-03 (P3) | Zombie-link break on consecutive failures | 3 | WinRT reports stale `is_connected=True` on dead links after wake |
| D-04 (P3) | No MAC cache — scan every cycle | 3 | Stateless; ~8s scan fits the 120s SLA |
| D-05 (P3) | Split fast-reconnect (8s) vs slow-search (60s) backoff | 3 | Protects the 120s SLA on known-good link drops |
| D-02 (P4) | Single brand mark + colored corner status bubble | 4 | Three states (Connected/Scanning/Error), brand derived from `logo.h` |
| D-08 (P4) | Headless launch via `pythonw.exe` | 4 | No console window on login startup |
| D-10 (P4) | Hardware record + static no-WSL-paths guard | 4 | Independence proven both empirically and by regression test |

---

## 6. Tech Debt & Deferred Items

**Deferred (parked for v2):**
- PyInstaller one-file exe (PKG-01) and Windows Service / Scheduled Task run
  model (PKG-02) — current run model stops at logout, acceptable for an
  always-logged-in desk machine.
- Token-expiry-during-long-disconnect / max-failure give-up behavior — noted as
  a future hardening pass; current per-cycle skip-on-missing carries forward.

**Process debt surfaced in the retrospective:**
- **Requirements/todos bookkeeping drifted from reality.** BLE-03/APP-01/APP-02
  and two todos stayed marked "Pending" even after the phases shipped them — all
  reconciled at milestone close. *Lesson: sync the traceability table at phase
  close, not milestone close.*
- **No formal milestone audit was run** before close — relied on per-phase
  verification/UAT. Fine here because everything was hardware-verified, but it
  left the (stale) requirements table as the only coverage signal.
- **SUMMARY.md one-liner extraction is unreliable** — several files used a
  heading the CLI couldn't parse, so MILESTONES.md accomplishments needed a
  manual rewrite.

**Bug caught & fixed in-milestone:** SC#3 (power-cycle) in Phase 3 surfaced a
daemon-crashing gap (**G-03-01**) in the optional REQ subscription — fixed
TDD-style with graceful degradation (wrap `start_notify` in a broad `except`,
continue the loop) and re-verified to PASS on hardware.

---

## 7. Getting Started

**Run the Windows daemon (turnkey):**
```powershell
# From the repo on a native Windows checkout (NOT a \\wsl$ share):
.\install-windows.ps1   # venv -> pinned deps -> autostart -> launch tray
```
Prerequisite: Claude Code installed **natively on Windows** (`claude login`) so
the daemon can read a Windows-local token. See `daemon/README-windows.md`.

**Key files (Windows daemon):**
- `daemon/claude_usage_daemon_windows.py` — main daemon: token read, API poll, BLE scan/connect/write, reconnect loop (521 LOC)
- `daemon/tray_windows.py` — pystray tray app + `TrayState` thread-safe bridge (276 LOC)
- `daemon/autostart_windows.py` — `winreg` HKCU\Run autostart toggle (108 LOC)
- `daemon/icon_assets.py` — Pillow per-state tray icon compositor (156 LOC)
- `install-windows.ps1` — pure-ASCII PowerShell bootstrap + WSL-path guard
- `daemon/README-windows.md` — install/run docs

**Tests:**
```bash
cd daemon && python -m pytest        # httpx-mocked + BLE-mocked unit suites
```

**Where to look first:** Start with `daemon/claude_usage_daemon_windows.py`
(`main()` → `connect_and_run()`) to follow the scan→connect→poll→write→reconnect
loop. The firmware side and GATT contract are documented in the repo's `CLAUDE.md`
("Daemon / host side") and `.planning/codebase/INTEGRATIONS.md`.

---

## Stats

- **Timeline:** 2026-06-01 → 2026-06-02 (~2 days)
- **Phases:** 4 / 4 complete · **Plans:** 12 / 12 complete · **Tasks:** 13
- **Windows daemon code:** ~1,061 LOC (+ ~3,000 LOC tests)
- **Milestone commits:** ~110 (first phase commit → HEAD)
- **Files changed (incl. planning):** 98 files, +14,820 / -2
- **New runtime deps:** `bleak`, `httpx`, `pystray`, `Pillow`
- **Verification:** Phases 2/3/4 success criteria confirmed on real hardware
- **Contributor:** kvenanzi

---

*Source artifacts: `PROJECT.md`, `v1.0-ROADMAP.md`, `v1.0-REQUIREMENTS.md`,
`RETROSPECTIVE.md`, `STATE.md`, and all phase CONTEXT/SUMMARY/VERIFICATION files.*
