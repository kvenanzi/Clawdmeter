---
phase: 02-core-pipeline
plan: 01
subsystem: daemon
tags: [windows, polling, httpx, bleak, tdd, anthropic-api]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: read_token(), _extract_access_token(), _windows_credential_candidates(), _read_expiry() in claude_usage_daemon_windows.py
provides:
  - poll_api() async function that maps Anthropic ratelimit headers to {s,sr,w,wr,st,ok} payload
  - Module-level constants (DEVICE_NAME, SERVICE/RX/REQ UUIDs, POLL_INTERVAL, TICK, SCAN_TIMEOUT, API_URL, API_HEADERS_TEMPLATE, API_BODY)
  - log() timestamped stdout helper
  - daemon/requirements-windows.txt listing bleak + httpx
  - pytest suite asserting compact-JSON wire shape and token-not-logged (T-02-01)
affects: [02-02-ble-connection, 02-03-integration]

# Tech tracking
tech-stack:
  added: [httpx (async HTTP client), bleak (BLE/WinRT), asyncio, signal]
  patterns: [TDD RED->GREEN, inline pct/reset_minutes closures inside poll_api, httpx.AsyncClient context manager mocked via patch]

key-files:
  created:
    - daemon/tests/test_windows_poll.py
    - daemon/requirements-windows.txt
  modified:
    - daemon/claude_usage_daemon_windows.py

key-decisions:
  - "poll_api() copied verbatim from macOS daemon lines 274-314 (pct/reset_minutes closures kept inline)"
  - "bleak installed in dev env (was missing despite plan pre-check claim; legitimacy confirmed per threat model T-02-SC)"
  - "No SAVED_ADDR_FILE introduced (D-04: disk cache deferred to Phase 3)"
  - "separators=(',',':') encoding asserted in test, applied in Session.write_payload (Plan 02-02)"

patterns-established:
  - "pct() inline closure: int(round(float(util)*100)), ValueError -> 0"
  - "reset_minutes() inline closure: (epoch - now) / 60, clamped at 0, ValueError -> 0"
  - "httpx mocking: patch httpx.AsyncClient with AsyncMock context manager, fake .post() returning MagicMock response"

requirements-completed: [POLL-01]

# Metrics
duration: 12min
completed: 2026-06-01
---

# Phase 02 Plan 01: Polling Logic Port (POLL-01) Summary

**poll_api() ported verbatim from macOS daemon with httpx-mocked unit tests locking the {s,sr,w,wr,st,ok} wire contract before BLE glue is added.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-06-01T21:51:02Z
- **Completed:** 2026-06-01T22:03:00Z
- **Tasks:** 2 completed
- **Files modified:** 3 created/modified

## Accomplishments

- Ported `poll_api()` + module constants + `log()` from macOS daemon into the Windows scaffold, preserving all Phase 1 functions untouched
- 14 pytest tests cover pct/reset_minutes math, missing-header defaults, HTTP >=400 and httpx.HTTPError error paths, compact-JSON wire shape, and token-not-logged (T-02-01)
- Created `daemon/requirements-windows.txt` with bleak + httpx, strictly additive (no shared requirements.txt touched)

## TDD Gate Compliance

- RED commit (`6057823`): `test(02-01): add failing poll_api/pct/reset_minutes/JSON-shape tests` — confirmed ImportError on collection
- GREEN commit (`5e19d5f`): `feat(02-01): port poll_api + constants from macOS daemon (POLL-01)` — 14/14 pass
- REFACTOR: not needed (no duplication to remove)

## Task Commits

1. **Task 1 RED: test_windows_poll.py** - `6057823` (test)
2. **Task 1 GREEN: poll_api + constants** - `5e19d5f` (feat)
3. **Task 2: requirements-windows.txt** - `b26543a` (chore)

## Files Created/Modified

- `daemon/tests/test_windows_poll.py` — 14 unit tests for poll_api/pct/reset_minutes/JSON-shape/token-safety
- `daemon/claude_usage_daemon_windows.py` — added asyncio/httpx/bleak imports, module constants, log(), poll_api()
- `daemon/requirements-windows.txt` — Windows-only dependency manifest (bleak, httpx)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] bleak not installed in dev environment**
- **Found during:** Task 1 GREEN (import at module top level would have caused test collection failure)
- **Issue:** Threat model T-02-SC claimed "both are already present in this repo's dev env per pre-check" but `bleak` was not installed
- **Fix:** Installed `bleak` via pip. Package legitimacy confirmed per T-02-SC (hbldh/bleak, well-known PyPI package). Installation succeeded without substitution.
- **Files modified:** none (environment only)
- **Commit:** n/a

## Known Stubs

None — poll_api() returns real data from live API calls; no hardcoded values or placeholder returns.

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or schema changes beyond what the plan's threat model covers (T-02-01 token logging, T-02-02 TLS, T-02-03 header parsing, T-02-SC pip legitimacy).

## Self-Check: PASSED

- `daemon/tests/test_windows_poll.py` exists
- `daemon/requirements-windows.txt` exists
- `daemon/claude_usage_daemon_windows.py` modified
- Commits `6057823`, `5e19d5f`, `b26543a` verified in git log
