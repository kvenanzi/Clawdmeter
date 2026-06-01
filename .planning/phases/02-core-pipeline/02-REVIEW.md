---
phase: 02-core-pipeline
reviewed: 2026-06-01T17:05:00Z
depth: standard
files_reviewed: 5
files_reviewed_list:
  - daemon/claude_usage_daemon_windows.py
  - daemon/tests/test_windows_poll.py
  - daemon/tests/test_windows_token.py
  - daemon/requirements-windows.txt
  - daemon/README-windows.md
findings:
  critical: 1
  warning: 6
  info: 4
  total: 11
status: issues_found
---

# Phase 2: Code Review Report

**Reviewed:** 2026-06-01T17:05:00Z
**Depth:** standard
**Files Reviewed:** 5
**Status:** issues_found

## Summary

Native-Windows BLE daemon port (Python; bleak WinRT + httpx). Reviewed the
asyncio scan/connect/poll run loop, exponential backoff, signal handling
fallback, the compact-JSON wire contract, token handling, and TLS posture.

Good news on the two named threats:
- **T-02-01 (token never logged):** Holds. The bearer token is only inserted
  into a local `headers` dict in `poll_api`; it is never passed to `log()`.
  Error logs print `resp.text[:200]` and exception objects, not the
  Authorization header. `write_payload` logs the payload, which never contains
  the token. A dedicated regression test (`test_poll_api_does_not_log_token`)
  guards stdout/stderr.
- **T-02-02 (no `verify=False`):** Holds. `httpx.AsyncClient(timeout=20.0)`
  uses default TLS verification; no `verify=False`, no custom unsafe SSL context.

The remaining issues are real correctness/robustness defects. The most serious
is a signal-handling defect on Windows that prevents clean shutdown (the named
fallback path is itself broken). Several smaller robustness gaps exist around
the backoff schedule, the refresh-event race, and `_read_expiry`'s
first-hit-wins loop. The dependency manifest is unpinned, which is a supply-chain
concern for a credential-reading daemon.

## Critical Issues

### CR-01: Windows signal fallback never sets the asyncio stop_event — Ctrl+C cannot stop the run loop cleanly

**File:** `daemon/claude_usage_daemon_windows.py:291-300`

**Issue:** On Windows, `loop.add_signal_handler` raises `NotImplementedError`,
so the code falls back to `signal.signal(sig, _stop)`. But `_stop` calls
`stop_event.set()` on an `asyncio.Event`, and `asyncio.Event.set()` is **not
thread-safe and not signal-safe**. On CPython, a C-level signal handler runs the
Python callback between bytecode instructions on the main thread, but the event
loop is blocked inside `await asyncio.wait_for(...)`/`scan_for_device()` and will
not re-evaluate `stop_event.is_set()` or wake the `stop_event.wait()` futures
until the current await resumes on its own. `Event.set()` schedules waiter
callbacks via `loop.call_soon`, which from a signal handler is not guaranteed to
wake a sleeping loop. In practice on Windows the SIGINT fallback leaves the
daemon hung in the scan/backoff sleep; the process only dies on a second Ctrl+C
via `KeyboardInterrupt` (the `__main__` guard), meaning the advertised "logs
`Daemon stopping` and exits cleanly" contract (README line 101) is not met.

This is the explicitly-called-out Windows path of this phase, and it is the one
that does not work. The README and tests assert clean shutdown behavior that the
fallback does not deliver.

**Fix:** Wake the loop from the signal handler in a loop-safe way. Capture the
loop and use `loop.call_soon_threadsafe`, and on Windows additionally register a
`KeyboardInterrupt`-tolerant path. Minimal robust version:

```python
async def main() -> None:
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _stop(*_args: object) -> None:
        log("Daemon stopping")
        loop.call_soon_threadsafe(stop_event.set)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop)
        except NotImplementedError:
            # Windows: schedule the set() onto the loop thread-safely so a
            # sleeping wait_for() actually wakes.
            signal.signal(sig, lambda *_: loop.call_soon_threadsafe(stop_event.set))
```

Note `call_soon_threadsafe` is the documented mechanism to wake a loop from a
signal/thread context; calling `stop_event.set()` directly is the bug.

## Warnings

### WR-01: Exponential backoff is never reset after a successful scan-but-failed-connect, and double-increments

**File:** `daemon/claude_usage_daemon_windows.py:305-325`

**Issue:** The backoff state machine has two defects:
1. After `scan_for_device()` succeeds but `connect_and_run` returns `False`
   (connect failed, or connected but never wrote successfully), `backoff` keeps
   doubling toward 60s. That is intended for connect failures — fine. But if the
   device is *found every scan* yet connect keeps failing, the daemon waits up to
   60s between attempts with no upper retry cap and no jitter. Acceptable, but
   combined with (2) below it compounds.
