---
phase: 02-core-pipeline
plan: "02"
subsystem: daemon/windows
tags: [ble, windows, bleak, async, gatt]
dependency_graph:
  requires: [02-01]
  provides: [02-03]
  affects: [daemon/claude_usage_daemon_windows.py]
tech_stack:
  added: []
  patterns:
    - BleakScanner.find_device_by_name returns BLEDevice (not address string) — WinRT D-05
    - BleakClient(device, address_type="random", use_cached_services=False) — locked WinRT recipe
    - asyncio.Event for device-initiated REQ refresh subscription
    - compact JSON separators=(",",":") for GATT MTU efficiency
    - NotImplementedError fallback for signal handling on Windows
    - Exponential backoff (1s -> 60s cap) on scan/connect failure
key_files:
  created: []
  modified:
    - daemon/claude_usage_daemon_windows.py
    - daemon/tests/test_windows_token.py
decisions:
  - "Returned BLEDevice from scan_for_device (not address string) so BleakClient can receive it with WinRT kwargs directly (D-05)"
  - "Single connect attempt in connect_and_run with no retry wrapper — WinRT stale-connection hardening deferred to Phase 3 (D-02)"
  - "Updated two superseded __main__ subprocess tests to match new async runner contract; old token-printing behavior intentionally replaced"
metrics:
  duration: "~6 minutes"
  completed: "2026-06-01"
  tasks_completed: 2
  files_modified: 2
---

# Phase 2 Plan 02: BLE Glue — scan_for_device, Session, connect_and_run, main Summary

BLE end-to-end pipeline added: `scan_for_device` returns a `BLEDevice` via `find_device_by_name`, `Session` subscribes to the REQ characteristic and writes compact JSON to RX with `response=False`, and `connect_and_run` + `main` complete the scan→connect→poll→write loop with signal shutdown and exponential backoff.

## Task 0: Package Legitimacy Gate

**Status: Pre-approved by orchestrator/user before execution.**

Both `bleak` (github.com/hbldh/bleak, MIT, Henrik Blidh) and `httpx` (github.com/encode/httpx, BSD-3, Encode/Tom Christie) were verified as legitimate upstream packages on PyPI. No code was written in this task; it was a blocking gate resolved before this agent ran.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | scan_for_device + Session | 1926b2e | daemon/claude_usage_daemon_windows.py |
| 2 | connect_and_run + main + __main__ async runner | cb8f561 | daemon/claude_usage_daemon_windows.py, daemon/tests/test_windows_token.py |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated two superseded __main__ subprocess tests**

- **Found during:** Task 2
- **Issue:** `test_main_output_redacts_token` and `test_main_empty_token_exits_one` in `daemon/tests/test_windows_token.py` called the module as `__main__` and expected Phase 1 behavior (token/expiry printed to stdout, exit 1 on empty token). The new `__main__` replaces that with `asyncio.run(main())`, so the old tests would hang/fail.
- **Fix:** Replaced both tests with `test_main_emits_linux_warning` and `test_main_emits_linux_warning_before_loop` — both verify the new contract: on non-Windows, a "WinRT BLE will not be available" warning is emitted to stderr before the BLE loop starts. Tests use subprocess with a 3s timeout and catch `TimeoutExpired` to read partial stderr.
- **Files modified:** daemon/tests/test_windows_token.py
- **Commit:** cb8f561
- **Plan reference:** Task 2 acceptance criteria explicitly anticipated this: "the token __main__ test was a Phase 1 artifact — confirm it still passes or, if the __main__ contract intentionally changed, note the superseded test in the SUMMARY for Plan 03's operator." Contract intentionally changed; tests updated to match.

**Note for Plan 03 operator:** The Phase 1 `__main__` token-printing tests have been replaced. If Plan 03 adds any `__main__`-level smoke tests, they should verify the async runner behavior (warning + asyncio.run), not the old token display. The `read_token()`, `_extract_access_token()`, `_windows_credential_candidates()`, and `_read_expiry()` functions remain untouched — their unit tests in `test_windows_token.py` are all still green.

## Acceptance Criteria Verification

All acceptance criteria from the plan pass:

- `scan_for_device`, `Session`, `connect_and_run`, `main`, `poll_api`, `read_token`, `_extract_access_token`, `_read_expiry` all present in AST
- `grep find_device_by_name` = 1 (returns BLEDevice, not address string)
- `grep start_notify(REQ_CHAR_UUID` = 1 (D-06 REQ subscription)
- `grep response=False` on write_gatt_char line = confirmed; `grep response=True` = 0
- `grep separators=(",", ":")` = 1 (compact JSON)
- `grep 0003` = 0 (no TX characteristic referenced)
- `grep address_type="random"` = 1; `grep use_cached_services=False` = 1 (D-05 locked WinRT recipe)
- `grep last_poll = 0.0` = 1 (D-03 poll-immediately)
- `grep SAVED_ADDR_FILE` = 0; `grep discover_target` = 0; `grep darwin` = 0 (D-04 stripped macOS paths)
- `grep asyncio.run(main())` = 1
- `grep add_signal_handler` = 1 (with NotImplementedError fallback)
- `python -m pytest daemon/tests/test_windows_poll.py daemon/tests/test_windows_token.py -q` → 28 passed

## Known Stubs

None. All functions are fully implemented. Hardware verification is Plan 03's scope.

## Threat Flags

None. No new network endpoints, auth paths, or trust boundaries introduced beyond what the plan's threat model covers (T-02-04 accepted, T-02-05 accepted, T-02-06 mitigated via backoff, T-02-SC resolved by Task 0 gate).

## Self-Check: PASSED
