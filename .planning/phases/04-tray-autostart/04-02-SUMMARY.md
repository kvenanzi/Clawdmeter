---
phase: 04-tray-autostart
plan: "02"
subsystem: daemon-autostart
tags: [autostart, winreg, windows, tdd, stdlib]
dependency_graph:
  requires: []
  provides: [daemon/autostart_windows.py]
  affects: [daemon/tray_windows.py (04-03), install-windows.ps1 (04-04)]
tech_stack:
  added: []
  patterns: [winreg HKCU\\Run, idempotent-on-missing (FileNotFoundError swallow), pythonw.exe headless launch, mock-the-platform-binding TDD]
key_files:
  created:
    - daemon/autostart_windows.py
    - daemon/tests/test_windows_autostart.py
  modified: []
decisions:
  - "winreg module guarded via try/except ImportError so module is importable on Linux dev box; tests patch `daemon.autostart_windows.winreg` at the module attribute"
  - "tray_script parameter on enable() defaults to __file__ but callers (04-03) will pass tray_windows.py path"
  - "is_enabled() queries live registry every call to avoid Pitfall 6 stale-checkmark bug"
metrics:
  duration: ~10 minutes
  completed: 2026-06-02
  tasks: 1
  files: 2
requirements: [APP-01]
---

# Phase 4 Plan 2: Windows Login-Autostart Toggle Summary

## One-liner

stdlib `winreg` HKCU\\Run toggle (`enable`/`disable`/`is_enabled`) using `pythonw.exe` derived from `sys.executable` — no console, no admin, no hard-coded paths.

## What Was Built

`daemon/autostart_windows.py` — a pure-stdlib helper that creates, removes, and queries a per-user `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` registry value named `Clawdmeter`. The value command launches the tray entry script via the venv's `pythonw.exe` (no console window).

`daemon/tests/test_windows_autostart.py` — 6-test TDD suite with `winreg` fully mocked so tests run on the Linux dev box.

## TDD Gate Compliance

RED commit: `8609b79` — `test(04-02): add failing tests for winreg autostart toggle`
GREEN commit: `b8c5e10` — `feat(04-02): implement winreg HKCU\Run autostart toggle (enable/disable/is_enabled)`

Both gates are present and in order.

## Tasks Completed

| Task | Description | Commit |
|------|-------------|--------|
| 1 RED | Failing tests for enable/disable/is_enabled with winreg mocked | 8609b79 |
| 1 GREEN | autostart_windows.py implementation — all 6 tests pass | b8c5e10 |

## Verification Results

- `python -m pytest daemon/tests/test_windows_autostart.py -x -q` — 6 passed
- `python -c "import daemon.autostart_windows"` — exits 0 (winreg guarded)
- `python -m pytest daemon/tests/ -q` — 53 passed (full suite)
- `grep -E "HKEY_LOCAL_MACHINE|HKLM" daemon/autostart_windows.py` — no matches
- `grep "pythonw" daemon/autostart_windows.py` — line 50: derived from `sys.executable`
- `grep 'C:\\\\' daemon/autostart_windows.py` — no hard-coded drive paths

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None. `autostart_windows.py` is complete pure-logic CRUD with no placeholder values.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: persistence | daemon/autostart_windows.py | Writes an HKCU\\Run persistence hook — mitigated per T-04-03: HKCU-only, no admin, value clearly named "Clawdmeter", removable via disable() |
| threat_flag: path-injection | daemon/autostart_windows.py | Run-value command path derived from sys.executable at runtime — mitigated per T-04-04: never hard-coded, both paths quoted for space safety |

Both threat flags are within the plan's threat model (T-04-03, T-04-04) and are mitigated by the implementation.

## Self-Check: PASSED

- daemon/autostart_windows.py exists: FOUND
- daemon/tests/test_windows_autostart.py exists: FOUND
- RED commit 8609b79 exists: FOUND
- GREEN commit b8c5e10 exists: FOUND
- Full suite: 53 passed
