---
phase: 260607-mah-auto-refresh-expired-claude-oauth-token
reviewed: 2026-06-07T00:00:00Z
depth: quick
files_reviewed: 2
files_reviewed_list:
  - daemon/claude_usage_daemon_windows.py
  - daemon/tests/test_windows_token.py
findings:
  critical: 1
  warning: 3
  info: 2
  total: 6
status: issues_found
---

# Phase 260607-mah: Code Review Report

**Reviewed:** 2026-06-07
**Depth:** quick (extended to standard for focus areas from prompt)
**Files Reviewed:** 2
**Status:** issues_found

## Summary

Reviewed the OAuth token auto-refresh implementation added in `daemon/claude_usage_daemon_windows.py` and its test suite `daemon/tests/test_windows_token.py`. The core logic — expires-in conversion, atomic write recipe, reactive single-retry, token redaction — is largely correct. One critical bug exists: `AuthError` raised on the proactive refresh path propagates unhandled through the daemon loop and crashes the process. Three warnings cover a malformed-200-response token burn, a redundant import, and a TOCTOU in the write-back path. Two info items flag test coverage gaps.

---

## Critical Issues

### CR-01: Uncaught `AuthError` from proactive `get_valid_token` crashes the daemon

**File:** `daemon/claude_usage_daemon_windows.py:665`

**Issue:** `get_valid_token()` documents and propagates `AuthError` when `_refresh_oauth_token` returns a genuine 400/401/403. In the _reactive_ path inside `_poll_with_refresh` this is caught correctly (line 562). But in the _proactive_ path — called at line 665 inside `connect_and_run`'s while-loop body — there is no `except AuthError` and no outer catch anywhere between that call and `asyncio.run(main())` (which only catches `KeyboardInterrupt`).

Consequence: the first genuine OAuth refresh failure during proactive refresh (expired or revoked refresh token) propagates as an unhandled exception through `connect_and_run` → `main()` → `asyncio.run()`, crashing the entire daemon process. The comment at line 670–671 says "by design," but the intended design (show a toast then keep running) is not implemented — the daemon dies instead.

The old code at the same call site (`read_token()`) could never raise; `get_valid_token` introduced a new raise path that was not guarded at the call site.

**Fix:**
```python
# In connect_and_run, replace the bare await at line 665:
try:
    token = await get_valid_token(tray_state)
except AuthError:
    log("Proactive token refresh failed (genuine); firing 'run claude login' toast")
    if tray_state:
        tray_state.set_error("token expired — run claude login")
    token = None
```
This matches how `_poll_with_refresh` handles the same exception class on the reactive path and keeps the daemon alive for subsequent ticks/reconnects.

---

## Warnings

### WR-01: Empty `access_token` in a 200 response burns the refresh token and writes corrupt credentials

**File:** `daemon/claude_usage_daemon_windows.py:503-528`

**Issue:** When the OAuth server returns HTTP 200 but omits `access_token` (or returns an empty string), `new_access_token` is set to `""` (line 503). The code then writes the entire updated object — including the newly rotated `refreshToken` and `expiresAt = now_ms + 0` — to disk via `_atomic_write_credentials` (line 528) before returning `""`. The single-use refresh token is burned. On the next tick, `expires_ms <= threshold_ms` immediately (because `expires_in=0` produces `expiresAt = now_ms`), so the daemon re-reads the rotated refresh token and tries again — creating a perpetual retry loop using whatever token the server last issued. If the server consistently returns `200 {}` the daemon loops silently forever.

**Fix:**
```python
# After line 503, validate before writing:
new_access_token = refresh_result.get("access_token", "")
if not new_access_token:
    log("get_valid_token: OAuth 200 response missing access_token — treating as transient")
    return None  # do NOT write back; do NOT burn the refresh token
```
Also validate `expires_in > 0` before computing `new_expires_ms`, or clamp to a safe minimum (e.g. `max(expires_in_secs, 300)`).

