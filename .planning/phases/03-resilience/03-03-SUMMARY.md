---
phase: 03-resilience
plan: 03
subsystem: daemon-windows
tags: [ble, reconnect, resilience, hardware-verification, checkpoint, windows]
dependency_graph:
  requires: [03-01, 03-02]
  provides: [on-hardware-reconnect-attestation, G-03-01-fix]
  affects:
    - .planning/phases/03-resilience/03-WINDOWS-VERIFICATION.md
    - daemon/claude_usage_daemon_windows.py
    - daemon/tests/test_windows_reconnect.py
tech_stack:
  added: []
  patterns: [graceful-degradation, optional-subscription, human-verify-checkpoint]
key_files:
  created:
    - .planning/phases/03-resilience/03-WINDOWS-VERIFICATION.md
  modified:
    - daemon/claude_usage_daemon_windows.py
    - daemon/tests/test_windows_reconnect.py
decisions:
  - "SC#1/SC#2 passed on first hardware run; SC#3 exposed gap G-03-01 (uncaught OSError from start_notify on post-power-cycle reconnect)"
  - "G-03-01 fixed inline as TDD gap-closure: widen setup_refresh_subscription except to include OSError"
  - "Refresh subscription is optional — degrade gracefully (log + continue poll loop) rather than crash, preserving SC#4 no-restart guarantee"
  - "SC#3 + SC#4 re-verified PASS on hardware after the fix"
metrics:
  completed: "2026-06-02"
  tasks: 1
  files_changed: 3
---

# Phase 3 Plan 03: On-Hardware Reconnect Verification (SC#1–4) Summary

**One-liner:** Operator-driven on-hardware run proved BLE-03 reconnect resilience against real WinRT; SC#3 surfaced a daemon-crashing gap (G-03-01) that was fixed TDD-style and re-verified to PASS.

## What Was Built

`.planning/phases/03-resilience/03-WINDOWS-VERIFICATION.md` — an operator-attested record of the
four resilience success criteria run against real hardware (Clawdmeter, BLE MAC 28:84:85:55:65:39)
on native Windows, exercising the hardened code from 03-01 (D-01 connect-retry, D-03 zombie-break)
and 03-02 (D-05 split backoff). Timestamps + `Sending:` lines only; no credential content (T-03-07).

This checkpoint also produced — and closed — a real defect that the 03-01/03-02 mocks could not catch.

## Hardware Results

| SC | Scenario | First run | Final |
|----|----------|-----------|-------|
| SC#1 | sleep/wake reconnect ≤120s | PASS | PASS |
| SC#2 | out-of-range auto-reconnect | PASS | PASS |
| SC#3 | power-cycle pickup, no crash | **FAIL (crash)** | **PASS** (after G-03-01 fix) |
| SC#4 | single continuous PID, no restart | FAIL (consequential) | **PASS** |

## Gap G-03-01 (found → fixed → re-verified)

**Symptom:** On the post-power-cycle reconnect, the daemon connected to the just-rebooted device
then crashed at `setup_refresh_subscription()` → `start_notify()` with
`OSError: [WinError -2147023673] The operation was canceled by the user.` The uncaught `OSError`
propagated through `connect_and_run` → `main()` → `asyncio.run()` and killed the process.

**Root cause:** `Session.setup_refresh_subscription()` caught `(BleakError, ValueError)` but not
`OSError`. WinRT's CCCD descriptor write inside `start_notify()` surfaces a raw `OSError`/`WinError`
when the peer GATT server is transiently unavailable — exactly the state of a freshly power-cycled
ESP32. The path sat between the D-01 (connect) and D-03 (write loop) hardening and was left with a
too-narrow `except`.

**Fix (TDD):** widen the `except` to `(BleakError, ValueError, OSError)`. The refresh subscription
is optional (the 60s poll loop is unaffected), so the failure now degrades gracefully — logs
`Refresh subscription unavailable: ...` and continues — instead of crashing.

- RED: `b58c190` — `test(03-03): OSError from start_notify must not crash connect_and_run`
- GREEN: `f303eb4` — `fix(03-03): tolerate WinRT OSError in setup_refresh_subscription`

**Re-verification:** On the hardware re-run, the power-cycled device reconnected, logged
`Refresh subscription unavailable`, landed a fresh `Sending:`, and the daemon stayed a single
continuous process (no restart). SC#3 + SC#4 attested PASS by operator.

## Tasks

### Task 1: Operator on-hardware reconnect run (SC#1–4) + record

**Status:** Complete (checkpoint:human-verify, gate passed after gap closure)
**Commits:**
- `381d78d` — docs(03-03): record on-hardware verification (initial, gap recorded)
- `b58c190` — test(03-03): G-03-01 regression (RED)
- `f303eb4` — fix(03-03): G-03-01 fix (GREEN)
- verification record flipped to `status: passed` after hardware re-run

## Acceptance Criteria Verification

- [x] `03-WINDOWS-VERIFICATION.md` exists with frontmatter mirroring the Phase 2 record
- [x] A dedicated section per SC#1–4 with Expected + Operator-reported result (+ SC#1 latency vs 120s SLA)
- [x] Captured console excerpt has `[HH:MM:SS]` timestamps and `Sending:` lines, no token/credential (T-03-07)
- [x] Summary block reports total/passed/issues/gaps (4/4/0/0 after fix; gap fully documented, not silently passed)
- [x] SC#4 single continuous PID attested across all three scenarios (after fix)

## Threat Surface Scan

No new endpoints, auth paths, or dependencies. The fix only broadens an exception clause to
degrade gracefully; the new log line carries no credential (T-03-06/T-03-07 intact). The committed
verification record embeds only timestamps and a stack trace with abbreviated paths — no token.

## Known Stubs

None.

## Self-Check: PASSED

- `.planning/phases/03-resilience/03-WINDOWS-VERIFICATION.md` — created, status: passed
- `daemon/claude_usage_daemon_windows.py` — modified (OSError fix), present
- `daemon/tests/test_windows_reconnect.py` — modified (G-03-01 regression test), present
- Commits `381d78d`, `b58c190` (RED), `f303eb4` (GREEN) confirmed in git log
- 47/47 daemon suite passes; SC#1–4 PASS on hardware (SC#3/SC#4 re-verified after fix)
