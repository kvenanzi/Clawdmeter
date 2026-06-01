# Phase 3: Resilience - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-01
**Phase:** 3-Resilience
**Areas discussed:** Connect-retry & wake handling, Address caching, Backoff vs. 120s SLA, Verification method

---

## Connect-retry & wake handling

### Dropped/stale link recovery

| Option | Description | Selected |
|--------|-------------|----------|
| Explicit connect() retry wrapper | ~3 tries, ~2s apart, disconnect-and-clear between, for WinRT Unreachable/stale-is_connected; fall through to re-scan only after retries exhaust | ✓ |
| Passive loop only (mirror macOS) | One connect() attempt; on failure fall straight to re-scan + backoff. Simplest, but each recovery costs a full scan cycle | |
| You decide | Let Claude pick based on bleak's internal retries | |

**User's choice:** Explicit connect() retry wrapper (→ D-01)

### Sleep/wake detection

| Option | Description | Selected |
|--------|-------------|----------|
| Passive — let the loop notice | 5s tick loop polls is_connected; reconnects within one TICK after wake. No Windows-specific code. Mirrors macOS | ✓ |
| Active wake listener | Win32 power-broadcast/session-change events (pywin32) for instant reconnect. Faster but Windows-only dep + plumbing | |
| You decide | Let Claude choose based on measured passive recovery | |

**User's choice:** Passive — let the loop notice (→ D-02)

### Zombie connection (is_connected stays True but writes fail)

| Option | Description | Selected |
|--------|-------------|----------|
| Break on consecutive write failures | After N (≈2–3) failed cycles, treat link as dead, break, reconnect. Cheap, no extra GATT traffic, defeats stale-True trap | ✓ |
| Active liveness probe | Periodic GATT read on TX to confirm link; reintroduces a TX read Phase 2 D-08 avoided | |
| Trust is_connected (no extra guard) | Assume WinRT eventually flips to False. Simplest, but risks hanging past 120s SLA | |

**User's choice:** Break on consecutive write failures (→ D-03)

---

## Address caching

| Option | Description | Selected |
|--------|-------------|----------|
| Keep scan-every-cycle (no cache) | Stateless. 8s scan fits 120s SLA; cache adds disk state + invalidation for little gain. Confirms Phase 2 D-04 | ✓ |
| Add MAC cache with scan fallback | Cache resolved address at %APPDATA%\claude-usage-monitor\ble-address; try cached first, fall back to scan, drop on failure | |
| You decide | Let Claude choose based on measured timing | |

**User's choice:** Keep scan-every-cycle (no cache) (→ D-04; closes tray-todo item 4)

---

## Backoff vs. 120s SLA

| Option | Description | Selected |
|--------|-------------|----------|
| Split fast-reconnect vs. slow-search | 'Lost a known-good link' retries fast (~5–10s cap); 'never found device' backs off slow (→60s). Protects the 120s SLA for SC#1–3 | ✓ |
| Cap reconnect backoff lower | One counter, lower max (~15–30s). Simpler, but slows the genuinely-absent-device case | |
| Keep current backoff (1→60s) | Rely on retry wrapper + fast detection. Least code, but stacked failures could near the SLA edge | |

**User's choice:** Split fast-reconnect vs. slow-search (→ D-05)

---

## Verification method

| Option | Description | Selected |
|--------|-------------|----------|
| Both: unit tests + hardware record | Mock-test new logic (retry exhaustion, zombie-break, backoff selection) in CI + record the three physical scenarios on hardware. Mirrors Phase 2 D-10 | ✓ |
| Manual hardware record only | Just record physical scenarios; no automated regression guard for new logic | |
| You decide | Let Claude choose the split | |

**User's choice:** Both: unit tests + hardware record (→ D-06)

---

## Claude's Discretion

- Exact retry counts/intervals: connect-retry ~3 tries/~2s (D-01), zombie-break N≈2–3 (D-03), fast-reconnect cap ~5–10s (D-05) — tune during planning/testing to clear the 120s SLA.
- Placement of the retry wrapper, failure counter, and backoff-regime logic within `claude_usage_daemon_windows.py`.
- Console log wording for reconnect events (reuse existing `log()` style).

## Deferred Ideas

- System-tray icon + login autostart + WSL-independence verification → Phase 4 (APP-01, APP-02).
- PyInstaller packaging → v2 (PKG-01).
- Active Win32 power/session-event wake detection → rejected (D-02); revisit only if passive proves too slow.
- MAC-address cache → rejected (D-04); revisit only if scan time threatens the SLA.
- Token-expiry-during-long-disconnect / max-failure give-up → not a Phase 3 concern; existing per-cycle skip-on-missing-token (Phase 2 D-09) carries forward.
- Reviewed but not folded: `verify-gatt-characteristics-unencrypted.md` — already resolved in Phase 1 (D-01).
