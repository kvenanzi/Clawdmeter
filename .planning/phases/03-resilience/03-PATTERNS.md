# Phase 3: Resilience - Pattern Map

**Mapped:** 2026-06-01
**Files analyzed:** 2 (1 modified, 1 new test file)
**Analogs found:** 2 / 2

This phase is strictly additive hardening of ONE existing file
(`daemon/claude_usage_daemon_windows.py`) plus new unit tests under `daemon/tests/`.
Every analog is in-repo and exact — the file being hardened IS its own primary analog,
and the macOS daemon supplies the outer-loop shape. No new files, dependencies, or
shared/macOS/firmware edits (CONTEXT.md `<domain>` boundary).

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `daemon/claude_usage_daemon_windows.py` (MODIFY) | service (BLE reconnect daemon) | event-driven / request-response | itself (Phase 2 loop) + `daemon/claude_usage_daemon.py` `main()` L400–449 | exact (self) |
| `daemon/tests/test_windows_reconnect.py` (NEW) | test | request-response (mocked async) | `daemon/tests/test_windows_poll.py` | exact |

**Note:** The new test filename is a suggestion (`test_windows_reconnect.py` — mirrors
the `test_windows_<area>.py` naming of the two existing test files). Planner may split
into separate files per D-01/D-03/D-05 if preferred. CONTEXT.md D-06 leaves test
structure to planner discretion.

## Pattern Assignments

### `daemon/claude_usage_daemon_windows.py` (service, event-driven) — MODIFY

**Analog:** itself (Phase 2 substrate) + `daemon/claude_usage_daemon.py` `main()` for outer-loop shape.

This file is hardened in three surgical spots. All three reuse patterns already present
in the file — no new idioms are introduced.

---

#### Change 1 — D-01: connect-retry wrapper around `client.connect()`

**Current connect path** (`claude_usage_daemon_windows.py` L232–249) — this is the
exact block the retry wraps. The `BleakClient(...)` construction (L236–240) must be
reused **per attempt** (D-05 recipe is locked: positional `device`, `address_type="random"`,
`use_cached_services=False`):

```python
log(f"Connecting to {device.address}...")
# D-05: pass BLEDevice (not address string), address_type="random" (NimBLE
# static-random), use_cached_services=False (DIY firmware ...)
client = BleakClient(
    device,
    address_type="random",
    use_cached_services=False,
)
try:
    await client.connect()
except (BleakError, asyncio.TimeoutError) as e:
    log(f"Connection failed: {e}")
    return False

if not client.is_connected:
    log("Connection failed (no error but not connected)")
    return False
```

**Pattern to apply:** Wrap the `BleakClient(...)` + `await client.connect()` +
`is_connected` check in an N-attempt loop (≈3 tries / ~2s apart). Between failed
attempts, `await client.disconnect()` (guarded by `try/except BleakError`, mirroring
the existing `finally` cleanup at L278–281) and rebuild a fresh `BleakClient`. Only
after retries exhaust does `connect_and_run` return its failure value. The
`Unreachable` / stale-`is_connected` WinRT failure modes are caught by the existing
`except (BleakError, asyncio.TimeoutError)` + the `if not client.is_connected` guard —
reuse both as the per-attempt failure signal.

**Disconnect/cleanup pattern to reuse** (L277–281):

```python
finally:
    try:
        await client.disconnect()
    except BleakError:
        pass
```

**Logging:** reuse `log(...)` `[HH:MM:SS]` style (L46–47) for retry/exhaustion lines.

---

#### Change 2 — D-03: consecutive-failure break inside the `while client.is_connected` loop

**Current loop** (`claude_usage_daemon_windows.py` L257–276):

```python
last_poll = 0.0  # D-03: poll immediately on first connect
used_successfully = False
try:
    while client.is_connected and not stop_event.is_set():
        now = time.time()
        elapsed = now - last_poll
        if session.refresh_requested.is_set() or elapsed >= POLL_INTERVAL:
            session.refresh_requested.clear()
            token = read_token()  # D-09: fresh each cycle
            if not token:
                log("No token; skipping poll")
            else:
                payload = await poll_api(token)
                if payload is not None:
                    if await session.write_payload(payload):
                        last_poll = time.time()
                        used_successfully = True

        try:
            await asyncio.wait_for(session.refresh_requested.wait(), timeout=TICK)
        except asyncio.TimeoutError:
            pass
```

**Failure signal already present** — `write_payload()` returns `bool` (L117–125):

