# Phase 1: Foundation - Research

**Researched:** 2026-06-01
**Domain:** Windows OAuth credential file location + GATT encryption verification
**Confidence:** HIGH

## Summary

Phase 1 is a tightly-scoped de-risk + bootstrap slice. It has two deliverables: (1) record the GATT-encryption verdict (already answered by reading `firmware/src/ble.cpp`) into the exploration note, and (2) create a minimal Python scaffold `daemon/claude_usage_daemon_windows.py` whose `read_token()` reads the Claude OAuth token from the correct Windows-local path.

The single meaningful open question was WHERE native-Windows Claude Code writes its credential file. The official Claude Code documentation (code.claude.com/docs/en/authentication, confirmed 2026-06-01) states unambiguously: `%USERPROFILE%\.claude\.credentials.json`. This is the primary candidate in D-02. The JSON structure on disk follows the nested form `{"claudeAiOauth": {"accessToken": "sk-ant-oat01-…", "refreshToken": "sk-ant-ort01-…", "expiresAt": <epoch_ms>, "scopes": […]}}`, which `_extract_access_token()` already handles via its nested-dict branch — copy verbatim per D-08 is fully sufficient.

The GATT verdict is confirmed: `firmware/src/ble.cpp` lines 185–199 create the custom data service characteristics with plain `NIMBLE_PROPERTY::WRITE | WRITE_NR` (RX), `READ | NOTIFY` (TX), and `NOTIFY` (REQ) — no `_ENC`, `_AUTHEN`, or `_AUTHOR` variants. The NimBLE library does have these encrypted variants (visible in `NimBLEHIDDevice.cpp`), but they are not applied to the custom service. No pairing step is needed.

