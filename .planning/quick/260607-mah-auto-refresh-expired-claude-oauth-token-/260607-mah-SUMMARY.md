---
phase: 260607-mah
plan: "01"
subsystem: daemon-windows
tags: [oauth, token-refresh, tdd, windows-daemon]
dependency_graph:
  requires: []
  provides: [oauth-refresh-flow, get_valid_token, atomic-writeback]
  affects: [daemon/claude_usage_daemon_windows.py, daemon/tests/test_windows_token.py]
tech_stack:
  added: []
  patterns: [atomic-tempfile-replace, proactive-plus-reactive-refresh, race-reread-before-refresh]
key_files:
  modified:
    - daemon/claude_usage_daemon_windows.py
    - daemon/tests/test_windows_token.py
decisions:
  - "Use asyncio.run() in _run() test helper (not get_event_loop()) for Python 3.10+ safety"
  - "ensure_ascii=False in json.dump so UTF-8 bytes written literally (not \\uXXXX escaped)"
  - "Status-code-only gating for auth vs transient: 400/401/403 = AuthError, everything else = None"
  - "_poll_with_refresh extracted as unit-testable helper; connect_and_run calls it instead of inlining"
  - "import datetime inside get_valid_token to avoid shadowing the top-level import alias"
metrics:
  duration: "~8 minutes"
  completed: "2026-06-07"
  tasks_completed: 3
  files_modified: 2
---

# Phase 260607-mah Plan 01: OAuth Token Auto-Refresh Summary

OAuth refresh-token flow implemented in the Windows daemon so expired Claude access tokens are silently refreshed (proactively and reactively) instead of firing the "run claude login" tray toast multiple times a day.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Atomic write-back + full-credentials read helpers | 0ac16d8 | daemon/claude_usage_daemon_windows.py, daemon/tests/test_windows_token.py |
| 2 | OAuth refresh call + get_valid_token | 9e39239 | daemon/claude_usage_daemon_windows.py |
| 3 | Wire proactive + reactive refresh into connect_and_run | f442d58 | daemon/claude_usage_daemon_windows.py, daemon/tests/test_windows_token.py |

## What Was Built

**New helpers in `daemon/claude_usage_daemon_windows.py`:**

- `_parse_expiry_ms(full_obj)` — extracts `claudeAiOauth.expiresAt` as epoch ms int; None-safe. Refactors `_read_expiry()` to use it (existing contract preserved).
- `_read_full_credentials()` — reads first-hit candidate path, returns the complete parsed dict (including refreshToken, subscriptionType, rateLimitTier, etc.), or None.
- `_atomic_write_credentials(path, full_obj)` — same-dir mkstemp + fsync + os.replace; ensure_ascii=False UTF-8; unlinks temp on failure; never logs token values.
- `async _refresh_oauth_token(refresh_token)` — POSTs to OAUTH_TOKEN_URL (platform.claude.com) with JSON `grant_type=refresh_token` body; falls back to OAUTH_FALLBACK_URL (console.anthropic.com) on connection error or non-OAuth 404; raises AuthError on 400/401/403; returns None on transient failures.
- `async get_valid_token(tray_state=None)` — proactive refresh: reads full creds, returns cached token if fresh (>5 min remaining, no network); RE-READs disk before spending refresh token (race mitigation); calls `_refresh_oauth_token` if stale; atomic write-back of full object with only token keys mutated; propagates AuthError on genuine failure; returns None on transient.
- `async _poll_with_refresh(token, tray_state=None)` — unit-testable reactive retry helper: calls `poll_api`; on AuthError, performs exactly ONE forced refresh + ONE retry; toasts only if forced refresh raises AuthError.

**Module-level constants added:**
- `OAUTH_TOKEN_URL = "https://platform.claude.com/v1/oauth/token"`
- `OAUTH_FALLBACK_URL = "https://console.anthropic.com/v1/oauth/token"`
- `OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"`
- `OAUTH_PROACTIVE_REFRESH_SECS = 300` (5 minutes)

