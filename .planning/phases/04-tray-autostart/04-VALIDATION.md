---
phase: 4
slug: tray-autostart
status: draft
nyquist_compliant: false
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

> Planner fills one row per task. Deterministic-logic targets identified in
> RESEARCH.md "## Validation Architecture": autostart toggle (mocked `winreg`),
> icon-state → image mapping, no-WSL-paths static guard, `logo.h` → PNG conversion.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 0 | APP-02 | — | N/A | unit | `python -m pytest daemon/tests/test_no_wsl_paths.py -q` | ❌ W0 | ⬜ pending |
| 04-01-02 | 01 | 0 | APP-01 | — | N/A | unit | `python -m pytest daemon/tests/test_autostart.py -q` | ❌ W0 | ⬜ pending |
| 04-01-03 | 01 | 0 | APP-01 | — | N/A | unit | `python -m pytest daemon/tests/test_icon_state.py -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*
*Planner: replace/extend these rows to match the actual plan/task breakdown.*

---

## Wave 0 Requirements

- [ ] `daemon/tests/test_no_wsl_paths.py` — static guard: daemon source references no `\\wsl$`, `wsl.exe`, `/home`, `/mnt` (APP-02 / D-10)
- [ ] `daemon/tests/test_autostart.py` — autostart toggle create/remove/query with mocked `winreg` (APP-01 / D-07)
- [ ] `daemon/tests/test_icon_state.py` — icon-state → image mapping (connected/scanning/error → bubble color) (APP-01 / D-01,D-02)
- [ ] `daemon/tests/test_logo_to_png.py` — `logo.h` RGB565 → PNG conversion + brand-hex derivation (D-03) *(if planner makes this a standalone deterministic step)*

*Reuse existing `daemon/tests/conftest.py` fixtures if present.*

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

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