### WR-02: Redundant `import datetime as _dt` inside `get_valid_token`

**File:** `daemon/claude_usage_daemon_windows.py:529`

**Issue:** `datetime` is already imported at module scope on line 10. The in-function `import datetime as _dt` at line 529 shadows it with an alias and re-runs the import machinery on every successful token refresh (no-op in CPython due to `sys.modules` caching, but still misleading). If the module-level `datetime` import is ever removed or the alias is mixed with the bare name, this creates a latent confusion.

**Fix:** Remove line 529 and replace `_dt.datetime` / `_dt.timezone` references with the module-level `datetime.datetime` / `datetime.timezone` already in scope.

```python
# Replace:
import datetime as _dt
expiry_dt = _dt.datetime.fromtimestamp(new_expires_ms / 1000, tz=_dt.timezone.utc)

# With:
expiry_dt = datetime.datetime.fromtimestamp(new_expires_ms / 1000, tz=datetime.timezone.utc)
```

### WR-03: Write-back path selection is a separate `path.exists()` scan, not the path that was actually read (TOCTOU)

**File:** `daemon/claude_usage_daemon_windows.py:521-525`

**Issue:** After a successful refresh, `get_valid_token` iterates `_windows_credential_candidates()` a third time looking for the first `path.exists()` to write back to (lines 521–525). `_read_full_credentials` (called twice above) also iterates the same candidates and returns the first _readable_ file — it does not expose which path it used. If files are created or deleted between the second read and the write-back scan, the write could target a _different_ file than the one that was read: e.g., if `~/.claude/.credentials.json` didn't exist at read time but does at write time, the daemon reads from `LOCALAPPDATA/Claude/.credentials.json` and writes back to `~/.claude/.credentials.json`. This silently splits credentials across two files.

The risk is low in practice (credential files rarely appear mid-flight) but the fix is straightforward.

**Fix:** Thread the resolved path through `_read_full_credentials` by returning a tuple, or track it in `get_valid_token` by replicating the read loop locally and capturing the path on success:

```python
# Replace _read_full_credentials with a version that also returns the path:
def _read_full_credentials() -> tuple[dict, Path] | tuple[None, None]:
    for path in _windows_credential_candidates():
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            return json.loads(raw), path
        except (json.JSONDecodeError, ValueError):
            return None, None
    return None, None
```
Then use the returned path directly in `get_valid_token` rather than re-scanning.

---

## Info

### IN-01: No test for the race re-read "token became fresh on second read" path

**File:** `daemon/tests/test_windows_token.py`

**Issue:** `TestGetValidToken` has no test that exercises the branch at line 483–486 (`get_valid_token: on-disk token already fresh after re-read, skipping network refresh`). This is the primary correctness property of the race-condition mitigation: the daemon should skip the network call when Claude Code has refreshed concurrently. Without a test, a future refactor could silently break this guard and start burning single-use refresh tokens.

**Fix:** Add a test that monkeypatches `_read_full_credentials` to return a stale token on the first call and a fresh token on the second call, then asserts that no HTTP call was made and the fresh token is returned.

### IN-02: No test for the primary-to-fallback URL escalation in `_refresh_oauth_token`

**File:** `daemon/tests/test_windows_token.py`

**Issue:** `TestRefreshOauthToken` has no test that exercises the fallback URL path: primary returns 404 → retry on `OAUTH_FALLBACK_URL`, or primary raises `httpx.ConnectError` → retry on fallback. The existing `test_network_error_returns_none` applies the same `ConnectError` to all calls (both primary and fallback), which only exercises the "all URLs exhausted" branch. A regression in the `i < len(urls_to_try) - 1` guard condition would go undetected.

**Fix:** Add a test where `mock_client.post` returns a 404 on the first call and a 200 on the second, asserting that the 200 response body is returned (i.e., the fallback was reached).

---

_Reviewed: 2026-06-07_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: quick/standard (focused)_
