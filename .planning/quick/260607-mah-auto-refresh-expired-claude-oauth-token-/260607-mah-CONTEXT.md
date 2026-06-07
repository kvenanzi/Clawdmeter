# Quick Task 260607-mah: Auto-refresh expired Claude OAuth token - Context

**Gathered:** 2026-06-07
**Status:** Ready for planning

<domain>
## Task Boundary

The Windows daemon (`daemon/claude_usage_daemon_windows.py`) reads only the
short-lived `accessToken` from `.credentials.json` and never refreshes it. When
the access token expires — which happens within hours, and reliably across PC
sleep/power-off because nothing else refreshes it while idle — `poll_api()` gets
a 401/403, raises `AuthError`, and the tray fires *"token expired — run claude
login"* multiple times a day.

Fix: implement the OAuth refresh-token flow that Claude Code performs
internally. When the access token is expired/near-expiry, POST the stored
`refreshToken` to Anthropic's OAuth token endpoint, obtain a fresh
`accessToken` + new `expiresAt` (+ rotated `refreshToken`), and persist it back
to `.credentials.json`. Re-running `claude login` should then only be needed if
the refresh token itself is revoked.

Scope is the Windows daemon token path only. The Linux bash daemon and macOS
daemon are out of scope for this task.
</domain>

<decisions>
## Implementation Decisions

### Write-back behavior
- Refreshed credentials ARE written back to `.credentials.json` atomically
  (temp file + atomic replace), so native-Windows Claude Code stays logged in
  too and the rotated refresh token is preserved across daemon restarts.

### Refresh timing
- Proactive + reactive. Before each poll, check `expiresAt`; if expired or
  within ~5 minutes of expiry, refresh first. Additionally, refresh-and-retry
  once on an unexpected 401 (handles early revocation / a wrong `expiresAt`).

### Race safety (daemon vs native Claude Code, rotating refresh tokens)
- Right before refreshing, RE-READ `.credentials.json`. If Claude Code already
  wrote a fresh token (not expired), use that instead of spending the daemon's
  cached (possibly already-rotated) refresh token. Only perform the network
  refresh if the on-disk token is still stale. Persist the result via
  temp-file + atomic replace to avoid corrupting a file another process may be
  reading.

### Claude's Discretion
- Exact module structure (new helper functions vs. a small token-manager class)
  — planner/executor decides, keep it consistent with the existing single-file
  daemon style.
- Logging/redaction: never log raw token values (existing daemon already avoids
  this — preserve that).
- Failure handling when refresh itself returns 401/invalid_grant: THAT is the
  genuine "run claude login" case and should still toast.
</decisions>

<specifics>
## Specific Ideas

- The credentials file stores `claudeAiOauth.{accessToken, refreshToken,
  expiresAt, scopes, subscriptionType}` (epoch-ms `expiresAt`, JS convention —
  the daemon already divides by 1000 in `_read_expiry()`).
- Existing seams to reuse/extend: `read_token()`, `_read_expiry()`,
  `_extract_access_token()`, `_windows_credential_candidates()`, and the
  `AuthError` distinction in `poll_api()` / `connect_and_run()`.
- Tests live in `daemon/tests/test_windows_token.py` with fixtures under
  `daemon/tests/fixtures/` — extend these (no real network calls; mock httpx).
</specifics>

<canonical_refs>
## Canonical References

- Research (RESEARCH phase) must confirm the exact Anthropic OAuth token
  endpoint, the Claude Code OAuth `client_id`, and the refresh request/response
  shape (`grant_type=refresh_token`, returned `expires_in` vs `expiresAt`).
- `.planning/notes/windows-daemon-port.md` — Windows daemon port background.
</canonical_refs>
