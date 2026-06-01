# Phase 1: Foundation - Context

**Gathered:** 2026-06-01
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase delivers two things and nothing more:

1. **Close the GATT-encryption gate.** Confirm in `firmware/src/ble.cpp` whether the
   custom data-service characteristics (RX/TX/REQ) require encryption/bonding, and
   record the verdict in `.planning/notes/windows-daemon-port.md`.
2. **Bootstrap a Windows-local token reader.** A minimal
   `daemon/claude_usage_daemon_windows.py` skeleton whose `read_token()` reads the
   Claude OAuth token from a native-Windows credentials path (never a WSL path) and
   whose `__main__` prints a recognizable credential field.

**Explicitly NOT in this phase:** BLE scan/connect/write (Phase 2), Anthropic API
polling (Phase 2), reconnect resilience (Phase 3), tray icon / autostart (Phase 4),
the MAC-address cache. This is the de-risk + bootstrap slice only.

</domain>

<decisions>
## Implementation Decisions

### GATT-encryption gate (resolved during this discussion)
- **D-01:** The gate is **already answered: UNENCRYPTED.** Scout of `firmware/src/ble.cpp`
  (lines 185–199) shows the characteristics are created with plain NimBLE flags —
  RX = `WRITE | WRITE_NR`, TX = `READ | NOTIFY`, REQ = `NOTIFY` — with **no
  `_ENC` / `_AUTHEN` / `_AUTHOR` variants.** Consequence: the Windows daemon needs
  **no manual Bluetooth pairing** and **no firmware change.** Phase 1 work is just to
  record this verdict in `.planning/notes/windows-daemon-port.md` (Success Criterion #1).
  The "what if it's encrypted?" contingency is therefore dead — do not plan a pairing step.

### Token location strategy
- **D-02:** `read_token()` **searches candidate paths in priority order**, first hit wins:
  1. `%USERPROFILE%\.claude\.credentials.json` (most likely native location)
  2. `%LOCALAPPDATA%\Claude\.credentials.json`
  3. `%APPDATA%\Claude\.credentials.json`
- **D-03:** Honor a **`CLAUDE_CREDENTIALS_PATH` environment override** that, when set,
  takes precedence over the candidate search.
- **D-04:** Do **not** add a Windows Credential Manager / keyring fallback in Phase 1.
  (The macOS daemon uses Keychain; Windows Claude Code is expected to use a plain file.
  Researcher confirms the actual native path — if it turns out to live in the vault,
  that's a follow-up, not a Phase 1 assumption.)

### Scaffold scope
- **D-05:** **Minimal scaffold.** Phase 1 ships only: `_extract_access_token()`,
  `read_token()`, and a `__main__` that reads and prints. **No** config-dir helper,
  logging framework, or main-loop placeholder — Phase 2 introduces the daemon structure.

### Output & failure UX
- **D-06:** On success, print a **redacted confirmation plus expiry**, e.g.
  `Token OK (sk-ant-…<last4>), expires <date>`. **Never echo the full access token**
  to the terminal/scrollback (it leaks into shell history).
- **D-07:** On failure (no token found / wrong path / Claude Code not installed natively),
  print an **actionable message**, e.g. `No Windows token found — install Claude Code
  natively on Windows and run 'claude login'.` Exit non-zero.

### macOS code parity
- **D-08:** Create a **separate `daemon/claude_usage_daemon_windows.py`** and **copy**
  `_extract_access_token()` from the macOS daemon into it (handles the direct,
  nested `claudeAiOauth.accessToken`, regex, and raw-token forms). Do **not** `import`
  from `claude_usage_daemon.py` — importing the macOS module on Windows runs its
  top-level Keychain/path code and is fragile. Mirrors the locked "ship its own daemon,
  don't refactor into a shared codebase" decision.

### Folded Todos
- **`verify-gatt-characteristics-unencrypted.md`** (HIGH) — the de-risk gate for this
  phase. Resolved during discussion (see D-01): characteristics are unencrypted, no
  pairing needed. Phase 1 records the verdict in the windows-daemon-port note.
- **`implement-windows-daemon-tray.md`** (medium) — folded for visibility, but only its
  **token-reading slice** (item 3: "read the native-Windows Claude OAuth credentials
  path") is in Phase 1 scope. Its BLE (item 1–2, 4), tray (item 5), autostart (item 6),
  and packaging (item 7) items belong to Phases 2–4 and are tracked in Deferred Ideas.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project intent & scope
- `.planning/PROJECT.md` — overall Windows-daemon-port intent, locked Key Decisions,
  out-of-scope boundaries.
- `.planning/REQUIREMENTS.md` — **TOKEN-01** is the requirement this phase satisfies.
- `.planning/notes/windows-daemon-port.md` — exploration findings; **the GATT-gate
  verdict (D-01) must be written back here** to satisfy Success Criterion #1.

### The GATT gate (firmware)
- `firmware/src/ble.cpp` §185–199 — RX/TX/REQ characteristic creation; the plain
  NimBLE flags that prove the data service is unencrypted. UUIDs at §10–12.

### The daemon to mirror (macOS)
- `daemon/claude_usage_daemon.py` §57–127 — `_extract_access_token()`, the
  Keychain/file `read_token()` structure, and the credential-blob shapes to support.
  This is the source of the helper to copy (D-08) and the parity reference.

### Folded todos
- `.planning/todos/pending/verify-gatt-characteristics-unencrypted.md`
- `.planning/todos/pending/implement-windows-daemon-tray.md`

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `daemon/claude_usage_daemon.py::_extract_access_token()` (§57–87) — **copy verbatim**
  into the Windows file. Handles `{"accessToken": …}`, nested
  `{"claudeAiOauth": {"accessToken": …}}`, a regex fallback, and a raw-token form.
- `daemon/claude_usage_daemon.py::read_token()` (§124–127) — pattern reference: macOS
  branches Keychain-vs-file by platform. The Windows version is **file-search only**
  (D-02/D-04), so it is simpler than the macOS one.

### Established Patterns
- macOS/Linux daemons resolve credentials from a home-relative `.claude/.credentials.json`
  file (Linux) or Keychain (macOS). Windows mirrors the **file** approach against
  Windows-local env paths — never `\\wsl$` / `wsl.exe`.
- Existing config/cache convention is `~/.config/claude-usage-monitor/` on *nix. The
  Windows equivalent (`%APPDATA%\claude-usage-monitor\`) is **deferred** — not needed
  for Phase 1's minimal scaffold.

### Integration Points
- New file `daemon/claude_usage_daemon_windows.py` — standalone, sits beside the
  existing macOS/Linux daemons; no edits to existing daemon files in this phase.

</code_context>

<specifics>
## Specific Ideas

- Redacted success line format: `Token OK (sk-ant-…<last4>), expires <date>` (D-06).
- Env override variable name: `CLAUDE_CREDENTIALS_PATH` (D-03).
- Candidate path priority order is explicit (D-02) — researcher confirms which is the
  real native location and may reorder, but all three should be probed.

</specifics>

<deferred>
## Deferred Ideas

- **BLE scan/connect/write** (`bleak` WinRT, `address_type="random"`,
  `use_cached_services=False`, pass scanned `BLEDevice`) → Phase 2.
- **Anthropic API polling** (`httpx`, session + weekly utilization) → Phase 2.
- **MAC-address cache** at `%APPDATA%\claude-usage-monitor\ble-address`, mirroring the
  macOS connect-by-name → cache → drop-on-failure resilience → Phase 2/3.
- **Auto-reconnect** after sleep / out-of-range / device drop (retry loop, stale
  `is_connected`) → Phase 3.
- **System-tray icon** (`pystray` + `Pillow`) + **login autostart** (`shell:startup`
  `.lnk` / Run-key, `pythonw`/packaged exe) → Phase 4.
- **Packaging** (`pyinstaller` one-file exe) and **Windows Credential Manager fallback**
  → v2 / follow-up (PKG-01, and only if the native token turns out to live in the vault).

### Reviewed Todos (not folded)
None — both matched todos were folded (see Folded Todos above), with their
out-of-phase scope tracked in Deferred Ideas.

</deferred>

---

*Phase: 1-Foundation*
*Context gathered: 2026-06-01*
