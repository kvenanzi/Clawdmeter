---
phase: 03-resilience
plan: 02
subsystem: daemon-windows
tags: [ble, reconnect, backoff, resilience, tdd, windows]
dependency_graph:
  requires: [03-01]
  provides: [D-05-split-backoff, fast-reconnect-regime, slow-search-regime]
  affects: [daemon/claude_usage_daemon_windows.py, daemon/tests/test_windows_reconnect.py]
tech_stack:
  added: []
  patterns: [exponential-backoff, two-regime-backoff, interruptible-wait, pure-helper-extraction]
key_files:
  created: []
  modified:
    - daemon/claude_usage_daemon_windows.py
    - daemon/tests/test_windows_reconnect.py
decisions:
  - RECONNECT_BACKOFF_CAP=8 chosen (mid-range of 5–10s band per CONTEXT.md Claude's Discretion)
  - _next_backoff() extracted as pure helper for direct unit-testability
  - asyncio.Event() capture via side_effect used to terminate main() loop in tests
  - search_backoff also reset on success (belt-and-suspenders, not strictly required by spec)
metrics:
  duration: ~20 min
  completed: "2026-06-02T00:35:14Z"
  tasks: 1
  files_changed: 2
---

# Phase 3 Plan 02: D-05 Split Backoff Regimes Summary

**One-liner:** Split single `backoff` counter into `search_backoff` (60s cap, gentle) and `reconnect_backoff` (8s cap, fast) to protect the 120s reconnect SLA after known-good link drops.

## What Was Built

`main()` in `daemon/claude_usage_daemon_windows.py` now uses two distinct exponential backoff counters:

- **`search_backoff`** (slow-search regime): used in `if not device:` branch when `scan_for_device()` returns `None`. Doubles toward 60s. Device is genuinely absent — no scan hammering, gentle retry.
- **`reconnect_backoff`** (fast-reconnect regime): used in `if not ok:` branch after `connect_and_run()` returns `False`. Doubles toward `RECONNECT_BACKOFF_CAP=8`. Lost a known-good link (sleep/range/power-cycle) — retry quickly to clear the 120s SLA.

Both backoff waits use the verbatim interruptible idiom:
```python
try:
    await asyncio.wait_for(stop_event.wait(), timeout=backoff)
except asyncio.TimeoutError:
    pass
```

A successful `connect_and_run` (returns `True`) resets both counters to `1` (floor).

New module-level additions:
- `RECONNECT_BACKOFF_CAP = 8` — tunable fast cap constant
- `_next_backoff(current, cap) -> int` — pure helper: `min(current * 2, cap)`, unit-testable without driving the full loop

## TDD Gate Compliance

- RED commit: `9c364f3` — `test(03-02): add failing D-05 tests for split fast-reconnect vs slow-search backoff`
- GREEN commit: `d722b19` — `feat(03-02): implement D-05 split fast-reconnect vs slow-search backoff in main()`

Gate order verified: test commit precedes implementation commit in git log.

## Tasks

### Task 1: RED->GREEN D-05 split fast-reconnect vs slow-search backoff in main()

**Status:** Complete  
**Commits:**
- RED: `9c364f3` — test(03-02): add failing D-05 tests
- GREEN: `d722b19` — feat(03-02): implement D-05 in main()

**Files modified:**
- `daemon/tests/test_windows_reconnect.py` — 9 new D-05 tests appended (file extended, not overwritten)
- `daemon/claude_usage_daemon_windows.py` — `RECONNECT_BACKOFF_CAP`, `_next_backoff()`, split `main()` loop

**Verification:** `python -m pytest daemon/tests/test_windows_reconnect.py -x -q` exits 0 (18/18 passed). Full daemon suite: 46/46 passed.

## Deviations from Plan

### Auto-fixed Issues

None.

### Deliberate Differences from Plan

**Test design: `asyncio.Event` capture instead of direct stop_event injection**

The plan described "patch `asyncio.wait_for` to record the `timeout=` it receives and to set `stop_event` after a fixed number of iterations." The loop-level tests need to terminate `main()`'s `while not stop_event.is_set():` loop. Since `main()` creates its own internal `stop_event = asyncio.Event()`, setting an external event doesn't affect it.

Fix: patch `daemon.claude_usage_daemon_windows.asyncio.Event` with a `side_effect=capturing_Event` factory that captures the created event into `internal_stop_event[0]`, then the `fake_wait_for` sets `internal_stop_event[0]` to terminate the real loop. This is the minimal correct approach without refactoring `main()` to accept an injectable event.

**`search_backoff` also reset on success**

The plan specifies resetting `reconnect_backoff = 1` on success. The implementation also resets `search_backoff = 1` on success. This is a belt-and-suspenders addition: if the device was previously absent and is now found and connected, the search backoff should restart from 1 for the next scan cycle. No test was broken or added for this; it follows the same reset logic.

## Acceptance Criteria Verification

- [x] `main()` uses `search_backoff` (caps at 60) and `reconnect_backoff` (caps at `RECONNECT_BACKOFF_CAP=8`)
- [x] `if not device:` branch waits on `search_backoff`; `if not ok:` branch waits on `reconnect_backoff` (asserted via patched `asyncio.wait_for` timeout capture)
- [x] Successful `connect_and_run` resets `reconnect_backoff` to 1 (and `search_backoff` to 1)
- [x] Both waits use verbatim `asyncio.wait_for(stop_event.wait(), timeout=...)` + `except asyncio.TimeoutError`
- [x] `grep -nv '^#' daemon/claude_usage_daemon_windows.py | grep -c "SAVED_ADDR_FILE\|skip_addr"` == 0
- [x] `requirements-windows.txt` unchanged (`git diff --stat` shows no output)
- [x] `python -m pytest daemon/tests/test_windows_reconnect.py -x -q` exits 0 (18 passed)

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes. Log lines added (`"Device not found, retrying in Xs..."` and `"Connection lost, reconnecting in Xs..."`) carry only device timing info — no token, no address disclosed beyond what 03-01 already logs. Consistent with T-03-06 mitigation.

## Known Stubs

None. Both backoff regimes are fully wired into `main()`.

## Self-Check: PASSED

- `daemon/claude_usage_daemon_windows.py` — modified, present
- `daemon/tests/test_windows_reconnect.py` — modified, present
- `.planning/phases/03-resilience/03-02-SUMMARY.md` — this file
- Commits `9c364f3` (RED) and `d722b19` (GREEN) confirmed in git log
- 18/18 tests pass; 46/46 full daemon suite pass
- No SAVED_ADDR_FILE/skip_addr in daemon; requirements-windows.txt unchanged
