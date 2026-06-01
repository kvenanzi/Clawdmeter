# Phase 3: Resilience - Context

**Gathered:** 2026-06-01
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase **hardens the existing Phase 2 run-loop** so the native Windows daemon
recovers — with **zero user intervention and no restart** — from every expected
disruption: PC sleep/wake, the device going out of BLE range and back, and the
Clawdmeter being powered off and on.

It is **not a rewrite.** Phase 2 already ships scan-by-name → connect → poll/write
every 60s → on-disconnect re-scan with 1→60s exponential backoff
(`daemon/claude_usage_daemon_windows.py`, D-01). Phase 3 layers reconnect hardening
**on top of that loop** — wrapping `connect()`, escaping zombie links, and splitting
the backoff — without changing the polling logic, wire protocol, or BLE recipe.

Satisfies **BLE-03** (auto-reconnect after sleep / out-of-range / device drop, with
a retry loop handling stale `is_connected` / `Unreachable`).

**Hard SLA (from ROADMAP SC#1):** after wake, reconnect **and push a fresh usage
update within 2 poll cycles (120 seconds)**. SC#2 (out-of-range), SC#3 (power-cycle),
and SC#4 (never needs a restart) follow from the same hardening.

**Explicitly NOT in this phase:**
- System-tray icon, login autostart, WSL-independence verification — **Phase 4**
  (APP-01, APP-02).
- PyInstaller packaging — v2 (PKG-01).
- Any edits to `daemon/claude_usage_daemon.py` (macOS), `daemon/claude-usage-daemon.sh`
  (Linux), or firmware. **Phase 3 stays strictly additive to the Windows daemon**,
  honoring the locked PROJECT.md "ship its own daemon, don't refactor into a shared
  codebase" boundary.

</domain>

<decisions>
## Implementation Decisions

### Connect-retry & wake handling
- **D-01: Explicit `connect()` retry wrapper.** Wrap the connect attempt in a short
  N-attempt retry (~3 tries, ~2s apart, with a `disconnect()`-and-clear between
  attempts) to defeat the WinRT post-wake failure modes flagged in research:
  `Could not get GATT services: Unreachable` and stale `is_connected`. Only after the
  retries exhaust does control fall through to the outer re-scan loop. This recovers
  fast without paying a full ~8s scan cycle on every transient WinRT hiccup. The
  polling/payload logic inside `connect_and_run` is untouched — this wraps only the
  connect path (matches Phase 2 D-02's promise that Phase 3 "wraps connect(), doesn't
  rewrite the loop").
- **D-02: Passive wake detection — no Win32 power events.** Do **not** subscribe to
  Windows power-broadcast / session-change events. The existing 5s `TICK` loop already
  observes the link each cycle; after wake it notices the dead connection and triggers
  reconnect well within the 120s SLA. Mirrors the macOS daemon (which is also passive)
  and avoids a Windows-only `pywin32` dependency and event-loop plumbing for marginal
  gain.
- **D-03: Break the loop on consecutive write/poll failures — don't trust
  `is_connected` alone.** WinRT can report a stale `is_connected=True` on a link that
  is actually dead after wake, which would trap the inner `while client.is_connected`
  loop in a half-open state (writes silently fail, loop never exits). Track consecutive
  failed poll/write cycles and, after **N failures (≈2–3, sized to stay within the 120s
  SLA)**, treat the link as dead: break out, disconnect, and reconnect. No extra GATT
  traffic — keeps Phase 2 D-08's "no TX read" intact.

### Address discovery & state
- **D-04: Keep scan-every-cycle — NO MAC-address cache.** Stay stateless. An ~8s
  scan-by-name fits comfortably inside the 120s reconnect SLA, so the
  `%APPDATA%\claude-usage-monitor\ble-address` cache buys little while adding disk
  state, a Windows cache path, and load/save/invalidate logic. Scan-by-name also
  naturally survives the device acquiring a different address. This confirms and closes
  Phase 2 D-04's deferred "cache only if it proves worth it" — verdict: not worth it on
  Windows (no macOS HID-invisibility problem to force it).

### Backoff strategy
- **D-05: Split fast-reconnect from slow-search backoff.** Replace the single shared
  1→60s counter with two regimes:
  - **Lost a known-good link** (had a working connection, then sleep/range/power-cycle
    dropped it) → retry **quickly**, low cap (~5–10s). Protects the 120s SLA for the
    exact SC#1–3 scenarios.
  - **Device never found** (scan turns up nothing — genuinely absent/off) → back off
    **slower** toward the existing 60s cap so the daemon doesn't hammer scans.
  This prevents stacked failures from pushing reconnect latency past the 120s budget
  while staying gentle when the device is simply gone.

### Verification
- **D-06: Both unit tests AND a manual on-hardware record.** Mirror Phase 2 D-10's
  split:
  - **Unit-test the deterministic new logic** with a mocked/fake BLE client: connect-
    retry exhaustion (D-01), zombie-link break after N write failures (D-03), and
    fast-vs-slow backoff selection (D-05). These guard the logic in CI and need no
    hardware.
  - **Record a manual on-hardware run** covering the three physical scenarios —
    sleep/wake, walk out-of-range-and-back, power-cycle the device — capturing observed
    reconnect timing against the 120s SLA. This proves SC#1–4 against real WinRT, which
    mocks cannot.

### Claude's Discretion
- Exact retry counts/intervals (D-01's ~3 tries/~2s, D-03's N≈2–3, D-05's ~5–10s fast
  cap) — tune during planning/testing so reconnect comfortably clears the 120s SLA; the
  values above are starting points, not hard constants.
- Where the connect-retry wrapper, failure counter, and backoff-regime selection live
  within `claude_usage_daemon_windows.py` (helper function vs. inline) — planner's call,
  as long as D-01..D-06 hold and no shared/macOS/firmware files are touched.
- Console log lines for reconnect events — reuse the existing `log()` `[HH:MM:SS]` style.

### Folded Todos
- **`implement-windows-daemon-tray.md`** (score 0.6) — its **item 4 (MAC-address
  cache)** was the only Phase-3-relevant slice. Resolved by **D-04: not needed on
  Windows** (keep scan-every-cycle). Items 5–7 (tray, autostart, packaging) remain
  deferred to Phase 4 / v2; items 1–3 already shipped in Phases 1–2.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project intent & scope (locked decisions — do not re-litigate)
- `.planning/PROJECT.md` — Windows-daemon-port intent; the **strictly-additive,
  "ship its own daemon, don't refactor into a shared codebase"** out-of-scope boundary
  Phase 3 must honor.
- `.planning/REQUIREMENTS.md` — **BLE-03** is the single requirement this phase
  satisfies.
- `.planning/phases/02-core-pipeline/02-CONTEXT.md` — Phase 2 decisions still in force,
  especially D-01 (the run-loop this phase hardens), D-02 (Phase 3 wraps `connect()`,
  doesn't rewrite the loop), D-04 (scan-every-cycle; cache deferred to here), D-05 (WinRT
  connect recipe: `address_type="random"`, `use_cached_services=False`, no pairing),
  D-08 (no TX read), D-10 (test-split philosophy).
- `.planning/phases/01-foundation/01-CONTEXT.md` — Phase 1: GATT unencrypted (no
  pairing), separate Windows file (copy, don't import macOS), `read_token()` strategy.

### BLE resilience research (the locked WinRT reconnect facts)
- `.planning/notes/windows-daemon-port.md` — §"BLE research findings" point **#4
  (post-sleep reconnect)**: ESP32/NimBLE static-random address → `address_type="random"`;
  after wake the OS may report **stale `is_connected`** or **`Could not get GATT
  services: Unreachable`** → **wrap connect in a retry loop** (this is the direct source
  for D-01/D-03). Also point #3 (`use_cached_services=False` mandatory for DIY firmware).
  Cited bleak issues: #367, #1291, #809.

### The file to harden (the Phase 2 Windows daemon)
- `daemon/claude_usage_daemon_windows.py` — the standalone file Phase 3 extends:
  - `connect_and_run()` (~L227) — wrap the `client.connect()` call (~L242) with the
    D-01 retry wrapper; add the D-03 consecutive-failure break inside the
    `while client.is_connected` loop (~L258–276); `write_payload()` already returns a
    bool the counter can consume (~L117).
  - `main()` (~L287) — replace the single `backoff` (~L305, 314, 323) with the D-05
    fast-reconnect-vs-slow-search split.
  - `scan_for_device()` (~L93) — unchanged; D-04 keeps scan-every-cycle.

### The daemon to mirror (macOS — READ-ONLY reference, never edit)
- `daemon/claude_usage_daemon.py` — `main()` (~L400–449) shows the macOS scan/connect/
  backoff outer loop. Note: the macOS `skip_addr` / `retrieve_connected_macos` HID path
  and the Linux `SAVED_ADDR_FILE` cache are **macOS/Linux-only** — Windows drops both
  (D-04). Copy the resilience *shape*, not the platform-specific cache branch.

### Wire protocol contract (firmware — read-only, unchanged)
- `.planning/codebase/INTEGRATIONS.md` — §"Custom GATT data service" (service
  `4c41555a-…0001`, RX `…0002` WRITE, TX `…0003` NOTIFY, REQ `…0004` NOTIFY). Phase 3
  does not touch the protocol.

### Folded todo
- `.planning/todos/pending/implement-windows-daemon-tray.md` — item 4 (MAC cache)
  resolved by D-04; items 5–7 deferred to Phase 4 / v2.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `daemon/claude_usage_daemon_windows.py` — the entire Phase 2 loop is the substrate.
  `connect_and_run()`, the `Session` class (REQ subscribe + RX write), `scan_for_device()`,
  `poll_api()`, and `read_token()` all stay; Phase 3 only wraps connect, adds a
  failure-counter break, and reshapes the backoff.
- `write_payload()` already returns `True/False` — the D-03 consecutive-failure counter
  consumes that return value directly; no new failure-signal plumbing needed.
- `main()`'s `stop_event` + `asyncio.wait_for(..., timeout=backoff)` pattern is reused
  for both backoff regimes (D-05) — keeps Ctrl-C/SIGTERM responsiveness during waits.

### Established Patterns
- Outer loop idiom (macOS/Linux/Windows): scan → connect → use → on-failure re-scan with
  backoff. Phase 3 refines the *failure* and *backoff* branches, not the happy path.
- WinRT connect recipe is locked (D-05 from Phase 2): pass the `BLEDevice`,
  `address_type="random"`, `use_cached_services=False`. The D-01 retry wrapper reuses
  this exact `BleakClient(...)` construction per attempt.
- `log()` `[HH:MM:SS]` stdout style for all new reconnect/retry/zombie-break messages.

### Integration Points
- All Phase 3 changes land **inside `daemon/claude_usage_daemon_windows.py`** only.
- New unit tests under `daemon/tests/` exercising connect-retry exhaustion, zombie-break,
  and backoff-regime selection with a mocked/fake BLE client (no real WinRT).
- **No** new runtime dependency (D-02 rejects `pywin32`/power-event listeners; D-04
  rejects a cache file). `requirements-windows.txt` is unchanged.

</code_context>

<specifics>
## Specific Ideas

- The three physical verification scenarios to record (SC#1–3): (1) sleep the PC, wake
  it, confirm reconnect + fresh push within 120s; (2) carry the device out of BLE range
  and back, confirm auto-reconnect; (3) power the Clawdmeter off and on, confirm pickup
  on the next scan. Capture observed reconnect latency for each, mirroring Phase 1/2's
  native-Windows test notes.
- The two failure classes for the D-05 backoff split: "lost a known-good link" (we had a
  successful connection this run, i.e. `connect_and_run` returned after `used_successfully`
  or after a mid-session drop) vs. "device never found" (scan returned `None`). The
  existing `main()` already branches on these two outcomes — D-05 just assigns each its
  own backoff cap.
- Starting-point constants (Claude's discretion to tune): connect-retry ≈3 tries / ~2s
  apart; zombie-break after ≈2–3 consecutive write failures; fast-reconnect cap ~5–10s;
  slow-search cap stays at 60s.

</specifics>

<deferred>
## Deferred Ideas

- **System-tray icon + login autostart + WSL-independence verification** → **Phase 4**
  (APP-01, APP-02).
- **PyInstaller one-file exe packaging** → v2 (PKG-01).
- **Active Win32 power/session-event wake detection** → rejected for Phase 3 (D-02);
  could be revisited only if passive detection proves too slow in hardware testing.
- **MAC-address cache** → rejected for Phase 3 (D-04); revisit only if measured scan time
  ever threatens the SLA.
- **Token-expiry-during-long-disconnect / max-failure give-up behavior** → not raised as
  a concern for this phase; existing per-cycle `read_token()` skip-on-missing behavior
  (Phase 2 D-09) carries forward unchanged. Note for a future hardening pass if needed.

### Reviewed Todos (not folded)
- **`verify-gatt-characteristics-unencrypted.md`** (score 0.4) — already resolved in
  Phase 1 (D-01: characteristics unencrypted, no pairing). Carried as a settled fact;
  nothing to do in Phase 3.

</deferred>

---

*Phase: 3-Resilience*
*Context gathered: 2026-06-01*
