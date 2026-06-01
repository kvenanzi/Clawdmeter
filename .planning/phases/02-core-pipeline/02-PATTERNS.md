# Phase 2: Core Pipeline - Pattern Map

**Mapped:** 2026-06-01
**Files analyzed:** 2 (1 extended, 1 created)
**Analogs found:** 2 / 2

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `daemon/claude_usage_daemon_windows.py` | daemon / async service | request-response + event-driven | `daemon/claude_usage_daemon.py` | exact (same logic, Windows platform layer) |
| `daemon/requirements-windows.txt` | config / dependency manifest | n/a | `daemon/requirements-windows.txt` (new; no prior analog) | no analog |

---

## Pattern Assignments

### `daemon/claude_usage_daemon_windows.py` (daemon, request-response + event-driven)

**Analog:** `daemon/claude_usage_daemon.py`

**Copy verbatim (shared, platform-neutral code):** Everything from lines 274–397 ports with zero modification. The WinRT-specific changes are surgical and limited to `scan_for_device()` and `connect_and_run()` as noted below.

---

#### Imports pattern (macOS analog lines 9–22)

The Windows file currently imports only stdlib modules. Phase 2 adds the three async-capable external packages. Copy this block and drop the `subprocess`/`getpass` macOS-only imports:

```python
import asyncio
import json
import os
import re
import signal
import sys
import time
from pathlib import Path

import httpx
from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError
```

Note: `subprocess` and `getpass` are NOT needed on Windows (no Keychain call). `datetime` (already in the scaffold) can be removed once `_read_expiry` is no longer the only `__main__` action.

---

#### Module-level constants (macOS analog lines 24–50)

Copy verbatim. Do NOT add `SAVED_ADDR_FILE` (D-04: no disk cache in Phase 2):

```python
DEVICE_NAME = "Claude Controller"
SERVICE_UUID = "4c41555a-4465-7669-6365-000000000001"
RX_CHAR_UUID = "4c41555a-4465-7669-6365-000000000002"
REQ_CHAR_UUID = "4c41555a-4465-7669-6365-000000000004"

POLL_INTERVAL = 60
TICK = 5
SCAN_TIMEOUT = 8.0

API_URL = "https://api.anthropic.com/v1/messages"
API_HEADERS_TEMPLATE = {
    "anthropic-version": "2023-06-01",
    "anthropic-beta": "oauth-2025-04-20",
    "Content-Type": "application/json",
    "User-Agent": "claude-code/2.1.5",
}
API_BODY = {
    "model": "claude-haiku-4-5-20251001",
    "max_tokens": 1,
    "messages": [{"role": "user", "content": "hi"}],
}
```

---

#### `log()` helper (macOS analog line 53–54)

Copy verbatim:

```python
def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)
```

---

#### `poll_api()` (macOS analog lines 274–314)

Copy verbatim. No Windows-specific changes needed — `httpx.AsyncClient` is platform-neutral:

```python
async def poll_api(token: str) -> dict | None:
    headers = dict(API_HEADERS_TEMPLATE)
    headers["Authorization"] = f"Bearer {token}"
    try:
        async with httpx.AsyncClient(timeout=20.0) as http:
            resp = await http.post(API_URL, headers=headers, json=API_BODY)
    except httpx.HTTPError as e:
        log(f"API call failed: {e}")
        return None
    if resp.status_code >= 400:
        log(f"API HTTP {resp.status_code}: {resp.text[:200]}")
        return None

    def hdr(name: str, default: str = "0") -> str:
        return resp.headers.get(name, default)

    now = time.time()

    def reset_minutes(reset_ts: str) -> int:
        try:
            r = float(reset_ts)
        except ValueError:
            return 0
        mins = (r - now) / 60.0
        return int(round(mins)) if mins > 0 else 0

    def pct(util: str) -> int:
        try:
            return int(round(float(util) * 100))
        except ValueError:
            return 0

    payload = {
        "s": pct(hdr("anthropic-ratelimit-unified-5h-utilization")),
        "sr": reset_minutes(hdr("anthropic-ratelimit-unified-5h-reset")),
        "w": pct(hdr("anthropic-ratelimit-unified-7d-utilization")),
        "wr": reset_minutes(hdr("anthropic-ratelimit-unified-7d-reset")),
        "st": hdr("anthropic-ratelimit-unified-5h-status", "unknown"),
        "ok": True,
    }
    return payload
```

**Key extraction helpers (lines 291–304):**
- `pct(util)` — multiplies the `0.0–1.0` utilization float by 100 and rounds to int.
- `reset_minutes(reset_ts)` — converts epoch-seconds string to integer minutes from now; clamps negative to 0.
- Both helpers are defined inline inside `poll_api` (closure over `now`). Keep them there.

