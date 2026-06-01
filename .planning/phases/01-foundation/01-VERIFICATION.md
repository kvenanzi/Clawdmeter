---
phase: 01-foundation
verified: 2026-06-01T00:00:00Z
status: passed
score: 3/3 must-haves verified (SC3 confirmed via manual native-Windows run 2026-06-01)
overrides_applied: 0
human_verification:
  - test: "Run `python daemon\\claude_usage_daemon_windows.py` on a native Windows machine that has Claude Code installed and `claude login` completed"
    expected: "Prints a redacted token line (e.g. `Token OK (sk-ant-…XXXX), expires YYYY-MM-DD HH:MM UTC`) sourced from `%USERPROFILE%\\.claude\\.credentials.json`. No `\\\\wsl$` path is accessed. Exit code 0."
    why_human: "Success Criterion #3 requires a real native-Windows Python process with a live Windows-local OAuth token at the D-02 primary path. Cannot be exercised from WSL/Linux because Path.home() resolves to the Linux home directory, not a Windows user profile. No CI substitute exists."
    result: "PASSED (2026-06-01) — ran from native-Windows PowerShell, output `Token OK (sk-ant-…jgAA), expires 2026-06-02 02:09 UTC`. No WSL warning emitted (sys.platform == win32), confirming native path resolution; real-token expiry decoded correctly."
---

# Phase 01: Foundation Verification Report

**Phase Goal:** The GATT encryption question is answered and the daemon can read a valid Windows-local OAuth token
**Verified:** 2026-06-01
**Status:** passed
**Re-verification:** Yes — SC#3 confirmed via manual native-Windows run (2026-06-01)

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | GATT encryption verdict (UNENCRYPTED) recorded in `.planning/notes/windows-daemon-port.md` | VERIFIED | Section "GATT encryption gate — verdict (D-01)" at line 74 of the note; contains "CONFIRMED UNENCRYPTED", names all three characteristics (RX/TX/REQ) with plain NimBLE flags, ends with "Satisfies Phase 1 Success Criterion #1." |
| 2 | `daemon/claude_usage_daemon_windows.py` skeleton exists with a `read_token()` function that reads the OAuth token and returns the access-token string | VERIFIED | File exists at 127 lines, stdlib-only. All 9 pytest cases GREEN (`9 passed in 0.12s`). `read_token()` returns correct token across nested shape, direct shape, env overrides, 3-candidate fallback, and no-file None. `__main__` prints `Token OK (sk-ant-…1234), expires 2286-11-20 17:46 UTC` against the nested fixture; exits 1 with actionable message on missing file. |
| 3 | Running the script on a native Windows machine with Claude Code installed prints the token expiry without touching any WSL path | HUMAN NEEDED | Requires a real Windows machine + live token at `%USERPROFILE%\.claude\.credentials.json`. Cannot be verified from WSL/Linux. Per plan, this is explicitly a manual-only success criterion. |

**Score:** 2/3 truths verified (SC3 is human-gated by design)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `.planning/notes/windows-daemon-port.md` | GATT verdict section containing "UNENCRYPTED" and "Success Criterion #1" | VERIFIED | Lines 74-94: H2 section present, all three characteristics named with NimBLE flag details, "Satisfies Phase 1 Success Criterion #1." on last line |
| `daemon/claude_usage_daemon_windows.py` | read_token(), _extract_access_token(), _windows_credential_candidates(), _read_expiry(), __main__; min 60 lines; stdlib-only | VERIFIED | 127 lines; all 4 functions present; `grep -E "bleak\|httpx\|asyncio\|expandvars\|wsl"` returns nothing; `expires_ms / 1000` present (1 match) |
| `daemon/tests/test_windows_token.py` | 9 test functions, exact names from VALIDATION.md | VERIFIED | 9 functions counted; all 9 names match plan spec exactly; import line `from daemon.claude_usage_daemon_windows import _extract_access_token, read_token, _windows_credential_candidates, _read_expiry` present |
| `daemon/tests/fixtures/credentials_nested.json` | claudeAiOauth.accessToken == sk-ant-test-1234, expiresAt == 9999999999000 | VERIFIED | JSON parses; both values confirmed programmatically |
| `daemon/tests/fixtures/credentials_direct.json` | accessToken == sk-ant-test-5678 | VERIFIED | JSON parses; value confirmed |
| `conftest.py` (repo root) | sys.path.insert for daemon.* import resolution | VERIFIED | Line `sys.path.insert(0, os.path.dirname(__file__))` confirmed present |
| `daemon/__init__.py` | Empty package marker | VERIFIED | File exists |
| `daemon/tests/__init__.py` | Empty package marker | VERIFIED | File exists |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `daemon/tests/test_windows_token.py` | `daemon.claude_usage_daemon_windows` | `from daemon.claude_usage_daemon_windows import _extract_access_token, read_token, _windows_credential_candidates, _read_expiry` | VERIFIED | Import line present at line 11; all 4 names imported |
| `daemon/claude_usage_daemon_windows.py:read_token` | `_extract_access_token` | calls on each candidate file's read_text() | VERIFIED | Line 77: `return _extract_access_token(path.read_text(encoding="utf-8"))` inside the candidates loop |
| `daemon/claude_usage_daemon_windows.py:__main__` | `read_token` + redacted print | `token[-4:]` — never full token | VERIFIED | Line 119: `token = read_token()`; line 127: `print(f"Token OK (sk-ant-…{token[-4:]}), ...")` — confirmed the full token variable is never printed |
| `daemon/claude_usage_daemon_windows.py:_read_expiry` | `_windows_credential_candidates` | shared candidate function, no duplicated path logic | VERIFIED | Line 90: `for path in _windows_credential_candidates():` — same function as read_token, no duplication |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|--------------------|--------|
| `daemon/claude_usage_daemon_windows.py` | `token` (str\|None) | `_windows_credential_candidates()` -> `path.read_text()` -> `_extract_access_token()` | Yes — reads from filesystem, parses JSON, extracts real token value | FLOWING |
| `daemon/claude_usage_daemon_windows.py` | `expiry_str` (str) | `_windows_credential_candidates()` -> `path.read_text()` -> `json.loads()` -> `datetime.fromtimestamp(expires_ms / 1000)` | Yes — derives real datetime from ms-epoch in credentials file | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| pytest suite all 9 GREEN | `python -m pytest daemon/tests/test_windows_token.py -q` | `9 passed in 0.12s` | PASS |
| __main__ redacted output (nested fixture) | `CLAUDE_CREDENTIALS_PATH=daemon/tests/fixtures/credentials_nested.json python daemon/claude_usage_daemon_windows.py` | `Token OK (sk-ant-…1234), expires 2286-11-20 17:46 UTC` | PASS |
| __main__ failure path exit code | `CLAUDE_CREDENTIALS_PATH=/nonexistent/x.json python daemon/claude_usage_daemon_windows.py; echo "exit=$?"` | `No Windows token found — install Claude Code natively on Windows and run 'claude login'.` / `exit=1` | PASS |
| No forbidden imports | `grep -E "bleak\|httpx\|asyncio\|expandvars\|wsl" daemon/claude_usage_daemon_windows.py \| wc -l` | 0 | PASS |
| ms-to-s division present | `grep -c "expires_ms / 1000" daemon/claude_usage_daemon_windows.py` | 1 | PASS |
| No Darwin/Keychain platform branch (D-04) | `grep -n "sys.platform.*darwin\|keychain\|Keychain\|keyring"` | no output | PASS |

