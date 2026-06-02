---
phase: 04-tray-autostart
plan: 03
subsystem: daemon/tray-windows
tags: [pystray, pillow, tray, asyncio, threading, call_soon_threadsafe, state-bridge]
requirements: [APP-01]
dependency_graph:
  requires: [daemon/icon_assets.py (04-01), daemon/autostart_windows.py (04-02)]
  provides: [daemon/tray_windows.py]
  affects: [install-windows.ps1 (04-04 uses tray_windows.py as the autostart target)]
tech_stack:
  added: [pystray (requirements-windows.txt), Pillow (requirements-windows.txt)]
  patterns:
    - asyncio loop in bg thread (threading.Thread daemon=True) + pystray.Icon on main thread (RESEARCH Pattern 1)
    - thread-safe scalar bridge (TrayState — no lock, atomic attribute writes, loop writes / tray reads)
    - Quit via loop.call_soon_threadsafe(stop_event.set) — never stop_event.set() directly from tray thread
    - D-04 error toast on state entry only (prev_state transition guard)
    - Pitfall 6 live-callable checked=lambda for Start-at-login toggle
key_files:
  created:
    - daemon/tray_windows.py
    - daemon/tests/test_windows_tray.py
  modified:
    - daemon/claude_usage_daemon_windows.py
    - daemon/requirements-windows.txt
    - daemon/tests/test_windows_reconnect.py
decisions:
  - "TrayState uses plain attribute writes (no threading.Lock) — only scalar reads/writes, tray is a passive reader"
  - "import pystray deferred inside main() so module is importable on GTK-less Linux dev box (RESEARCH Wave-0 gap)"
  - "poll_api None treated as auth error trigger alongside read_token None — simplest additive signal without changing poll_api return type"
  - "asyncio.get_event_loop().run_until_complete() in test_windows_reconnect.py upgraded to asyncio.run() — Python 3.10 compatibility after asyncio.run() closes the loop"
metrics:
  duration: ~40min
  completed: 2026-06-02
  tasks_completed: 2
  files_created: 2
  files_modified: 3
---

# Phase 4 Plan 3: Windows Tray App — pystray + TrayState bridge + Quit + Error toast Summary

**One-liner:** pystray tray app with TrayState scalar bridge (daemon loop bg thread, Icon on main thread), D-05 menu (status header + live-checked autostart toggle + Quit via call_soon_threadsafe), D-04 error toast on state entry only.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | TrayState bridge + additive daemon setter injection | 66b145d | daemon/tray_windows.py, daemon/tests/test_windows_tray.py, daemon/claude_usage_daemon_windows.py, daemon/tests/test_windows_reconnect.py |
| 2 | pystray runtime + requirements | 66327b5 | daemon/requirements-windows.txt, daemon/tests/test_windows_reconnect.py |

## What Was Built

`daemon/tray_windows.py` — the tray entry module with:

- `class TrayState`: thread-safe scalar bridge with `state`/`reason`/`last_sync`/`loop`/`stop_event` attributes. Setters: `set_connected(ts_float)`, `set_scanning()`, `set_error(why)`. Plain attribute writes — no lock needed (tray reads scalars, loop writes scalars).
- `def header_text(ts) -> str`: produces D-05 menu header strings: `"Connected · last update HH:MM"`, `"Connected · last update never"` (when last_sync is None), `"Scanning…"`, `"Error: {reason}"`.
- `def main()`: tray entry point. `import pystray` is inside this function (not module top) so the module imports cleanly on the Linux dev box. Builds per-state icons via `icon_assets.build_state_icons()` once at startup. Runs `asyncio.run(daemon_main(tray_state=ts))` in a `threading.Thread(daemon=True)`. Runs `pystray.Icon.run(setup=_refresh)` on the main thread. Menu: non-clickable status header (lambda reading `header_text(ts)` live), Start-at-login `checked=lambda _item: autostart.is_enabled()` (CALLABLE — Pitfall 6 guard), Quit handler calling `ts.loop.call_soon_threadsafe(ts.stop_event.set)` then `icon_ref.stop()`. Setup callback `_refresh()` polls at ~1s, swaps `icon.icon = images[ts.state]` on state change, fires `icon.notify()` only on transition INTO error (D-04).

`daemon/claude_usage_daemon_windows.py` — additive changes only:
- `async def main(tray_state=None)` — accepts optional TrayState. Immediately after the existing `stop_event = asyncio.Event()` / `loop = asyncio.get_running_loop()` lines: if tray_state is not None, sets `tray_state.loop = loop` and `tray_state.stop_event = stop_event`.
- Setter injections guarded by `if tray_state:` at existing decision points: `set_scanning()` in slow-search and fast-reconnect branches in main(); `set_error("token expired — run claude login")` when `read_token()` returns None; `set_connected(time.time())` after `write_payload()` returns True; `set_error(...)` when `poll_api()` returns None (HTTP 400+).
- `connect_and_run(device, stop_event, tray_state=None)` — accepts `tray_state` and threads it through the poll loop.
- Loop logic is unchanged; exactly one `stop_event = asyncio.Event()` line.

`daemon/requirements-windows.txt` — `pystray` and `Pillow` appended; comment header + bleak/httpx unchanged; winreg not added (stdlib).

