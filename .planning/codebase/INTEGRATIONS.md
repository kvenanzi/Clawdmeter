# External Integrations

**Analysis Date:** 2026-06-01

## APIs & External Services

**Anthropic API (usage polling):**
- Service: Anthropic Claude API — queried solely to read rate-limit headers; actual response discarded
- Endpoint: `POST https://api.anthropic.com/v1/messages`
- SDK/Client (Linux): `curl` with bash script in `daemon/claude-usage-daemon.sh`
- SDK/Client (macOS): `httpx` async client in `daemon/claude_usage_daemon.py`
- Auth: OAuth bearer token — see **Authentication** section below
- Headers consumed:
  - `anthropic-ratelimit-unified-5h-utilization` — 5-hour window utilization (0.0–1.0)
  - `anthropic-ratelimit-unified-5h-reset` — Unix timestamp when 5h window resets
  - `anthropic-ratelimit-unified-7d-utilization` — 7-day window utilization (0.0–1.0)
  - `anthropic-ratelimit-unified-7d-reset` — Unix timestamp when 7d window resets
  - `anthropic-ratelimit-unified-5h-status` — `"allowed"` or `"limited"`
- Probe body: `{"model":"claude-haiku-4-5-20251001","max_tokens":1,"messages":[{"role":"user","content":"hi"}]}`
- API version header: `anthropic-version: 2023-06-01`
- Beta header: `anthropic-beta: oauth-2025-04-20`
- User-Agent: `claude-code/2.1.5`

**claudepix.vercel.app (splash animation asset source):**
- Service: External web app hosting 20×20 pixel-art creature animations
- SDK/Client: `tools/scrape_claudepix.js` — headless Node.js scraper (uses `vm` module to eval JS bundles)
- Auth: None (public)
- Output: `tools/claudepix_data/*.json` — scraped animation data, committed to repo
- This is a one-time pipeline step, not a runtime integration

## Data Storage

**Databases:**
- None — no database used in firmware or daemon

**File Storage:**
- Firmware: assets baked into flash at build time (fonts as `.c` arrays, icons in `firmware/src/icons.h`, splash animations in `firmware/src/splash_animations.h`)
- Daemon state files (Linux/macOS):
  - BLE address cache: `~/.config/claude-usage-monitor/ble-address` — persisted MAC (Linux) or CoreBluetooth UUID (macOS) for fast reconnect
  - Refresh flag file: `/tmp/claude-usage-refresh-<PID>` — transient IPC between dbus-monitor pipe and daemon poll loop (Linux only)

**Caching:**
- BLE address cache file described above; invalidated on connect failure

## Authentication & Identity

**Auth Provider: Claude Code OAuth (Anthropic)**
- The daemon authenticates to Anthropic's API using the Claude Code OAuth access token
- Linux: token read from `~/.claude/.credentials.json` (JSON with `"accessToken"` field)
  - Reader: `daemon/claude-usage-daemon.sh` `read_token()` — `grep` + `cut`
  - Multiple JSON shapes handled: direct `{"accessToken":"..."}`, nested `{"claudeAiOauth":{"accessToken":"..."}}`, or raw token string
- macOS: token read from macOS Keychain, service name `"Claude Code-credentials"`, account = current username
  - Reader: `daemon/claude_usage_daemon.py` `_read_token_keychain()` — `security find-generic-password -w`
  - Same multi-shape extraction logic: `_extract_access_token()` in `claude_usage_daemon.py`
- Token is refreshed each poll cycle (read fresh from keychain/file every 60 seconds)

## BLE (Bluetooth Low Energy) Transport

**Firmware peripheral (ESP32):**
- Device name: `"Claude Controller"`
- Protocol: BLE GATT peripheral (NimBLE-Arduino 2.5.0)
- Max connections: 2 simultaneous (one HID OS link + one daemon data link)
- Security: bonding + Secure Connections (`NimBLEDevice::setSecurityAuth(true, false, true)`)
- Implementation: `firmware/src/ble.cpp`, `firmware/src/ble.h`