### Probe Execution

Step 7c: SKIPPED — no `scripts/*/tests/probe-*.sh` files declared or discovered for this phase. Phase is a Python module + pytest suite, covered by behavioral spot-checks above.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| TOKEN-01 | 01-01, 01-02 | Daemon reads Claude OAuth token from native-Windows credentials path (no WSL/`\\wsl$`) | SATISFIED | 9 unit tests GREEN covering nested shape, direct shape, env overrides, 3-candidate fallback, no-file None, CLAUDE_CONFIG_DIR override, ms-expiry decode. REQUIREMENTS.md marks `[x] TOKEN-01`. `grep -E "expandvars\|wsl"` on implementation returns nothing. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None found | — | — | — | — |

No TBD/FIXME/XXX markers. No TODO/HACK/PLACEHOLDER markers. No placeholder returns. No hardcoded empty data flowing to output. Debt marker gate: PASS.

### Code Review Context (from 01-REVIEW.md — outside phase must-haves)

The pre-existing code review flagged real bugs that survive in the implementation. These are documented here for completeness but are NOT blockers for this phase's success criteria:

- **CR-01 (Critical — outside must-haves):** Empty-string `accessToken` (`{"accessToken": ""}`) passes `isinstance(data.get("accessToken"), str)` and is returned as a valid token. `__main__` then prints "Token OK" instead of triggering the failure path (checks `if token is None`, not `if not token`). Reproduced in the review with `printf '{"accessToken": ""}' > creds.json`. No test covers this path (WR-03). Phase 2 should add `tok.strip()` guards and a `if not token:` check in `__main__`.
- **WR-01 (Warning — outside must-haves):** `_read_expiry` crashes with `AttributeError` when credentials file is valid JSON but not a dict (e.g. `[1,2,3]`). The except clause at line 107 does not include `AttributeError`, contradicting the docstring promise of "expiry unknown on any parse failure". Fix: add `AttributeError` to the except tuple or add `if not isinstance(data, dict): return "expiry unknown"`.
- **WR-02 (Warning):** No test asserts the D-06 token-redaction behavior of `__main__` output. A future refactor could leak the full token and the suite would stay green.
- **WR-04 (Warning):** `_read_expiry` and `read_token` each independently call `_windows_credential_candidates()` and read the file. TOCTOU possibility and redundant I/O; `expiry_str` will show "expiry unknown" for any token read from the direct-shape format (which has no `claudeAiOauth.expiresAt`).

These are legitimate post-phase hardening items. They do not block the phase goal as defined.

### Human Verification Required

#### 1. Native Windows token read (Success Criterion #3)

**Test:** On a native Windows machine with Python and Claude Code installed natively (not in WSL), run `python daemon\claude_usage_daemon_windows.py` from the repo root (or with `CLAUDE_CREDENTIALS_PATH` unset, allowing the D-02 primary path to resolve).

**Expected:** Output matches `Token OK (sk-ant-…XXXX), expires YYYY-MM-DD HH:MM UTC` where XXXX is the last 4 characters of the real token and the year is a plausible near-future date (not year ~57000). Exit code 0. No `\\wsl$` or Linux path appears in the output or in any error message.

**Why human:** Requires a real native Windows Python process. `Path.home()` on Linux/WSL resolves to `/home/<user>` not `C:\Users\<user>`, so the D-02 primary candidate will not exist. The test cannot be satisfied with a monkeypatched `CLAUDE_CREDENTIALS_PATH` pointing at the fixture because the goal is to confirm the real Windows path resolution works end-to-end with a live token.

### Gaps Summary

No automated gaps found. All three verification checks that can be run from Linux/WSL pass. The only open item is Success Criterion #3, which is explicitly a manual-only check requiring a native Windows machine — this was declared human-only in the phase plan and does not block phase goal assessment.

---

_Verified: 2026-06-01_
_Verifier: Claude (gsd-verifier)_
