---
phase: 4
slug: tray-autostart
status: secured
threats_open: 0
asvs_level: 2
created: 2026-06-02
---

# SECURITY.md — Phase 4: Tray + Autostart (Windows daemon port)

**Audit date:** 2026-06-02
**ASVS Level:** 2
**Disposition:** SECURED — all 13 declared threats CLOSED, 0 open.

This document records the verification of every threat in the Phase 4 STRIDE
register against the implemented code. Implementation files were treated as
read-only; no implementation was modified during this audit.

---

## Threat Verification

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-04-01 | Tampering | mitigate | CLOSED | `daemon/icon_assets.py:86-90` — `expected = W*H*3`; `if len(raw_bytes) != expected: raise ValueError(...)` before any indexing of `raw_bytes`. Bound check precedes the `rgb_bytes[i*2]` indexing loop (L98-102). |
| T-04-02 | Information Disclosure | accept | CLOSED | `daemon/icon_assets.py` imports only `re` + `PIL`; no network, no token, no credentials. Module operates purely on `logo.h` image bytes. Accepted risk logged below. |
| T-04-03 | Elevation of Privilege | mitigate | CLOSED | `daemon/autostart_windows.py:74,87,103` — every `OpenKey` uses `winreg.HKEY_CURRENT_USER`. No `HKLM`/`HKEY_LOCAL_MACHINE` reference anywhere (grep clean). `disable()` (L80-92) removes the value idempotently. |
| T-04-04 | Tampering | mitigate | CLOSED | `daemon/autostart_windows.py:59-61` — `pythonw = os.path.join(sys.base_exec_prefix, "pythonw.exe")`; `script = os.path.abspath(...)`; returns `f'"{pythonw}" "{script}"'` (both quoted). Path derived at runtime, never hard-coded. |
| T-04-05 | Information Disclosure | accept | CLOSED | `daemon/autostart_windows.py:77,90` — `log()` calls emit only the launch command (pythonw + script path) and "Autostart enabled/disabled" state. No token present in the module at all. Accepted risk logged below. |
| T-04-06 | Tampering | mitigate | CLOSED | `daemon/tray_windows.py:222-224` (`_on_quit`) — guards `ts.loop`/`ts.stop_event` then routes `ts.loop.call_soon_threadsafe(ts.stop_event.set)`. No direct `stop_event.set()` from the tray thread. Backing contract documented at `claude_usage_daemon_windows.py:451-453`. |
| T-04-07 | Information Disclosure | mitigate | CLOSED | `daemon/tray_windows.py:90-107` (`header_text`) surfaces only state + `time.strftime("%H:%M")` last-sync. Error path emits `ts.reason` only; the only error reason set is the fixed string `"token expired — run claude login"` (`claude_usage_daemon_windows.py:386,393`). Toast (`tray_windows.py:265`) uses `ts.reason`. Token (`token` var) flows only into the `Authorization` header (`claude_usage_daemon_windows.py:111`) — never into a `log()`, tooltip, header, or toast. |
| T-04-08 | Denial of Service | accept | CLOSED | `daemon/tray_windows.py:269` — `time.sleep(1.0)` passive poll. Icons built once at startup (`tray_windows.py:187-188` → `build_state_icons`), swapped by reference at L261, never recomposited per tick. Accepted risk logged below. |
| T-04-SC | Tampering | mitigate | CLOSED | `daemon/requirements-windows.txt` pins the dependency set (bleak, httpx, pystray, Pillow); `install-windows.ps1:82` installs only `-r $RequirementsFile`. See T-04-09 for the no-remote-code verification. |
| T-04-09 | Tampering | mitigate | CLOSED | `install-windows.ps1:79-83` — `pip install --quiet -r daemon\requirements-windows.txt` only. grep for `Invoke-WebRequest\|curl\|wget\|iwr\|DownloadString\|Net.WebClient` returns nothing. Header comment L16-17 + L174 assert "downloads nothing from the internet". |
| T-04-10 | Tampering | mitigate | CLOSED | `install-windows.ps1:28,92,114-115` — `$RepoRoot = $PSScriptRoot`; `$TrayScript = Join-Path $RepoRoot ...`; base pythonw derived via `& $PythonExe -c "import sys; print(sys.base_exec_prefix)"`. No hard-coded absolute path; grep for `[A-Z]:\Users` returns nothing. |
| T-04-11 | Information Disclosure | mitigate | CLOSED | `install-windows.ps1` Log lines emit only progress + paths, never a token. `daemon/README-windows.md:38-46,139-140` instructs the user to run `claude login`; never asks for a pasted token. README L31-33 carries an explicit "never share / never embed" security note. |
| T-04-12 | Tampering | mitigate | CLOSED | `daemon/tests/test_windows_no_wsl.py` — `FORBIDDEN = [r"\\wsl\$", r"wsl\.exe", r"/home/", r"/mnt/"]` asserted against all three core sources (daemon, tray, autostart). Test run: `3 passed in 0.11s`. `install-windows.ps1:43-59` adds a runtime WSL-path refusal guard. |