---

#### `Session` class (macOS analog lines 317–341)

Copy verbatim. Both `start_notify` and `write_gatt_char` are Bleak cross-platform APIs:

```python
class Session:
    def __init__(self, client: BleakClient) -> None:
        self.client = client
        self.refresh_requested = asyncio.Event()

    def _on_refresh(self, _char, _data: bytearray) -> None:
        log("Refresh requested by device")
        self.refresh_requested.set()

    async def setup_refresh_subscription(self) -> None:
        try:
            await self.client.start_notify(REQ_CHAR_UUID, self._on_refresh)
        except (BleakError, ValueError) as e:
            log(f"Refresh subscription unavailable: {e}")

    async def write_payload(self, payload: dict) -> bool:
        data = json.dumps(payload, separators=(",", ":")).encode()
        log(f"Sending: {data.decode()}")
        try:
            await self.client.write_gatt_char(RX_CHAR_UUID, data, response=False)
            return True
        except BleakError as e:
            log(f"Write failed: {e}")
            return False
```

**D-08 enforcement:** `response=False` is load-bearing — do not change to `response=True`. No TX characteristic (`...0003`) read or subscription. The macOS code does not subscribe to TX either; Windows must match exactly.

---

#### `scan_for_device()` — Windows divergence from D-05

The macOS analog (`scan_for_device`, lines 150–157) returns an address string. On Windows, the scan **must return the `BLEDevice` object**, not just an address string, so `BleakClient` can use it directly with `address_type="random"` and `use_cached_services=False`:

```python
async def scan_for_device():
    """Scan for DEVICE_NAME and return the BLEDevice, or None."""
    log(f"Scanning for '{DEVICE_NAME}' ({SCAN_TIMEOUT}s)...")
    device = await BleakScanner.find_device_by_name(DEVICE_NAME, timeout=SCAN_TIMEOUT)
    if device:
        log(f"Found: {device.address}")
    return device  # BLEDevice or None — NOT an address string
```

`BleakScanner.find_device_by_name` is preferred over `.discover()` + manual loop because it stops as soon as the target is seen. The returned `BLEDevice` is passed directly to `BleakClient(device, ...)` in `connect_and_run`.

---

#### `connect_and_run()` — Windows divergence from D-05 (macOS analog lines 343–397)

The macOS version accepts `target` as either an address string or a `BLEDevice`. On Windows, target is always a `BLEDevice` (from `scan_for_device`). The three WinRT-specific constructor kwargs are the only divergence; the rest of the function copies verbatim:

```python
async def connect_and_run(device, stop_event: asyncio.Event) -> bool:
    """Connect to device and poll until disconnected or stopped.

    Returns True if at least one successful write occurred.
    """
    log(f"Connecting to {device.address}...")
    # D-05: pass BLEDevice (not address string), address_type="random" (NimBLE
    # static-random), use_cached_services=False (DIY firmware — WinRT GATT cache
    # may be stale after firmware reflash).
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

    log("Connected")
    session = Session(client)
    await session.setup_refresh_subscription()

    last_poll = 0.0  # D-03: poll immediately on first connect
    used_successfully = False
    try:
        while client.is_connected and not stop_event.is_set():
            now = time.time()
            elapsed = now - last_poll
            if session.refresh_requested.is_set() or elapsed >= POLL_INTERVAL:
                session.refresh_requested.clear()
                token = read_token()
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
    finally:
        try:
            await client.disconnect()
        except BleakError:
            pass

    log("Device disconnected" if not stop_event.is_set() else "Stopping")
    return used_successfully
```

**D-09 enforcement:** `read_token()` is called inside the poll loop (line 377 equivalent), NOT cached at session start. This reuses the existing Phase 1 `read_token()` already in the file.

---

#### `main()` — Windows version stripped of macOS-only paths (macOS analog lines 400–456)

Copy the macOS `main()` structure and **strip** the following macOS-specific elements:
- The `skip_addr` / `discover_target` / `retrieve_connected_macos` HID-recovery path (D-04, D-05)
- The address-cache invalidation (`SAVED_ADDR_FILE.unlink`) branch on connect failure (D-04)
- The `sys.platform == "darwin"` conditional blocks

The resulting Windows `main()` is the clean minimal form:

