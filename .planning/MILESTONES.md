# Milestones

## v1.0 Windows Daemon (Shipped: 2026-06-02)

**Delivered:** A native Windows host daemon that keeps the Clawdmeter connected over BLE, polls the Anthropic API for usage, runs from a login-startup system-tray app, and works fully independently of WSL.

**Phases completed:** 4 phases, 12 plans, 13 tasks
**Code:** ~1,061 LOC Windows daemon + tray/autostart/icon modules; ~3,400 insertions across 16 daemon files (incl. tests)
**Timeline:** 2026-06-01 → 2026-06-02 (~2 days)
**Git range:** `91a1d09` (feat 01-02 token reader) → `fc0bf02`

**Key accomplishments:**

- **GATT de-risked + token reader (Phase 1):** Confirmed the custom GATT characteristics are UNENCRYPTED (no pairing / firmware change needed), then shipped a stdlib-only Windows OAuth token reader (`_extract_access_token` copied verbatim from the macOS daemon, first-hit-wins `read_token` with env overrides + 3-path fallback, ms-epoch expiry decode) — all 9 TOKEN-01 tests GREEN.
- **API-to-BLE pipeline (Phase 2):** Ported `poll_api()` verbatim from the macOS daemon (httpx-mocked tests lock the `{s,sr,w,wr,st,ok}` wire contract), then wired the `bleak` WinRT BLE glue (scan-by-name, `address_type="random"`, `use_cached_services=False`, REQ subscribe + RX write). Verified end-to-end on hardware: device left its waiting screen and showed session 46% / weekly 4% at macOS-daemon latency.
- **Reconnect resilience (Phase 3):** Connect-retry wrapper + zombie-link consecutive-failure break, plus split fast-reconnect (8s cap) vs slow-search (60s cap) backoff to protect the 120s reconnect SLA. Hardware run proved BLE-03 against real WinRT; SC#3 surfaced a daemon-crashing gap (G-03-01, uncaught `OSError` from `start_notify`) that was fixed TDD-style and re-verified PASS.
- **Tray + autostart + WSL independence (Phase 4):** Pillow icon layer (logo.h → per-state corner-bubble tray icons), stdlib `winreg` HKCU\Run autostart toggle via `pythonw.exe`, pystray tray runtime (status icon + Quit + error toast on a thread-safe `TrayState` bridge), and a turnkey `install-windows.ps1` bootstrap with a static no-WSL-paths regression guard. SC#1–5 confirmed on hardware including `wsl --shutdown` leaving the daemon undisturbed.

**Requirements:** 7/7 v1 requirements delivered and hardware-verified (TOKEN-01, POLL-01, BLE-01, BLE-02, BLE-03, APP-01, APP-02).

**Notes:** Closed without a separate `/gsd:audit-milestone` pass — work was already hardware-verified per phase verification/UAT records; 2 stale todos (GATT-encryption check, tray implementation) resolved by Phase 1/4 and moved to completed at close.

---
