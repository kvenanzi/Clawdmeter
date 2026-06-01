# Phase 1: Foundation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-01
**Phase:** 1-Foundation
**Areas discussed:** Token location strategy, Scaffold scope, Output & failure UX, macOS code parity

---

## Pre-discussion findings

- **GATT-encryption gate resolved by scout** before discussion began. `firmware/src/ble.cpp`
  §185–199 creates RX/TX/REQ with plain `WRITE|WRITE_NR`, `READ|NOTIFY`, `NOTIFY` — no
  encrypted variants. Verdict: unencrypted, no Windows pairing, no firmware change. This
  collapsed the "if encrypted, then pair / drop encryption" contingency, so it was not put
  to the user as a gray area.

## Todo Folding

| Todo | Decision |
|------|----------|
| verify-gatt-characteristics-unencrypted.md | Folded — de-risk gate, resolved during scout |
| implement-windows-daemon-tray.md | Folded — only its token-reading slice is Phase 1; rest deferred to Phases 2–4 |

**User's choice:** Fold both.

---

## Token location strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Search candidates + env override | Probe %USERPROFILE%\.claude, %LOCALAPPDATA%\Claude, %APPDATA%\Claude in order; CLAUDE_CREDENTIALS_PATH override | ✓ |
| Single canonical path | Hardcode only %USERPROFILE%\.claude\.credentials.json | |
| Files + Credential Manager fallback | Search files, then Windows Credential Manager (keyring) | |

**User's choice:** Search candidates + env override
**Notes:** Researcher still confirms the actual native path; this fixes the lookup strategy. Credential Manager fallback deferred unless the token turns out to live in the vault.

---

## Scaffold scope

| Option | Description | Selected |
|--------|-------------|----------|
| Minimal | read_token() + _extract_access_token() + __main__ that prints | ✓ |
| Skeleton with structure | Also stub config-dir helper, logging, main()-loop placeholder | |

**User's choice:** Minimal
**Notes:** De-risk phase stays tight; Phase 2 introduces daemon structure and config dir.

---

## Output & failure UX

| Option | Description | Selected |
|--------|-------------|----------|
| Redacted confirmation + expiry | `Token OK (sk-ant-…<last4>), expires <date>`; actionable failure message | ✓ |
| Expiry field only | Print just expiry; generic error | |
| Full token (debug) | Print raw access token | |

**User's choice:** Redacted confirmation + expiry
**Notes:** Never echo the full secret to terminal/scrollback. Failure message points the user to install Claude Code natively + `claude login`; exit non-zero.

---

## macOS code parity

| Option | Description | Selected |
|--------|-------------|----------|
| Separate file, copy helper | New claude_usage_daemon_windows.py; copy _extract_access_token() | ✓ |
| Separate file, import helper | from claude_usage_daemon import _extract_access_token | |

**User's choice:** Separate file, copy helper
**Notes:** Importing the macOS module on Windows runs its top-level Keychain/path code — fragile. Matches the locked "ship its own daemon, don't share a codebase" decision.

---

## Claude's Discretion

None — the user selected an explicit option for every area (all on the recommended choice).

## Deferred Ideas

- BLE scan/connect/write → Phase 2
- Anthropic API polling → Phase 2
- MAC-address cache (`%APPDATA%\claude-usage-monitor\`) → Phase 2/3
- Auto-reconnect after sleep/range/drop → Phase 3
- System-tray icon + login autostart → Phase 4
- PyInstaller packaging + Windows Credential Manager fallback → v2 / follow-up
