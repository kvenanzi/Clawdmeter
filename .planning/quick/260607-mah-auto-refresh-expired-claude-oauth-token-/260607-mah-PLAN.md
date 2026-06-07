---
phase: 260607-mah
plan: 01
type: tdd
wave: 1
depends_on: []
files_modified:
  - daemon/claude_usage_daemon_windows.py
  - daemon/tests/test_windows_token.py
autonomous: true
requirements: [TOKEN-REFRESH-01]
must_haves:
  truths:
    - "When the on-disk access token is expired or within ~5 min of expiry, the daemon POSTs the refreshToken to the OAuth endpoint and obtains a fresh access token before polling (proactive)."
    - "On an unexpected poll 401, the daemon forces ONE refresh-and-retry before toasting (reactive)."
    - "Refreshed credentials are written back to .credentials.json atomically, preserving the full claudeAiOauth object and mutating only accessToken/refreshToken/expiresAt (and scopes if returned)."
    - "Right before refreshing, the daemon re-reads .credentials.json; if the on-disk token is already fresh, it uses that and skips the network refresh."
    - "A refresh that itself returns 400/401/403 raises AuthError (genuine 'run claude login' toast); a transient/network refresh failure returns None (no toast)."
    - "Raw token values are never logged."
  artifacts:
    - path: "daemon/claude_usage_daemon_windows.py"
      provides: "OAuth refresh: _atomic_write_credentials, _read_full_credentials, _refresh_oauth_token, get_valid_token; reactive retry wired in connect_and_run"
      contains: "async def get_valid_token"
    - path: "daemon/tests/test_windows_token.py"
      provides: "Refresh test coverage (success+writeback, rotation persisted, re-read skips network, atomic preserves keys, invalid_grant raises, transient returns None)"
      contains: "_refresh_oauth_token"
  key_links:
    - from: "connect_and_run"
      to: "get_valid_token"
      via: "replaces read_token() in poll loop + reactive retry on AuthError"
      pattern: "get_valid_token\\("
    - from: "get_valid_token"
      to: "_atomic_write_credentials"
      via: "persists refreshed credentials after a 200 response"
      pattern: "_atomic_write_credentials\\("
    - from: "_refresh_oauth_token"
      to: "OAUTH_TOKEN_URL"
      via: "httpx.AsyncClient.post with json grant_type=refresh_token body"
      pattern: "grant_type.*refresh_token"
---

<objective>
Add OAuth refresh-token support to the Windows daemon so an expired Claude
access token is silently refreshed (and persisted) instead of firing the
"run claude login" toast after PC sleep/power-off.

Purpose: The daemon currently only reads the short-lived `accessToken` and
never refreshes it; the token reliably expires across idle/sleep and the tray
nags the user multiple times a day. Implementing the same refresh flow Claude
Code performs internally makes the daemon self-healing.

Output: New refresh helpers + `get_valid_token()` in
`claude_usage_daemon_windows.py`, reactive refresh-and-retry wired into
`connect_and_run()`, and full mocked-network test coverage in
`test_windows_token.py`.

Scope: Windows daemon ONLY. Do not touch the Linux bash daemon or macOS daemon.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/quick/260607-mah-auto-refresh-expired-claude-oauth-token-/260607-mah-CONTEXT.md
@.planning/quick/260607-mah-auto-refresh-expired-claude-oauth-token-/260607-mah-RESEARCH.md
@daemon/claude_usage_daemon_windows.py
@daemon/tests/test_windows_token.py

<interfaces>
<!-- Existing seams to reuse — extracted from claude_usage_daemon_windows.py.
     Use these directly; no codebase exploration needed. -->

Existing helpers (keep, reuse, do not break their signatures or behavior):
- `_extract_access_token(blob: str) -> str | None`  — fast-path token extraction
- `_windows_credential_candidates() -> list[Path]`  — ordered path probe (first hit wins; honors CLAUDE_CREDENTIALS_PATH / CLAUDE_CONFIG_DIR)
- `read_token() -> str | None`  — KEEP unchanged (still used by tests); new code adds get_valid_token alongside it
- `_read_expiry() -> str`  — human-readable expiry string; expiresAt is epoch MS (divide by 1000)
- `class AuthError(Exception)`  — genuine 401/403 -> toast. None return == transient (no toast).
- `async def poll_api(token: str) -> dict | None`  — raises AuthError on 401/403
- `log(msg)`  — already redaction-disciplined; never pass it a raw token
- `httpx` is already imported at module top