```python
async def write_payload(self, payload: dict) -> bool:
    ...
    try:
        await self.client.write_gatt_char(RX_CHAR_UUID, data, response=False)
        return True
    except BleakError as e:
        log(f"Write failed: {e}")
        return False
```

**Pattern to apply:** Add a `consecutive_failures` counter before the loop. On the
`else` branch of the existing `if await session.write_payload(payload):` test (i.e.
write returned `False`), increment the counter; on success (where `used_successfully = True`
is set, L271), reset it to 0. After N consecutive failures (≈2–3, sized to clear the
120s SLA), `break` out of the `while` — the existing `finally` (L277–281) disconnects,
and `connect_and_run` returns `used_successfully`, falling back into `main()`'s reconnect
branch. No new GATT traffic (honors Phase 2 D-08 "no TX read"). The counter consumes the
existing `write_payload` bool directly — no new failure-signal plumbing (CONTEXT.md
`<code_context>` Reusable Assets).

---

#### Change 3 — D-05: split fast-reconnect vs slow-search backoff in `main()`

**Current single-backoff loop** (`claude_usage_daemon_windows.py` L305–325):

```python
backoff = 1
while not stop_event.is_set():
    device = await scan_for_device()
    if not device:
        log(f"Device not found, retrying in {backoff}s...")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=backoff)
        except asyncio.TimeoutError:
            pass
        backoff = min(backoff * 2, 60)
        continue

    ok = await connect_and_run(device, stop_event)
    if not ok:
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=backoff)
        except asyncio.TimeoutError:
            pass
        backoff = min(backoff * 2, 60)
    else:
        backoff = 1
```

**The two failure classes already branch here** (CONTEXT.md `<specifics>`):
- `if not device:` (scan returned `None`) → **device never found** → slow-search regime.
- `if not ok:` after `connect_and_run` (had/attempted a link that dropped) → **lost a
  known-good link** → fast-reconnect regime.

**Pattern to apply:** Replace the single `backoff` with two counters — e.g.
`search_backoff` (caps at 60, used in the `if not device:` branch) and `reconnect_backoff`
(caps at ~5–10s, used in the `if not ok:` branch). Reset the relevant counter to its
floor on success (`else: ... = 1`). **Keep the wait idiom identical** — the
`asyncio.wait_for(stop_event.wait(), timeout=backoff)` + `except asyncio.TimeoutError`
pattern (L310–313 / L319–322) is reused verbatim for both regimes so Ctrl-C / SIGTERM
stays responsive during waits (CONTEXT.md Reusable Assets).

**Outer-loop shape reference** — `daemon/claude_usage_daemon.py` `main()` (L417–449)
shows the same scan → connect → on-failure-backoff skeleton. **Copy the shape, NOT the
platform branches:** drop the macOS `skip_addr` / `retrieve_connected_macos` HID path
(L418, 422–423, 436–439) and the Linux `SAVED_ADDR_FILE.unlink()` cache invalidation
(L441–442). Windows is stateless — D-04 keeps scan-every-cycle, no MAC cache.

```python
# macOS main() L435-447 — the cache/skip branches Windows MUST NOT copy:
if not ok:
    if sys.platform == "darwin":
        skip_addr = addr                    # <-- macOS-only, drop
    else:
        log("Invalidating cached address")
        SAVED_ADDR_FILE.unlink(missing_ok=True)   # <-- Linux-only, drop
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=backoff)
    except asyncio.TimeoutError:
        pass
    backoff = min(backoff * 2, 60)
else:
    backoff = 1
```

**Unchanged:** `scan_for_device()` (L93–99) stays as-is (D-04). `poll_api`, `Session`,
`read_token` untouched.

---

### `daemon/tests/test_windows_reconnect.py` (test) — NEW

**Analog:** `daemon/tests/test_windows_poll.py` (exact — same dir, same harness conventions).

**Module header + import-under-test pattern** (`test_windows_poll.py` L1–16):

```python
#!/usr/bin/env python3
"""Unit tests for ... — <REQ-ID>.

Run: python -m pytest daemon/tests/test_windows_<area>.py -x -q
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from daemon.claude_usage_daemon_windows import connect_and_run  # + helpers to test
```

Path resolution is handled by root `conftest.py` (L1–6: `sys.path.insert(0, repo_root)`),
so `from daemon.claude_usage_daemon_windows import ...` works with no per-test setup.

**Async-coroutine-under-sync-test runner** (`test_windows_poll.py` L35–37) — reuse for
exercising `connect_and_run`:

```python
def _run(coro):
    """Run a coroutine synchronously for synchronous test functions."""
    return asyncio.get_event_loop().run_until_complete(coro)
```

