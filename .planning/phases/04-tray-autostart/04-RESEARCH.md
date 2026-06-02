# Phase 4: Tray & Autostart - Research

**Researched:** 2026-06-01
**Domain:** Windows Python desktop integration — system tray (pystray), toast notifications, login autostart (winreg), C-array→PNG asset conversion (Pillow), asyncio/GUI-thread concurrency
**Confidence:** HIGH

## Summary

Phase 4 wraps the already-shipped, unchanged Phase 2/3 asyncio daemon loop
(`daemon/claude_usage_daemon_windows.py`) in a Windows system-tray presentation +
lifecycle/install shell. The entire technical surface is well-trodden, stdlib-or-
small-dependency Windows desktop integration: a tray icon library (`pystray`), an
image library to build the per-state icon (`Pillow`, already installed in the dev
env at 11.2.1), a stdlib registry call for login autostart (`winreg`, in the Python
stdlib — no dependency), and a one-line C-array parse to turn the existing
`firmware/src/logo.h` RGB565A8 logo into a PNG. I verified the full logo→PNG→corner-
bubble pipeline end-to-end with Pillow on this machine and visually confirmed the
output (terracotta crab mark on transparency + green/amber/red corner bubble) — see
Code Examples. [VERIFIED: local Pillow 11.2.1 run, /tmp/logo_test.png + /tmp/icon_connected.png]

