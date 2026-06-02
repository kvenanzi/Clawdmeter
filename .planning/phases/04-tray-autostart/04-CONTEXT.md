# Phase 4: Tray & Autostart - Context

**Gathered:** 2026-06-02
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase **wraps the existing Phase 2/3 Windows daemon run-loop**
(`daemon/claude_usage_daemon_windows.py`) in a **system-tray app** that surfaces
connection status and a clean Quit, registers it to **launch at Windows logon
with no terminal window**, and **verifies the daemon is fully independent of WSL**.

It is **not a rewrite and not a refactor.** The asyncio `main()` loop, BLE recipe,
polling, reconnect hardening (D-01..D-06), and wire protocol all stay exactly as
shipped. Phase 4 adds a tray presentation layer + lifecycle/install shell **on top
of** that loop, hooking the existing `stop_event` for clean shutdown. Strictly
additive to the Windows daemon — **no firmware, no macOS/Linux daemon edits**
(locked PROJECT.md "ship its own daemon, don't refactor into a shared codebase"
boundary).

Satisfies **APP-01** (login-startup tray app with status icon + quit) and
**APP-02** (operates fully independent of WSL).

**Success criteria (from ROADMAP):**
1. Installs a startup entry; launches automatically on logon, **no terminal window**.
2. Tray icon visible; hover/click shows current status (connected / scanning / error).
3. Right-click → **Quit** stops the daemon cleanly.
4. `wsl --shutdown` does **not** disconnect the Clawdmeter or error the daemon.
5. Fresh Windows session (WSL never launched) → device connects and shows usage normally.

**Explicitly NOT in this phase:**
- PyInstaller one-file `.exe` packaging → **v2 (PKG-01)**.
- Windows Service / Scheduled Task run model → **v2 (PKG-02)** (login-startup tray is locked).
- Active Win32 power/session-event wake detection → rejected in Phase 3 (D-02); passive detection stands.
- Surfacing usage percentages in the tray → out of scope (the device screen already shows them; APP-01 is *connection status*).
- Any change to polling logic, the BLE recipe, the wire protocol, or the macOS/Linux daemons/firmware.

</domain>

<decisions>
## Implementation Decisions

### Tray icon — states & visuals (APP-01, SC#2)
- **D-01: Three connection states — Connected / Scanning / Error.** Matches SC#2
  exactly. "Scanning" subsumes both the slow-search (device absent) and
  fast-reconnect (link dropped) regimes from Phase 3 D-05. "Error" covers
  actionable failures — chiefly missing/expired token (`read_token()` → None, API
  HTTP 401). Normal connect/scan/reconnect churn is **not** an error state.
- **D-02: Single constant brand mark + colored corner status bubble.** The tray
  icon is **one** Clawdmeter mark, always rendered in the **Anthropic Claude brand
  color** (warm clay/terracotta orange), that never changes. State is conveyed by a
  **small colored bubble overlaid in the corner**: green = connected, amber =
  scanning, red = error. The base mark stays recognizable at notification-area size;
  only the bubble + tooltip change.
- **D-03: Base icon derived from `firmware/src/logo.h`.** Convert the existing
  80×80 RGB565 brand logo to a PNG for the tray — reuse the real on-device brand
  mark, **do not invent new art**. The corner status bubble is the only thing drawn
  programmatically (a small filled circle composited onto the base). Pick the brand
  hex from the logo itself.
- **D-04: Toast on Error state only.** State transitions update the corner bubble +
  tooltip silently; a Windows toast/balloon fires **only** when entering the Error
  state (e.g. "token expired — run `claude login`"). Avoids notification noise from
  routine sleep/range reconnect churn on an always-on desk monitor.