`daemon/tests/test_windows_tray.py` — 11 tests:
- 4 TrayState setter tests (initial state, set_connected, set_scanning, set_error)
- 4 header_text tests (scanning, error, connected with last_sync, connected with last_sync=None → "never")
- `test_main_populates_tray_state_loop_and_stop_event`: runs daemon main(tray_state=ts) via asyncio.run with mocked scan_for_device; asserts ts.loop and ts.stop_event are populated before the first scan call
- `test_quit_uses_call_soon_threadsafe`: constructs the Quit handler closure with mocked loop/stop_event/icon; asserts call_soon_threadsafe(stop_event.set) was called, icon.stop() was called, stop_event.set() was NOT called directly
- `test_error_toast_on_entry_only`: drives the state-change handler through scanning→error→error; asserts notify fired exactly once (on entry, not on repeated error)

`daemon/tests/test_windows_reconnect.py` — auto-fixed:
- `_run()` upgraded from `asyncio.get_event_loop().run_until_complete()` to `asyncio.run()` — Python 3.10 compatibility after asyncio.run() in test_windows_tray.py closes the event loop (Rule 1 - Bug from test ordering)
- 10 `asyncio.get_event_loop().run_until_complete(_make_event(...))` calls also upgraded to `asyncio.run(_make_event(...))`
- 2 `fake_connect_and_run(device, event)` mocks updated to accept `tray_state=None` (Rule 1 - Bug from additive param)
- `test_requirements_windows_unchanged` → `test_requirements_windows_contains_required_deps`: updated from "assert no change" (Phase 3 guard) to "assert correct Phase 4 state" (pystray/Pillow present, winreg absent)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed asyncio event loop compatibility in test_windows_reconnect.py**
- **Found during:** Task 1 verification run (`python -m pytest daemon/tests/test_windows_tray.py daemon/tests/test_windows_reconnect.py -x -q`)
- **Issue:** `asyncio.run()` in `test_main_populates_tray_state_loop_and_stop_event` closes the Python 3.10 event loop. Subsequent tests in `test_windows_reconnect.py` using `asyncio.get_event_loop().run_until_complete()` then fail with `RuntimeError: There is no current event loop in thread 'MainThread'`.
- **Fix:** Upgraded `_run()` helper and all `_make_event()` call sites to use `asyncio.run()` — Python 3.10 compatible regardless of test ordering.
- **Files modified:** daemon/tests/test_windows_reconnect.py
- **Commit:** 66b145d

**2. [Rule 1 - Bug] Fixed fake_connect_and_run mock arity after adding tray_state param**
- **Found during:** Task 1 — same verification run
- **Issue:** Two tests in `test_windows_reconnect.py` mock `connect_and_run` with a 2-arg `fake_connect_and_run(device, event)`. After adding the optional `tray_state=None` parameter, `main()` passes 3 positional args, causing `TypeError: takes 2 positional arguments but 3 were given`.
- **Fix:** Added `tray_state=None` to both `fake_connect_and_run` definitions.
- **Files modified:** daemon/tests/test_windows_reconnect.py
- **Commit:** 66b145d

**3. [Rule 1 - Bug] Updated test_requirements_windows guard for Phase 4**
- **Found during:** Task 2 — planning (the Phase 3 guard would fail on intentional Phase 4 additions)
- **Issue:** `test_requirements_windows_unchanged` asserts git diff == "" which would fail once pystray/Pillow are added to requirements-windows.txt.
- **Fix:** Replaced with `test_requirements_windows_contains_required_deps` that asserts the correct Phase 4 state (pystray + Pillow present, winreg absent, bleak + httpx still present).
- **Files modified:** daemon/tests/test_windows_reconnect.py
- **Commit:** 66327b5

## Verification

```
python -m pytest daemon/tests/test_windows_tray.py -x -q
# 11 passed

python -m pytest daemon/tests/ -q
# 70 passed, 3 warnings

python -c "import daemon.tray_windows"
# exits 0 (deferred pystray import)

grep -E "async def main\(.*tray_state" daemon/claude_usage_daemon_windows.py
# async def main(tray_state=None) -> None:

grep -c "^    stop_event = asyncio.Event()$" daemon/claude_usage_daemon_windows.py
# 1 (exactly one live line)

grep -n "call_soon_threadsafe" daemon/tray_windows.py
# line 125: ts.loop.call_soon_threadsafe(ts.stop_event.set)

grep -n "import pystray" daemon/tray_windows.py
# line 101:     import pystray  (indented — inside function)

grep -n "checked=lambda" daemon/tray_windows.py
# line 139: MenuItem("Start at login", _on_toggle, checked=lambda _item: autostart.is_enabled())
```

## Self-Check: PASSED

- [x] daemon/tray_windows.py exists with `class TrayState`, `def header_text`, `def main`
- [x] daemon/tests/test_windows_tray.py exists with `test_quit_uses_call_soon_threadsafe` and `test_error_toast_on_entry_only`
- [x] daemon/requirements-windows.txt contains pystray and Pillow; bleak and httpx still present; winreg absent
- [x] commit 66b145d exists in git log
- [x] commit 66327b5 exists in git log
- [x] 11 new tray tests pass; full suite 70 passed

## Known Stubs

None — all functions are fully implemented. TrayState setters write real state, header_text produces real strings, the tray main() builds real icons from logo.h and wires the real daemon loop. The tray app is functional on Windows (pystray + Pillow), modules import cleanly on Linux (deferred import).

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: cross-thread-state | daemon/tray_windows.py | TrayState bridges asyncio loop thread to pystray main thread — mitigated per T-04-06: Quit routes through loop.call_soon_threadsafe(stop_event.set), never direct stop_event.set() from tray thread |
| threat_flag: information-disclosure | daemon/tray_windows.py | Tray status header / Error toast surface is bounded to state + last-sync time + fixed "token expired — run claude login" string — no token value exposed (T-04-07 mitigated) |