**Custom GATT data service:**
- Service UUID: `4c41555a-4465-7669-6365-000000000001`
- RX characteristic (`...0002`): host daemon writes JSON payload here (WRITE | WRITE_NR)
- TX characteristic (`...0003`): firmware notifies ack (`{"ack":true}`) or nack (`{"err":true}`) (READ | NOTIFY)
- REQ characteristic (`...0004`): firmware fires `0x01` byte notify when it needs a data refresh — daemon subscribes via CCCD (NOTIFY)

**BLE HID keyboard service:**
- Service UUID: `0x1812` (standard BLE HID)
- Appearance: `HID_KEYBOARD`
- PnP ID: source=BT SIG (0x01), vendor=Espressif (0x02E5), product=0x0001, version=0x0100
- Manufacturer string: `"Anthropic"`
- Country: 33 (US ANSI) — prevents macOS Keyboard Setup Assistant from launching
- Reports: 6-KRO + LED output report (modifier byte + 6 key slots; LED output required for macOS)
- Keys sent: Space (0x2C) on PRIMARY button, Shift+Tab (0x2B + 0x02) on SECONDARY button

**Host daemon BLE client (Linux):**
- Tool: `bluetoothctl` + `busctl` D-Bus calls
- Discovery: scan by device name `"Claude Controller"`, cache resolved MAC at `~/.config/claude-usage-monitor/ble-address`
- GATT writes: `busctl call org.bluez <char_path> org.bluez.GattCharacteristic1 WriteValue "aya{sv}"`
- Refresh subscription: `dbus-monitor` pipe + `awk` flag-file IPC (see daemon comments for pipe-buffering gotchas)
- On connect failure: removes device from bluez (`bluetoothctl remove`) to force re-scan

**Host daemon BLE client (macOS):**
- Library: `bleak` (CoreBluetooth backend)
- Discovery: `retrieve_connected_macos()` first (handles HID-held device invisible to scans), then `BleakScanner.find_device_by_name()` fallback
  - CoreBluetooth lookup: custom service UUID (`4c41555a-...0001`) first, HID UUID `0x1812` + name-match second
- GATT writes: `client.write_gatt_char(RX_CHAR_UUID, data, response=False)`
- Refresh subscription: `client.start_notify(REQ_CHAR_UUID, callback)` → asyncio Event

## Monitoring & Observability

**Error Tracking:**
- None — no crash reporting or telemetry

**Logs:**
- Firmware: `Serial.printf()` at 115200 baud to USB-CDC; structured events prefixed (`BLE:`, `JSON parse error:`, etc.)
- Linux daemon: `log()` function → stdout with timestamp `[HH:MM:SS]`; journald captures via systemd user service
- macOS daemon: stdout/stderr → `~/Library/Logs/claude-usage-daemon.{out,err}.log` (configured in plist)

## CI/CD & Deployment

**Hosting:**
- Firmware: flashed directly to device via PlatformIO (`pio run -t upload`)
- No OTA update mechanism

**CI Pipeline:**
- None detected (no GitHub Actions, no CI config)

## Webhooks & Callbacks

**Incoming:**
- None (no webhook endpoints)

**Outgoing:**
- None (daemon polls Anthropic API on a 60-second timer or on device-initiated REQ characteristic notify)

## Environment Configuration

**Required for daemon (Linux):**
- `~/.claude/.credentials.json` must exist with valid `accessToken`
- `bluetoothctl`, `busctl`, `dbus-monitor`, `curl`, `awk` must be on PATH

**Required for daemon (macOS):**
- macOS Keychain must have entry: service `"Claude Code-credentials"`, account = current user
- Bluetooth permission granted to terminal / launchd agent
- Python 3 with `bleak>=0.22` and `httpx>=0.27` (installed by `install-mac.sh` into `daemon/.venv`)

**Required for firmware build:**
- PlatformIO with pioarduino platform (fetched from GitHub ZIP on first build)
- `BOARD_HAS_PSRAM` flag set for S3 boards (controls LVGL buffer allocation strategy)

**Secrets location:**
- Linux: `~/.claude/.credentials.json` (never committed; read at runtime)
- macOS: macOS Keychain (accessed via `security` CLI)

---

*Integration audit: 2026-06-01*
