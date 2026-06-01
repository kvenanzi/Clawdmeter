---
phase: 02-core-pipeline
verified: 2026-06-01T00:00:00Z
status: passed
score: 11/11 must-haves verified
overrides_applied: 0
re_verification: null
gaps: []
deferred: []
human_verification: []
---

# Phase 02: Core Pipeline Verification Report

**Phase Goal:** Core Pipeline — BLE scan/connect/write + Anthropic API polling end-to-end on native Windows.
**Verified:** 2026-06-01
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | poll_api() returns the {s,sr,w,wr,st,ok} payload from Anthropic ratelimit headers (D-07) | VERIFIED | Lines 82–90 of daemon; all 6 keys present; unit tests confirm 42→s, 10→w, "allowed"→st, ok=True |
| 2 | pct() converts utilization string to int percentage; ValueError-safe | VERIFIED | Inner closure at line 76–79; test suite exercises 0.42→42, 1.0→100, "0"→0; "garbage"/"bad" confirmed 0 via spot-check |
| 3 | reset_minutes() converts epoch-seconds to minutes-from-now, clamped at 0 | VERIFIED | Inner closure at lines 68–74; tests confirm ~60min, negative→0, "notanumber"→0 |
| 4 | Wire payload serializes as compact JSON with separators (",",":") | VERIFIED | Session.write_payload line 118: `json.dumps(payload, separators=(",", ":")).encode()`; test_wire_bytes_compact_json_shape asserts no ": " or ", " |
| 5 | scan_for_device() returns BLEDevice (not address string) or None; no disk cache (D-04, D-05) | VERIFIED | Lines 93–99; calls `BleakScanner.find_device_by_name` returning BLEDevice; SAVED_ADDR_FILE=0, discover_target=0, darwin=0 |
| 6 | connect_and_run() uses BleakClient with address_type="random" and use_cached_services=False; single connect attempt (D-02, D-05) | VERIFIED | Lines 237–240: `BleakClient(device, address_type="random", use_cached_services=False)`; no retry wrapper; confirmed in hardware run (SC#2) |
| 7 | Session.write_payload writes compact-JSON to RX with response=False; no TX characteristic reference (D-08) | VERIFIED | Line 121: `write_gatt_char(RX_CHAR_UUID, data, response=False)`; response=True count=0; "0003" count=0 |
| 8 | Session subscribes to REQ characteristic; polls immediately on device 0x01 notify (D-06) | VERIFIED | Line 113: `start_notify(REQ_CHAR_UUID, self._on_refresh)`; refresh_requested event drives poll; hardware-confirmed |
| 9 | Run loop: polls immediately on connect (last_poll=0.0), reads token fresh each cycle, exponential backoff on failure (D-01, D-03, D-09) | VERIFIED | last_poll=0.0 at line 255; read_token() at line 263 inside loop; backoff doubling at lines 314, 323; min(backoff*2,60) confirmed |
| 10 | __main__ launches asyncio scan/connect/poll loop with signal-based shutdown and Windows fallback | VERIFIED | Lines 296–301: add_signal_handler with NotImplementedError fallback; line 335: asyncio.run(main()); non-win32 warning confirmed |
| 11 | Manual hardware verification (SC#1-4) recorded: device leaves waiting screen, BLE connects, RX write accepted, first-paint documented | VERIFIED | 02-WINDOWS-VERIFICATION.md dated 2026-06-01; all 4 SC entries present; SC#4 PASS-WITH-CAVEAT accepted per operator disposition |

**Score:** 11/11 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `daemon/claude_usage_daemon_windows.py` | poll_api, Session, scan_for_device, connect_and_run, main, __main__ runner | VERIFIED | All functions confirmed via AST parse; 338 lines; substantive implementation |
| `daemon/tests/test_windows_poll.py` | Unit tests for poll_api/pct/reset_minutes/JSON shape with httpx mocked | VERIFIED | 12 tests covering all PLAN behaviors; imported and passing |
| `daemon/requirements-windows.txt` | Windows-only manifest with bleak + httpx | VERIFIED | Lines: comment + `bleak` + `httpx`; grep -qx confirms exact lines |
| `daemon/README-windows.md` | Windows setup + run instructions | VERIFIED | Covers venv, requirements-windows.txt, native token, launch command, no-pairing note, no tray/autostart scope |
| `.planning/phases/02-core-pipeline/02-WINDOWS-VERIFICATION.md` | Recorded manual hardware verification of SC#1-4 | VERIFIED | Dated 2026-06-01; all four criteria with expected/result; summary count 4/4/0 |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `claude_usage_daemon_windows.py::poll_api` | `httpx.AsyncClient.post` | POST to API_URL with Authorization Bearer | WIRED | `async with httpx.AsyncClient(...) as http: resp = await http.post(API_URL, ...)` at lines 54–55 |
| `daemon/tests/test_windows_poll.py` | `poll_api` | `from daemon.claude_usage_daemon_windows import poll_api` | WIRED | Line 16; all 12 tests call poll_api via _run(); 28 tests pass |
| `connect_and_run` | `bleak.BleakClient` | `BleakClient(device, address_type="random", use_cached_services=False)` | WIRED | Lines 237–240; `address_type="random"` count=2 (comment + value); `use_cached_services=False` count=2 |
| `Session.write_payload` | `RX_CHAR_UUID (...0002)` | `client.write_gatt_char(RX_CHAR_UUID, data, response=False)` | WIRED | Line 121; response=False confirmed; no response=True |
| `Session.setup_refresh_subscription` | `REQ_CHAR_UUID (...0004)` | `client.start_notify(REQ_CHAR_UUID, self._on_refresh)` | WIRED | Line 113; count=1 |
| `connect_and_run` | `poll_api / read_token` | `read_token()` fresh inside while loop, result passed to poll_api | WIRED | Line 263: `token = read_token()  # D-09: fresh each cycle`; inside while loop at line 258 |
| `daemon/README-windows.md` | `daemon/claude_usage_daemon_windows.py` | documented launch command | WIRED | `python daemon\claude_usage_daemon_windows.py` present; `requirements-windows.txt` install step present |

---

### Data-Flow Trace (Level 4)

Not applicable. The daemon is a pipeline process, not a UI component rendering dynamic data. Data flows externally (Anthropic API → BLE device) and is verified end-to-end by the hardware record.

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| pct("garbage") returns 0 (ValueError-safe) | Python in-process via poll_api with "garbage" headers | `pct(garbage)=0, reset_minutes(bad)=0` | PASS |
| All unit tests pass | `python -m pytest daemon/tests/test_windows_poll.py daemon/tests/test_windows_token.py -q` | 28 passed in 6.20s | PASS |
| AST defines all required symbols | `python -c "import ast; ..."` | Session, connect_and_run, main, poll_api, read_token, scan_for_device, _extract_access_token, _read_expiry all confirmed | PASS |
| requirements-windows.txt contains exact lines | `grep -qx 'bleak' && grep -qx 'httpx'` | OK | PASS |

---

### Probe Execution

No `scripts/*/tests/probe-*.sh` probes defined for this phase. Phase 03 is a documentation + manual-hardware-verification plan with no executable probes.

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| POLL-01 | 02-01-PLAN.md | Daemon polls Anthropic API and derives session + weekly rate-limit utilization | SATISFIED | `poll_api()` at lines 50–90; 12 mocked-httpx tests; REQUIREMENTS.md marked [x] |
| BLE-01 | 02-02-PLAN.md | Discover + connect via WinRT BLE; scan-first; BLEDevice; address_type="random"; use_cached_services=False | SATISFIED | `scan_for_device()` returns BLEDevice; `BleakClient(device, address_type="random", use_cached_services=False)`; REQUIREMENTS.md marked [x] |
| BLE-02 | 02-02-PLAN.md | Write usage JSON to GATT RX characteristic in unchanged wire format | SATISFIED | `Session.write_payload` writes compact-JSON to RX_CHAR_UUID with response=False; hardware-confirmed SC#3 PASS; REQUIREMENTS.md marked [x] |

All three phase-claimed requirements are satisfied. No orphaned requirements: REQUIREMENTS.md traceability table maps BLE-01, BLE-02, POLL-01 to Phase 2 with status "Complete".

---

### Anti-Patterns Found

No TBD, FIXME, or XXX markers found in any phase-modified file. No placeholder stubs, empty return values, or hardcoded empty data detected. No `return null` / `return {}` / `return []` anti-patterns in production paths.

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | None found | — | — |

---

### Human Verification Required

None. All four success criteria are verified by the recorded hardware run in `02-WINDOWS-VERIFICATION.md`. The operator confirmed SC#1-4 on 2026-06-01. SC#4 carries an accepted caveat (~19s first-paint due to HTTPS latency, matching macOS daemon parity). No automated or human verification items remain open.

---

### Gaps Summary

No gaps. All eleven must-haves are verified in code. All three requirements (BLE-01, BLE-02, POLL-01) are satisfied by implementation and recorded hardware evidence. The phase goal — a working BLE scan/connect/write + Anthropic API polling pipeline on native Windows — is achieved.

---

_Verified: 2026-06-01_
_Verifier: Claude (gsd-verifier)_