The single real architecture question is the **asyncio-loop ↔ tray-main-thread
coexistence** (D-11, Claude's discretion). `pystray.Icon.run()` is blocking and
documented as "must be called from the main thread"; the daemon's `main()` is an
asyncio loop that also conventionally owns the main thread. The canonical, robust
resolution (confirmed against pystray source and docs): **run the asyncio daemon
loop in a background thread via `asyncio.run(main())`, and run pystray on the main
thread via `icon.run(setup=...)`.** State flows loop→tray by the loop calling
`loop.call_soon`-free plain thread-safe setters (the tray only reads simple
state/timestamp values — no cross-loop awaiting needed); Quit flows tray→loop by
scheduling `stop_event.set()` onto the loop with
`loop.call_soon_threadsafe(stop_event.set)`, then `icon.stop()`. This reuses the
existing `stop_event` clean-shutdown hook untouched (SC#3). The inverse split
(asyncio on main, `icon.run_detached()` on a background thread) also works on Win32
— pystray's `_run_detached()` literally just spawns the message loop on a new thread
— but the "tray on main thread" arrangement is the documented-blessed one and avoids
the macOS `NSApplication` caveat entirely. [VERIFIED: pystray 0.19.5 source `_base.py`/`_win32.py`] [CITED: pystray.readthedocs.io]

**Primary recommendation:** Add a new `tray_windows.py` module beside the daemon that
(a) builds three Pillow icon images from `logo.h`, (b) launches `asyncio.run(main(...))`
in a `threading.Thread(daemon=True)` with shared state passed in, (c) runs
`pystray.Icon.run()` on the main thread with a status-header + checkable "Start at
login" + Quit menu, (d) toasts once on Error entry via `icon.notify()` (zero extra
dependency) or `winotify` (if a clickable action is wanted). Autostart = stdlib
`winreg` `HKCU\…\Run` value pointing at the venv `pythonw.exe`. Add `pystray` to
`requirements-windows.txt`; `Pillow` is pulled in transitively but pin it explicitly.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| BLE poll/connect/reconnect loop | Daemon asyncio loop (background thread) | — | Untouched Phase 2/3 substrate; owns `stop_event`, `connect_and_run`, `write_payload` |
| Tray icon render + menu + click handling | Tray (Win32 message loop, main thread) | — | pystray requires the main thread; GUI events pumped here |
| Connection-state model (Connected/Scanning/Error) | Shared state object (thread-safe) | Daemon loop writes, tray reads | Loop is the source of truth; tray is a passive reader |
| Last-sync timestamp | Daemon loop (`write_payload`→True path) | Tray reads for header | Already a bool return; no new plumbing |
| Quit → clean shutdown | Tray click → `stop_event` | Daemon loop unwinds + disconnects | Reuses existing SC#3 hook via `call_soon_threadsafe` |
| Login autostart register/unregister | `winreg` (stdlib) | install-windows.ps1 (bootstrap) | Per-user HKCU, no admin; toggle + installer share one helper |
| Error toast | Tray (`icon.notify` or winotify) | — | Fires only on Error-state entry (D-04) |
| logo.h → PNG icon asset | Pillow (build-time or import-time) | — | One-shot C-array parse + RGB565→RGB888 expand |
| WSL-independence proof | Static unit test + manual hardware record | — | Emergent property; verify, don't build (D-10) |

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Three connection states — Connected / Scanning / Error. "Scanning" subsumes slow-search (device absent) and fast-reconnect (link dropped). "Error" = actionable failures, chiefly missing/expired token (`read_token()`→None, API HTTP 401). Normal connect/scan/reconnect churn is NOT Error.
- **D-02:** Single constant brand mark (always the Anthropic warm clay/terracotta orange, never changes) + a small colored corner bubble: green=connected, amber=scanning, red=error. Only the bubble + tooltip change.
- **D-03:** Base icon derived from `firmware/src/logo.h` (convert 80×80 RGB565[A8] → PNG). Do NOT invent new art. Corner bubble is the only programmatic draw. Pick brand hex from the logo itself.
- **D-04:** Toast on Error state ONLY (e.g. "token expired — run `claude login`"). State transitions otherwise update bubble + tooltip silently. Avoids notification noise.
- **D-05:** Menu = status header (non-clickable: `state + reason + last-sync time`, e.g. `Connected · last update 14:32`, `Scanning…`, `Error: token expired — run claude login`; `—`/`never` before first push) + "Start at login" checkable toggle (reflects current registration on menu open) + Quit (sets `stop_event`, lets loop unwind/disconnect, then exits).
- **D-06:** No usage percentages in the tray — connection status only.
- **D-08:** Headless launch via the venv's `pythonw.exe` + script — no console window (SC#1). Raw-Python autostart (PyInstaller exe is v2).
- **D-09:** `install-windows.ps1` does setup AND enables autostart: create venv → `pip install -r requirements-windows.txt` → register autostart → launch tray app, in one run. The menu toggle then disables/re-enables afterward.
- **D-10:** WSL-independence = manual on-hardware record (SC#4 `wsl --shutdown` leaves link up; SC#5 fresh WSL-never-launched session connects + displays) + automatable static guard asserting daemon source references no `\\wsl$`, `wsl.exe`, `/home`, `/mnt`.

### Claude's Discretion
- **Threading/concurrency model** (asyncio loop vs tray main-thread coexistence, status/last-sync hand-off, Quit join) — architecture is the planner's/executor's call as long as D-01..D-11 hold and loop logic stays untouched. **(See Architecture Patterns → Pattern 1 for the recommended resolution.)**
- **D-07 Autostart mechanism:** `.lnk` in `shell:startup` vs `HKCU\…\Run` value. Both per-user, no-admin. **Lean stdlib-only** (`winreg` Run-key avoids a new dependency a `.lnk` typically needs); choose `.lnk` only if user-discoverability is judged worth the dependency.
- **D-11 Tray library:** Claude's discretion, leaning `pystray` + `Pillow`. Whatever is chosen, add to `requirements-windows.txt` and resolve the asyncio-vs-main-thread coexistence.
- **Exact brand hex** and corner-bubble size/placement — derive from `logo.h`; tune for 16×16/32×32 legibility.
- **Error-state precise triggers** beyond token/auth (e.g. whether sustained BLE failure counts as Error vs lingering Scanning) — planner's call within D-01's intent.
- Reuse the existing `log()` `[HH:MM:SS]` style for new tray/install log lines.

### Deferred Ideas (OUT OF SCOPE)
- **PyInstaller one-file `.exe` packaging** → v2 (PKG-01). Phase 4 ships raw-Python + `pythonw` autostart.
- **Windows Service / Scheduled Task run model** → v2 (PKG-02). Login-startup tray is locked.
- **Usage percentages in the tray** → out of scope (duplicates device screen).
- **Active Win32 power/session-event wake detection** → rejected in Phase 3 (D-02); passive detection stands.
- **Startup self-check log of resolved token path** → considered for D-10, not adopted (could be a debugging aid).

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| APP-01 | Login-startup tray app with status icon + quit action | pystray Icon + Menu (status header / checkable toggle / Quit), Pillow per-state icon from logo.h, winreg HKCU\…\Run autostart, pythonw headless launch — all verified below |
| APP-02 | Operates fully independent of WSL | Emergent from Phase 1 native token read + Phase 2 native BLE; verified by static no-WSL-paths guard (daemon source already clean — confirmed) + manual hardware record (SC#4/SC#5) |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `pystray` | 0.19.5 | System-tray icon, menu, click handling, native toast | The de-facto cross-platform Python tray library; first-class Win32 backend using `Shell_NotifyIcon`; supports dynamic icon image, checkable/radio menu items, runtime `update_menu()`, and `notify()`. License: **LGPL-3.0** (dynamically linked — acceptable; no source-disclosure obligation for the daemon) [VERIFIED: PyPI `pip index versions pystray` → 0.19.5 latest; source headers `_info.py`] |
| `Pillow` | 11.2.1 | Build the per-state tray icon (logo.h → RGBA PNG, resize, composite corner bubble) | Standard Python imaging library; already installed in dev env; `Image.new`/`ImageDraw.ellipse`/`resize(LANCZOS)` cover the entire D-02/D-03 need [VERIFIED: local `import PIL; PIL.__version__` → 11.2.1; full pipeline run] |
| `winreg` | stdlib | Login autostart: create/remove/query `HKCU\…\Run` value (D-07 lean path) | Part of the Python stdlib on Windows — **zero new dependency**, satisfies the Phase 3 D-08 "stdlib-leaning scaffolding" lean [CITED: docs.python.org winreg] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `winotify` | 1.1.0 | Modern Win10/11 toast with optional clickable action button | ONLY if D-04's Error toast wants a clickable action (e.g. a "Copy `claude login`" button). Pure-Python, no native deps. Otherwise NOT needed — `pystray.Icon.notify()` covers a plain Error balloon with zero extra dependency [VERIFIED: PyPI 1.1.0; slopcheck OK] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `pystray.Icon.notify()` (Shell_NotifyIcon balloon) | `winotify` 1.1.0 | pystray.notify: zero new dependency, but legacy balloon — one-at-a-time, queued, 10–30s system timeout, no action buttons. winotify: proper toast + clickable actions, but +1 dependency. For D-04's single rare "token expired" toast, **pystray.notify() is the lean default**; upgrade to winotify only if a clickable remediation button is wanted. [CITED: learn.microsoft.com NOTIFYICONDATAA limits; github.com/versa-syahptr/winotify] |
| `winreg` Run-key (D-07) | `.lnk` in `shell:startup` | Run-key: stdlib-only, easy programmatic create/remove/query, invisible to casual users. `.lnk`: user-discoverable in the Startup folder, but needs `pywin32`/`winshell` or a PowerShell `WScript.Shell.CreateShortcut` shell-out to author the shortcut (+1 dependency or +1 PS dependency). **Recommend Run-key** per D-07's stdlib lean. |
| `pystray` | `infi.systray`, `pywin32` raw `Shell_NotifyIcon` | infi.systray: Windows-only, no per-state dynamic image API as clean, less maintained. Raw pywin32: full control but hand-rolls the message loop, menu, and icon bitmap — exactly the "don't hand-roll" trap. pystray is the right abstraction. |
| asyncio thread + pystray main | `pythonw` + Qt/`pywebview` tray | Heavyweight GUI frameworks are overkill for a status bubble + 3-item menu. |

**Installation:**
```bash
# in requirements-windows.txt (today: bleak, httpx) — add:
pystray
Pillow
# winotify  ← only if Error toast needs a clickable action button (D-04)
```

**Version verification:**
- `pystray` — `pip index versions pystray` → **0.19.5** (latest), released 2023-09-17. [VERIFIED: PyPI]
- `Pillow` — installed **11.2.1**. [VERIFIED: local import]
- `winotify` — `pip index versions winotify` → **1.1.0** (latest). [VERIFIED: PyPI]
- `winreg` — stdlib, no version (ships with CPython on Windows). [CITED: docs.python.org]

## Package Legitimacy Audit

slopcheck 0.6.1 ran clean against all candidates (`slopcheck install pystray winotify Pillow`).

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| `pystray` | PyPI | ~10 yrs (since 2016) | high (widely used) | github.com/moses-palmer/pystray | [OK] | Approved (core) |
| `Pillow` | PyPI | mature, ubiquitous | very high | github.com/python-pillow/Pillow | [OK] | Approved (core) — already installed |
| `winotify` | PyPI | mature | moderate | github.com/versa-syahptr/winotify | [OK] | Approved (optional — only if clickable Error action wanted) |
| `winreg` | stdlib | — | — | CPython stdlib | n/a | stdlib, no install |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

*No postinstall-script risk applies (PyPI wheels, pure-Python except Pillow's vetted C extension). slopcheck was available and returned 3/3 OK, so packages are tagged `[VERIFIED: PyPI]` rather than `[ASSUMED]`.*

## Architecture Patterns

### System Architecture Diagram

```text
            ┌──────────────────────── tray_windows.py (NEW, main thread) ────────────────────────┐
            │                                                                                     │
  Windows   │   build_icons(logo.h) ──► {connected.png, scanning.png, error.png}  [Pillow]        │
  logon ───►│   pythonw.exe tray_windows.py                                                       │
 (HKCU\Run) │        │                                                                            │
            │        ├─► threading.Thread(daemon=True): asyncio.run(main(shared_state, stop_event))│
            │        │                         │                                                  │
            │        │                         ▼                                                  │
            │        │        ┌──── claude_usage_daemon_windows.py (UNCHANGED) ────┐              │
            │        │        │  scan_for_device → connect_and_run → write_payload  │              │
            │        │        │  on success: shared_state.set_connected(ts)         │──┐           │
            │        │        │  on scan/reconnect: shared_state.set_scanning()      │  │ writes    │
            │        │        │  read_token()→None / API 401: set_error("token …")  │  │ state     │
            │        │        └──────────────────────────────────────────────────┘  │           │
            │        │                                                                ▼           │
            │        └─► pystray.Icon.run(setup):  reads shared_state on menu open / refresh tick  │
            │                  • icon.icon = icon_for(state)        (green/amber/red bubble)        │
            │                  • Menu: [status header] [☑ Start at login] [Quit]                    │
            │                  • on Error ENTRY: icon.notify("token expired — run claude login")    │
            │                  • Quit → loop.call_soon_threadsafe(stop_event.set); icon.stop()      │
            │                  • Start-at-login toggle → autostart.enable()/disable()  [winreg]     │
            └─────────────────────────────────────────────────────────────────────────────────────┘

  install-windows.ps1 (NEW): venv → pip install -r requirements-windows.txt
                             → autostart.enable() (winreg HKCU\Run → pythonw + tray_windows.py)
                             → launch tray app
```

The daemon loop (left) is the unchanged source of truth; the tray (right) is a passive
reader of a shared thread-safe state object + a writer of `stop_event` via the loop.

### Recommended Project Structure
```text
daemon/
├── claude_usage_daemon_windows.py   # UNCHANGED — loop, BLE, poll, reconnect
├── tray_windows.py                  # NEW — tray entry: icons, menu, state bridge, Quit
├── autostart_windows.py             # NEW — winreg HKCU\Run enable/disable/is_enabled (pure logic, testable)
├── icon_assets.py  (or in tray)     # NEW — logo.h → PNG + corner-bubble compositor (pure logic, testable)
├── requirements-windows.txt         # +pystray +Pillow
├── README-windows.md                # extend "What is NOT covered" → document tray/autostart/install
└── tests/
    ├── test_windows_autostart.py    # NEW — toggle logic (winreg mocked)
    ├── test_windows_icon.py         # NEW — logo parse + RGB565→888 + state→image mapping
    └── test_windows_no_wsl.py       # NEW — static no-WSL-paths guard (D-10)
install-windows.ps1                  # NEW (repo root or daemon/) — bootstrap + autostart + launch (D-09)
```
Note `daemon/` already has `__init__.py`, `tests/__init__.py`, `tests/fixtures/`, and a
root `conftest.py` that puts the repo root on `sys.path` so `import daemon.*` resolves.
New tests follow the existing `daemon/tests/test_windows_*.py` convention. [VERIFIED: ls + read]

### Pattern 1: asyncio loop in background thread, pystray on main thread (RECOMMENDED — D-11)
**What:** Run the daemon's `asyncio.run(main(...))` inside a `threading.Thread(daemon=True)`;
run `pystray.Icon.run()` on the main thread. The tray reads a shared state object; Quit
schedules `stop_event.set()` onto the loop with `loop.call_soon_threadsafe`.
**When to use:** This phase — pystray docs state `run()` "*must* be called from the main thread."
**Why this over the inverse:** `icon.run_detached()` (tray on a background thread, asyncio
on main) also works on Win32 — `_run_detached()` just does `threading.Thread(target=self._run).start()`
[VERIFIED: pystray `_win32.py:130`] — but the documented-blessed arrangement is tray-on-main,
and it sidesteps the macOS `NSApplication` caveat run_detached carries. Either is acceptable
under D-11; the planner picks one. The key invariants both share: **the daemon loop logic is
untouched**, and **Quit routes through the existing `stop_event`**.
**Example:** see Code Examples → "Tray + asyncio coexistence skeleton".

### Pattern 2: Thread-safe state hand-off (loop → tray)
**What:** A small `TrayState` object holding `state` (enum), `reason` (str), `last_sync` (float|None),
guarded by a `threading.Lock` (or just atomic attribute writes — the tray only reads scalars).
The loop calls `state.set_connected(time.time())` / `set_scanning()` / `set_error(reason)` at the
existing decision points (`write_payload`→True, scan/reconnect branches, `read_token()`→None / API 401).
The tray reads it on menu-open and on a periodic `icon.update_menu()` / `icon.icon = …` refresh.
**Why:** No cross-loop awaiting needed — state is plain scalars. Avoids `run_coroutine_threadsafe`
complexity. The daemon stays untouched except for cheap setter calls injected at existing branch points
(additive, no logic change).

### Pattern 3: Quit join (tray → loop → clean disconnect)
**What:** Quit menu action does: `loop.call_soon_threadsafe(stop_event.set)` then `icon.stop()`.
The existing `main()` while-loop sees `stop_event.is_set()`, unwinds `connect_and_run`'s `finally:
await client.disconnect()`, and returns; the background thread's `asyncio.run` completes; the daemon
thread (being `daemon=True`) won't block process exit. **Reuses the existing SC#3 hook** — `stop_event`
is already wired to SIGINT/SIGTERM; Quit is just a third trigger, exactly as CONTEXT.md describes.

### Anti-Patterns to Avoid
- **Calling `stop_event.set()` directly from the tray thread.** `asyncio.Event` is not thread-safe;
  set it via `loop.call_soon_threadsafe(stop_event.set)`. [CITED: docs.python.org asyncio-dev]
- **Rebuilding the daemon as a tray-driven state machine.** Strictly additive — inject setter calls,
  don't restructure the loop. CONTEXT.md locks "loop logic stays untouched."
- **Regenerating the icon image on every refresh tick.** Build the three state images once at startup;
  swap `icon.icon = self._images[state]` — cheap. Pillow compositing per-tick is wasteful.
- **Using `HKLM\…\Run` for autostart.** Needs admin; D-07 is explicitly per-user `HKCU` (no elevation).
- **Pointing the Run-key at `python.exe`.** Spawns a console window. Must be `pythonw.exe` (D-08).
- **Hard-coding an absolute venv path in the installer that breaks when the repo moves** — derive
  `pythonw.exe` from `sys.executable` / the venv `Scripts/` dir at install time (mirrors the macOS
  daemon's "repoint ExecStart" lesson in CLAUDE.md).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Tray icon + Win32 message loop | Raw `ctypes` `Shell_NotifyIcon` + `WM_*` pump + popup menu | `pystray` | pystray already wraps the window class, message loop, icon registration, menu HMENU, and click dispatch — hand-rolling re-implements `_win32.py` (390 lines of ctypes) |
| Per-state icon image | Manual bitmap byte-poking | `Pillow` `Image`/`ImageDraw` | resize + alpha composite + ellipse are one-liners; verified working |
| Toast notification | Raw WinRT `ToastNotificationManager` ctypes | `pystray.Icon.notify()` (or `winotify`) | pystray.notify is one call; winotify wraps WinRT toast XML |
| Registry autostart | Shelling out to `reg add`/`reg delete` | stdlib `winreg` | `winreg` is in-process, typed, and testable with mocks; no subprocess parsing |
| RGB565→RGB888 | Approximate `*8` bit-shift | Proper `(v*255 + max/2)//max` rounding | bit-shift loses the low bits; proper rounding matches the firmware's panel rendering |

**Key insight:** Every piece of this phase has a mature, single-call abstraction.
The only genuinely custom code is ~15 lines of logo.h parsing + the state→image
mapping + the winreg toggle — all pure, deterministic, and unit-testable (which is
exactly what TDD mode + the Validation Architecture below target).

## Runtime State Inventory

> Rename/refactor inventory is not the dominant concern here (this is additive net-new
> code, not a rename), but Phase 4 *introduces* persistent OS-registered state — the
> autostart entry — which the inventory framing catches.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — tray reads in-memory state only; no new on-disk cache (Phase 3 D-04 rejected a MAC cache and that stands). | none |
| Live service config | **NEW: HKCU\Software\Microsoft\Windows\CurrentVersion\Run** value (e.g. `Clawdmeter`) created by the autostart toggle / installer. Lives in the registry, not git. | The "Start at login" toggle and an uninstall path must be able to *remove* it; document in README so a user can clean up manually (`reg delete`). |
| OS-registered state | The same HKCU\Run value is the OS-registered autostart hook (no Task Scheduler / Service — those are v2). | Toggle create/remove; installer registers it (D-09). |
| Secrets/env vars | None new. Token still read by the unchanged `read_token()` from native-Windows credential paths (Phase 1). `CLAUDE_CREDENTIALS_PATH` / `CLAUDE_CONFIG_DIR` overrides unchanged. | none |
| Build artifacts | venv created by `install-windows.ps1` (`.venv\Scripts\pythonw.exe` is the autostart target). If the repo/venv moves, the Run-key path goes stale. | Installer derives the path at install time; document re-run on move. |

## Common Pitfalls

### Pitfall 1: pystray `run()` blocks the main thread → asyncio can't also own it
**What goes wrong:** Naively calling both `asyncio.run(main())` and `icon.run()` on the
main thread deadlocks — whichever runs first never returns.
**Why it happens:** Both are blocking main-loops by design.
**How to avoid:** Pick ONE for the main thread (recommend pystray) and run the other in a
background thread (Pattern 1). [VERIFIED: pystray `_base.py:191` docstring "*must* be called from the main thread"]
**Warning signs:** App launches, tray icon never appears, or device never connects.

### Pitfall 2: Setting `asyncio.Event` from the tray thread
**What goes wrong:** Quit appears to fire but the loop never stops, or a "event loop is
not running"/threading error surfaces intermittently.
**Why it happens:** `asyncio.Event.set()` is not thread-safe; calling it from the tray
(non-loop) thread races the loop.
**How to avoid:** `loop.call_soon_threadsafe(stop_event.set)`; capture the `loop` reference
when the daemon thread starts (`asyncio.get_running_loop()` inside `main()`, hand it back via
the shared state). [CITED: docs.python.org asyncio-dev "Concurrency and Multithreading"]

### Pitfall 3: Console window flashes on login
**What goes wrong:** A black terminal appears at every logon.
**Why it happens:** The Run-key points at `python.exe`, which allocates a console.
**How to avoid:** Point at the venv's `pythonw.exe` (D-08). Verify the resolved path ends in
`pythonw.exe`, not `python.exe`. [CITED: docs.python.org "python.exe vs pythonw.exe"; geeksforgeeks autorun]

### Pitfall 4: Lucide-style black-on-transparent icon renders invisible (cross-check from firmware)
**What goes wrong:** Icon shows as a blank/black square at tray size.
**Why it happens:** The firmware icon convention is black-on-transparent that must be tinted.
**For logo.h specifically this is NOT an issue** — I verified the logo is already a colored
(terracotta #DE7552) mark with a real alpha plane, not black-on-transparent. [VERIFIED: parsed
logo.h, dominant opaque color = RGB565 0xDBAA = #DE7552, alpha plane present]. Listed only so the
planner doesn't re-apply the firmware tint step.

### Pitfall 5: Balloon toast queued/suppressed (D-04)
**What goes wrong:** The Error toast doesn't appear, or appears seconds late.
**Why it happens:** Shell_NotifyIcon shows one balloon at a time, queues the rest, with a
10–30s system timeout, and a hidden tray icon can't raise a balloon. [CITED: learn.microsoft.com NOTIFYICONDATAA]
**How to avoid:** Fire the toast only on *transition into* Error (D-04 already mandates this —
not on every Error-state tick), and ensure the icon is visible. If reliable modern toast is
required, use `winotify`. Acceptable for D-04's rare token-expiry case either way.

### Pitfall 6: "Start at login" checkmark out of sync with reality
**What goes wrong:** The toggle shows checked but the Run-key was deleted externally (or vice versa).
**How to avoid:** Make the menu item's `checked=` a *callable* that queries `winreg` live on each
menu open (pystray supports dynamic `checked`), not a cached boolean. [VERIFIED: pystray `_base.py:445` `checked` accepts a callable]. Call `icon.update_menu()` after toggling.

## Code Examples

### logo.h → RGBA PNG + corner-bubble state icon (verified end-to-end on this machine)
```python
# Source: VERIFIED locally — /tmp/logo_test.png (mark) and /tmp/icon_connected.png (bubble)
# Pillow 11.2.1. logo.h is RGB565A8: 6400 little-endian RGB565 pixels then 6400 alpha bytes.
import re
from PIL import Image, ImageDraw

W = H = 80  # LOGO_WIDTH / LOGO_HEIGHT from logo.h

def _expand565(v: int) -> tuple[int, int, int]:
    r5, g6, b5 = (v >> 11) & 0x1F, (v >> 5) & 0x3F, v & 0x1F
    # proper rounding, NOT a *8 shift — matches panel rendering
    return (r5 * 255 + 15) // 31, (g6 * 255 + 31) // 63, (b5 * 255 + 15) // 31

def load_logo_rgba(header_path: str) -> Image.Image:
    txt = open(header_path).read()
    body = re.search(r'logo_data\[\d+\]\s*=\s*\{(.*?)\};', txt, re.S).group(1)
    b = [int(x, 16) for x in re.findall(r'0x([0-9A-Fa-f]{2})', body)]
    n = W * H
    rgb, alpha = b[: n * 2], b[n * 2 : n * 2 + n]
    img = Image.new("RGBA", (W, H))
    px = img.load()
    for i in range(n):
        v = rgb[i * 2] | (rgb[i * 2 + 1] << 8)   # little-endian
        r, g, bb = _expand565(v)
        px[i % W, i // W] = (r, g, bb, alpha[i])
    return img

# Brand hex derived from the logo itself (D-03): dominant opaque color = #DE7552
BUBBLE = {"connected": (60, 200, 90, 255),   # green
          "scanning":  (240, 180, 40, 255),  # amber
          "error":     (220, 60, 60, 255)}   # red

def state_icon(base: Image.Image, state: str, size: int = 32) -> Image.Image:
    icon = base.resize((size, size), Image.LANCZOS).convert("RGBA")
    d = ImageDraw.Draw(icon)
    r = size // 3                      # corner bubble ~1/3 of the icon
    d.ellipse([size - r, size - r, size - 2, size - 2], fill=BUBBLE[state])
    return icon
```

### Tray + asyncio coexistence skeleton (Pattern 1 — RECOMMENDED)
```python
# Source: composed from VERIFIED pystray 0.19.5 API + CITED docs.python.org asyncio-dev
import asyncio, threading, time
import pystray
from pystray import Menu, MenuItem
import autostart_windows as autostart  # winreg helper, see below

class TrayState:
    """Thread-safe scalar bridge: daemon loop writes, tray reads."""
    def __init__(self):
        self.state = "scanning"; self.reason = ""; self.last_sync = None
        self.loop = None; self.stop_event = None
    def set_connected(self, ts): self.state, self.reason, self.last_sync = "connected", "", ts
    def set_scanning(self): self.state, self.reason = "scanning", ""
    def set_error(self, why): self.state, self.reason = "error", why

def _daemon_thread(ts: TrayState):
    # asyncio owns THIS thread. main() must accept (state, stop_event) — additive params,
    # or store loop+stop_event onto ts from inside main() at startup.
    asyncio.run(daemon_main(ts))   # daemon_main wraps the unchanged loop + injected setters

def _header_text(ts):
    if ts.state == "connected":
        when = time.strftime("%H:%M", time.localtime(ts.last_sync)) if ts.last_sync else "never"
        return f"Connected · last update {when}"
    if ts.state == "scanning": return "Scanning…"
    return f"Error: {ts.reason}"

def build_menu(ts, icon, images):
    def on_quit(_icon, _item):
        ts.loop.call_soon_threadsafe(ts.stop_event.set)   # thread-safe!
        _icon.stop()
    def on_toggle(_icon, _item):
        (autostart.disable if autostart.is_enabled() else autostart.enable)()
        _icon.update_menu()
    return Menu(
        MenuItem(lambda item: _header_text(ts), None, enabled=False),     # non-clickable header
        MenuItem("Start at login", on_toggle, checked=lambda item: autostart.is_enabled()),
        MenuItem("Quit", on_quit),
    )

def main():
    base = load_logo_rgba("firmware/src/logo.h")
    images = {s: state_icon(base, s) for s in ("connected", "scanning", "error")}
    ts = TrayState()
    icon = pystray.Icon("Clawdmeter", images["scanning"], "Clawdmeter")
    icon.menu = build_menu(ts, icon, images)
    threading.Thread(target=_daemon_thread, args=(ts,), daemon=True).start()

    prev = {"state": None}
    def refresh(_icon):                  # setup callback: runs in pystray's setup thread
        _icon.visible = True
        while _icon._running:            # cheap poll; or hook into state changes
            if ts.state != prev["state"]:
                _icon.icon = images[ts.state]
                _icon.title = _header_text(ts)
                if ts.state == "error" and prev["state"] != "error":
                    _icon.notify(ts.reason or "Clawdmeter error", "Clawdmeter")  # D-04 toast on ENTRY
                prev["state"] = ts.state
                _icon.update_menu()
            time.sleep(1.0)
    icon.run(setup=refresh)              # BLOCKS on main thread until icon.stop()

if __name__ == "__main__":
    main()
```

### winreg autostart toggle (stdlib, testable — D-07 lean path)
```python
# Source: VERIFIED API names against stdlib winreg + CITED docs.python.org/3/library/winreg.html
import os, sys, winreg

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "Clawdmeter"

def _command() -> str:
    # D-08: pythonw.exe (no console) from the active venv + this tray script
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    script = os.path.abspath(__file__)  # or the tray entry path
    return f'"{pyw}" "{script}"'

def enable() -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, _VALUE_NAME, 0, winreg.REG_SZ, _command())

def disable() -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, _VALUE_NAME)
    except FileNotFoundError:
        pass  # already absent — idempotent

def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_QUERY_VALUE) as k:
            winreg.QueryValueEx(k, _VALUE_NAME)
            return True
    except FileNotFoundError:
        return False
```
HKCU is per-user and needs **no admin elevation**. [CITED: docs.python.org winreg; daniweb/geeksforgeeks autorun]

### Static no-WSL-paths guard (D-10 — automatable regression lock)
```python
# Source: composed; daemon source VERIFIED already clean (grep found NONE)
import re
from pathlib import Path

FORBIDDEN = [r"\\wsl\$", r"wsl\.exe", r"/home/", r"/mnt/"]

def test_daemon_has_no_wsl_paths():
    src = Path("daemon/claude_usage_daemon_windows.py").read_text()
    for pat in FORBIDDEN:
        assert not re.search(pat, src), f"WSL path leaked into daemon: {pat}"
    # extend to tray_windows.py / autostart_windows.py once they exist
```
Confirmed today: `grep -niE '\\wsl\$|wsl\.exe|/home/|/mnt/' daemon/claude_usage_daemon_windows.py` → no matches. [VERIFIED: local grep]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `win10toast` for toasts | `winotify` / `windows-toasts` (or pystray.notify for simple balloon) | win10toast is effectively unmaintained, throws on modern Windows | Don't use win10toast; pystray.notify covers D-04, winotify if action needed |
| `infi.systray` | `pystray` | pystray is cross-platform + actively maintained | pystray is the standard tray choice |
| Hand-rolled `reg add` shell-out | stdlib `winreg` | always preferred | In-process, testable |

**Deprecated/outdated:**
- `win10toast` — abandoned, breaks on current Windows; do not add.
- `pywin32` raw `Shell_NotifyIcon` for a tray app — superseded by pystray for this use case.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Brand hex is **#DE7552** (the dominant opaque RGB565 color in logo.h). The 9 other opaque shades are anti-alias neighbors. | D-03 / Code Examples | Low — derived directly from the asset; if the planner wants a different anchor pixel it's a one-line change. The mark renders in its native colors anyway (D-02 says "rendered in the brand color" — the logo *is* already that color). |
| A2 | `pystray.Icon.notify()` (Shell_NotifyIcon balloon) is sufficient for D-04's single Error toast; winotify only needed for a clickable action. | Standard Stack / Pitfall 5 | Low — balloon is visible and adequate for a rare token-expiry alert; winotify is a documented drop-in upgrade if the user wants a button. |
| A3 | Pattern 1 (asyncio in background thread, pystray on main) is the right split vs the inverse run_detached. Both verified to work; this is a recommendation, not a hard constraint (D-11 is explicitly discretion). | Architecture Patterns | None — planner may choose either; invariants (untouched loop, stop_event Quit) hold for both. |
| A4 | `main()` can accept the shared state/stop_event without changing loop *logic* (additive params + injected setter calls at existing branch points). | Pattern 2/3 | Low — `main()` already creates `stop_event` and captures `loop`; exposing them is additive. If the executor prefers, the tray can read `loop`/`stop_event` off the state object the loop populates at startup instead of via params. |

## Open Questions

1. **Exact corner-bubble size/placement at 16×16.** Verified clean at 32×32; at 16×16 a 1/3-radius
   bubble may crowd the mark. Recommendation: executor renders both 16 and 32 PNGs and eyeballs;
   the device's own `screenshot.sh` QA discipline (CLAUDE.md) doesn't apply here (it's a desktop
   icon) — just open the PNGs. Tune radius constant in `state_icon()`.
2. **Does the daemon's `main()` need a small refactor to accept `(state, stop_event)`, or should the
   tray pull `loop`/`stop_event` off a shared object the loop sets at startup?** Either is additive;
   planner's call (A4). Recommendation: pass a `TrayState` in and have `main()` populate `ts.loop`/
   `ts.stop_event` at the top — keeps the existing `stop_event = asyncio.Event()` line intact.
3. **Error-state trigger breadth (D-01 discretion):** token None / API 401 are clearly Error. Whether
   a *sustained* BLE failure (many reconnect cycles) escalates Scanning→Error is left to the planner;
   recommend keeping BLE churn as Scanning (D-01 says routine reconnect is NOT Error) and only flagging
   Error on the token/auth path, to honor D-04's "no noise."

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Everything | ✓ (dev box 3.10.12; target Win 3.11+) | 3.10.12 here | — |
| pytest | Unit tests (TDD) | ✓ | 8.4.2 | — |
| Pillow | Icon conversion | ✓ | 11.2.1 | — |
| pystray | Tray app | ✓ installed; **imports only on Windows/macOS/X11** | 0.19.5 | On this Linux dev box pystray's top-level import fails (no GTK) — *expected*; tray code is Windows-target. Test icon/autostart logic in isolation (mock winreg, import Pillow only). |
| winreg | Autostart | ✗ on Linux (Windows stdlib only) | — | Tests must mock `winreg` (the module isn't importable off-Windows) — guard imports or inject. |
| pythonw.exe | Headless launch | (Windows only) | — | Target-only; not present on dev box. |
| pywin32 / winotify | optional toast action | not installed (winotify verified on PyPI) | — | pystray.notify needs neither. |

**Missing dependencies with no fallback:** none (all blocking deps are Windows-runtime-only and tested via mocks).
**Missing dependencies with fallback:**
- `pystray` import + `winreg` are Windows-only → unit tests must isolate pure logic (icon math, autostart command-string construction, state→image mapping) and **mock `winreg`** / avoid importing the pystray top-level on the CI/dev box. This mirrors how the existing reconnect tests mock `bleak`.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.4.2 [VERIFIED: local] |
| Config file | none dedicated; root `conftest.py` adds repo root to `sys.path` for `import daemon.*` [VERIFIED: read] |
| Quick run command | `python -m pytest daemon/tests/test_windows_autostart.py daemon/tests/test_windows_icon.py daemon/tests/test_windows_no_wsl.py -x -q` |
| Full suite command | `python -m pytest daemon/tests/ -q` (currently 47 passing) [VERIFIED: ran, 47 passed] |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| APP-01 | Autostart enable writes HKCU\Run = pythonw + script | unit (mock winreg) | `pytest daemon/tests/test_windows_autostart.py::test_enable_writes_pythonw_command -x` | ❌ Wave 0 |
| APP-01 | Autostart disable removes value, idempotent on absent | unit (mock winreg) | `pytest daemon/tests/test_windows_autostart.py::test_disable_idempotent -x` | ❌ Wave 0 |
| APP-01 | is_enabled reflects presence/absence | unit (mock winreg) | `pytest daemon/tests/test_windows_autostart.py::test_is_enabled -x` | ❌ Wave 0 |
| APP-01 | logo.h parses to 80×80 RGBA; dominant color = #DE7552 | unit | `pytest daemon/tests/test_windows_icon.py::test_logo_parse -x` | ❌ Wave 0 |
| APP-01 | RGB565→RGB888 rounding (0xDBAA→(222,117,82)) | unit | `pytest daemon/tests/test_windows_icon.py::test_rgb565_expand -x` | ❌ Wave 0 |
| APP-01 | state→image mapping returns distinct images per state; bubble color matches | unit | `pytest daemon/tests/test_windows_icon.py::test_state_icon_bubble -x` | ❌ Wave 0 |
| APP-01 | pythonw command string ends in `pythonw.exe` (D-08, no console) | unit | `pytest daemon/tests/test_windows_autostart.py::test_command_uses_pythonw -x` | ❌ Wave 0 |
| APP-02 | daemon source references no `\\wsl$`/`wsl.exe`/`/home`/`/mnt` | unit (static) | `pytest daemon/tests/test_windows_no_wsl.py -x` | ❌ Wave 0 |
| APP-01 | tray icon visible; hover/click shows status (Connected/Scanning/Error) | manual hardware record | — (on-device, SC#2) | manual |
| APP-01 | Quit stops daemon cleanly (stop_event → disconnect → exit) | manual hardware record | — (SC#3); optionally unit-test the Quit handler calls `call_soon_threadsafe(stop_event.set)` with a mocked loop | partial |
| APP-01 | no terminal window at logon | manual hardware record | — (SC#1) | manual |
| APP-02 | `wsl --shutdown` leaves link up; fresh WSL-never-launched session connects | manual hardware record | — (SC#4, SC#5) | manual |

### Sampling Rate
- **Per task commit:** quick run (the three new test files) — < 5s.
- **Per wave merge:** full suite `python -m pytest daemon/tests/ -q` (47 + new).
- **Phase gate:** full suite green + the manual hardware record for SC#1–#5 captured before `/gsd:verify-work` (mirrors Phase 1/2/3 D-06 split, reused by D-10).

### Wave 0 Gaps
- [ ] `daemon/tests/test_windows_autostart.py` — covers APP-01 (winreg toggle; mock `winreg`)
- [ ] `daemon/tests/test_windows_icon.py` — covers APP-01 (logo parse, RGB565→888, state→image)
- [ ] `daemon/tests/test_windows_no_wsl.py` — covers APP-02 (static no-WSL-paths guard, D-10)
- [ ] Import isolation so pystray's GTK-less top-level import doesn't break CI: keep `import pystray`
      inside `tray_windows.main()` (not module top) OR guard tests to import only the pure helpers.
      `winreg` import must be Windows-guarded or mocked (it's not importable off-Windows).
- [ ] No framework install needed — pytest 8.4.2 + Pillow 11.2.1 already present.

## Project Constraints (from CLAUDE.md)

CLAUDE.md is firmware-centric, but the binding constraints for this Python-side phase:
- **`logo.h` is the brand asset** (RGB565A8 — `w*h` RGB565 then `w*h` alpha; little-endian). Reuse it for the tray icon; do not author new art (echoes D-03 and the user-profile note "dislikes me authoring my own art when third-party assets are intended"). [VERIFIED: read logo.h header comment + parse]
- **Reuse the existing `log()` `[HH:MM:SS]` stdout style** for new tray/install log lines (CONTEXT.md + the daemon's `log()` at L53).
- **Strictly additive — no firmware, no macOS/Linux daemon edits** (PROJECT.md "ship its own daemon, don't refactor into a shared codebase"). The macOS daemon has NO tray code to copy (confirmed). [VERIFIED: grep]
- **Daemon "repoint the absolute path when switching checkouts" lesson** (CLAUDE.md daemon section): the autostart Run-key must derive `pythonw.exe`/script paths at install time, not hard-code a stale absolute path.

## Security Domain

> `security_enforcement` is not set in config.json (treated as enabled). Phase 4 is a local
> desktop integration with a narrow surface; most ASVS web categories N/A.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | indirect | OAuth token read by unchanged `read_token()` (Phase 1) — Phase 4 does not touch it |
| V3 Session Management | no | — |
| V4 Access Control | yes (light) | Autostart writes **HKCU** only (per-user, no admin elevation — D-07). Never HKLM. |
| V5 Input Validation | yes (light) | logo.h is a trusted in-repo asset; the C-array parse should still bound-check (`len == w*h*3`) before indexing — the verified example asserts this. |
| V6 Cryptography | no | Phase 4 hand-rolls no crypto; GATT confirmed unencrypted in Phase 1 (settled). |
| V7 Error Handling/Logging | yes | Reuse `log()`; never log the token (existing redaction in the daemon stands — Phase 4 adds no token logging). The D-10 "log resolved token path" idea was explicitly NOT adopted. |

### Known Threat Patterns for a Windows tray/autostart app
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Run-key abused for persistence (this is a *legitimate* use — but malware uses the same key) | Elevation/Persistence | HKCU-only, no admin, value clearly named `Clawdmeter`, removable via the toggle + documented in README |
| Stale/spoofed autostart path after repo move | Tampering | Derive path from `sys.executable` at install time; document re-run |
| Token leaked to logs via new tray log lines | Information Disclosure | Phase 4 logs state/last-sync only — never the token; D-10's token-path log not adopted |
| Untrusted icon data | Tampering | logo.h is in-repo & trusted; bound-check the parse anyway (V5) |

## Sources

### Primary (HIGH confidence)
- pystray 0.19.5 **source** (`_base.py`, `_win32.py`, `_info.py`) read directly in site-packages — verified `run`/`run_detached`/`stop`/`update_menu`/`notify`, `HAS_NOTIFICATION/HAS_MENU/HAS_MENU_RADIO=True`, `MenuItem(text, action, checked=callable, radio, default, enabled)`, win32 `_notify` uses `Shell_NotifyIcon` `NIF_INFO`, `_run_detached` spawns a thread.
- Local verification: Pillow 11.2.1 logo.h→RGBA→bubble pipeline (`/tmp/logo_test.png`, `/tmp/icon_connected.png`), `grep` no-WSL-paths clean, `pytest daemon/tests/` 47 passed, slopcheck 0.6.1 → 3/3 OK, `pip index versions` for pystray/winotify/windows-toasts/win10toast.
- [pystray reference docs](https://pystray.readthedocs.io/en/latest/reference.html) — `run`/`run_detached` main-thread requirement.
- [docs.python.org winreg](https://docs.python.org/3/library/winreg.html) — HKCU Run-key API.
- [docs.python.org asyncio-dev](https://docs.python.org/3/library/asyncio-dev.html) — thread-safety, `call_soon_threadsafe`.
- [learn.microsoft.com NOTIFYICONDATAA](https://learn.microsoft.com/en-us/windows/win32/api/shellapi/ns-shellapi-notifyicondataa) — balloon limits.

### Secondary (MEDIUM confidence)
- [pystray usage.rst](https://github.com/moses-palmer/pystray/blob/master/docs/usage.rst) — checkable items, run_detached intent (example code thin; backfilled from source).
- [winotify (PyPI / GitHub)](https://pypi.org/project/winotify/) — actionable toast, pure-python.
- [GeeksforGeeks / DaniWeb autorun-on-startup](https://www.geeksforgeeks.org/python/autorun-a-python-script-on-windows-startup/) — winreg Run-key + pythonw pattern.

### Tertiary (LOW confidence)
- General community discussion on asyncio-event-loop-in-thread (SuperFastPython, gist) — pattern corroboration only; superseded by stdlib docs.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions verified on PyPI, slopcheck clean, Pillow/pytest run locally, pystray API read from source.
- Architecture (asyncio↔tray): HIGH — main-thread requirement and run_detached behavior verified against pystray source + docs; thread-safety per stdlib docs.
- Icon pipeline: HIGH — full logo.h→PNG→bubble run and visually confirmed; brand hex parsed from the asset.
- Autostart (winreg): HIGH — stdlib API; daemon already WSL-clean (verified).
- Pitfalls: HIGH — each tied to a verified source or local observation.

**Research date:** 2026-06-01
**Valid until:** 2026-07-01 (stable ecosystem; pystray/Pillow/winreg are mature and slow-moving)