### Tray menu — actions (APP-01, SC#3)
- **D-05: Menu = status header + "Start at login" toggle + Quit.**
  - **Status header** (non-clickable): shows `state + reason + last-sync time`, e.g.
    `Connected · last update 14:32`, `Scanning…`, `Error: token expired — run claude login`.
    Last-sync timestamp is tracked off the existing successful `write_payload()`
    path; before the first successful push, show `—`/`never`.
  - **"Start at login"** checkable toggle — enables/disables autostart at runtime
    (see D-07). Reflects current registration state on menu open.
  - **Quit** — sets the existing `stop_event`, lets the asyncio loop unwind and
    disconnect cleanly, then exits (SC#3).
- **D-06: No usage percentages in the tray.** Connection status only — APP-01's
  scope. Surfacing session/weekly % would duplicate the device screen and is its own
  (deferred) feature.

### Autostart & install (SC#1)
- **D-07: Autostart mechanism is Claude's discretion** — `.lnk` in `shell:startup`
  vs. an `HKCU\…\Run` value. Both are per-user, no-admin, and satisfy SC#1. **Lean
  toward the stdlib-only path** (a `winreg` Run-key avoids a new dependency that a
  `.lnk` typically needs); choose `.lnk` instead only if user-discoverability is
  judged worth the dependency. The "Start at login" toggle (D-05) creates/removes
  whichever entry is chosen.
- **D-08: Headless launch via `pythonw.exe`.** The startup entry points at the
  venv's `pythonw.exe` + the script so **no console window** appears (SC#1). Phase 4
  ships raw-Python autostart (PyInstaller exe is v2).
- **D-09: `install-windows.ps1` does setup AND enables autostart.** A bootstrap
  PowerShell script creates the venv, `pip install -r requirements-windows.txt`,
  registers autostart immediately, and launches the tray app — turnkey first run.
  The menu toggle (D-05) then disables/re-enables autostart afterward. Fulfills the
  README-windows.md "Phase 4" promise.

### WSL-independence verification (APP-02, SC#4-5)
- **D-10: Hardware record + static no-WSL-paths guard.** Independence is an
  *emergent* property of Phase 1's native-Windows token read + Phase 2's native BLE
  ownership — nothing new to *build*, only to *verify*. Mirror the Phase 3 D-06
  split:
  - **Manual on-hardware record** for SC#4 (`wsl --shutdown` leaves the link up, no
    error) and SC#5 (fresh, WSL-never-launched session connects and displays usage),
    capturing observed behavior like the Phase 1/2/3 native-Windows test notes.
  - **Automatable static guard:** a cheap unit test asserting the daemon source
    references **no** WSL paths (`\\wsl$`, `wsl.exe`, `/home`, `/mnt`) — a
    CI-surviving regression guard that needs no hardware.

### Tray library
- **D-11: Tray library is Claude's discretion, leaning `pystray` + `Pillow`.** The
  design needs dynamic per-state icon images (D-02 corner bubble), a menu (D-05),
  and error toasts (D-04); `pystray` + `Pillow` (the libraries the exploration notes
  assumed) cover all three and are the likely landing spot. Whatever is chosen,
  add it to `requirements-windows.txt` (today just `bleak` + `httpx`) and resolve
  the **asyncio-loop vs. tray-main-thread** coexistence (most tray libs want the
  main thread) — planner's architectural call.

### Claude's Discretion
- **Threading/concurrency model** — how the asyncio daemon loop and the tray
  (main-thread) event loop coexist, how status + last-sync flow from the loop to the
  tray, and how Quit joins both. Architecture is the planner's/executor's call as
  long as D-01..D-11 hold and the loop logic stays untouched.
- **Autostart mechanism** (D-07: `.lnk` vs Run-key) and **tray library** (D-11).
- **Exact brand hex** and corner-bubble size/placement — derive from `logo.h`; tune
  for legibility at 16×16/32×32.
- **Error-state precise triggers** beyond token/auth (e.g. whether a sustained BLE
  failure counts as Error vs. lingering Scanning) — planner's call within D-01's intent.
- Reuse the existing `log()` `[HH:MM:SS]` style for any new tray/install log lines.