Poll loop site to modify (connect_and_run, ~line 380-394):
  token = read_token()                      # <- replace with: token = await get_valid_token(tray_state)
  ...
  try:
      payload = await poll_api(token)
  except AuthError:
      ... set_error("token expired — run claude login")  # <- gate behind ONE forced refresh+retry first

Credentials file shape (claudeAiOauth nested; fixture daemon/tests/fixtures/credentials_nested.json):
  {"claudeAiOauth": {"accessToken","refreshToken","expiresAt"(epoch ms),"scopes"[],"subscriptionType",...}}

OAuth refresh spec (from RESEARCH.md — VERIFIED values, use exactly):
  Primary URL : https://platform.claude.com/v1/oauth/token   (try first)
  Fallback URL: https://console.anthropic.com/v1/oauth/token  (on connection error / non-OAuth 404)
  client_id   : 9d1c250a-e61b-44d9-88ed-5944d1962f5e   (public PKCE client, NO client_secret)
  Request (Content-Type: application/json):
    {"grant_type":"refresh_token","refresh_token":"<stored>","client_id":"<above>"}
  Response 200: {access_token, refresh_token(rotated; may be absent->reuse old), expires_in(SECONDS), scope(space-delimited str)}
  expiresAt(ms) = int(time.time()*1000) + expires_in*1000      # off-by-1000 hazard
  scopes        = scope.split() ONLY if scope present, else leave existing array

Test mock pattern (from test_windows_poll.py — NO respx; stdlib unittest.mock only):
  from unittest.mock import AsyncMock, MagicMock, patch
  resp = MagicMock(); resp.status_code = 200; resp.json.return_value = {...}; resp.text = "..."
  mock_client = AsyncMock()
  mock_client.__aenter__ = AsyncMock(return_value=mock_client)
  mock_client.__aexit__  = AsyncMock(return_value=False)
  mock_client.post = AsyncMock(return_value=resp)
  with patch("httpx.AsyncClient", return_value=mock_client): ...
  # credential write-back tests: tmp_path + monkeypatch.setenv("CLAUDE_CREDENTIALS_PATH", str(creds))
</interfaces>
</context>

<tasks>

