---
phase: 01-foundation
plan: 02
subsystem: daemon
tags: [python, windows, token-reader, tdd, stdlib]

# Dependency graph
requires:
  - 01-01 (pytest test infrastructure + RED suite)
provides:
  - daemon/claude_usage_daemon_windows.py (TOKEN-01 satisfied)
  - _extract_access_token (verbatim copy from macOS daemon, D-08)
  - read_token (file-search first-hit-wins, D-02/D-03)
  - _windows_credential_candidates (env overrides + 3-path fallback)
  - _read_expiry (ms-epoch decoding, D-06)
  - __main__ redacted output (D-06/D-07)
affects:
  - Phase 2 BLE (will import read_token from this module)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - _extract_access_token verbatim copy pattern (D-08 — no import, copy body)
    - first-hit-wins candidate loop with OSError catch
    - JS-epoch-ms / 1000 decode via datetime.fromtimestamp
    - __main__ redaction: token[-4:] only, never full token (D-06)

key-files:
  created:
    - daemon/claude_usage_daemon_windows.py
  modified: []

key-decisions:
  - "D-08 enforced: _extract_access_token copied verbatim (not imported) from daemon/claude_usage_daemon.py §57-86"
  - "D-05 enforced: stdlib-only scaffold — no bleak/httpx/asyncio/logging framework/main loop"
  - "D-04 enforced: file-search only — no Windows Credential Manager / keyring / sys.platform Keychain branch"
  - "D-06/D-07 enforced: __main__ prints sk-ant-...last4 only; failure exits 1 with actionable message"
  - "expiresAt divided by 1000 — JS-convention milliseconds to Python seconds"

# Metrics
duration: 5min
completed: 2026-06-01
---

# Phase 01 Plan 02: Windows Token Reader Summary

**stdlib-only Windows OAuth token reader implementing _extract_access_token (verbatim copy), first-hit-wins read_token with env overrides + 3-path fallback, ms-epoch expiry decode, and redacted __main__ — all 9 TOKEN-01 tests GREEN**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-06-01T19:08:51Z
- **Completed:** 2026-06-01T19:12:07Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments

- Created `daemon/claude_usage_daemon_windows.py` satisfying all TOKEN-01 acceptance criteria
- Copied `_extract_access_token` verbatim from `daemon/claude_usage_daemon.py` §57-86 (D-08) — handles direct `accessToken`, nested `claudeAiOauth`, regex fallback, and raw-token fullmatch
- Implemented `_windows_credential_candidates()` with three-tier priority: `CLAUDE_CREDENTIALS_PATH` (D-03) → `CLAUDE_CONFIG_DIR` (official override) → three D-02 candidates using `Path.home()` (not `os.path.expandvars`)
- Implemented `read_token()` as a first-hit-wins loop catching `OSError` (covers `PermissionError` subclass per Windows file lock semantics)
- Implemented `_read_expiry()` with explicit `expires_ms / 1000` division (JS-epoch-ms to Python seconds — prevents year ~57000 output, satisfies Pitfall 2 from RESEARCH.md)
- Added `__main__` block with WSL platform warning, redacted `sk-ant-...{token[-4:]}` output, and D-07 failure path with `sys.exit(1)`
- All 9 TOKEN-01 unit tests GREEN (confirmed with `python -m pytest daemon/tests/test_windows_token.py -q`)

## Task Commits

Each task committed atomically:

1. **Task 1 (RED to GREEN): Implement _extract_access_token, candidates, read_token** - `91a1d09` (feat)
2. **Task 2 (GREEN to REFACTOR): Add _read_expiry and redacted __main__** - `c56c91c` (feat)

## Files Created/Modified

- `daemon/claude_usage_daemon_windows.py` — 127-line stdlib-only scaffold with 4 exported functions and `__main__` block

## Decisions Made

- `_extract_access_token` copied byte-for-byte (D-08) — not imported — because `daemon/claude_usage_daemon.py` executes macOS-specific code at module scope and would fail on import on Windows/WSL
- `_windows_credential_candidates` made a module-level function (not inline in `read_token`) so tests can monkeypatch it deterministically — enables the fallback path tests from plan 01-01
- `_read_expiry` calls `_windows_credential_candidates()` directly (same shared function as `read_token`) — no duplicated path logic (REFACTOR goal satisfied)
- `Path.home()` used instead of `os.path.expandvars('%USERPROFILE%')` — latter returns literal string on Linux/WSL, defeating cross-platform test execution

## Deviations from Plan

### Implementation Efficiency

**1. [Rule 1 - Efficiency] Both tasks implemented in one file write**
- **Found during:** Task 1 implementation
- **Issue:** The plan's two-task TDD split (Task 1: core reader, Task 2: expiry + main) was naturally implemented in one atomic file write since the functions are interdependent and small
- **Fix:** Committed full file under Task 1 message; Task 2 commit added the ms-division comment to `_read_expiry` as a meaningful documentation addition that makes the Pitfall 2 guard self-documenting
- **Files modified:** `daemon/claude_usage_daemon_windows.py`
- **Commits:** `91a1d09` (Task 1), `c56c91c` (Task 2)

## TDD Gate Compliance

- RED gate: `python -m pytest daemon/tests/test_windows_token.py -x -q` — confirmed failing at import (`ModuleNotFoundError`) before implementation (inherited from plan 01-01)
- GREEN gate: all 9 tests pass after `feat(01-02): implement Windows token reader` commit (`91a1d09`)
- REFACTOR gate: `_read_expiry` ms-division comment added in `feat(01-02): redacted token+expiry output for __main__` commit (`c56c91c`)

## Known Stubs

None — the module fully implements its stated scope. `read_token()` returns a real token string (not a placeholder) from the credentials file. Phase 2 (BLE) will consume this function directly.

## Threat Flags

No new threat surface beyond what the plan's threat model covers. The module reads from the filesystem only (no network endpoints, no new auth paths, no schema changes). T-01-ID (token redaction) is implemented: `token[-4:]` only in `__main__`, never `print(token)`.

## Self-Check

- [x] `daemon/claude_usage_daemon_windows.py` exists
- [x] `python -m pytest daemon/tests/test_windows_token.py -q` exits 0 (9 passed)
- [x] `grep -E "bleak|httpx|asyncio|expandvars|wsl" daemon/claude_usage_daemon_windows.py` returns nothing
- [x] `CLAUDE_CREDENTIALS_PATH=daemon/tests/fixtures/credentials_nested.json python daemon/claude_usage_daemon_windows.py` prints `Token OK (sk-ant-…1234), expires 2286-11-20 17:46 UTC`
- [x] `CLAUDE_CREDENTIALS_PATH=/nonexistent/x.json python daemon/claude_usage_daemon_windows.py` exits 1
- [x] `grep -c "expires_ms / 1000" daemon/claude_usage_daemon_windows.py` is 1
- [x] Commits `91a1d09` and `c56c91c` exist in git log

## Self-Check: PASSED