### Folded Todos
- **`implement-windows-daemon-tray.md`** — its **items 5 (tray app) and 6
  (autostart)** are exactly this phase's scope and are now folded into D-01..D-09.
  (Items 1–3 shipped in Phases 1–2; item 4, MAC cache, was resolved in Phase 3 D-04
  as not-needed.) Item 7 (PyInstaller packaging) remains **deferred to v2** — see
  Deferred Ideas.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project intent & scope (locked — do not re-litigate)
- `.planning/PROJECT.md` — Windows-daemon-port intent; **login-startup tray app
  (not Service/Scheduled Task)** run model; **strictly-additive, "ship its own
  daemon, don't refactor into a shared codebase"** boundary; tech stack lock
  (Python + bleak + httpx).
- `.planning/REQUIREMENTS.md` — **APP-01** and **APP-02** are the two requirements
  this phase satisfies; PKG-01/PKG-02 are explicitly v2.
- `.planning/ROADMAP.md` — Phase 4 goal + the five success criteria.

### Prior-phase decisions still in force
- `.planning/phases/03-resilience/03-CONTEXT.md` — Phase 3 hardening this phase
  wraps without touching: **D-02 (passive wake detection — no Win32 power events,
  carries forward)**, D-01/D-03 (connect-retry + zombie-break), D-04 (scan-every-
  cycle, no MAC cache), D-05 (fast-reconnect vs slow-search backoff → the two states
  D-01 maps to "Scanning"), D-06 (unit-tests-AND-hardware-record verification split,
  reused by D-10).
- `.planning/phases/02-core-pipeline/02-CONTEXT.md` — the run-loop being wrapped:
  `main()` `stop_event` (the Quit hook), `connect_and_run()`, `write_payload()`
  return bool (source of last-sync timestamp), the locked WinRT connect recipe.
- `.planning/phases/01-foundation/01-CONTEXT.md` — native-Windows `read_token()`
  credential-path strategy (the basis for WSL independence) and the GATT-unencrypted
  verdict.

### The file to extend (the Phase 2/3 Windows daemon — additive only)
- `daemon/claude_usage_daemon_windows.py` — the standalone daemon Phase 4 wraps:
  - `main()` (~L342) — the asyncio loop + `stop_event` + signal handlers; Quit wires
    into `stop_event`; the tray runs alongside this loop.
  - `connect_and_run()` (~L240) / `write_payload()` (returns bool) — the success
    signal feeding "Connected" state + last-sync timestamp.
  - `scan_for_device()` + the D-05 backoff regimes (~L360-387) — map to "Scanning".
  - `read_token()` (~L201) / `_read_expiry()` — None/expired → "Error" state + toast.
  - `__main__` (~L390) — current console entry; Phase 4 adds the tray/headless entry.

### Install / run docs (extend, don't duplicate)
- `daemon/README-windows.md` — Phase 2 manual-run guide; its "What is NOT covered"
  section promises the Phase 4 tray + autostart + `install-windows.ps1`. Extend with
  the tray/autostart/install steps.
- `daemon/requirements-windows.txt` — currently `bleak` + `httpx`; add the tray
  library (D-11) here.

### Brand asset
- `firmware/src/logo.h` — 80×80 RGB565 Clawdmeter brand logo; **source for the tray
  icon** (D-03). Convert to PNG; render in the Claude brand color.

### Wire protocol contract (firmware — read-only, unchanged)
- `.planning/codebase/INTEGRATIONS.md` — §"Custom GATT data service". Phase 4 does
  not touch the protocol.

### Reference (read-only, never edit)
- `daemon/claude_usage_daemon.py` (macOS) — the daemon being mirrored in spirit; has
  **no** tray/autostart code to copy. Tray/autostart is net-new, Windows-only.
- `.planning/notes/windows-daemon-port.md` — exploration notes; "Open questions"
  already floated `pystray` + `Pillow` and `pythonw` + `shell:startup` `.lnk`.
- `.planning/todos/pending/implement-windows-daemon-tray.md` — the folded Phase 4
  reference todo (items 5–6 in scope; item 7 deferred to v2).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `daemon/claude_usage_daemon_windows.py` — the entire Phase 2/3 daemon is the
  substrate. Phase 4 adds a presentation/lifecycle layer; the loop, BLE, polling,
  and reconnect logic are untouched.
