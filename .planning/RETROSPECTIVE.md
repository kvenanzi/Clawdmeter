# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.0 — Windows Daemon

**Shipped:** 2026-06-02
**Phases:** 4 | **Plans:** 12 | **Tasks:** 13

### What Was Built
- A native Windows host daemon (`daemon/claude_usage_daemon_windows.py`) that reads the Windows-local Claude OAuth token, polls the Anthropic API, and pushes the `{s,sr,w,wr,st,ok}` usage payload to the Clawdmeter over `bleak`/WinRT BLE.
- Reconnect resilience: connect-retry wrapper, zombie-link consecutive-failure break, and split fast-reconnect (8s) vs slow-search (60s) backoff protecting a 120s reconnect SLA.
- A login-startup system-tray app: pystray status icon + Quit + error toast on a thread-safe `TrayState` bridge, `winreg` HKCU\Run autostart via `pythonw.exe`, Pillow-composited per-state tray icons.
- A turnkey `install-windows.ps1` bootstrap (venv → pinned deps → autostart → launch) and `README-windows.md`, plus a static no-WSL-paths regression guard proving WSL independence.

### What Worked
- **De-risk-first phasing.** Phase 1 answered the GATT-encryption question (unencrypted → no pairing, no firmware change) before any BLE code was written, removing the project's single biggest unknown up front.
- **Verbatim porting from the macOS daemon.** `_extract_access_token` and `poll_api()` were copied verbatim rather than reimplemented, with httpx-mocked tests locking the wire contract — high parity, low risk.
- **TDD throughout.** Each phase landed RED tests before implementation; SC#3 in Phase 3 surfaced a real daemon-crashing bug (G-03-01) that was closed TDD-style and re-verified on hardware.
- **Hardware verification at each phase boundary** (D-06/D-10 operator records) caught issues unit tests couldn't — e.g. the venv redirector spawning a console window, autostart cwd-independence.

### What Was Inefficient
- **Requirements/todos bookkeeping drifted from reality.** BLE-03/APP-01/APP-02 stayed marked "Pending" and two todos stayed "pending" even though the phases shipped them — all had to be reconciled at milestone close.
- **No formal milestone audit was run** before close; relied on per-phase verification/UAT records instead. Fine here because everything was hardware-verified, but it left the requirements table as the only (stale) coverage signal.
- **Summary one-liner extraction is unreliable** — several SUMMARY.md files used a heading format the CLI couldn't parse, so the auto-generated MILESTONES.md accomplishments needed a manual rewrite.

### Patterns Established
- **Optional/degrade-gracefully BLE subscriptions:** wrap `start_notify` in a broad `except` and continue the poll loop rather than crash — preserves the no-restart guarantee.
- **Thread-safe scalar bridge** (`TrayState`, no lock) between an asyncio loop thread and a main-thread pystray UI; Quit always via `loop.call_soon_threadsafe`.
- **Deferred platform imports** (`import pystray` inside `main()`) keep the module importable on a GTK-less Linux dev box for testing.
- **Pure-ASCII PowerShell installer** to avoid smart-quote parse failures; install-time WSL-path guard refuses to run from a `\\wsl$` share.

### Key Lessons
1. Resolve the highest-risk unknown in its own gate phase before committing to an implementation approach — it shaped every later phase.
2. Keep the requirements traceability table and todos in sync at phase close, not milestone close — drift makes the final audit noisier than it needs to be.
3. Hardware/operator verification records are worth the friction; they caught console-window and cwd bugs that no unit test would have.

### Cost Observations
- Model mix: not tracked this milestone.
- Notable: worktree-isolated parallel executors were used (several `chore: merge executor worktree` commits) — wave-based parallelization across plans within a phase.

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Plans | Key Change |
|-----------|--------|-------|------------|
| v1.0 | 4 | 12 | First milestone — established de-risk-first phasing, TDD + per-phase hardware verification |

### Cumulative Quality

| Milestone | Windows daemon LOC | New deps | Hardware-verified SCs |
|-----------|--------------------|----------|------------------------|
| v1.0 | ~1,061 (+tests ≈3,000) | bleak, httpx, pystray, Pillow | Phases 2/3/4 SCs verified on real hardware |

### Top Lessons (Verified Across Milestones)

1. De-risk the biggest unknown in a dedicated gate phase before building.

*(More cross-milestone trends will accumulate as future milestones complete.)*
