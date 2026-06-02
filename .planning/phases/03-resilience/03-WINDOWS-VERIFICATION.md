---
status: passed
phase: 03-resilience
source: [03-03-PLAN.md]
verified: 2026-06-02
operator: kevin.venanzi@gmail.com
hardware: native Windows (Python 3.13, .venv, files over \\wsl.localhost mount)
---

> **Update (2026-06-02, after gap fix):** SC#3 and SC#4 were RE-VERIFIED on hardware
> and now PASS. Gap G-03-01 was closed by widening the `except` in
> `Session.setup_refresh_subscription()` to catch `OSError` (commits
> `b58c190` RED test, `f303eb4` GREEN fix). On the re-run, the post-power-cycle
> reconnect logged `Refresh subscription unavailable: ...` (graceful degradation),
> landed a fresh `Sending:`, and the daemon stayed a single continuous process
> (no restart). The per-scenario sections below retain the original failure
> account for the record; the Summary reflects the final all-pass state.

## Windows Hardware Verification — Phase 3: Resilience

**Verified:** 2026-06-02
**Daemon run command:** `python .\daemon\claude_usage_daemon_windows.py`
**Device under test:** Clawdmeter (Waveshare AMOLED-2.16, BLE MAC 28:84:85:55:65:39)
**Hardened code exercised:** 03-01 (D-01 connect-retry, D-03 zombie-link break) + 03-02 (D-05 split backoff)

SC#1 (sleep/wake) and SC#2 (out-of-range) PASSED against real WinRT. SC#3 (power-cycle)
exposed an **uncaught `OSError` from `start_notify()`** on the post-power-cycle reconnect,
which crashed the daemon — failing SC#3 and, because the process died, SC#4 (no restart).

Console excerpt captured at the SC#3 failure (timestamps + traceback only — no token/credential content, T-03-07):

```
[19:56:44] Write failed: Not connected
[19:56:44] Zombie link detected (1 consecutive write failures); abandoning connection
[19:56:44] Device disconnected
[19:56:44] Scanning for 'Claude Controller' (8.0s)...
[19:56:50] Found: 28:84:85:55:65:39
[19:56:50] Connecting to 28:84:85:55:65:39...
[19:56:51] Connected
Traceback (most recent call last):
  File "...\daemon\claude_usage_daemon_windows.py", line 391, in <module>
    asyncio.run(main())
  File "...\daemon\claude_usage_daemon_windows.py", line 369, in main
    ok = await connect_and_run(device, stop_event)
  File "...\daemon\claude_usage_daemon_windows.py", line 283, in connect_and_run
    await session.setup_refresh_subscription()
  File "...\daemon\claude_usage_daemon_windows.py", line 120, in setup_refresh_subscription
    await self.client.start_notify(REQ_CHAR_UUID, self._on_refresh)
  File "...\bleak\backends\winrt\client.py", line 1035, in start_notify
    await winrt_char.write_client_characteristic_configuration_descriptor_with_result_async(cccd)
OSError: [WinError -2147023673] The operation was canceled by the user.
```

---

## Tests

### SC#1 — sleep/wake reconnect within 120s

**Expected behavior:** After putting the PC to sleep and waking it, the daemon reconnects
and pushes a FRESH usage update within 2 poll cycles (120s) — without a restart.

**Operator-reported result:** PASS. The daemon reconnected and resumed pushing fresh
`Sending:` updates after wake, within the 120s SLA, with no restart. The D-01 connect-retry
wrapper handled the transient post-wake WinRT failure modes as designed.

---

### SC#2 — out-of-range auto-reconnect

**Expected behavior:** Carrying the Clawdmeter out of BLE range and back triggers an
automatic reconnect (new `Connected` + `Sending:`) with no user action.

**Operator-reported result:** PASS. The daemon detected the drop, re-scanned, and
auto-reconnected with no user action when the device returned to range.

---