2. More concretely: when a scan *fails* (`not device`), backoff doubles
   (line 314). When the *next* scan succeeds but connect fails, backoff doubles
   *again* (line 323) without ever having reset. A transient scan miss followed
   by a connect failure escalates the delay faster than the "starts at 1 second"
   contract in the README (line 97) implies. The reset to `backoff = 1`
   (line 325) only happens on a fully successful session, so a device that
   connects but never completes a write (e.g., GATT write always fails) holds the
   daemon at max backoff indefinitely.

**Fix:** Reset `backoff = 1` whenever a device is *found*, and only grow it on
scan-miss; track connect failures with a separate counter or reset on successful
connect (not successful write):

```python
ok = await connect_and_run(device, stop_event)
backoff = 1 if client_connected_at_least_once else min(backoff * 2, 60)
```
At minimum, reset `backoff = 1` after a successful `client.connect()` inside
`connect_and_run` rather than only after a successful write.

### WR-02: Refresh-event race — a refresh fired during a poll is cleared and lost

**File:** `daemon/claude_usage_daemon_windows.py:261-276`

**Issue:** The loop does `refresh_requested.clear()` (line 262) *before* the
`await poll_api(token)` (line 267). If the device fires a refresh notification
during the in-flight `poll_api`/`write_payload` await window, `_on_refresh` sets
the event again — good — but then control returns to line 274
`asyncio.wait_for(refresh_requested.wait(), ...)` which returns immediately, and
the *next* iteration handles it. That part is fine. The actual loss: if a refresh
arrives between `clear()` (262) and the `is_set()` check has already passed,
there's no double-poll bug, but the inverse is worse — because `clear()` runs
unconditionally at the top of the `if` whenever `elapsed >= POLL_INTERVAL` even
when no refresh was requested, a refresh that arrives *just before* the timer
elapses is swallowed: the timer branch clears the event without the refresh ever
triggering an immediate extra poll. Net effect: refresh-driven low latency is not
guaranteed under timer/refresh interleaving.

**Fix:** Only clear the event when it was actually the trigger, and clear *after*
deciding to poll:

```python
triggered_by_refresh = session.refresh_requested.is_set()
if triggered_by_refresh or elapsed >= POLL_INTERVAL:
    session.refresh_requested.clear()
    ...
```
(Clearing after the `is_set()` snapshot, as written, is correct; the real fix is
to ensure a refresh arriving during the poll forces another poll — re-check
`refresh_requested.is_set()` after the write and loop without waiting.)

### WR-03: `_read_expiry` first-hit-wins loop returns "expiry unknown" without trying fallback files

**File:** `daemon/claude_usage_daemon_windows.py:205-224`

**Issue:** `_read_expiry` iterates candidate paths, but the inner `try` returns
`"expiry unknown"` from inside the loop on *any* parse problem or missing
`expiresAt` (lines 215, 223). If the first readable candidate file exists but is
the wrong/partial file (no `claudeAiOauth`, or malformed), the function returns
early and never probes the LOCALAPPDATA / APPDATA fallbacks — even though
`read_token()` (line 190) would happily fall through to a later file. The two
functions can therefore disagree about which credential file is authoritative:
`read_token` may succeed from fallback #2 while `_read_expiry` reports "unknown"
from a stale primary. This is inconsistent and confusing in logs.

**Fix:** Treat malformed/missing-field as `continue` (try next candidate), and
only return `"expiry unknown"` after the loop exhausts:

```python
for path in _windows_credential_candidates():
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        expires_ms = data.get("claudeAiOauth", {}).get("expiresAt")
        if expires_ms is None:
            continue
        dt = datetime.datetime.fromtimestamp(expires_ms / 1000, tz=datetime.timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except (OSError, TypeError, ValueError, AttributeError, json.JSONDecodeError):
        continue
return "expiry unknown"
```

### WR-04: `pct()` / `reset_minutes()` catch only `ValueError`, not `TypeError` — non-string header values crash the poll

**File:** `daemon/claude_usage_daemon_windows.py:68-80`

**Issue:** Both helpers do `float(x)` inside a `try/except ValueError`. With real
httpx, `resp.headers.get(name, "0")` always returns a `str`, so this is safe in
the happy path. But the contract is fragile: if any header value is ever `None`
or a non-string (e.g., a future code change, a different mock, or a header
library quirk), `float(None)` raises `TypeError`, which is *not* caught and
crashes `poll_api` mid-payload-build, returning an unhandled exception up into
`connect_and_run`'s poll branch (which has no try/except around `poll_api`,
line 267) and tearing down the session. Confirmed: `float(None)` raises
`TypeError`, not `ValueError`.

**Fix:** Catch both, or coerce to str first:

```python
def pct(util: str) -> int:
    try:
        return int(round(float(util) * 100))
    except (ValueError, TypeError):
        return 0
```
Apply the same to `reset_minutes`.

### WR-05: `poll_api` exception is unguarded inside the run loop