**Mock-client pattern** (`test_windows_poll.py` L64–67, used throughout) — the existing
tests mock `httpx.AsyncClient`. For reconnect tests, build an analogous **fake/mock
`BleakClient`** with `AsyncMock` methods and a controllable `is_connected` property:

```python
# Adapt this httpx mock idiom (test_windows_poll.py L100-103) to a BleakClient:
mock_client = AsyncMock()
mock_client.connect = AsyncMock(side_effect=BleakError("Unreachable"))  # D-01 exhaustion
mock_client.is_connected = True            # D-03 stale-is_connected zombie link
mock_client.disconnect = AsyncMock()
# patch the constructor so connect_and_run gets the fake:
with patch("daemon.claude_usage_daemon_windows.BleakClient", return_value=mock_client):
    ...
```

**Three deterministic test targets** (CONTEXT.md D-06):
1. **D-01 connect-retry exhaustion** — `connect()` always raises `BleakError("Unreachable")`
   (or `asyncio.TimeoutError`); assert exactly N attempts were made (`mock_client.connect.call_count`)
   and `connect_and_run` returns its failure value.
2. **D-03 zombie-link break** — `is_connected=True` but `write_gatt_char` raises `BleakError`
   each cycle (via a mock `Session`/client); assert the loop breaks after N consecutive
   failures rather than spinning, and `disconnect()` was called.
3. **D-05 backoff selection** — assert the `if not device:` path uses the slow-search cap
   and the `if not ok:` path uses the fast-reconnect cap. Test the cap arithmetic directly
   (extract a helper, or assert on the timeout passed to a patched `asyncio.wait_for`).

**`capsys` log-assertion pattern** (`test_windows_poll.py` L394, 418–420) is available if a
test needs to assert a reconnect/zombie-break log line was emitted:

```python
def test_x(monkeypatch, capsys):
    ...
    captured = capsys.readouterr()
    assert "..." in captured.out
```

**Fixtures dir** (`daemon/tests/fixtures/`) exists for file-based fixtures (used by
token tests) — reconnect tests are pure-mock and need no fixtures.

---

## Shared Patterns

### Logging
**Source:** `daemon/claude_usage_daemon_windows.py` L46–47
**Apply to:** All new reconnect/retry/zombie-break log lines (CONTEXT.md D-05 discretion).
```python
def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)
```

### Interruptible backoff wait
**Source:** `daemon/claude_usage_daemon_windows.py` L310–313 (and L319–322)
**Apply to:** Both D-05 backoff regimes — reuse verbatim, only the `timeout=` value and
the cap differ. Keeps SIGINT/SIGTERM responsive during sleeps.
```python
try:
    await asyncio.wait_for(stop_event.wait(), timeout=backoff)
except asyncio.TimeoutError:
    pass
```

### Guarded BLE disconnect
**Source:** `daemon/claude_usage_daemon_windows.py` L278–281
**Apply to:** D-01 inter-attempt cleanup and the existing loop `finally`.
```python
try:
    await client.disconnect()
except BleakError:
    pass
```

### Locked WinRT connect recipe (do not alter — Phase 2 D-05)
**Source:** `daemon/claude_usage_daemon_windows.py` L236–240
**Apply to:** Every `BleakClient(...)` construction inside the D-01 retry wrapper.
```python
client = BleakClient(
    device,                      # BLEDevice, NOT an address string
    address_type="random",       # NimBLE static-random
    use_cached_services=False,   # DIY firmware — WinRT GATT cache may be stale
)
```

### Test harness conventions
**Source:** `daemon/tests/test_windows_poll.py` (L9–16, L35–37, L64–67) + root `conftest.py`
**Apply to:** The new reconnect test file. Sync test functions + `_run(coro)` helper +
`unittest.mock` (`AsyncMock`/`MagicMock`/`patch`) + `from daemon.claude_usage_daemon_windows import ...`.

## No Analog Found

None. Every file in scope has an exact in-repo analog (the file hardens itself; the macOS
daemon supplies the outer-loop shape; the existing Windows tests supply the harness).

## Metadata

**Analog search scope:** `daemon/`, `daemon/tests/`
**Files scanned:** `claude_usage_daemon_windows.py`, `claude_usage_daemon.py` (main() L390–457),
`tests/test_windows_poll.py`, `tests/test_windows_token.py` (header), `conftest.py`,
`requirements-windows.txt`, `tests/fixtures/`
**Pattern extraction date:** 2026-06-01
