# Quick Task 260607-mah: Auto-refresh expired Claude OAuth token — Research

**Researched:** 2026-06-07
**Domain:** Anthropic / Claude Code OAuth refresh-token flow; atomic file write-back on Windows
**Confidence:** HIGH on endpoint/client_id/request shape (cross-confirmed by a working public implementation + multiple sources); MEDIUM on the endpoint-vs-content-type pairing (two valid variants exist — see Pitfall 1).

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Write-back:** Refreshed credentials ARE written back to `.credentials.json` atomically (temp file + atomic replace), so native Claude Code stays logged in and the rotated refresh token survives daemon restarts.
- **Timing:** Proactive + reactive. Before each poll, check `expiresAt`; if expired or within ~5 min of expiry, refresh first. Additionally refresh-and-retry **once** on an unexpected 401.
- **Race safety:** Right before refreshing, RE-READ `.credentials.json`. If Claude Code already wrote a fresh (non-expired) token, use that instead of spending the daemon's cached (possibly already-rotated) refresh token. Only do the network refresh if on-disk token is still stale. Persist via temp-file + atomic replace.

### Claude's Discretion
- Module structure (helpers vs small token-manager class) — keep single-file style.
- Never log raw token values (preserve existing behavior).
- Refresh itself returning 401 / `invalid_grant` IS the genuine "run claude login" case — still toast.

### Deferred / Out of Scope
- Linux bash daemon and macOS daemon token paths. Windows daemon only.

## OAuth Refresh Spec (CRITICAL — copy-pasteable)

### Token endpoint
- **`https://console.anthropic.com/v1/oauth/token`** — `[VERIFIED]` working in the canonical public implementation `RavenStorm-bit/claude-token-refresh` (`claude_token_refresh.py` line 22) and confirmed by community refresh notes.
- **`https://platform.claude.com/v1/oauth/token`** — `[LIKELY]` the *current* endpoint per the shubcodes gist and recent docs/issues. Anthropic rebranded `console.anthropic.com` → `platform.claude.com`. The old host historically still works (often via redirect), but treat `platform.claude.com` as the primary going forward. **See Pitfall 1 for the recommended try-both strategy.**

### Client ID (public PKCE client)
- **`9d1c250a-e61b-44d9-88ed-5944d1962f5e`** — `[VERIFIED]` (canonical impl line 23; shubcodes gist). Public application identifier for "Claude Code". No client secret (public PKCE client).

### Refresh request

```
POST https://console.anthropic.com/v1/oauth/token
Content-Type: application/json

{
  "grant_type": "refresh_token",
  "refresh_token": "<stored refreshToken, e.g. sk-ant-ort01-...>",
  "client_id": "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
}
```

| Field | Value | Confidence |
|-------|-------|-----------|
| Method | `POST` | `[VERIFIED]` |
| `Content-Type` | `application/json` (canonical impl sends `json=payload`) | `[VERIFIED]` for the `console.anthropic.com` host. The gist claims `application/x-www-form-urlencoded` for `platform.claude.com` — `[LIKELY]` both content types are accepted; JSON is proven to work. |
| body `grant_type` | `"refresh_token"` | `[VERIFIED]` |
| body `refresh_token` | stored token | `[VERIFIED]` |
| body `client_id` | the public client_id | `[VERIFIED]` |
| `client_secret` | **omit** (public client) | `[VERIFIED]` — none stored, none sent |

### Refresh response (HTTP 200)

```json
{
  "token_type": "Bearer",
  "access_token": "sk-ant-oat01-...",
  "refresh_token": "sk-ant-ort01-...",
  "expires_in": 28800,
  "scope": "user:inference user:profile ..."
}
```

| Field | Meaning | Confidence |
|-------|---------|-----------|
| `access_token` | new access token | `[VERIFIED]` |
| `refresh_token` | **rotated** — a NEW refresh token each time. Persist it; the old one is consumed server-side. May be absent in some responses → fall back to the existing one. | `[VERIFIED]` rotation shipped in Claude Code 10.41.0 (Apr 2026); canonical impl uses `.get('refresh_token', existing)` |
| `expires_in` | lifetime in **seconds** (typically `28800` = 8h; access tokens are short-lived) | `[VERIFIED]` |
| `scope` | space-delimited string | `[LIKELY]` — note it's a STRING here, but `.credentials.json` stores `scopes` as an array. Convert: `scope.split()`. |

