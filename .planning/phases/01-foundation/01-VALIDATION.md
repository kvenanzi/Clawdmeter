---
phase: 1
slug: foundation
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-06-01
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x+ |
| **Config file** | none — Wave 0 installs (`pytest.ini` or `pyproject.toml [tool.pytest]`) |
| **Quick run command** | `python -m pytest daemon/tests/test_windows_token.py -x -q` |
| **Full suite command** | `python -m pytest daemon/tests/ -q` |
| **Estimated runtime** | ~2 seconds (pure-Python unit tests, no hardware/network) |

`test_macos_connect.py` already exists but is a live-hardware/macOS integration test — out of scope for Phase 1's automated suite. Phase 1 tests are pure-Python units against fixture JSON.

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest daemon/tests/test_windows_token.py -x -q`
- **After every plan wave:** Run `python -m pytest daemon/tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** ~5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD (planner) | 0X | 0 | — | — | N/A (test scaffold) | infra | `python -m pytest --version` | ❌ W0 | ⬜ pending |
| TBD (planner) | 0X | 1 | TOKEN-01 | — | `read_token()` returns token from `%USERPROFILE%\.claude\.credentials.json` | unit | `python -m pytest daemon/tests/test_windows_token.py::test_read_token_primary_path -x` | ❌ W0 | ⬜ pending |
| TBD (planner) | 0X | 1 | TOKEN-01 | — | `read_token()` returns token from `%LOCALAPPDATA%\Claude\.credentials.json` fallback | unit | `python -m pytest daemon/tests/test_windows_token.py::test_read_token_localappdata_fallback -x` | ❌ W0 | ⬜ pending |
| TBD (planner) | 0X | 1 | TOKEN-01 | — | `read_token()` returns token from `%APPDATA%\Claude\.credentials.json` fallback | unit | `python -m pytest daemon/tests/test_windows_token.py::test_read_token_appdata_fallback -x` | ❌ W0 | ⬜ pending |
| TBD (planner) | 0X | 1 | TOKEN-01 | T-info-disclosure | `read_token()` honours `CLAUDE_CREDENTIALS_PATH` override (D-03) | unit | `python -m pytest daemon/tests/test_windows_token.py::test_read_token_env_override -x` | ❌ W0 | ⬜ pending |
| TBD (planner) | 0X | 1 | TOKEN-01 | — | `_extract_access_token()` handles nested `claudeAiOauth` shape (real Windows format) | unit | `python -m pytest daemon/tests/test_windows_token.py::test_extract_nested_shape -x` | ❌ W0 | ⬜ pending |
| TBD (planner) | 0X | 1 | TOKEN-01 | — | `_extract_access_token()` handles direct `accessToken` shape | unit | `python -m pytest daemon/tests/test_windows_token.py::test_extract_direct_shape -x` | ❌ W0 | ⬜ pending |
| TBD (planner) | 0X | 1 | TOKEN-01 | — | `read_token()` returns `None` when no candidate path exists | unit | `python -m pytest daemon/tests/test_windows_token.py::test_read_token_no_file -x` | ❌ W0 | ⬜ pending |
| TBD (planner) | 0X | 1 | TOKEN-01 | — | `read_token()` honours official `CLAUDE_CONFIG_DIR` override (research-derived extension of D-03) | unit | `python -m pytest daemon/tests/test_windows_token.py::test_read_token_config_dir_override -x` | ❌ W0 | ⬜ pending |
| TBD (planner) | 0X | 2 | TOKEN-01 | — | `_read_expiry()` decodes `expiresAt` epoch-**milliseconds** correctly (fixture `9999999999000` → year 2286, NOT ~57000) | unit | `python -m pytest daemon/tests/test_windows_token.py::test_read_expiry_decodes_milliseconds -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky. Task IDs are assigned by the planner; the planner must map each TOKEN-01 behavior above to a concrete task with an `<automated>` verify or a Wave 0 dependency.*

**Test set: 9 cases.** The original 7 TOKEN-01 cases plus two coverage additions from the plan-checker pass: `test_read_token_config_dir_override` (the `CLAUDE_CONFIG_DIR` branch — official Claude override the implementation honours but D-03 did not name; tracked here as an accepted extension) and `test_read_expiry_decodes_milliseconds` (asserts the ms→s division so the year-57000 pitfall cannot regress).

---

## Wave 0 Requirements

- [ ] `daemon/tests/__init__.py` — makes `daemon/tests/` a package
- [ ] `daemon/tests/test_windows_token.py` — covers all 9 unit cases above
- [ ] `daemon/tests/fixtures/credentials_nested.json` — `{"claudeAiOauth": {"accessToken": "sk-ant-test-1234", "expiresAt": 9999999999000, "scopes": []}}`
- [ ] `daemon/tests/fixtures/credentials_direct.json` — `{"accessToken": "sk-ant-test-5678"}`
- [ ] pytest available: the Wave 0 task (PLAN 01-01 Task 2) runs `python -m pytest --version` and `pip install pytest` if it is missing — so a fresh machine is self-sufficient, not reliant on a pre-installed pytest. (pytest 8.4.2 is already present in the current dev env.)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Running `claude_usage_daemon_windows.py` on a real native-Windows machine prints `Token OK (sk-ant-…<last4>), expires <date>` against the live `.credentials.json` | TOKEN-01 (SC #3) | Requires native Windows + Claude Code installed + `claude login`; cannot run in WSL/CI (path resolution & live token) | On a Windows box with Claude Code installed and logged in, run `python daemon\claude_usage_daemon_windows.py`; confirm a redacted token + expiry prints and no `\\wsl$` path is touched |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (incl. pytest availability via PLAN 01-01 Task 2)
- [x] No watch-mode flags
- [x] Feedback latency < 5s
- [x] `nyquist_compliant: true` set in frontmatter

*`wave_0_complete` stays `false` until execution actually builds the test package and fixtures — it is an execution-time flag, not a planning-time one.*

**Approval:** approved 2026-06-01