### SC#3 — power-cycle pickup on next scan

**Expected behavior:** Powering the Clawdmeter off and on, the daemon picks it up on the
next scan cycle (`Found:` → `Connected` → `Sending:`) without a restart.

**Operator-reported result:** FAIL on first run → **PASS after gap fix (re-verified
2026-06-02).** First run: the daemon correctly detected the dropped link
(D-03 zombie-break fired at 19:56:44), re-scanned, found the device, and reconnected
(`Connected` at 19:56:51) — but then **crashed** during post-connect setup. The freshly
power-cycled device's GATT server was not yet ready for the CCCD descriptor write that
`start_notify()` performs, and WinRT raised `OSError: [WinError -2147023673] The operation
was canceled by the user.` That `OSError` is not caught by `setup_refresh_subscription()`
(which only catches `BleakError`/`ValueError`), so it propagated through `connect_and_run`
(L283) → `main()` (L369) → `asyncio.run()` and terminated the process.

**Root cause:** `Session.setup_refresh_subscription()` (daemon/claude_usage_daemon_windows.py
L118–122) catches `(BleakError, ValueError)` but not `OSError`. On WinRT, `start_notify()`'s
CCCD write can surface a raw `OSError`/`WinError` (not wrapped as `BleakError`) when the peer
GATT server is transiently unavailable — exactly the state of a just-rebooted ESP32. The
refresh subscription is optional (the 60s poll loop works without it), so the correct behavior
is to catch the failure and degrade gracefully, as the existing `except` already intends for
`BleakError`. This path was outside the D-01/D-03 hardening (D-01 wraps `connect()`; D-03 wraps
the write loop; the `start_notify()` between them was left with a too-narrow `except`).

**Resolution (re-verified PASS):** `except (BleakError, ValueError)` → `except
(BleakError, ValueError, OSError)` in `setup_refresh_subscription()`. On the hardware
re-run, the power-cycled device reconnected, logged `Refresh subscription unavailable`
(the optional subscription degraded gracefully), and a fresh `Sending:` landed on the
next poll — daemon never crashed.

---

### SC#4 — single continuous run (no restart)

**Expected behavior:** The SAME daemon process recovers from all three scenarios without
a restart (one continuous PID).

**Operator-reported result:** FAIL on first run → **PASS after gap fix (re-verified
2026-06-02).** First run: SC#1 and SC#2 were survived by a single continuous process,
but the SC#3 crash terminated it. After the G-03-01 fix, the daemon survived all three
scenarios as a single continuous process (same PID, no restart) — SC#4 attested PASS.

---

## Summary

```
total:   4
passed:  4  (SC#1, SC#2 first run; SC#3, SC#4 after G-03-01 fix, re-verified 2026-06-02)
issues:  0
gaps:    0  (G-03-01 closed and re-verified on hardware)
```

**Gap G-03-01 (CLOSED) — uncaught `OSError` from `start_notify()` crashed the daemon on
post-power-cycle reconnect.** Fixed by widening the `except` in
`Session.setup_refresh_subscription()` to include `OSError` so a transient not-ready GATT
server on a just-rebooted device degrades gracefully (logs "Refresh subscription
unavailable", continues into the 60s poll loop) instead of killing the process. Guarded by
regression test `test_start_notify_oserror_does_not_crash_connect_and_run`
(RED `b58c190` → GREEN `f303eb4`). Re-verified PASS on hardware 2026-06-02.

## Notes

- No OAuth token or credential content is embedded in this record (T-03-07). The captured
  traceback contains only file paths and the WinRT error code; absolute WSL/venv paths were
  abbreviated to `...`.
- SC#1/SC#2 confirm the D-01 connect-retry and D-05 split backoff hardening work against real
  WinRT. The defect is a narrow exception-handling gap in the optional refresh-subscription
  setup, not in the reconnect/backoff logic itself.
</content>
</invoke>
