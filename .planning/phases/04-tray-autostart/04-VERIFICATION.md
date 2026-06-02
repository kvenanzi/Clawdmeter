---
phase: 04-tray-autostart
verified: 2026-06-02T18:30:00Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: none
  note: "Initial verification — no prior VERIFICATION.md"
---

# Phase 4: Tray & Autostart — Verification Report

**Phase Goal:** The daemon starts at Windows login, shows connection status in the system tray, and works entirely independently of WSL.
**Verified:** 2026-06-02T18:30:00Z
**Status:** passed
**Re-verification:** No — initial verification
**Mode:** mvp (declarative phase goal with 5 explicit success criteria; verified against the success-criteria contract)

## Goal Achievement

### Verification approach

The 5 success criteria are physical-Windows / live-BLE behaviors. They cannot
be executed from this Linux/WSL environment. Verification therefore proves three
independent layers per criterion:

1. **Code path exists and is substantive** — the implementing source is present,
   non-stub, and wired into the runtime (data flows / handlers connected).
2. **Automated regression coverage** — `python -m pytest daemon/tests/ -q`
   → **89 passed** (matches the expected 89). The named tests the operator cited
   (`test_poll_api_raises_autherror_on_401_403`, `test_transient_poll_failure_does_not_set_error`)
   exist and pass.
3. **Operator on-hardware confirmation** — `04-HARDWARE-RECORD.md` (SC#1–SC#5 all
   PASS) and `04-UAT.md` (8/8 pass, 0 issues), both recorded 2026-06-02 on real
   Windows hardware with the device powered.

This mirrors the Phase 1/2/3 "unit-tests AND hardware-record" split (D-06 / D-10).

### Observable Truths

