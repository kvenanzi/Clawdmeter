# Phase 2: Core Pipeline - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-01
**Phase:** 2-Core Pipeline
**Areas discussed:** Loop & reconnect depth, MAC-address cache, Test strategy, Device REQ refresh, Dependency setup

---

## Clarification before discussion

The user paused the initial area selection to ask why we were "messing with the macOS
code," concerned this might change existing macOS/Linux functionality — the goal is a
purely additive Windows port that can later be PR'd upstream. Clarified that the macOS
daemon is a **read-only reference to copy from**, never edited or imported (Phase 1
D-08), and that the strictly-additive boundary traces to a locked PROJECT.md
out-of-scope rule. The user agreed to fold "strictly additive — one new Windows file,
zero edits to macOS/Linux/firmware" in as an explicit locked constraint, then returned
to the discussion.

---

## Loop & reconnect depth

| Option | Description | Selected |
|--------|-------------|----------|
| Loop + reconnect | Mirror macOS `main()`: scan → connect → poll/write 60s → on disconnect re-scan w/ backoff. Defers sleep/wake/range hardening to Phase 3. | ✓ |
| Single-shot | Connect once, poll while connected, exit on disconnect; all reconnect logic → Phase 3. | |

**Follow-up question (P2/P3 line):**

| Option | Description | Selected |
|--------|-------------|----------|
| Basic loop now, hardening P3 | Clean macOS-style loop in P2; WinRT stale-connection/`Unreachable` retry wrapper around `connect()` → Phase 3. | ✓ |
| Fold the retry wrapper in now | Include connect-retry-on-`Unreachable` in P2; P3 only adds verification. | |

**User's choice:** Loop + reconnect, with the WinRT `Unreachable`/stale-connection retry deferred to Phase 3.
**Notes:** Keeps Phase 2 demonstrable end-to-end and reviewable; Phase 3 wraps `connect()` without rewriting the loop.

---

## MAC-address cache

| Option | Description | Selected |
|--------|-------------|----------|
| Scan-every-time, defer cache | Stateless `BleakScanner` scan-by-name each cycle; `%APPDATA%\claude-usage-monitor` cache → Phase 3. | ✓ |
| Cache now (full macOS parity) | Implement disk cache + load/save/drop-on-failure in Phase 2. | |

**User's choice:** Scan-every-time; defer the cache to Phase 3.
**Notes:** Windows lacks the macOS HID-invisibility problem that made caching necessary.

---

## Test strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Unit pure logic + manual BLE | Pytest on header→payload mapping, `pct()`/`reset_minutes()`, JSON shape (httpx mocked); BLE connect/write verified manually on Windows hardware. | ✓ |
| Add mocked-bleak integration tests | Also mock BleakScanner/BleakClient to assert loop call order. | |
| Manual-only | No new automated tests; prove the whole pipeline against hardware. | |

**User's choice:** Unit-test pure logic + manual hardware verification for BLE.
**Notes:** Matches how Phase 1 closed its native-Windows criterion; avoids brittle mock-bleak tests.

---

## Device REQ refresh

| Option | Description | Selected |
|--------|-------------|----------|
| Include REQ subscription | `start_notify(REQ)` → asyncio Event → poll immediately (~6 lines, macOS parity); helps <10s first paint. | ✓ |
| Defer to Phase 3 | Poll only on 60s timer; ignore device-initiated refresh until Phase 3. | |

**User's choice:** Include the REQ subscription in Phase 2.
**Notes:** Part of the core macOS loop; reinforces SC#4 (<10s first paint).

---

## Dependency setup

| Option | Description | Selected |
|--------|-------------|----------|
| requirements-windows.txt + venv, no installer yet | Windows requirements file (bleak, httpx) + documented manual venv steps; installer/exe → Phase 4/v2. | ✓ |
| install-windows.ps1 / .bat now | Write a Windows install script in Phase 2. | |
| Reuse a shared requirements file | Point Windows at the macOS dependency list. | |

**User's choice:** `requirements-windows.txt` + documented manual venv steps; polished installer deferred.
**Notes:** A Windows-specific requirements file preserves the strictly-additive, self-contained constraint.

---

## Claude's Discretion

- Internal module organization of `claude_usage_daemon_windows.py` (function vs class split, loop placement), within the locked decisions.
- Backoff constants / scan timeout (may match macOS unless WinRT tuning is warranted).
- Console logging format (reuse macOS `log()` `[HH:MM:SS]` stdout style).

## Deferred Ideas

- WinRT stale-connection/`Unreachable` retry wrapper → Phase 3.
- MAC-address cache (`%APPDATA%\claude-usage-monitor\ble-address`) → Phase 3.
- Out-of-range / device-power-cycle reconnect verification → Phase 3.
- System-tray icon + login autostart + polished `install-windows.ps1` → Phase 4.
- PyInstaller one-file exe → v2 (PKG-01).
- Windows Credential Manager token fallback → v2 / only if needed.