<task type="tdd" tdd="true">
  <name>Task 1: Atomic write-back + full-credentials read helpers (RED -> GREEN)</name>
  <files>daemon/claude_usage_daemon_windows.py, daemon/tests/test_windows_token.py</files>
  <behavior>
    - `_atomic_write_credentials(path, full_obj)`: writes via tempfile.mkstemp in the SAME directory as path, json.dump(indent=2), f.flush() + os.fsync(fileno), then os.replace(tmp, path). On exception, unlinks the temp file and re-raises. After a successful call, path contains exactly full_obj and no `.cred-*.tmp` siblings remain in the directory.
    - `_read_full_credentials()`: returns the parsed top-level dict from the first-hit candidate path (reusing `_windows_credential_candidates()`), or None if no file / unparseable. Returns the WHOLE object (so callers can mutate claudeAiOauth and re-dump untouched keys).
    - `_parse_expiry_ms(oauth_obj_or_full) -> int | None`: returns claudeAiOauth.expiresAt as int epoch ms, or None if absent/unparseable. (Factored from _read_expiry's parsing; _read_expiry stays working.)
    - Test: atomic write preserves an unrelated key (subscriptionType / rateLimitTier untouched) after mutating only accessToken/refreshToken/expiresAt.
    - Test: no `.cred-*.tmp` file remains after a successful atomic write.
    - Test: _read_full_credentials returns the nested object including refreshToken from a tmp file.
  </behavior>
  <action>
    Write the RED tests first in test_windows_token.py, then implement to GREEN.
    Add `import tempfile` (os/json/time already imported). Implement
    `_atomic_write_credentials`, `_read_full_credentials`, and `_parse_expiry_ms`
    exactly per the RESEARCH.md atomic-write recipe (same-dir mkstemp, fsync,
    os.replace which is atomic + overwrites on Windows). Do NOT write a `.backup`
    file. Use encoding="utf-8" everywhere. Refactor `_read_expiry()` to call
    `_parse_expiry_ms()` so there is one parser; keep _read_expiry's existing
    return contract and its passing tests green. Never log token values — log
    lengths/prefixes or "credentials written" only.
  </action>
  <verify>
    <automated>python -m pytest daemon/tests/test_windows_token.py -x -q</automated>
  </verify>
  <done>New helpers exist and pass; all pre-existing test_windows_token.py tests still pass; no temp file leaks; unrelated credential keys preserved through a write.</done>
</task>

<task type="tdd" tdd="true">
  <name>Task 2: OAuth refresh call + get_valid_token (proactive + race re-read) (RED -> GREEN)</name>
  <files>daemon/claude_usage_daemon_windows.py, daemon/tests/test_windows_token.py</files>
  <behavior>
    - `async def _refresh_oauth_token(refresh_token: str) -> dict`: POSTs the JSON body {grant_type:"refresh_token", refresh_token, client_id} to OAUTH_TOKEN_URL (platform.claude.com), falling back to the console.anthropic.com constant on a connection error or non-OAuth 404. On 200 returns the parsed dict. On 400/401/403 raises AuthError (genuine). On timeout/5xx/other network error raises a transient signal the caller maps to None (e.g. return None or raise a distinct TransientRefreshError caught locally) — choose one and be consistent.
    - `async def get_valid_token(tray_state=None) -> str | None`: reads full creds; if accessToken present AND expiresAt > now + ~5 min -> return accessToken (NO network). Else RE-READ disk (race rule) and re-check; still stale -> call _refresh_oauth_token with the on-disk refreshToken. On 200: build new claudeAiOauth (mutate accessToken, refreshToken := response.get('refresh_token', existing), expiresAt := now_ms + expires_in*1000, scopes := scope.split() only if 'scope' present), _atomic_write_credentials the FULL object, return new accessToken. On AuthError from refresh: propagate (genuine). On transient: return None.
    - OAUTH_TOKEN_URL / OAUTH_FALLBACK_URL / OAUTH_CLIENT_ID are module-level constants.
    - Tests (all network mocked via patch("httpx.AsyncClient")):
      1. successful refresh -> returns new access token AND .credentials.json now holds it + new expiresAt (proactive on near-expiry fixture).
      2. rotated refresh_token in the 200 body is persisted to disk; absent refresh_token reuses the old one.
      3. on-disk token already fresh -> get_valid_token returns it and httpx.AsyncClient.post is NEVER called (assert_not_called / mock unused).
      4. atomic-replace preserves subscriptionType and other keys through the refresh write-back.
      5. genuine invalid_grant: post returns status_code 400 -> _refresh_oauth_token raises AuthError (and get_valid_token propagates it).
      6. transient: post raises httpx.HTTPError (or returns 503) -> get_valid_token returns None (no AuthError).
      7. never-log assertion: capture log output, assert no full token substring appears.
  </behavior>
  <action>
    RED tests first, then GREEN. Add module constants OAUTH_TOKEN_URL =
    "https://platform.claude.com/v1/oauth/token", OAUTH_FALLBACK_URL =
    "https://console.anthropic.com/v1/oauth/token", OAUTH_CLIENT_ID =
    "9d1c250a-e61b-44d9-88ed-5944d1962f5e". Implement _refresh_oauth_token and
    get_valid_token per behavior above, reusing _read_full_credentials,
    _parse_expiry_ms, _atomic_write_credentials from Task 1. Gate genuine vs
    transient by STATUS CODE only (400/401/403 = AuthError; everything else =
    transient), per RESEARCH Pitfall — parse body for redacted logging only,
    never to decide behavior. Use the existing httpx import and the same
    AsyncClient(timeout=...) style as poll_api. Keep read_token() intact for the
    legacy tests. Never log raw tokens.
  </action>
  <verify>
    <automated>python -m pytest daemon/tests/test_windows_token.py -x -q</automated>
  </verify>
  <done>_refresh_oauth_token and get_valid_token implemented; all 7 behavior cases pass; fresh-on-disk path makes zero network calls; invalid_grant raises AuthError; transient returns None; no raw token logged.</done>
</task>

<task type="tdd" tdd="true">
  <name>Task 3: Wire proactive + reactive refresh into connect_and_run (RED -> GREEN)</name>
  <files>daemon/claude_usage_daemon_windows.py, daemon/tests/test_windows_token.py</files>
  <behavior>
    - In connect_and_run's poll cycle, replace `token = read_token()` with `token = await get_valid_token(tray_state)`. Preserve the existing "No token; skipping poll" + set_error branch when get_valid_token returns None DUE TO no credentials at all (transient/None already does not toast for network failures — keep that distinction; the proactive None for a transient refresh must NOT toast, matching the existing transient-poll behavior).
    - Reactive: when poll_api(token) raises AuthError, force ONE refresh attempt (call get_valid_token again, or a forced-refresh variant that bypasses the freshness check) and retry poll_api ONCE. If the retry succeeds -> write payload as normal. If the forced refresh itself raises AuthError, THEN set_error("token expired — run claude login"). A transient refresh failure on the reactive path -> leave tray unchanged, payload None (no toast), next tick retries.
    - Keep AuthError semantics intact everywhere else: None == transient (no toast), AuthError == genuine (toast).
    - Test: a unit-level test of the reactive retry logic — first poll_api call raises AuthError, refresh succeeds, second poll_api returns a payload; assert toast NOT fired and payload produced. (Mock poll_api + get_valid_token; drive the smallest extractable unit. If the retry logic is inlined in connect_and_run, factor it into a tiny helper, e.g. `async def _poll_with_refresh(token, tray_state) -> dict | None`, to keep it unit-testable without a live BLE client.)
    - Test: reactive path where the forced refresh raises AuthError -> toast IS fired, payload None.
  </behavior>
  <action>
    RED tests first. To keep the reactive logic unit-testable without a live
    BleakClient, extract the poll+refresh-retry into a small async helper
    (e.g. _poll_with_refresh(token, tray_state)) and call it from connect_and_run;
    this avoids driving the whole BLE loop in tests. Implement: proactive token
    via get_valid_token before poll; on AuthError from poll_api, force exactly ONE
    refresh + ONE retry; toast only if the forced refresh raises AuthError. Do not
    change the existing transient-None no-toast behavior. Confirm no Linux/macOS
    daemon files are touched. Run the full daemon test suite to ensure no
    regressions in poll/BLE tests.
  </action>
  <verify>
    <automated>python -m pytest daemon/tests/test_windows_token.py daemon/tests/ -q</automated>
  </verify>
  <done>connect_and_run uses get_valid_token; reactive refresh-and-retry fires exactly once and only toasts on a genuine forced-refresh AuthError; all daemon tests pass; Linux/macOS daemon files untouched.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| daemon -> Anthropic OAuth endpoint | refreshToken (a long-lived secret) crosses the network in a POST body |
| daemon <-> .credentials.json on disk | concurrent reader/writer (native Claude Code) shares the same file; rotated single-use tokens |
| log sink (file/stdout) | token material must never cross into logs |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-mah-01 | Information Disclosure | log() calls in refresh path | mitigate | Never pass raw access/refresh tokens to log(); log lengths/prefixes/expiry only. Task 2 includes an explicit "no raw token in logs" test. |
| T-mah-02 | Tampering | .credentials.json write-back | mitigate | Atomic same-dir mkstemp + fsync + os.replace; full object preserved, only 3-4 keys mutated; temp file unlinked on failure (no half-written creds). Task 1 tests key preservation + no temp leak. |
| T-mah-03 | Denial of Service | rotating single-use refresh tokens vs native Claude Code | mitigate | Re-read disk immediately before refresh; if on-disk token is fresh, skip network and reuse it; persist rotated token atomically right after success. Task 2 case 3 asserts the skip-network path. |
| T-mah-04 | Spoofing/Elevation | wrong/redirected OAuth endpoint causing silent refresh failure | mitigate | Two module-level constant URLs (platform.claude.com primary, console.anthropic.com fallback) with explicit fallback on connection error/non-OAuth 404; status-code-gated error handling (400/401/403 = genuine). |
| T-mah-05 | Repudiation | misclassifying transient failure as auth failure | accept/mitigate | Gate toast strictly on AuthError (400/401/403 from refresh) only; transient (timeout/5xx/network) returns None and never toasts — preserves the existing SC#5 DNS-blip fix. Task 3 tests both branches. |
| T-mah-SC | Tampering | npm/pip/cargo installs | n/a | No new dependencies added (stdlib + already-vendored httpx). No package installs in this plan. |
</threat_model>

<verification>
- `python -m pytest daemon/tests/test_windows_token.py -q` passes (new + all pre-existing token tests).
- `python -m pytest daemon/tests/ -q` passes (no regressions in poll/BLE suites).
- `git diff --name-only` shows ONLY daemon/claude_usage_daemon_windows.py and daemon/tests/test_windows_token.py changed (no Linux/macOS daemon files).
- Grep confirms no raw-token logging: refresh-path log() calls reference lengths/prefixes/expiry, not token variables.
</verification>

<success_criteria>
- Proactive: near-expiry on-disk token triggers a refresh + atomic write-back before polling; fresh on-disk token skips the network entirely.
- Reactive: an unexpected poll 401 triggers exactly one forced refresh + one retry before any toast.
- Rotated refresh tokens are persisted; the full claudeAiOauth object (subscriptionType etc.) survives the write.
- Genuine refresh failure (400/401/403) toasts "run claude login"; transient/network failure stays silent (None).
- No new dependencies; no raw token values logged; Windows daemon only.
</success_criteria>

<output>
Create `.planning/quick/260607-mah-auto-refresh-expired-claude-oauth-token-/260607-mah-SUMMARY.md` when done.
</output>