**File:** `daemon/claude_usage_daemon_windows.py:267`

**Issue:** `poll_api` is awaited directly in the loop with no surrounding
try/except. `poll_api` itself only catches `httpx.HTTPError`. Any other
exception (e.g., the `TypeError` from WR-04, a `json`/header parsing surprise,
or an unexpected bleak exception bubbling through) propagates out of the
`while client.is_connected` loop. The `finally` (line 277-281) will disconnect,
but the exception then propagates out of `connect_and_run` entirely — it is *not*
one of the `(BleakError, asyncio.TimeoutError)` types caught at the call site
(line 317 has no try/except around `connect_and_run`), so it kills `main()` and
the whole daemon instead of triggering the backoff/rescan resilience the README
promises (lines 96-97).

**Fix:** Wrap the poll branch defensively so a poll error degrades to a skipped
cycle rather than a daemon crash:

```python
try:
    payload = await poll_api(token)
except Exception as e:           # noqa: BLE001 — daemon must stay up
    log(f"Poll error: {e}")
    payload = None
```

### WR-06: Unpinned dependencies in credential-reading daemon (supply-chain)

**File:** `daemon/requirements-windows.txt:3-4`

**Issue:** `bleak` and `httpx` are unpinned (no version, no hash). This daemon
reads an OAuth bearer token from disk and sends authenticated requests to the
Anthropic API; a compromised or breaking transitive update of either package is
a meaningful supply-chain and stability risk. `bleak`'s WinRT backend in
particular has had API-shaping changes across minor versions (e.g.
`address_type`, `use_cached_services` kwargs used at lines 237-239 are
version-sensitive). An unpinned `pip install` can silently pull a version where
those kwargs are rejected, breaking the documented setup with no reproducibility.

**Fix:** Pin compatible ranges (and ideally hashes) verified against the kwargs
used:

```
bleak>=0.22,<0.23
httpx>=0.27,<1.0
```

## Info

### IN-01: README claims the daemon "redacts" the token in logs, but no redaction code exists

**File:** `daemon/README-windows.md:30-31`

**Issue:** The security note states the daemon "redacts it in all log output
(e.g., `sk-ant-…XXXX`)." The code never logs the token at all (good), but it also
contains no redaction logic — there is no masking helper, and `read_token`/
`_read_expiry` return the raw token to callers. The claim is misleading: it
implies an active redaction control that isn't there. If a future edit logs the
token, nothing redacts it. Either implement a redaction helper used at the
token-handling boundary, or reword the doc to "never logs the token."

**Fix:** Change the sentence to: "The daemon never writes the token to any log
output." Optionally add a `_redact(tok)` helper for defense-in-depth.

### IN-02: Tests use deprecated `asyncio.get_event_loop().run_until_complete`

**File:** `daemon/tests/test_windows_poll.py:35-37`

**Issue:** `_run` calls `asyncio.get_event_loop().run_until_complete(coro)`.
`asyncio.get_event_loop()` with no running loop is deprecated (DeprecationWarning
in 3.10+, scheduled for removal) and emits warnings / will fail under stricter
future runtimes. It also reuses a shared loop across tests, which can leak state.

**Fix:** Use `asyncio.run(coro)` per call, or mark tests `@pytest.mark.asyncio`
with `pytest-asyncio`:

```python
def _run(coro):
    return asyncio.run(coro)
```

### IN-03: `monkeypatch` fixture imported into many tests but unused

**File:** `daemon/tests/test_windows_poll.py:44,86,111,137,168,193,219,249,273`

**Issue:** Nearly every test in `test_windows_poll.py` takes a `monkeypatch`
parameter that is never used (the tests use `patch(...)` context managers
instead). Dead fixture parameters are noise and obscure which tests actually
mutate global state.

**Fix:** Drop the unused `monkeypatch` parameter from those signatures.

### IN-04: Raw-token regex fallback can accept a non-token blob

**File:** `daemon/claude_usage_daemon_windows.py:158`

**Issue:** The final fallback `re.fullmatch(r"[A-Za-z0-9_\-.~+/=]{20,}", blob)`
accepts *any* 20+ char alphanumeric/symbol blob as a "raw token" — e.g. a
20-char file of base64 noise or a stray config value with no JSON wrapper. This
is defensive-by-design (handles raw-token files) but loose: it does not require
the `sk-ant-` prefix the comment claims ("must look plausible (sk-ant-... etc.)").
A misconfigured `CLAUDE_CREDENTIALS_PATH` pointing at an arbitrary file could
yield a garbage "token" that then fails opaquely at the API with a 401 rather
than a clear "no token" message.

**Fix:** Tighten to the known token prefix, or at least log when the raw-token
fallback path is taken:

```python
if re.fullmatch(r"sk-ant-[A-Za-z0-9_\-.~+/=]{10,}", blob):
    return blob
```

---

_Reviewed: 2026-06-01T17:05:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