### expires_in → expiresAt mapping (load-bearing)

`.credentials.json` stores `claudeAiOauth.expiresAt` as **epoch milliseconds** (JS convention — `_read_expiry()` already divides by 1000). Convert the seconds response to ms:

```python
expires_at_ms = int(time.time() * 1000) + new["expires_in"] * 1000
```

`[VERIFIED]` — this exact formula is in the canonical impl (line 192).

### Error responses
| Status | Body | Meaning | Daemon action |
|--------|------|---------|---------------|
| `400` | `{"error": "invalid_grant", ...}` | refresh token revoked/expired/already-consumed | **GENUINE auth failure** → toast "run claude login" `[LIKELY]` — issue #54443 confirms 400 on bad refresh; `invalid_grant` is the OAuth-standard code (`[ASSUMED]` exact body string) |
| `401`/`403` | varies | same as above | genuine → toast |
| timeout / 5xx / network | — | transient | return None, no toast, retry next tick |
| `404` | — | refresh token already consumed by a concurrent process (single-use) | treat as transient on first occurrence; re-read disk before deciding `[LIKELY]` per community race notes |

**Safest fallback:** distinguish by status code, not body parsing. `400/401/403` from the token endpoint = genuine re-login. Anything else = transient. Only parse the body for logging (redacted), never to gate behavior.

## `.credentials.json` write-back safety (Windows)

- **Atomic replace:** write to a temp file in the **same directory** (so `os.replace` is a same-volume rename), `f.flush()` + `os.fsync(f.fileno())`, then `os.replace(tmp, target)`. On Windows `os.replace` IS atomic and overwrites an existing target (unlike `os.rename`, which raises if target exists). `[VERIFIED: Python docs — os.replace]`
- **Preserve the full object:** load existing JSON, mutate only `accessToken`, `refreshToken`, `expiresAt` (and `scopes` if you choose to update from `scope.split()`). Keep `subscriptionType`, `rateLimitTier`, and any other keys untouched. Re-dump the whole `claudeAiOauth` object inside its parent. `[VERIFIED]` matches canonical impl's `oauth_config.update({...})` approach.
- **Encoding:** read/write `encoding="utf-8"` (the daemon already does this everywhere). `json.dump(..., indent=2)` to match Claude Code's formatting.
- **Cleanup:** wrap in try/finally to unlink the temp file if replace fails.
- **Skip the `.backup` file** the canonical impl writes — unnecessary churn next to a file native Claude Code watches.

```python
import os, json, tempfile
def _atomic_write_credentials(path: Path, full_obj: dict) -> None:
    d = path.parent
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".cred-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(full_obj, f, indent=2)
            f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)   # atomic on Windows + POSIX, overwrites target
    except BaseException:
        try: os.unlink(tmp)
        except OSError: pass
        raise
```

## Integration points in the existing daemon

The hook lives inside `connect_and_run()` at the existing `token = read_token()` line (currently line ~382). Recommended flow:

1. **Replace `read_token()` with a new `get_valid_token()`** that:
   - Reads the FULL credential object from the first-hit path (extend `_windows_credential_candidates()`; you already have it).
   - If `accessToken` present AND `expiresAt` more than ~5 min in the future → return it (no network).
   - Else **re-read disk** (CONTEXT race rule — Claude Code may have just refreshed) and re-check expiry. Still stale → call refresh.
   - On refresh 200 → atomic write-back, return new access token.
   - On refresh `400/401/403` → raise `AuthError` (genuine; existing handler already toasts).
   - On refresh network/timeout → return None (transient; existing "No token; skipping poll" path, no toast). Consider a dedicated log line.
2. **Reactive retry on poll 401:** wrap the existing `poll_api(token)` so that catching `AuthError` from the *poll* triggers ONE forced refresh + single retry before toasting. If the forced refresh itself fails with `400/401/403`, THEN toast. This satisfies CONTEXT "refresh-and-retry once on an unexpected 401."
3. **Keep AuthError semantics intact:** `None` = transient (no toast); `AuthError` = genuine. The only new genuine-auth source is a refresh endpoint `400/401/403`. Everything else maps to None.
4. **Reuse existing seams:** `_windows_credential_candidates()` (path resolution), `_extract_access_token()` (still useful for the no-refresh fast path), `_read_expiry()` parsing logic (factor out a `_parse_expiry_ms()` helper returning the int ms for the proactive check). Refresh uses the same `httpx.AsyncClient` already imported.