**Primary recommendation:** Use `Path.home() / ".claude" / ".credentials.json"` as the primary path (resolves correctly on native Windows via Python's `pathlib`), with `CLAUDE_CONFIG_DIR` env-var override checked first (per official docs), then the `CLAUDE_CREDENTIALS_PATH` project-specific override (D-03), then the full three-candidate fallback search (D-02).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** GATT gate = UNENCRYPTED. RX=`WRITE|WRITE_NR`, TX=`READ|NOTIFY`, REQ=`NOTIFY`. No pairing needed. Dead contingency — do not plan a pairing step.
- **D-02:** `read_token()` searches candidate paths in priority order, first hit wins: (1) `%USERPROFILE%\.claude\.credentials.json`, (2) `%LOCALAPPDATA%\Claude\.credentials.json`, (3) `%APPDATA%\Claude\.credentials.json`.
- **D-03:** Honor `CLAUDE_CREDENTIALS_PATH` environment override that, when set, takes precedence over the candidate search.
- **D-04:** Do NOT add a Windows Credential Manager / keyring fallback in Phase 1 (file-search only).
- **D-05:** Minimal scaffold only: `_extract_access_token()`, `read_token()`, and a `__main__`. No config-dir helper, logging framework, or main-loop.
- **D-06:** On success, print redacted confirmation + expiry: `Token OK (sk-ant-…<last4>), expires <date>`. Never echo the full token.
- **D-07:** On failure, print an actionable message and exit non-zero.
- **D-08:** Create `daemon/claude_usage_daemon_windows.py` and COPY `_extract_access_token()` from the macOS daemon — do NOT import from `claude_usage_daemon.py`.

### Claude's Discretion
- Candidate path probing order may be refined based on confirmed native location — research confirms `%USERPROFILE%\.claude\.credentials.json` is primary (matches D-02 priority 1).
- Whether to also check `CLAUDE_CONFIG_DIR` env var (official override) before the D-03 override or as an additional candidate.

### Deferred Ideas (OUT OF SCOPE)
- BLE scan/connect/write (`bleak` WinRT, `address_type="random"`, `use_cached_services=False`) — Phase 2.
- Anthropic API polling (`httpx`, session + weekly utilization) — Phase 2.
- MAC-address cache at `%APPDATA%\claude-usage-monitor\ble-address` — Phase 2/3.
- Auto-reconnect after sleep / out-of-range / device drop — Phase 3.
- System-tray icon (`pystray` + `Pillow`) + login autostart — Phase 4.
- Packaging (`pyinstaller` one-file exe) and Windows Credential Manager fallback — v2.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TOKEN-01 | Daemon reads the Claude OAuth token from a native-Windows credentials path (no WSL/`\\wsl$` access) | Official docs confirm `%USERPROFILE%\.claude\.credentials.json`; `Path.home()` resolves correctly on native Windows Python; `_extract_access_token()` verbatim copy handles the nested `claudeAiOauth` JSON shape on disk. |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| OAuth credential file read | Daemon / host process | — | Token lives on the Windows filesystem; read at daemon startup and on 401. |
| GATT service encryption audit | Firmware verification (read-only) | — | Flags are baked into firmware at compile time; Phase 1 only reads and records them. |
| Token extraction / parsing | Daemon / host process | — | `_extract_access_token()` is a pure Python function; no network or OS call. |
| Redacted output / failure UX | Daemon `__main__` | — | Terminal output only; no logging framework in Phase 1. |

## Standard Stack

### Core

Phase 1 is **stdlib-only**. No third-party packages are installed.

| Module | Version | Purpose | Why Standard |
|--------|---------|---------|--------------|
| `os` | stdlib | Resolve `%USERPROFILE%`, `%LOCALAPPDATA%`, `%APPDATA%`, read env overrides | Cross-platform; `os.environ.get()` is the correct approach on Windows |
| `pathlib.Path` | stdlib | Construct and test credential paths; `Path.home()` resolves to `C:\Users\<user>` on native Windows | Official Python recommendation for filesystem paths |
| `json` | stdlib | Parse `.credentials.json` contents | |
| `re` | stdlib | Regex fallback in `_extract_access_token()` | Already used in macOS daemon copy-source |
| `sys` | stdlib | `sys.exit(1)` on failure, `sys.platform` guard if needed | |
| `datetime` | stdlib | Convert `expiresAt` (epoch milliseconds) to human-readable date for D-06 output | |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `pathlib.Path.home()` | `os.path.expandvars('%USERPROFILE%')` | `expandvars` works on Windows but returns the literal string `%USERPROFILE%` on Linux/WSL — makes the file un-runnable during development. `Path.home()` is always correct on both. |
| `Path.home() / ".claude" / ".credentials.json"` | Hardcoded string path | Hardcoded paths break for non-default usernames and drive letters. |

**Installation:** None required for Phase 1.

## Package Legitimacy Audit

Phase 1 installs no external packages. The scaffold is pure Python stdlib.

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
Windows filesystem
  %USERPROFILE%\.claude\.credentials.json   <── primary path (D-02 #1)
  %LOCALAPPDATA%\Claude\.credentials.json   <── fallback #2
  %APPDATA%\Claude\.credentials.json        <── fallback #3

Environment overrides (checked before filesystem):
  CLAUDE_CONFIG_DIR (official Claude override)
  CLAUDE_CREDENTIALS_PATH (project override, D-03)

                         ┌─────────────────────────────┐
 candidate paths ──────> │     read_token()             │
                         │  first-hit-wins loop         │
                         │  OSError → try next          │
                         └──────────┬──────────────────┘
                                    │ raw blob string
                                    v
                         ┌─────────────────────────────┐
                         │  _extract_access_token()    │ <── copied verbatim from macOS daemon
                         │  1. JSON parse              │
                         │  2. direct accessToken key  │
                         │  3. nested claudeAiOauth    │  <── THIS is the real on-disk shape
                         │  4. regex fallback          │
                         │  5. raw token form          │
                         └──────────┬──────────────────┘
                                    │ token string or None
                                    v
                         ┌─────────────────────────────┐
                         │       __main__               │
                         │  success: redacted + expiry  │
                         │  failure: actionable msg +   │
                         │           sys.exit(1)        │
                         └─────────────────────────────┘
```

### Recommended Project Structure

```
daemon/
├── claude_usage_daemon.py           # macOS daemon (unchanged)
├── claude-usage-daemon.sh           # Linux daemon (unchanged)
├── claude_usage_daemon_windows.py   # NEW: Windows scaffold (Phase 1)
├── test_macos_connect.py            # existing macOS test
└── ...
```

### Pattern 1: Windows credential path resolution

**What:** Resolve Windows-local credential file path using Python stdlib only, never touching WSL paths.

**When to use:** All path construction in the Windows daemon scaffold.

```python
# Source: official Claude Code docs (code.claude.com/docs/en/authentication)
# and Python stdlib pathlib documentation

import os
from pathlib import Path

def _windows_credential_candidates() -> list[Path]:
    # 1. Project-specific env override (D-03)
    if override := os.environ.get("CLAUDE_CREDENTIALS_PATH"):
        return [Path(override)]

    # 2. Official CLAUDE_CONFIG_DIR env override (per official Claude docs)
    if config_dir := os.environ.get("CLAUDE_CONFIG_DIR"):
        return [Path(config_dir) / ".credentials.json"]

    # 3. D-02 candidate priority list — first hit wins
    home = Path.home()  # C:\Users\<user> on native Windows Python
    local_appdata = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
    appdata = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
    return [
        home / ".claude" / ".credentials.json",        # primary (confirmed)
        local_appdata / "Claude" / ".credentials.json", # fallback 2
        appdata / "Claude" / ".credentials.json",       # fallback 3
    ]
```

**Key insight:** `Path.home()` on native Windows Python resolves to `C:\Users\<user>`, NOT a WSL path. Never use `os.path.expandvars('%USERPROFILE%')` — it returns the literal string on Linux/WSL, making the module awkward to test. [CITED: docs.python.org/3/library/pathlib.html]

### Pattern 2: expiresAt millisecond timestamp decoding

**What:** Convert the `expiresAt` field (Unix epoch in milliseconds) to a human-readable date for D-06 output.

```python
# Source: Python stdlib datetime documentation
import datetime

def _format_expiry(credentials_dict: dict) -> str:
    """Return human-readable expiry from claudeAiOauth.expiresAt (ms epoch)."""
    try:
        oauth = credentials_dict.get("claudeAiOauth", {})
        expires_ms = oauth.get("expiresAt")
        if expires_ms is None:
            return "expiry unknown"
        dt = datetime.datetime.fromtimestamp(expires_ms / 1000, tz=datetime.timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except (TypeError, ValueError, OSError):
        return "expiry unknown"
```

Note: `_extract_access_token()` (copied verbatim from macOS daemon) returns only the token string. Expiry display requires a separate pass over the raw parsed JSON. The `__main__` should parse the blob once, call `_extract_access_token()` for the token, and extract expiry separately.

### Pattern 3: Redacted token output (D-06)

```python
# Never print the full token — only last 4 characters
def _redact(token: str) -> str:
    return f"sk-ant-…{token[-4:]}"

# Success output:
print(f"Token OK ({_redact(token)}), expires {expiry}")

# Failure output (D-07):
print("No Windows token found — install Claude Code natively on Windows and run 'claude login'.")
sys.exit(1)
```

### Anti-Patterns to Avoid

- **`os.path.expandvars('%USERPROFILE%')`:** Returns the literal string `%USERPROFILE%` on Linux/WSL. Use `Path.home()` instead.
- **Importing from `claude_usage_daemon.py`:** That module runs top-level macOS Keychain and path code on import. It will fail or behave incorrectly on Windows. Copy `_extract_access_token()` verbatim per D-08.
- **`\\wsl$` or `wsl.exe` paths:** Explicitly forbidden per TOKEN-01 and REQUIREMENTS.md. Not applicable in Phase 1 since we're using `Path.home()` which always resolves to the native Windows home.
- **Printing the full token:** Leaks into shell history / scrollback. Always redact (D-06).
- **`sys.platform == "darwin"` guard from macOS daemon's `read_token()`:** The Windows `read_token()` is file-search-only per D-04 — no platform branch needed.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON credential parsing | Custom parser | `json.loads()` + `_extract_access_token()` verbatim copy | The macOS function already handles all four credential shapes including the real `claudeAiOauth` nested form |
| Epoch millisecond decoding | Custom arithmetic | `datetime.datetime.fromtimestamp(ms/1000, tz=...)` | stdlib; handles DST, timezone, overflow correctly |
| Path resolution | String formatting with hardcoded `C:\Users\` | `pathlib.Path.home()` + `os.environ.get()` | Portable; handles non-default drive letters and locale usernames |

**Key insight:** `_extract_access_token()` in the macOS daemon was written to handle multiple credential blob shapes precisely because Claude Code's format has evolved. Copying it verbatim means the Windows daemon inherits that robustness for free.

## GATT Encryption Verdict (D-01)

**Status: CONFIRMED UNENCRYPTED** [VERIFIED: firmware/src/ble.cpp]

Direct inspection of `firmware/src/ble.cpp` lines 185–199 (read during this session):

```cpp
// Lines 185-200 — custom data service, NO encryption flags
rx_char = svc->createCharacteristic(
    RX_CHAR_UUID,
    NIMBLE_PROPERTY::WRITE | NIMBLE_PROPERTY::WRITE_NR   // plain write only
);
tx_char = svc->createCharacteristic(
    TX_CHAR_UUID,
    NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::NOTIFY      // plain read/notify
);
req_char = svc->createCharacteristic(
    REQ_CHAR_UUID,
    NIMBLE_PROPERTY::NOTIFY                              // plain notify only
);
```

The NimBLE library DOES have `NIMBLE_PROPERTY::READ_ENC`, `WRITE_ENC`, `READ_AUTHEN`, `WRITE_AUTHEN`, `READ_AUTHOR`, `WRITE_AUTHOR` variants (confirmed in `NimBLEHIDDevice.cpp` and `NimBLEDescriptor.cpp`). None are present in the custom data service. The HID keyboard characteristics DO use `READ_ENC | WRITE_ENC` (as required for HID over BLE), but those are separate from the `4c41555a-…` service.

**Consequence:** The Windows daemon needs no manual Bluetooth pairing and no firmware change.

**Action:** Write this verdict to `.planning/notes/windows-daemon-port.md` (Success Criterion #1).

## Windows Credential File — Confirmed Location

**Primary path:** `%USERPROFILE%\.claude\.credentials.json` [CITED: code.claude.com/docs/en/authentication]

The official documentation states: *"On Windows, credentials are stored in `%USERPROFILE%\.claude\.credentials.json` and inherit the access controls of your user profile directory, which restricts the file to your user account by default."*

Also documented: *"If you've set the `CLAUDE_CONFIG_DIR` environment variable on Linux or Windows, the `.credentials.json` file lives under that directory instead."*

**On-disk JSON structure** [CITED: claude-code-sandbox lift-and-shift docs + web search cross-verification]:

```json
{
  "claudeAiOauth": {
    "accessToken": "sk-ant-oat01-…",
    "refreshToken": "sk-ant-ort01-…",
    "expiresAt": 1748276587173,
    "scopes": ["user:inference", "user:profile"]
  }
}
```

This is the **nested** form. `_extract_access_token()` handles it via the `for v in data.values()` branch (line 77–79 in macOS daemon). The `expiresAt` is epoch milliseconds (divide by 1000 for `datetime.fromtimestamp`).

**Alternative paths from D-02:** The `%LOCALAPPDATA%\Claude\` and `%APPDATA%\Claude\` candidates are plausible secondary locations if Anthropic changes the install layout, but the primary `%USERPROFILE%\.claude\` is the confirmed current location. All three should still be probed per D-02.

**`CLAUDE_CONFIG_DIR` consideration:** The official docs describe this as the authoritative override. The planner should decide whether to check it before or alongside `CLAUDE_CREDENTIALS_PATH` (D-03). Suggested priority: `CLAUDE_CREDENTIALS_PATH` → `CLAUDE_CONFIG_DIR` → D-02 candidates.

## Common Pitfalls

### Pitfall 1: `Path.home()` in WSL vs. native Windows Python

**What goes wrong:** If the script is run under WSL Python (not native Windows Python), `Path.home()` returns `/home/<user>`, not `C:\Users\<user>`. The credential file never exists at that path — silent `None` return from `read_token()`, confusing failure.

**Why it happens:** Users sometimes have Python in their PATH from WSL even when they mean to run it on Windows.

**How to avoid:** The `__main__` block should add a platform check: `if sys.platform != "win32": print("Warning: running under Linux/WSL — Windows credential paths will not resolve correctly.")` Alternatively, let the failure message (D-07) make this clear.

**Warning signs:** `read_token()` returns `None` when Claude Code is installed natively on Windows.

### Pitfall 2: `expiresAt` is milliseconds, not seconds

**What goes wrong:** `datetime.datetime.fromtimestamp(expires_at)` with the raw millisecond value produces a date far in the future (~year 57000). Easy to overlook in testing.

**Why it happens:** JavaScript Date.now() convention (used by Claude Code's Node.js internals) is milliseconds. Python's `fromtimestamp` expects seconds.

**How to avoid:** Always divide by 1000: `datetime.datetime.fromtimestamp(expires_ms / 1000, tz=datetime.timezone.utc)`.

**Warning signs:** Expiry date shows year 57000+ or throws `OverflowError`.

### Pitfall 3: JSON blob may be read-locked during active Claude Code session

**What goes wrong:** On Windows, Claude Code may hold `.credentials.json` open with an exclusive write lock. `Path.read_text()` raises `PermissionError` rather than `OSError`.

**Why it happens:** Windows file locking semantics differ from POSIX. Node.js may briefly hold the file open when refreshing the token.

**How to avoid:** Catch both `OSError` and `PermissionError` (the latter is a subclass of `OSError` in Python 3, so `except OSError` covers both). The failure path can retry once after a short sleep in Phase 2; for Phase 1's minimal scaffold, a clear error message is sufficient.

**Warning signs:** `[Errno 13] Permission denied` on `.credentials.json` while Claude Code is running.

### Pitfall 4: `CLAUDE_CONFIG_DIR` overrides the path silently

**What goes wrong:** If a user has `CLAUDE_CONFIG_DIR` set (e.g., for a work account), `.credentials.json` lives under that directory, not `%USERPROFILE%\.claude\`. The D-02 candidate search returns `None` even though a valid token exists.

**Why it happens:** Official docs describe `CLAUDE_CONFIG_DIR` as the authoritative override. D-02's candidates cover the default layout only.

**How to avoid:** Check `CLAUDE_CONFIG_DIR` before the D-02 candidate search. This is a one-line addition to `read_token()`.

**Warning signs:** User reports `No Windows token found` despite `claude` working in their terminal.

## Code Examples

### _extract_access_token() — copy verbatim from macOS daemon

```python
# Source: daemon/claude_usage_daemon.py §57-86
# Copy this function exactly — do not import from that file (D-08)
def _extract_access_token(blob: str) -> str | None:
    """Pull the accessToken out of a credentials blob."""
    blob = blob.strip()
    if not blob:
        return None
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict):
        # direct: {"accessToken": "..."}
        if isinstance(data.get("accessToken"), str):
            return data["accessToken"]
        # nested: {"claudeAiOauth": {"accessToken": "..."}}  <-- real Windows shape
        for v in data.values():
            if isinstance(v, dict) and isinstance(v.get("accessToken"), str):
                return v["accessToken"]
    m = re.search(r'"accessToken"\s*:\s*"([^"]+)"', blob)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_\-.~+/=]{20,}", blob):
        return blob
    return None
```

### read_token() — Windows-specific, file-only

```python
# Source: pattern derived from daemon/claude_usage_daemon.py §115-127 (D-04/D-08)
def read_token() -> str | None:
    for path in _windows_credential_candidates():
        try:
            return _extract_access_token(path.read_text(encoding="utf-8"))
        except OSError:
            continue
    return None
```

### __main__ — redacted output per D-06/D-07

```python
if __name__ == "__main__":
    import sys
    token = read_token()
    if token is None:
        print(
            "No Windows token found — install Claude Code natively on Windows "
            "and run 'claude login'."
        )
        sys.exit(1)
    # Expiry: re-read file to get the raw dict (read_token() returns string only)
    expiry_str = _read_expiry()  # helper reads first-hit candidate for expiresAt
    print(f"Token OK (sk-ant-…{token[-4:]}), expires {expiry_str}")
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| macOS Keychain storage | `%USERPROFILE%\.claude\.credentials.json` plain file on Windows | Claude Code Windows support (2025-2026) | File-based read is simpler than Keychain; no OS secret store call needed |
| `{"accessToken": "..."}` direct JSON | Nested `{"claudeAiOauth": {"accessToken": "..."}}` | Introduced with OAuth 2.0 flow (sk-ant-oat01 tokens) | `_extract_access_token()` handles both shapes |

**Deprecated/outdated:**
- `~/.claude/.credentials.json` (Linux path convention): Not applicable on Windows — `Path.home()` returns `C:\Users\<user>`, not `/home/<user>`.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `%LOCALAPPDATA%\Claude\` and `%APPDATA%\Claude\` are valid fallback locations for future Claude Code Windows installs | Standard Stack / Architecture Patterns | Minor — D-02 already specifies probing all three; primary path is confirmed. |
| A2 | Python `PermissionError` is the error class for Windows file locks during active Claude Code session | Common Pitfalls #3 | Minor — the catch-`OSError` pattern covers `PermissionError` as a subclass regardless. |

**All other claims were verified or cited — no user confirmation needed for those.**

## Open Questions

1. **`CLAUDE_CONFIG_DIR` priority relative to `CLAUDE_CREDENTIALS_PATH` (D-03)**
   - What we know: Both are env-var overrides; `CLAUDE_CONFIG_DIR` is the official Claude override, `CLAUDE_CREDENTIALS_PATH` is the project-specific one.
   - What's unclear: Which should win when both are set?
   - Recommendation: `CLAUDE_CREDENTIALS_PATH` (explicit project override) takes precedence over `CLAUDE_CONFIG_DIR` (official app config). One-liner in `read_token()` — planner chooses order.

2. **`expiresAt` availability for D-06 output**
   - What we know: `_extract_access_token()` returns only the token string; expiry lives in the raw JSON.
   - What's unclear: Should `read_token()` return a richer type (token + expiry), or should `__main__` parse the file twice?
   - Recommendation: Add a separate `_read_credentials_dict()` helper that returns the parsed dict; `__main__` calls it once for both token and expiry. This is a two-line addition compatible with D-05's minimal scope.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.10+ | Daemon scaffold | ✓ (WSL) | 3.10.12 | — |
| Python for Windows (native) | Running the script on target machine | Not verified here (WSL env) | — | User must install CPython for Windows |
| `.credentials.json` on Windows | `read_token()` | Not verified here (WSL env) | — | D-07 failure message guides user |

**Missing dependencies with no fallback:** None that affect Phase 1 development. The script runs in any CPython 3.10+ environment; the credential file must exist on the target Windows machine (user installs Claude Code natively).

**Missing dependencies with fallback:** None — Phase 1 is stdlib-only.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (no config file detected — Wave 0 gap) |
| Config file | None — `pytest.ini` or `pyproject.toml` needed in Wave 0 |
| Quick run command | `python -m pytest daemon/tests/ -x -q` |
| Full suite command | `python -m pytest daemon/tests/ -q` |

Note: `test_macos_connect.py` exists but is an integration test requiring live hardware and macOS. Phase 1 tests are pure-Python unit tests exercising `_extract_access_token()` and `read_token()` against fixture data — no hardware or Windows required.

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TOKEN-01 | `read_token()` returns token from `%USERPROFILE%\.claude\.credentials.json` | unit | `python -m pytest daemon/tests/test_windows_token.py::test_read_token_primary_path -x` | ❌ Wave 0 |
| TOKEN-01 | `read_token()` returns token from `%LOCALAPPDATA%\Claude\.credentials.json` fallback | unit | `python -m pytest daemon/tests/test_windows_token.py::test_read_token_localappdata_fallback -x` | ❌ Wave 0 |
| TOKEN-01 | `read_token()` returns token from `%APPDATA%\Claude\.credentials.json` fallback | unit | `python -m pytest daemon/tests/test_windows_token.py::test_read_token_appdata_fallback -x` | ❌ Wave 0 |
| TOKEN-01 | `read_token()` honours `CLAUDE_CREDENTIALS_PATH` override (D-03) | unit | `python -m pytest daemon/tests/test_windows_token.py::test_read_token_env_override -x` | ❌ Wave 0 |
| TOKEN-01 | `_extract_access_token()` handles nested `claudeAiOauth` shape (real Windows format) | unit | `python -m pytest daemon/tests/test_windows_token.py::test_extract_nested_shape -x` | ❌ Wave 0 |
| TOKEN-01 | `_extract_access_token()` handles direct `accessToken` shape | unit | `python -m pytest daemon/tests/test_windows_token.py::test_extract_direct_shape -x` | ❌ Wave 0 |
| TOKEN-01 | `read_token()` returns `None` when no candidate path exists | unit | `python -m pytest daemon/tests/test_windows_token.py::test_read_token_no_file -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `python -m pytest daemon/tests/test_windows_token.py -x -q`
- **Per wave merge:** `python -m pytest daemon/tests/ -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `daemon/tests/__init__.py` — makes `daemon/tests/` a package
- [ ] `daemon/tests/test_windows_token.py` — covers all TOKEN-01 unit tests above
- [ ] `daemon/tests/fixtures/credentials_nested.json` — fixture: `{"claudeAiOauth": {"accessToken": "sk-ant-test-1234", "expiresAt": 9999999999000, "scopes": []}}`
- [ ] `daemon/tests/fixtures/credentials_direct.json` — fixture: `{"accessToken": "sk-ant-test-5678"}`
- [ ] pytest installable: `pip install pytest` (verify: `python -m pytest --version`)

## Security Domain

> `security_enforcement` not set in config.json → treated as enabled.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes — token storage read | Plain file read with `Path(path).read_text()`; no custom crypto |
| V3 Session Management | no — Phase 1 does not manage sessions | — |
| V4 Access Control | no — reads own-user file only | Windows file ACL (user profile permissions) enforces access |
| V5 Input Validation | yes — JSON parsing of credential blob | `json.loads()` in stdlib; `_extract_access_token()` validates token format with `re.fullmatch` |
| V6 Cryptography | no — no encryption in Phase 1 | — |

### Known Threat Patterns for Phase 1 Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Token printed in full to terminal | Information Disclosure | D-06: redact to last 4 chars; never `print(token)` |
| Credential path traversal via env override | Tampering | `Path(override)` is sufficient; no user-controlled directory traversal beyond what the user already controls (it is their own env var) |
| Token in shell history via `--token` flag | Information Disclosure | Phase 1 has no CLI flags; token is printed only in redacted form |

## Sources

### Primary (HIGH confidence)

- [Official Claude Code authentication docs](https://code.claude.com/docs/en/authentication) — Windows credential path `%USERPROFILE%\.claude\.credentials.json`, `CLAUDE_CONFIG_DIR` override, file mode documentation. Fetched 2026-06-01.
- `firmware/src/ble.cpp` lines 185–199 — characteristic flags `WRITE|WRITE_NR`, `READ|NOTIFY`, `NOTIFY`. Read directly during this session.
- `daemon/claude_usage_daemon.py` lines 57–127 — `_extract_access_token()` and `read_token()` source for D-08 copy. Read directly during this session.

### Secondary (MEDIUM confidence)

- [claude-code-sandbox lift-and-shift-credentials.md](https://git.joshthomas.dev/mirrors/claude-code-sandbox/src/commit/b44cf1a84e0bab3f5f2ded8a871cbdc43ce50249/docs/lift-and-shift-credentials.md) — confirmed `claudeAiOauth` nested JSON structure with `expiresAt` in milliseconds and `scopes` array. Cross-verified with web search findings.
- [GitHub issue #27791 anthropics/claude-code](https://github.com/anthropics/claude-code/issues/27791) — confirms `C:\Users\<user>\.claude` directory path in Windows native binary error message.

### Tertiary (LOW confidence)

- None — all critical claims verified with official sources.

## Metadata

**Confidence breakdown:**
- GATT encryption verdict: HIGH — directly read from firmware source file in this session
- Windows credential path: HIGH — confirmed from official Claude Code documentation
- Credential JSON structure: MEDIUM-HIGH — confirmed from multiple sources including sandbox docs and web search cross-verification
- Python stdlib patterns: HIGH — standard library documentation

**Research date:** 2026-06-01
**Valid until:** 2026-08-01 (stable — Windows credential path unlikely to change; credential JSON structure could change with Claude Code OAuth updates)