**Closed: 13/13. Open: 0.**

---

## Unregistered Flags

None. Every `## Threat Flags` entry in the Phase 4 SUMMARY files maps to a
registered threat ID:

- `04-01-SUMMARY.md` — "None" (icon_assets handles image bytes only) → maps to T-04-02 (accept).
- `04-02-SUMMARY.md` — `threat_flag: persistence` → T-04-03; `threat_flag: path-injection` → T-04-04.
- `04-03-SUMMARY.md` — `threat_flag: cross-thread-state` → T-04-06; `threat_flag: information-disclosure` → T-04-07.

No new attack surface appeared during implementation without a threat mapping.

---

## Accepted Risks Log

| Threat ID | Risk | Rationale |
|-----------|------|-----------|
| T-04-02 | `icon_assets` parses untrusted-shaped image bytes | Module is pure (re + Pillow), no token/credential/network access. The only externally-derived input (`logo.h`) is an in-repo build asset, and is still bound-checked (T-04-01). |
| T-04-05 | autostart logging | Logs only enable/disable state + the launch command (interpreter + script path). The module never touches the token. |
| T-04-08 | tray refresh ~1s passive poll | Bounded CPU: `time.sleep(1.0)` loop, icons built once at startup and swapped by reference. No per-tick recompositing. |

---

## Observation / Recommendation (non-blocking, out of Phase-4 scope)

**BLE custom GATT characteristic encryption (firmware scope).** The custom
data-service characteristics (RX `4c41555a-…0002`, REQ `…0004`) are
written/notified over the bonded BLE link. The captured TODO "verify ESP32
custom GATT characteristics are unencrypted" concerns the firmware
(`firmware/src/ble.cpp`), not this Windows-daemon phase.

Disclosure assessment of the daemon-side payload: `write_payload`
(`claude_usage_daemon_windows.py:189-203`) sends only
`{"s","sr","w","wr","st","ok"}` — rate-limit utilization percentages, reset
minutes, and a status flag. **No OAuth token, no credential, and no PII cross
the BLE link.** The OAuth token stays in the `Authorization` header to
`api.anthropic.com` over TLS and is never serialized into the BLE payload.

Therefore the disclosure value of an eavesdropped GATT payload is low
(usage percentages only). The link is already bonded
(`NimBLEDevice::setSecurityAuth(true, false, true)`), which provides
connection-level pairing. Characteristic-level encryption would raise the bar
against a paired-but-malicious peer reading the data characteristic, but the
sensitivity of the leaked data does not make this a Phase-4 blocker. Recommend
tracking characteristic-level encryption as a firmware-phase hardening item,
not gating the Windows daemon ship.

---

## Documentation accuracy note (informational, not a threat)

`daemon/README-windows.md:31-33` states the daemon "redacts it [the token] in
all log output (e.g., `sk-ant-…XXXX`)." The implementation does not perform
active redaction — instead it **never logs the token at all** (the token only
ever populates the `Authorization` header at
`claude_usage_daemon_windows.py:111`; no `log()` call receives it). The
security outcome the README promises (token never disclosed in logs) holds, so
T-04-07/T-04-11 remain CLOSED. The README wording slightly overstates the
mechanism (redaction vs. never-logged); a future doc edit could align it.
This is a documentation-accuracy nit, not a mitigation gap.
