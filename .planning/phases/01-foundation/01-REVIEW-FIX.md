---
phase: 01-foundation
fixed_at: 2026-06-01T19:25:00Z
review_path: .planning/phases/01-foundation/01-REVIEW.md
iteration: 1
findings_in_scope: 4
fixed: 4
skipped: 1
status: partial
---

# Phase 1: Code Review Fix Report

**Fixed at:** 2026-06-01T19:25:00Z
**Source review:** .planning/phases/01-foundation/01-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 5 (CR-01, WR-01, WR-02, WR-03, WR-04)
- Fixed: 4 (CR-01, WR-01, WR-02, WR-03)
- Skipped: 1 (WR-04)
- Final test count: 14 (9 original + 5 new), all GREEN

## Fixed Issues

### CR-01: Empty-string `accessToken` reported as a valid token

**Files modified:** `daemon/claude_usage_daemon_windows.py`
**Commit:** 6dcf744
**Applied fix:**
- In `_extract_access_token`, tightened the JSON dict paths to require `tok.strip()` to be truthy before returning. The direct path changed from `if isinstance(data.get("accessToken"), str): return data["accessToken"]` to `tok = data.get("accessToken"); if isinstance(tok, str) and tok.strip(): return tok`. Same guard applied to the nested dict loop.
- In `__main__`, changed `if token is None` to `if not token` for defense-in-depth, so any falsy token (None or empty string) triggers the actionable failure message and `sys.exit(1)`.
- `_extract_access_token` stays at parity with the macOS source structure (D-08 preserved) — the only change is adding `.strip()` guards on the return conditions. The regex path was not modified (the `[^"]+` quantifier already rejects empty strings at that path).

### WR-01: `_read_expiry` crashes on non-dict JSON (uncaught `AttributeError`)

**Files modified:** `daemon/claude_usage_daemon_windows.py`
**Commit:** 6dcf744
**Applied fix:**
- Added `AttributeError` to the except tuple in `_read_expiry`: changed `except (TypeError, ValueError, OSError, json.JSONDecodeError)` to `except (TypeError, ValueError, OSError, AttributeError, json.JSONDecodeError)`. Now when the credentials file is valid JSON but the top-level value is not a dict (e.g. `[1,2,3]`), the call to `data.get(...)` raises `AttributeError` which is caught and returns `"expiry unknown"`, honoring the docstring promise.

### WR-03: No test for the empty/blank-token path (CR-01 regression guard)

**Files modified:** `daemon/tests/test_windows_token.py`
**Commit:** 60fb759
**Applied fix:**
- Added `test_extract_empty_token_is_none`: directly calls `_extract_access_token('{"accessToken": ""}')` and `_extract_access_token('{}')`, asserts both return None.
- Added `test_read_token_empty_credential_file_returns_none`: end-to-end via `read_token()` with a temp file containing `{"accessToken": ""}`, asserts None is returned.

### WR-02: D-06 redaction requirement has no test coverage

**Files modified:** `daemon/tests/test_windows_token.py`
**Commit:** 60fb759
**Applied fix:**
- Added `test_main_output_redacts_token`: runs the module as a subprocess with `CLAUDE_CREDENTIALS_PATH` pointing at `credentials_nested.json`, asserts full token `sk-ant-test-1234` is absent from stdout and last-4 `1234` is present. Confirms D-06 is tested.
- Added `test_main_empty_token_exits_one`: runs the module as a subprocess with an empty-token credential file, asserts exit code 1 and "No Windows token found" in stdout.
- Added `test_read_expiry_non_dict_json_returns_unknown`: confirms WR-01 fix via the public API with a temp file containing `[1, 2, 3]`.

## Skipped Issues

### WR-04: `_read_expiry` re-reads and re-parses the credentials file independently of `read_token`

**File:** `daemon/claude_usage_daemon_windows.py:73-80, 90-96`
**Reason:** This is a maintainability/consistency smell (the REVIEW.md itself labels it "not a crash"). The fix requires extracting read+parse into a shared helper and passing the parsed dict into both `read_token` and `_read_expiry` — a structural refactor that is not mandated by the phase constraints and would change the public interface. The constraints explicitly address CR-01, WR-01, WR-02, and WR-03 only. Deferred to a future maintenance pass.
**Original issue:** `__main__` calls `read_token()` (reads file #1) then `_read_expiry()` (reads+parses the same file again), creating a TOCTOU window and duplicate candidate-resolution logic. A valid token from the direct `{"accessToken": ...}` shape always reports `expiry unknown` from `_read_expiry` because that function only looks under `claudeAiOauth`.

---

_Fixed: 2026-06-01T19:25:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