- `main()`'s `stop_event` + signal handlers — the **clean-shutdown hook** the tray
  Quit sets (SC#3). Already handles SIGINT/SIGTERM; Quit is a third trigger.
- `write_payload()` returning `True/False` — the success signal that drives the
  "Connected" state and the last-sync timestamp (D-05) without new plumbing.
- The D-05 two-regime backoff in `main()` already distinguishes "device absent"
  (slow-search) from "link dropped" (fast-reconnect) — both collapse into the
  "Scanning" tray state (D-01).
- `firmware/src/logo.h` — brand-logo source for the tray icon (D-03).
- `log()` `[HH:MM:SS]` stdout style — reuse for tray/install log lines.

### Established Patterns
- Phase 1/2/3 verification pattern: **unit tests for deterministic logic + a manual
  on-hardware record** for what mocks can't prove (D-06 → reused by D-10).
- Stateless, stdlib-leaning Windows daemon: Phase 3 D-04 rejected a disk cache; D-08
  enforced stdlib-only scaffolding. D-07 inherits this lean (`winreg` Run-key over a
  dependency-requiring `.lnk` where possible).
- "Ship its own Windows daemon, additive only" — no shared/macOS/Linux/firmware edits.

### Integration Points
- **New tray + autostart code lives alongside `claude_usage_daemon_windows.py`**
  (tray entry/module + `install-windows.ps1`), driving the *same* `main()` loop.
- New runtime dependency (tray lib, D-11) → `requirements-windows.txt`.
- New unit tests under `daemon/tests/` — the static no-WSL-paths guard (D-10) and any
  testable autostart-toggle / icon-state logic; tray + WSL behavior proven by the
  manual hardware record.
- **Open architectural question for planning:** asyncio loop vs. tray main-thread
  coexistence + status/last-sync hand-off + Quit join (D-11; Claude's discretion).

</code_context>

<specifics>
## Specific Ideas

- Tray icon: one constant Clawdmeter mark in the Anthropic Claude brand color
  (warm clay/terracotta), derived from `firmware/src/logo.h`, with a small corner
  bubble — **green** connected, **amber** scanning, **red** error.
- Status header / tooltip text shape: `Connected · last update 14:32`, `Scanning…`,
  `Error: token expired — run claude login`.
- Toast fires once on entering Error (the only user-actionable state); otherwise
  silent.
- Menu order: status header → "Start at login" (checkable) → Quit.
- `install-windows.ps1`: venv → `pip install -r requirements-windows.txt` → register
  autostart → launch tray app, in one run.
- WSL verification record covers two scenarios: (1) connected, then `wsl --shutdown`
  → link stays up, no error; (2) reboot into a fresh session, never launch WSL →
  device connects and shows usage.

</specifics>

<deferred>
## Deferred Ideas

- **PyInstaller one-file `.exe` packaging** → **v2 (PKG-01)** / todo item 7. Phase 4
  ships raw-Python + `pythonw` autostart.
- **Windows Service / Scheduled Task (before-login) run model** → **v2 (PKG-02)**;
  login-startup tray is the locked model.
- **Usage percentages in the tray** (session/weekly %) → out of scope; would
  duplicate the device screen. Possible future "rich tray" feature.
- **Active Win32 power/session-event wake detection** → rejected in Phase 3 (D-02);
  revisit only if passive detection proves too slow on hardware.
- **Startup self-check log of the resolved token path** → considered for D-10 (WSL
  verification) but not adopted as an enforced test; could be added as a debugging aid.

### Reviewed Todos (not folded)
- **`verify-gatt-characteristics-unencrypted.md`** — already resolved in Phase 1
  (characteristics unencrypted, no pairing). Settled fact; nothing for Phase 4.

</deferred>

---

*Phase: 4-Tray & Autostart*
*Context gathered: 2026-06-02*