```python
async def main() -> None:
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _stop(*_args: object) -> None:
        log("Daemon stopping")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop)
        except NotImplementedError:
            # Windows: add_signal_handler not supported; fall back to signal.signal
            signal.signal(sig, _stop)

    log("=== Claude Usage Tracker Daemon (BLE, Windows) ===")
    log(f"Poll interval: {POLL_INTERVAL}s")

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


if __name__ == "__main__":
    if sys.platform != "win32":
        print(
            "Warning: running under Linux/WSL — WinRT BLE will not be available.",
            file=sys.stderr,
        )
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
```

**`NotImplementedError` note (macOS analog lines 408–412):** `loop.add_signal_handler` raises `NotImplementedError` on Windows (Python 3.12 docs). The macOS code already handles this with `signal.signal` fallback. Keep the fallback — it is not macOS-specific.

**`__main__` guard:** Replace the Phase 1 scaffold's `__main__` block (which only prints the token) with the async runner above. The Phase 1 `read_token()` / `_extract_access_token()` / `_windows_credential_candidates()` / `_read_expiry()` functions are preserved untouched in the same file.

---

### `daemon/requirements-windows.txt` (config, n/a)

**Analog:** No prior analog exists (first non-stdlib Windows requirements file).

**Pattern source:** D-11. Create a minimal pinned file following the same style as any `requirements*.txt` in the repo if present; otherwise use unpinned names:

```
bleak
httpx
```

Both packages are cross-platform and available from PyPI. No version pins required for Phase 2 (clean installs will get recent stable releases). If a minimum version becomes relevant (e.g. a known Bleak WinRT fix), add it as a comment with the reason.

---

## Shared Patterns

### `log()` — timestamped stdout
**Source:** `daemon/claude_usage_daemon.py` line 53–54
**Apply to:** All new functions in `claude_usage_daemon_windows.py`
```python
def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)
```

### Error handling — BleakError + asyncio.TimeoutError pairing
**Source:** `daemon/claude_usage_daemon.py` lines 354–358
**Apply to:** `connect_and_run()`, `Session.setup_refresh_subscription()`, `Session.write_payload()`

The pattern is: `except (BleakError, asyncio.TimeoutError)` for connect; `except BleakError` for notify/write (write doesn't time out independently). Do not broaden the exception to bare `Exception` — let unexpected errors propagate and surface.

### Compact JSON serialization
**Source:** `daemon/claude_usage_daemon.py` line 333
**Apply to:** `Session.write_payload()`
```python
data = json.dumps(payload, separators=(",", ":")).encode()
```
The `separators=(",",":")` is load-bearing for payload size on the GATT MTU — do not use the default spaced format.

### Signal handling with Windows fallback
**Source:** `daemon/claude_usage_daemon.py` lines 408–412
**Apply to:** `main()`
```python
for sig in (signal.SIGINT, signal.SIGTERM):
    try:
        loop.add_signal_handler(sig, _stop)
    except NotImplementedError:
        signal.signal(sig, _stop)
```
`add_signal_handler` raises `NotImplementedError` on Windows. The `NotImplementedError` fallback already exists in the macOS code and is kept as-is.

### Backoff pattern
**Source:** `daemon/claude_usage_daemon.py` lines 417–449
**Apply to:** `main()` outer loop

```python
backoff = 1
# ... on failure:
backoff = min(backoff * 2, 60)
# ... on success:
backoff = 1
```
Doubles on each failed connect/scan cycle; resets to 1 on any successful cycle. Cap is 60s.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `daemon/requirements-windows.txt` | config | n/a | First Windows-specific requirements file in the repo |

---

## WinRT Divergence Summary

These are the four points where the Windows port deliberately differs from the macOS analog (all sourced from D-04 and D-05):

| Location | macOS analog | Windows version | Reason |
|----------|-------------|-----------------|--------|
| `scan_for_device()` return type | `str` (address) | `BLEDevice` object | Must pass object to `BleakClient` with WinRT kwargs |
| `BleakClient(...)` constructor | `BleakClient(target)` — target is str or BLEDevice, no extra kwargs | `BleakClient(device, address_type="random", use_cached_services=False)` | NimBLE uses static-random address; WinRT caches GATT table |
| `discover_target()` / address cache | Present (SAVED_ADDR_FILE, `retrieve_connected_macos`) | Absent | D-04: scan-every-cycle, no disk state in Phase 2 |
| `main()` platform branches | `sys.platform == "darwin"` blocks + `skip_addr` logic | Removed entirely | D-04 + D-05: Windows has none of these paths |

---

## Metadata

**Analog search scope:** `daemon/` directory
**Files scanned:** 2 (`claude_usage_daemon.py`, `claude_usage_daemon_windows.py`)
**Pattern extraction date:** 2026-06-01