**`connect_and_run` updated:**
- `read_token()` replaced with `await get_valid_token(tray_state)` (proactive refresh before every poll)
- `poll_api()` + `except AuthError` block replaced with `await _poll_with_refresh(token, tray_state)` (reactive retry on unexpected 401, exactly once, toast only on genuine forced-refresh AuthError)

## Test Coverage

45 tests in `test_windows_token.py` (31 new, 14 pre-existing preserved):

- `TestAtomicWriteCredentials` (4 tests): writes exact content, preserves unrelated keys (subscriptionType/rateLimitTier), no .cred-*.tmp leak on success, UTF-8 encoding
- `TestReadFullCredentials` (3 tests): returns nested object with refreshToken, None on missing file, None on invalid JSON
- `TestParseExpiryMs` (5 tests): returns int, None on absent/non-numeric/no-oauth-key, _read_expiry still passes
- `TestRefreshOauthToken` (6 tests): 200 returns dict, 400/401/403 raises AuthError, network error returns None, 5xx returns None, correct client_id/grant_type sent
- `TestGetValidToken` (7 tests): fresh token no network, proactive refresh on near-expiry, rotated refresh_token persisted, absent refresh_token reuses old, subscriptionType preserved, invalid_grant->AuthError, transient->None, no-raw-token-in-logs (T-mah-01)
- `TestPollWithRefresh` (4 tests): reactive retry succeeds no toast, forced-refresh AuthError fires toast, transient refresh no toast, first-try success returns payload

Full suite: **120 passed** (no regressions in poll, BLE, reconnect, tray, autostart, icon suites).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] asyncio.get_event_loop() fails in Python 3.10+ when run under full test suite**
- **Found during:** Task 3 full suite run
- **Issue:** `asyncio.get_event_loop()` raises `RuntimeError: There is no current event loop` in Python 3.10+ when called from a test that runs after another test module that closed/replaced the loop.
- **Fix:** Changed `_run()` helper in test file to use `asyncio.run(coro)` which always creates a fresh event loop and closes it after.
- **Files modified:** daemon/tests/test_windows_token.py
- **Commit:** f442d58

**2. [Rule 1 - Bug] json.dump encodes non-ASCII as \uXXXX by default**
- **Found during:** Task 1 UTF-8 encoding test
- **Issue:** Default `json.dump` escapes non-ASCII characters (e.g., `café` -> `café`), which fails the test asserting raw UTF-8 bytes are present. Claude Code writes files with ensure_ascii=False to match native formatting.
- **Fix:** Added `ensure_ascii=False` to `json.dump` call in `_atomic_write_credentials`.
- **Files modified:** daemon/claude_usage_daemon_windows.py
- **Commit:** 0ac16d8

## Security Notes (Threat Mitigations)

| Threat ID | Status |
|-----------|--------|
| T-mah-01 (no raw token logging) | Mitigated — log() calls reference len()/expiry only; explicit test asserts no token in stdout/stderr |
| T-mah-02 (atomic write-back) | Mitigated — same-dir mkstemp + fsync + os.replace; temp unlinked on failure |
| T-mah-03 (rotating single-use refresh tokens) | Mitigated — re-read disk immediately before refresh; skip network if fresh; persist rotated token atomically |
| T-mah-04 (wrong OAuth endpoint) | Mitigated — two module-level constants; primary tries platform.claude.com, falls back to console.anthropic.com on connection error or non-OAuth 404 |
| T-mah-05 (transient vs genuine auth failure) | Mitigated — status-code-only gating: 400/401/403 = AuthError; everything else = None (no toast) |

## Known Stubs

None. All functionality is wired end-to-end.

## Threat Flags

None. No new network endpoints or trust boundaries introduced beyond what the plan specified.

## Self-Check: PASSED

- daemon/claude_usage_daemon_windows.py: FOUND
- daemon/tests/test_windows_token.py: FOUND
- Commit 0ac16d8 (Task 1): FOUND
- Commit 9e39239 (Task 2): FOUND
- Commit f442d58 (Task 3): FOUND
- 45 token tests pass: VERIFIED
- 120 full suite tests pass: VERIFIED
- Only daemon/claude_usage_daemon_windows.py and daemon/tests/test_windows_token.py changed: VERIFIED
- No raw token logging: VERIFIED (grep confirms only len() reference)
