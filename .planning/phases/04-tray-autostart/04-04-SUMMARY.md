---
phase: 04-tray-autostart
plan: "04"
subsystem: install/docs/wsl-independence
tags: [powershell, installer, autostart, docs, no-wsl-guard, hardware-record, APP-01, APP-02]
dependency_graph:
  requires:
    - daemon/autostart_windows.py (04-02)
    - daemon/tray_windows.py (04-03)
  provides:
    - install-windows.ps1
    - daemon/README-windows.md
    - daemon/tests/test_windows_no_wsl.py
  affects: []
tech_stack:
  added: []
  patterns:
    - turnkey PowerShell bootstrap (venv -> pip -r pinned reqs -> autostart enable -> launch tray)
    - pure-ASCII installer (no smart-quotes/unicode — avoids PS parse failures)
    - install-time WSL-path guard (refuses to run from \\wsl$ / \\wsl.localhost share)
    - static no-WSL-paths regression test over daemon + tray + autostart sources
    - operator hardware-record split (D-10) mirroring Phase 1/2/3 D-06
key_files:
  created:
    - install-windows.ps1
    - daemon/README-windows.md
    - daemon/tests/test_windows_no_wsl.py
    - .planning/phases/04-tray-autostart/04-HARDWARE-RECORD.md
  modified: []
decisions:
  - "Installer derives the venv pythonw + tray script path from $PSScriptRoot / base_exec_prefix at install time — never a hard-coded absolute path (CLAUDE.md repoint lesson; T-04-10)"
  - "Installer installs ONLY from the in-repo pinned daemon/requirements-windows.txt — no remote DownloadString/Invoke-WebRequest of untrusted code (T-04-09)"
  - "Installer refuses to run from a WSL share path so the venv + autostart entry never point at a path that vanishes on wsl --shutdown (APP-02)"
  - "no-WSL guard is a static FORBIDDEN-pattern test (\\\\wsl$, wsl.exe, /home, /mnt) over daemon/tray/autostart sources — a CI-surviving regression lock (D-10, APP-02)"
  - "Hardware record pre-seeded with SC#1-5 steps; operator fills observed results (manual half of D-10) — cannot be proven by mocks"
requirements: [APP-01, APP-02]
metrics:
  completed: 2026-06-02
  tasks_completed: 2
  files_created: 4
---

# Phase 4 Plan 4: Windows Install + Docs + WSL-Independence Summary

**One-liner:** Turnkey `install-windows.ps1` bootstrap (venv → pinned-deps → autostart → launch), tray/autostart/install docs in `README-windows.md`, a static no-WSL-paths regression guard, and the operator hardware-verification record for SC#1–SC#5.

## What Was Built

- **`install-windows.ps1`** — one-command bootstrap that creates `.venv`, installs `daemon/requirements-windows.txt` (pinned, in-repo only), registers login autostart via `autostart_windows.enable()`, and launches the tray headlessly. Pure-ASCII (no smart quotes), and refuses to run from a `\\wsl$` / `\\wsl.localhost` share (APP-02).
- **`daemon/README-windows.md`** — documents prerequisites (incl. native Windows Bluetooth pairing — bonded HID device), one-time setup, manual run, the tray icon/status/menu, autostart enable/disable, and WSL independence. The Phase-4 promise was removed from "What is NOT covered."
- **`daemon/tests/test_windows_no_wsl.py`** — static regression guard asserting daemon + tray + autostart sources contain no forbidden WSL path patterns (`\\wsl$`, `wsl.exe`, `/home`, `/mnt`).
- **`04-HARDWARE-RECORD.md`** — operator-recorded SC#1–SC#5 results (manual half of D-10): no-console logon launch, tray status, clean Quit, `wsl --shutdown` no-op, fresh WSL-never-launched session.

## Verification Results

- `python -m pytest daemon/tests/ -q` — full suite passing (89 at phase close).
- SC#1–SC#5 all PASS on real Windows hardware (see `04-HARDWARE-RECORD.md`); SC#3 criterion revised (bonded BLE HID link intentionally persists after Quit — documented with rationale).
- Phase verification: `04-VERIFICATION.md` — status passed, 5/5 success criteria. Security: `04-SECURITY.md` — 13/13 threats closed.

## Commits

| Commit | Description |
|--------|-------------|
| bac6391 | feat(04-04): install-windows.ps1 bootstrap + README-windows.md tray/autostart docs (D-09) |
| e395228 | test(04-04): add static no-WSL-paths regression guard (D-10, APP-02) |
| 41efdae | docs(04-04): pre-seed 04-HARDWARE-RECORD.md with SC#1-5 test steps (D-10 manual half) |
| 866582f | fix(04-04): pure-ASCII installer + WSL-path guard |

## Note

This SUMMARY was written retroactively (the plan's deliverables were committed but the SUMMARY was not authored at execution time — flagged during phase verification). All must-have truths and artifacts are present and verified.
