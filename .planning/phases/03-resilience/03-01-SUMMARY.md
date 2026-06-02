---
phase: 03-resilience
plan: 01
subsystem: daemon/windows
tags: [ble, reconnect, tdd, resilience, windows]
requirements: [BLE-03]

dependency_graph:
  requires: []
  provides:
    - connect_and_run() with D-01 connect-retry wrapper (CONNECT_RETRIES=3, CONNECT_RETRY_DELAY=2.0)
    - connect_and_run() with D-03 zombie-link break (ZOMBIE_BREAK_LIMIT=1, consecutive_failures counter)
    - daemon/tests/test_windows_reconnect.py with 9 unit tests (D-01 x5, D-03 x4)
  affects:
    - daemon/claude_usage_daemon_windows.py connect_and_run()
    - BLE-03 connect-path coverage in CI

tech_stack:
  added: []
  patterns:
    - TDD RED→GREEN per task (test commit before implementation commit)
    - Locked WinRT BleakClient recipe reused per retry attempt (address_type="random", use_cached_services=False)
    - Guarded disconnect idiom (try/except BleakError) reused for inter-attempt cleanup
    - for-else loop pattern for retry exhaustion
    - ZOMBIE_BREAK_LIMIT=1 enforced per 120s SLA timing math

key_files:
  created:
    - daemon/tests/test_windows_reconnect.py
  modified:
    - daemon/claude_usage_daemon_windows.py

decisions:
  - CONNECT_RETRIES=3 / CONNECT_RETRY_DELAY=2.0: worst-case 3x2=6s in connect phase, well inside 120s SLA
  - ZOMBIE_BREAK_LIMIT=1 not 2: N=1 breaks at T=60s leaving ~60s headroom; N=2 would break at T=120s and bust the SLA before reconnect begins
  - for-else pattern for retry loop: Python idiom — else branch runs only when loop exhausts without break, eliminates a separate "exhausted" boolean
  - monkeypatch POLL_INTERVAL=0 in D-03 tests to force immediate poll without time.time manipulation

metrics:
  duration: 6 minutes
  completed: "2026-06-02"
  tasks: 2
  files: 2
---

# Phase 3 Plan 1: D-01 Connect-Retry + D-03 Zombie-Break Summary

Connect-retry wrapper (CONNECT_RETRIES=3) and zombie-link break (ZOMBIE_BREAK_LIMIT=1) hardening of `connect_and_run()` with TDD RED→GREEN coverage for BLE-03.

## Tasks Completed

| Task | Name | Commit (RED) | Commit (GREEN) | Files |
|------|------|-------------|---------------|-------|
| 1 | D-01 connect-retry wrapper | 8d64e97 | 5232b3c | daemon/tests/test_windows_reconnect.py, daemon/claude_usage_daemon_windows.py |
| 2 | D-03 zombie-link break | 1feccd4 | fa4c740 | daemon/tests/test_windows_reconnect.py, daemon/claude_usage_daemon_windows.py |

## What Was Built

**D-01 — Connect-retry wrapper** (`CONNECT_RETRIES=3`, `CONNECT_RETRY_DELAY=2.0`):

The original single-attempt connect block (BleakClient construction + connect() + is_connected check) is now wrapped in a `for attempt in range(CONNECT_RETRIES)` loop. Each attempt rebuilds a fresh `BleakClient(device, address_type="random", use_cached_services=False)` (locked WinRT recipe per-attempt). `(BleakError, asyncio.TimeoutError)` and a not-connected condition are the per-attempt failure signals. Between failed attempts, a guarded `disconnect()` (try/except BleakError) cleans up, followed by `asyncio.sleep(CONNECT_RETRY_DELAY)` (skipped after the last attempt). The `for-else` pattern fires `return False` only when the loop exhausts without a successful connect. On success, `break` falls through to unchanged `Session` setup.

**D-03 — Zombie-link consecutive-failure break** (`ZOMBIE_BREAK_LIMIT=1`):

A `consecutive_failures = 0` counter is added before the `while client.is_connected` loop. Inside the existing `if await session.write_payload(payload):` branch: success resets the counter to 0; failure increments it, and when it reaches `ZOMBIE_BREAK_LIMIT` logs a zombie-break message and `break`s. The existing `finally` block handles disconnect unchanged. `return used_successfully` is unchanged — `main()` routes into its reconnect branch on a False return.

## TDD Gate Compliance

Both tasks followed RED→GREEN commit order:

- Task 1: RED `8d64e97` (test(03-01): add failing tests for D-01) → GREEN `5232b3c` (feat(03-01): implement D-01)
- Task 2: RED `1feccd4` (test(03-01): add failing tests for D-03) → GREEN `fa4c740` (feat(03-01): implement D-03)

RED phase confirmed for both: D-01 tests failed with `AttributeError: module has no attribute 'CONNECT_RETRIES'`; D-03 tests hung (infinite loop without the break logic).

## Verification Results

```
python -m pytest daemon/tests/test_windows_reconnect.py -x -q
9 passed, 1 warning in 0.16s

python -m pytest daemon/tests/ -q
37 passed, 1 warning in 6.26s

grep -n "address_type=.random." daemon/claude_usage_daemon_windows.py
  -> L248: address_type="random",   [present - recipe intact]

grep -nv '^#' daemon/claude_usage_daemon_windows.py | grep -c "read_gatt_char"
  -> 0   [D-08 intact - no TX read added]
```

## Deviations from Plan

None — plan executed exactly as written.

- ZOMBIE_BREAK_LIMIT default 1 (as specified in plan's timing math section)
- Locked WinRT recipe kwargs unaltered per-attempt
- No new GATT reads added
- Token never logged (capsys assertion passes)

## Known Stubs

None. Both changes are fully wired: the retry wrapper and break counter consume existing `BleakClient`, `connect()`, `is_connected`, and `write_payload()` without any placeholder or deferred logic.

## Threat Flags

No new threat surface introduced. The new `log()` lines in the connect-retry and zombie-break paths emit only addresses, attempt counts, and exception text — never the token. T-03-01 capsys test asserts the sentinel never appears in stdout.

## Self-Check: PASSED

| Item | Status |
|------|--------|
| daemon/tests/test_windows_reconnect.py | FOUND |
| daemon/claude_usage_daemon_windows.py | FOUND |
| .planning/phases/03-resilience/03-01-SUMMARY.md | FOUND |
| Commit 8d64e97 (RED D-01) | FOUND |
| Commit 5232b3c (GREEN D-01) | FOUND |
| Commit 1feccd4 (RED D-03) | FOUND |
| Commit fa4c740 (GREEN D-03) | FOUND |
