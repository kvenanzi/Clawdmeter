---
phase: 4
slug: tray-autostart
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-06-02
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.4.2 (47 existing tests green) |
| **Config file** | `daemon/pytest.ini` (or `daemon/pyproject.toml` — confirm at planning) |
| **Quick run command** | `python -m pytest daemon/tests -q` |
| **Full suite command** | `python -m pytest daemon/tests` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest daemon/tests -q`
- **After every plan wave:** Run `python -m pytest daemon/tests`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

> Tests are co-authored with their implementation inside Waves 1–3 (TDD plans
> 04-01/04-02 write RED tests first; execute plans 04-03/04-04 add their tests
> alongside the code). There is **no separate Wave 0** — the deterministic-logic
> targets from RESEARCH.md "## Validation Architecture" land in the plan rows below.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 04-01-T1 | 04-01 | 1 | APP-01 | — | N/A | tdd (unit) | `python -m pytest daemon/tests/test_windows_icon.py -q` | ❌ in-plan | ⬜ pending |
| 04-01-T2 | 04-01 | 1 | APP-01 | — | N/A | tdd (unit) | `python -m pytest daemon/tests/test_windows_icon.py -q` | ❌ in-plan | ⬜ pending |
| 04-02-T1 | 04-02 | 1 | APP-01 | autostart Run-key hijack / cmd injection | HKCU-only, `pythonw.exe`, runtime-derived path (no HKLM, no hard-coded path) | tdd (unit) | `python -m pytest daemon/tests/test_windows_autostart.py -q` | ❌ in-plan | ⬜ pending |
| 04-03-T1 | 04-03 | 2 | APP-01 | token leak via tooltip/state | no token in tooltip/header text | execute (unit) | `python -m pytest daemon/tests/test_windows_tray.py -q` | ❌ in-plan | ⬜ pending |
| 04-03-T2 | 04-03 | 2 | APP-01 | token leak via toast | Error toast says "token expired", never the token | execute (unit) | `python -m pytest daemon/tests/test_windows_tray.py -q` | ❌ in-plan | ⬜ pending |
| 04-04-T1 | 04-04 | 3 | APP-02 | — | daemon source references no WSL paths | execute (unit/grep) | `python -m pytest daemon/tests/test_windows_no_wsl.py -q` | ❌ in-plan | ⬜ pending |
| 04-04-T2 | 04-04 | 3 | APP-01 | install.ps1 remote-code / exec-policy | no remote download; local venv only | execute (manual) | install-windows.ps1 dry-run on target Windows PC | ❌ manual | ⬜ pending |
| 04-04-T3 | 04-04 | 3 | APP-01, APP-02 | — | N/A | checkpoint (human-verify) | manual hardware record (SC#1–#5) | ❌ manual | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Automated-Test Files (authored in-plan, Waves 1–3)

- [ ] `daemon/tests/test_windows_icon.py` — `logo.h` RGB565 → RGBA/PNG conversion, brand-hex `#DE7552` derivation, icon-state → bubble-color mapping (04-01 / D-01,D-02,D-03)
- [ ] `daemon/tests/test_windows_autostart.py` — autostart enable/disable/is_enabled with mocked `winreg`, HKCU-only, `pythonw.exe`, idempotent on missing (04-02 / D-07,D-08)
- [ ] `daemon/tests/test_windows_tray.py` — Error-toast-on-entry-only, state→tooltip mapping, no token in any tray text (04-03 / D-04,D-05)
- [ ] `daemon/tests/test_windows_no_wsl.py` — static guard: daemon source references no `\\wsl$`, `wsl.exe`, `/home`, `/mnt` (04-04 / APP-02 / D-10)

*Reuse existing `daemon/tests/conftest.py` (root `sys.path.insert`) and the
`test_windows_token.py` / `test_windows_reconnect.py` mock-the-platform-binding convention.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Launches at logon, no terminal window (SC#1) | APP-01 | Requires real Windows logon + `pythonw.exe` headless launch | Install via `install-windows.ps1`, log out/in, observe daemon running with no console |
| Tray icon visible + status on hover/click (SC#2) | APP-01 | Requires the Windows notification area | Observe tray icon; hover/click → tooltip shows connected/scanning/error |
| Right-click → Quit stops daemon cleanly (SC#3) | APP-01 | Requires real tray menu interaction + clean asyncio unwind | Right-click tray → Quit; confirm BLE disconnects, process exits 0 |
| `wsl --shutdown` does not disconnect/err (SC#4) | APP-02 | Requires live BLE link + WSL state change | Connect, run `wsl --shutdown`, confirm link stays up, no error logged |
| Fresh session, WSL never launched, connects (SC#5) | APP-02 | Requires a fresh Windows boot | Reboot, do not launch WSL, confirm device connects + shows usage |

*Tray / Quit / WSL behavior captured in the manual on-hardware record (mirrors Phase 1/2/3 D-06 split).*

---

## Validation Sign-Off

- [x] All impl tasks have `<automated>` verify (tests authored in-plan; no Wave 0 deferral)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (W1 3/3, W2 2/2, W3 impl 1/1)
- [x] No MISSING references (every test file is authored by its own plan)
- [x] No watch-mode flags (fast pytest/grep, ~5s)
- [x] Feedback latency < 10s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-06-02 (plan-checker VERIFICATION PASSED)
