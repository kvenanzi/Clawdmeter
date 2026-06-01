# Phase 2: Core Pipeline - Context

**Gathered:** 2026-06-01
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase makes the Windows daemon work **end-to-end** for the first time: scan +
connect to the Clawdmeter over native Windows (WinRT) BLE, poll the Anthropic API
for rate-limit headers, shape the usage payload, and write it to the GATT RX
characteristic so the device leaves its "waiting for data" bluetooth screen and
shows live session + weekly percentages.

Satisfies **BLE-01** (discover + connect via WinRT), **BLE-02** (write usage JSON to
the existing GATT data service unchanged), and **POLL-01** (poll the API, derive
session + weekly utilization, mirroring the macOS daemon).

**Explicitly NOT in this phase:**
- Auto-reconnect hardening for sleep/wake, out-of-range, and device power-cycle —
  incl. the WinRT stale-`is_connected` / `Unreachable` retry wrapper around
  `connect()` (**Phase 3**, BLE-03).
- MAC-address cache (`%APPDATA%\claude-usage-monitor\ble-address`) — **Phase 3**.
- System-tray icon, login autostart, polished install script, packaged exe —
  **Phase 4** / v2 (APP-01, APP-02, PKG-01).

**Hard constraint (locked):** Phase 2 is **strictly additive**. It adds ONE new file
(`daemon/claude_usage_daemon_windows.py`, already scaffolded in Phase 1) plus Windows
docs/deps. It makes **zero edits** to `daemon/claude_usage_daemon.py` (macOS),
`daemon/claude-usage-daemon.sh` (Linux), or any firmware. The macOS daemon is a
**read-only reference to copy from**, never an import target and never modified. This
mirrors the locked PROJECT.md out-of-scope boundary ("Windows ships as its own daemon
mirroring the macOS one") and keeps the eventual upstream PR maximally reviewable —
Windows support is purely additive.

</domain>

<decisions>
## Implementation Decisions

### Run loop & reconnect depth (Phase 2 / Phase 3 boundary)
- **D-01:** Phase 2 mirrors the macOS `main()` run-loop: scan-by-name → connect →
  poll/write every 60s while connected → on disconnect, loop back and re-scan with
  simple exponential backoff (1s → max 60s, like macOS). This makes "end-to-end"
  demonstrable and stable over time, not a one-shot proof.
- **D-02:** The **WinRT-specific** retry handling for post-sleep `Unreachable` / stale
  `is_connected` (BLE research point #4) is **deferred to Phase 3**, where it can be
  tested against real sleep/wake. Phase 2's connect path stays clean: a single
  `connect()` attempt; failure just falls through to the re-scan/backoff loop. Phase 3
  layers sleep/range/power-cycle hardening on top of this loop — it should not need to
  rewrite the loop, only wrap `connect()`.
- **D-03:** Poll immediately on first connect (initialize `last_poll = 0.0` as macOS
  does) so the first payload is sent without waiting a full 60s tick — this is part of
  hitting Success Criterion #4 (<10s poll-to-display first paint).

### Address discovery & state
- **D-04:** **Scan-every-cycle, no disk cache** in Phase 2. Use `BleakScanner`
  scan-by-name (`"Claude Controller"`) on each connect cycle; pass the scanned
  `BLEDevice` to `BleakClient`. Windows lacks the macOS HID-invisibility problem that
  forced address caching, so the cache buys little here and adds disk state +
  invalidation logic. The `%APPDATA%\claude-usage-monitor\ble-address` cache is a
  **Phase 3** reconnect optimization if it proves worth it. → keeps Phase 2 stateless.

### WinRT connect recipe (locked by prior research — carry forward, don't re-derive)
- **D-05:** Connect using: scan-first → pass `BLEDevice` to `BleakClient`,
  `address_type="random"` (ESP32/NimBLE static-random address), and
  `use_cached_services=False` (DIY firmware — WinRT caches the GATT table across
  firmware changes). No manual Bluetooth pairing — GATT data service is unencrypted
  (Phase 1 D-01). Source: `.planning/notes/windows-daemon-port.md` §"BLE research findings".

### Device-initiated refresh (REQ characteristic)
- **D-06:** **Include** the REQ refresh subscription in Phase 2 (full macOS parity,
  ~6 lines): `start_notify(REQ_CHAR_UUID, cb)` → set an `asyncio.Event` → poll
  immediately when the device fires `0x01`. The firmware fires REQ the moment it
  connects with no data, so this both completes the end-to-end pipeline and reinforces
  the <10s first-paint criterion. Mirror macOS `Session.setup_refresh_subscription`.

### Wire protocol & polling logic (copy verbatim from macOS reference)
- **D-07:** Copy the API-polling logic from `daemon/claude_usage_daemon.py` into the
  Windows file: same endpoint (`POST https://api.anthropic.com/v1/messages`), same
  headers (`anthropic-version`, `anthropic-beta: oauth-2025-04-20`, `User-Agent:
  claude-code/2.1.5`), same probe body, and the same header→payload mapping
  (`anthropic-ratelimit-unified-{5h,7d}-{utilization,reset,status}` →
  `{"s","sr","w","wr","st","ok"}`), via `httpx.AsyncClient`. The firmware expects this
  exact JSON byte-for-byte — copying guarantees protocol parity with no firmware change.
- **D-08:** Write the payload with `client.write_gatt_char(RX_CHAR_UUID, data,
  response=False)` exactly as macOS does. **Do NOT** subscribe to or read the TX
  characteristic (`...0003`) ack/nack in Phase 2 — the macOS daemon doesn't, and
  SC#3 only requires the firmware parse the write without nack (verified by the device
  leaving its waiting screen), not that the daemon reads the ack. Parity = no TX read.
- **D-09:** Read the token **fresh each poll cycle** via the existing Phase 1
  `read_token()` (macOS parity — token is re-read every 60s, not cached in memory).
  On a missing/expired token the cycle logs and skips, same as macOS; the daemon does
  not refresh OAuth itself (that's Claude Code's job).

### Test strategy
- **D-10:** **Unit-test the hardware-free logic, manually verify BLE.** Pytest covers
  the deterministic pure logic with `httpx` mocked: the ratelimit-header → payload
  mapping, the `pct()` (util×100, round) and `reset_minutes()` (epoch→minutes-from-now)
  math, and the compact JSON serialization shape. BLE scan/connect/write (SC#1–3) and
  the <10s latency (SC#4) are **verified manually on Windows hardware and recorded**,
  the same way Phase 1 closed its native-Windows criterion. No mocked-`bleak`
  integration tests (brittle, false confidence, don't exercise real WinRT).

### Dependency setup
- **D-11:** Add a Windows-specific **`daemon/requirements-windows.txt`** listing
  `bleak` and `httpx` (Phase 2 is the first non-stdlib Windows code; Phase 1 was
  stdlib-only). Document the manual `python -m venv` + `pip install -r` steps in the
  daemon docs. A polished `install-windows.ps1` / packaged exe is **not** in Phase 2 —
  that overlaps Phase 4 autostart UX and v2 packaging (PKG-01). A Windows-specific
  requirements file (not a shared one) preserves the strictly-additive, self-contained
  constraint.

### Claude's Discretion
- Exact module organization within `claude_usage_daemon_windows.py` (function vs class
  split, where the loop lives) — follow the macOS structure as the planner sees fit, as
  long as D-01..D-11 hold and no shared/macOS files are touched.
- Backoff constants and scan timeout may match macOS (`SCAN_TIMEOUT=8.0`,
  `POLL_INTERVAL=60`, `TICK=5`) unless research suggests WinRT-specific tuning.
- Console logging format — reuse the macOS `log()` `[HH:MM:SS]` stdout style.

### Folded Todos
- **`implement-windows-daemon-tray.md`** (medium) — its **BLE + polling slices (scope
  items 1–3: port the core loop, WinRT-friendly BLE connect, native token read)** are
  in Phase 2 scope and captured in D-01..D-11. Its MAC-cache (item 4) is Phase 3; tray
  (item 5), autostart (item 6), and packaging (item 7) remain deferred (see Deferred
  Ideas). Token read (item 3) already shipped in Phase 1.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project intent & scope (locked decisions — do not re-litigate)
- `.planning/PROJECT.md` — Windows-daemon-port intent; the **strictly-additive /
  "ship its own daemon, don't refactor into a shared codebase"** out-of-scope boundary
  this phase must honor.
- `.planning/REQUIREMENTS.md` — **BLE-01, BLE-02, POLL-01** are the requirements this
  phase satisfies.
- `.planning/phases/01-foundation/01-CONTEXT.md` — Phase 1 decisions still in force:
  D-01 (GATT unencrypted, no pairing), D-08 (separate Windows file, **copy don't
  import** macOS), the `read_token()` candidate-path strategy.

### BLE approach (research — the locked WinRT recipe)
- `.planning/notes/windows-daemon-port.md` — §"BLE research findings" (scan-first →
  `BLEDevice`, `address_type="random"`, `use_cached_services=False`, HID-share note,
  post-sleep retry note) and §"GATT encryption gate — verdict" (unencrypted, no pairing).

### The daemon to mirror (macOS — READ-ONLY reference, never edit)
- `daemon/claude_usage_daemon.py` — the source to **copy** the polling + BLE-write +
  run-loop logic from:
  - §274–314 `poll_api()` — API call + header→`{s,sr,w,wr,st,ok}` payload mapping,
    `pct()` / `reset_minutes()`.
  - §317–341 `Session` — `setup_refresh_subscription()` (REQ, D-06) and
    `write_payload()` (RX write, D-08).
  - §343–397 `connect_and_run()` — connect → poll-immediately (`last_poll=0.0`) →
    60s loop → disconnect.
  - §400–449 `main()` — scan/connect/backoff outer loop (D-01); **strip** the macOS
    CoreBluetooth `retrieve_connected_macos` / `discover_target` HID path and the
    address-cache branch (not needed on Windows — D-04).
- `daemon/claude_usage_daemon_windows.py` — the Phase 1 scaffold being extended
  (currently `read_token()` + `_extract_access_token()` + `__main__`).

### Wire protocol contract (firmware — read-only, must match byte-for-byte)
- `.planning/codebase/INTEGRATIONS.md` — §"Anthropic API" (exact headers consumed) and
  §"Custom GATT data service" (RX `...0002` WRITE, TX `...0003` NOTIFY ack/nack, REQ
  `...0004` NOTIFY `0x01`). Service UUID `4c41555a-...0001`.
- `firmware/src/ble.cpp` — characteristic definitions (read-only; not modified).

### Folded todo
- `.planning/todos/pending/implement-windows-daemon-tray.md` — items 1–3 are this phase.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `daemon/claude_usage_daemon_windows.py::read_token()` / `_extract_access_token()` —
  shipped in Phase 1; the daemon loop calls `read_token()` fresh each cycle (D-09).
- `daemon/claude_usage_daemon.py` (macOS) — copy-from source for `poll_api`, `Session`
  (REQ subscribe + RX write), `connect_and_run`, and the `main()` scan/backoff loop.
  The platform-portable parts (`httpx` polling, `bleak` write/notify) port nearly
  verbatim; only the macOS CoreBluetooth HID-recovery path and address cache are dropped.

### Established Patterns
- Daemon structure: module-level constants (UUIDs, intervals) → `log()` `[HH:MM:SS]`
  stdout → `asyncio` run-loop with `stop_event` signal handling. Mirror this.
- Payload is compact JSON (`json.dumps(..., separators=(",",":"))`) written with
  `response=False`. Poll-immediately-on-connect via `last_poll = 0.0`.
- Resilience idiom (macOS/Linux): connect → use → on failure re-scan with backoff.
  Phase 2 adopts the basic form; the cache + WinRT stale-connection hardening is Phase 3.

### Integration Points
- All new code lands in `daemon/claude_usage_daemon_windows.py` (standalone). New file
  `daemon/requirements-windows.txt` (bleak, httpx). Optional Windows section in daemon
  docs. **No** edits to existing daemon/firmware files.

</code_context>

<specifics>
## Specific Ideas

- Constants to reuse from macOS: `DEVICE_NAME="Claude Controller"`, `SERVICE_UUID
  4c41555a-...0001`, `RX_CHAR_UUID ...0002`, `REQ_CHAR_UUID ...0004`, `POLL_INTERVAL=60`,
  `TICK=5`, `SCAN_TIMEOUT=8.0`.
- Payload contract (must match firmware): `{"s":<5h util %>, "sr":<5h reset mins>,
  "w":<7d util %>, "wr":<7d reset mins>, "st":<5h status str>, "ok":true}`.
- Manual Windows verification record should mirror Phase 1's native-Windows test note
  (capture: device left waiting screen, percentages shown, observed first-paint latency).

</specifics>

<deferred>
## Deferred Ideas

- **WinRT stale-connection / `Unreachable` retry wrapper** around `connect()` for
  post-sleep/wake recovery → **Phase 3** (BLE-03).
- **MAC-address cache** (`%APPDATA%\claude-usage-monitor\ble-address`, load/save/
  drop-on-failure) → **Phase 3**.
- **Out-of-range and device-power-cycle reconnect verification** → **Phase 3**.
- **System-tray icon** (`pystray` + `Pillow`) + **login autostart** (`shell:startup`
  `.lnk` / Run-key, `pythonw`) + **polished `install-windows.ps1`** → **Phase 4**.
- **PyInstaller one-file exe packaging** → v2 (PKG-01).
- **Windows Credential Manager fallback** for the token → v2 / only if the native token
  turns out to live in the vault.

### Reviewed Todos (not folded)
- **`verify-gatt-characteristics-unencrypted.md`** — matched by keyword but **already
  resolved in Phase 1** (D-01: characteristics are unencrypted, no pairing). Nothing to
  do here; carried as a settled fact.

</deferred>

---

*Phase: 2-Core Pipeline*
*Context gathered: 2026-06-01*