**Async note:** `poll_api` is async and uses `httpx.AsyncClient`. Make the refresh call `async def refresh_token(...)` with `httpx.AsyncClient` too, so it composes inside `connect_and_run`'s loop. The file read/atomic-write are sync but fast — fine to call directly (or wrap in `asyncio.to_thread` if you want to be strict; not required for a tiny file).

## Pitfalls

1. **Endpoint + content-type pairing.** Two valid variants exist in the wild: `console.anthropic.com` + `application/json` (proven working) vs `platform.claude.com` + form-encoded (current-host claim). **Recommendation:** try `platform.claude.com` with JSON first; on a connection error or a 404-not-the-OAuth-error, fall back to `console.anthropic.com`. Make both the URL and content-type module-level constants so a one-line change fixes it if Anthropic flips behavior. Do NOT hardcode only one without a fallback — getting this wrong means silent refresh failure (the whole point of the task).
2. **Rotating refresh tokens race native Claude Code (single-use tokens).** Refresh tokens are single-use; the server consumes the old one on success. If the daemon refreshes using a token Claude Code already rotated away, you get `400/404`. The CONTEXT mitigation (re-read disk immediately before refreshing, prefer a fresh on-disk token) handles the common case. Also: persist the NEW refresh token immediately and atomically so a crash mid-cycle doesn't strand you. Issues #27933 / #24317 document this exact race.
3. **`expires_in` is seconds, `expiresAt` is milliseconds.** Multiply by 1000 and add `time.time()*1000`. Mirror the existing `_read_expiry()` ms convention. Off-by-1000 → token treated as expired-in-1970 or valid-until-year-57000.
4. **`scope` (string) vs `scopes` (array).** Response gives a space-delimited string; the file stores an array. `scope.split()`. Safer: only overwrite `scopes` if the response actually contains `scope`, else leave the existing array.
5. **No real network in tests.** Existing tests mock `httpx.AsyncClient` via `unittest.mock.patch("httpx.AsyncClient", ...)` (see `test_windows_poll.py`) — there is **no `respx` dependency**. Follow that pattern: patch `httpx.AsyncClient`, return an `AsyncMock` whose `post` yields a mock response with `.status_code` / `.json()` / `.text`. For write-back tests, use `tmp_path` + `monkeypatch.setenv("CLAUDE_CREDENTIALS_PATH", ...)` exactly like the existing token tests. Test cases: proactive refresh on near-expiry, reactive refresh on poll 401, refresh 400→AuthError, refresh network error→None, refresh-token rotation persisted, full object preserved (subscriptionType untouched), re-read-prefers-fresh-on-disk-token.
6. **Never log token values.** Log lengths/prefixes or "refreshed (expires <human time>)". The existing `log()` calls already redact; keep it.

## Standard stack
No new dependencies. `httpx` (already imported), stdlib `os`/`json`/`tempfile`/`time`. Tests use stdlib `unittest.mock` + `pytest` (already in use). `[VERIFIED]` — confirmed in the daemon and `test_windows_poll.py`.

## Assumptions Log
| # | Claim | Risk if wrong |
|---|-------|---------------|
| A1 | `invalid_grant` is the exact error string in a 400 body | LOW — daemon should gate on status code, not body, so this is logging-only |
| A2 | `platform.claude.com` is the current preferred host | LOW — fallback to `console.anthropic.com` (proven) covers it |
| A3 | Both JSON and form-encoded accepted | LOW-MED — JSON is VERIFIED working; form is the only alt if JSON ever fails |

## Sources
- `RavenStorm-bit/claude-token-refresh` `claude_token_refresh.py` (read via `gh api`) — endpoint, client_id, JSON body, response parsing, expiresAt ms formula, scope.split. **Primary, HIGH.**
- shubcodes gist `3c9c7ff…` — `platform.claude.com` endpoint, client_id, response field examples (`sk-ant-oat01-`, `expires_in`), form-encoded claim. MEDIUM.
- anthropics/claude-code issues #54443 (400 on refresh), #27933 / #24317 (single-use rotation race), #34306 / #50743 (no auto-refresh background). MEDIUM.
- doobidoo/mcp-memory-service refresh notes; community OAuth writeups — JSON + `console.anthropic.com`, rotation shipped 10.41.0. MEDIUM.
- Python docs: `os.replace` atomic + overwrites on Windows. HIGH.