| # | Truth (Success Criterion) | Status | Evidence |
|---|---------------------------|--------|----------|
| 1 | Daemon launches at logon with no terminal window | ✓ VERIFIED | `autostart_windows._command()` writes HKCU\Run = base-interp `pythonw.exe` + `tray_windows.py` (L59-61); rationale comment documents the venv-redirector-console bug fixed by base pythonw (L38-58). `install-windows.ps1` Step 3 registers autostart, Step 4 launches via `$BasePythonw` (L97-124). Hardware SC#1 PASS: "tray icon started automatically with no cmd or PowerShell popup" after the base-pythonw fix (commit `ba948f0`). UAT #1 pass. |
| 2 | Tray icon visible; hover/click shows connection status | ✓ VERIFIED | `tray_windows.main()` builds per-state icons (`icon_assets.build_state_icons`: green=connected/amber=scanning/red=error, L30-32) and a menu header via `header_text()` (L90-107: "Connected · last update HH:MM" / "Scanning…" / "Error: …"). `_refresh` updates `icon.title`+menu on state OR last_sync change (L248-269, the SC#2 "frozen tooltip" fix). Daemon wires `set_connected/set_scanning/set_error` at real branch points (daemon L385-499). Hardware SC#2 PASS; UAT #2/#3 pass. |
| 3 | Right-click Quit stops the daemon cleanly | ✓ VERIFIED | `_on_quit` routes `stop_event.set` via `loop.call_soon_threadsafe`, joins the daemon thread (timeout 6s), then `icon.stop()` (L211-225). Daemon `finally: client.disconnect()` runs on stop and logs `Stopping` (daemon L422-431). Criterion revised+documented: device is a bonded BLE HID keyboard, so the Windows link intentionally persists (README "Pair the device", record rationale L76-82). Hardware SC#3 PASS: tray gone promptly, no lingering pythonw/python, `Stopping` logged (graceful-shutdown fix `9048c64`). UAT #5 pass. |
| 4 | `wsl --shutdown` does not disconnect or error the daemon | ✓ VERIFIED | Static guard `test_windows_no_wsl.py` asserts FORBIDDEN `[\\wsl$, wsl.exe, /home/, /mnt/]` absent from all 3 core sources (daemon/tray/autostart); independent grep over the real sources returns zero matches. Daemon uses native Windows BLE (bleak) + `%APPDATA%` token path (no WSL coupling). `install-windows.ps1` adds a `\\wsl$`/`\\wsl.localhost` install-path guard (L43-59). Hardware SC#4 PASS: tray stayed Connected, no error logged, device kept showing usage. UAT #6 pass. |
| 5 | Fresh Windows session (WSL never launched) connects + shows usage | ✓ VERIFIED | Same WSL-independence evidence as #4 + autostart (#1). Transient boot-time false "token expired" toast root-caused and fixed: `poll_api` raises `AuthError` ONLY on 401/403 (daemon L119-123); network/DNS/timeout/429/5xx return `None`, no toast (L115-127). Regression-locked by `test_poll_api_raises_autherror_on_401_403` and `test_transient_poll_failure_does_not_set_error` (both pass). Hardware SC#5 PASS: device connected + showed usage after reboot, WSL never launched; transient toast self-cleared. UAT #7/#8 pass. |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `daemon/icon_assets.py` | Per-state tray icons (logo + colored bubble) | ✓ VERIFIED | `load_logo_rgba` + `build_state_icons`; green/amber/red bubble map. Imported & used in `tray_windows.main` (L184,187-188). 6 tests pass. |
| `daemon/autostart_windows.py` | HKCU\Run pythonw toggle | ✓ VERIFIED | `enable/disable/is_enabled`, base-pythonw command, runtime-derived path. Wired into tray toggle + install script. 6 tests pass. |
| `daemon/tray_windows.py` | pystray tray + TrayState + Quit | ✓ VERIFIED | Substantive (276 lines): TrayState bridge, header_text, single-instance mutex, daemon bg-thread, graceful Quit, live refresh. 18 tests pass. |
| `daemon/claude_usage_daemon_windows.py` | BLE daemon + AuthError handling | ✓ VERIFIED | `AuthError` raised only on 401/403; `tray_state` wired at scan/connect/error branches; graceful `finally` disconnect. 16 poll + 25 reconnect tests pass. |
| `install-windows.ps1` | venv→pip→autostart→headless tray | ✓ VERIFIED | All 4 steps in order; runtime-derived paths; no remote download; WSL-path install guard. (Plan 04-04 — committed, see observation below.) |
| `daemon/README-windows.md` | Tray/autostart/install docs | ✓ VERIFIED | Documents install, tray menu (status/Start-at-login/Quit), disable steps, Pair-the-device. "What is NOT covered" no longer lists tray/autostart/install (only PyInstaller v2 + Phase-3 MAC cache). |
| `daemon/tests/test_windows_no_wsl.py` | Static no-WSL-paths guard | ✓ VERIFIED | FORBIDDEN four patterns; references all 3 sources; 3 tests pass; real sources confirmed clean by independent grep. |
| `04-HARDWARE-RECORD.md` | Operator SC#1-5 record | ✓ VERIFIED | All five sections filled with observed behavior + Result: PASS; revisions documented with rationale. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `install-windows.ps1` | `requirements-windows.txt` | `pip install -r` | ✓ WIRED | L82 `& $PythonExe -m pip install --quiet -r $RequirementsFile` |
| `install-windows.ps1` | `autostart_windows.enable` | venv python `-c import…enable(tray_script)` | ✓ WIRED | L97-102, passes `$TrayScript` explicitly |
| `tray_windows` | `autostart_windows` | toggle calls enable/disable | ✓ WIRED | L227-235 `_on_toggle`, `checked=` callable |
| `tray_windows` | daemon loop | bg thread `asyncio.run(daemon_main(tray_state=ts))` | ✓ WIRED | L194-208; TrayState.loop/stop_event populated by daemon main (daemon L451-453) |
| daemon | TrayState | `set_connected/scanning/error` at branch points | ✓ WIRED | daemon L385-499 |
| `test_windows_no_wsl` | tray/autostart/daemon sources | source read + regex | ✓ WIRED | L20-22, L26-38 |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full daemon test suite | `python -m pytest daemon/tests/ -q` | 89 passed, 2 warnings, 6.41s | ✓ PASS |
| No-WSL guard isolated | (subset of suite) test_windows_no_wsl 3 tests | pass | ✓ PASS |
| AuthError only on 401/403 | `test_poll_api_raises_autherror_on_401_403` present + passes | pass | ✓ PASS |
| Transient failure no error state | `test_transient_poll_failure_does_not_set_error` present + passes | pass | ✓ PASS |
| Sources free of WSL paths | `grep -rE '\\wsl\$\|wsl\.exe\|/home/\|/mnt/'` over 3 sources | 0 matches | ✓ PASS |
| Installer no remote download | grep Invoke-WebRequest/curl/wget/iwr/DownloadString | none; comment asserts it | ✓ PASS |

Live-BLE / logon / `wsl --shutdown` behaviors are not runnable here — covered by
the operator hardware record + UAT (see Human Verification note below).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| APP-01 | 04-01/02/03/04 | Login-startup app, tray icon reflecting status, quit action | ✓ SATISFIED | Truths 1,2,3 verified (autostart + tray + Quit). Code + tests + hardware SC#1-3 PASS. |
| APP-02 | 04-04 | Fully WSL-independent — connects/stays connected with WSL stopped | ✓ SATISFIED | Truths 4,5 verified (static guard + native BLE/token + install guard). Hardware SC#4-5 PASS. |

No orphaned requirements: REQUIREMENTS.md maps only APP-01/APP-02 to Phase 4, both claimed and satisfied.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (none) | — | No TBD/FIXME/XXX debt markers in phase sources | — | Clean. `return None` in `poll_api` is intentional transient-failure signaling (documented, regression-tested), not a stub. |

Scanned `icon_assets.py`, `autostart_windows.py`, `tray_windows.py`,
`claude_usage_daemon_windows.py`, `install-windows.ps1`,
`test_windows_no_wsl.py`. No blocker or warning anti-patterns.

### Human Verification Required

None blocking. The 5 success criteria were already operator-verified on hardware
(04-HARDWARE-RECORD.md, all PASS) and reconfirmed in conversational UAT
(04-UAT.md, 8/8 pass, 0 issues). This verifier cannot independently re-run
Windows-logon / live-BLE / `wsl --shutdown` behaviors from a Linux environment;
the existing operator records are accepted as the on-hardware evidence per the
project's D-06/D-10 unit-tests-AND-hardware-record convention. No new untested
behavior was found.

### Observations (non-blocking)

1. **Plan 04-04 process gap.** `04-04-PLAN.md` is still unchecked `[ ]` in
   ROADMAP.md and has **no `04-04-SUMMARY.md`**. However, every 04-04 deliverable
   exists in the tree and is committed: `install-windows.ps1`
   (commits `bac6391`, `866582f`), `README-windows.md` tray/autostart docs
   (`bac6391`), the static no-WSL guard test (`e395228`), and
   `04-HARDWARE-RECORD.md`. Per the verification task guidance, this checkbox/
   SUMMARY bookkeeping gap does **not** fail the goal because the work is real and
   present. Recommend: write the missing 04-04-SUMMARY.md and tick the ROADMAP
   checkbox for audit completeness.
2. **SC#3 criterion revised** (device stays bonded after Quit) — revision is
   documented with engineering rationale in the hardware record (L76-82) and the
   README "Pair the device" section. "Clean stop" = tray gone + no leftover
   process + graceful GATT data-connection disconnect, which is what the code does
   and the operator observed. Accepted.

### Gaps Summary

No goal-blocking gaps. All 5 success criteria are backed by substantive, wired
code paths; 89/89 automated tests pass; the operator hardware record and UAT
confirm all five physical behaviors. The only finding is a process/bookkeeping
gap (missing 04-04 SUMMARY + unticked ROADMAP checkbox) which does not affect goal
achievement since the underlying deliverables are committed and verified.

Phase goal achieved. Ready to proceed.

---

_Verified: 2026-06-02T18:30:00Z_
_Verifier: Claude (gsd-verifier)_
