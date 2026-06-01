# Technology Stack

**Analysis Date:** 2026-06-01

## Languages

**Primary:**
- C++17 — ESP32-S3 firmware (`firmware/src/`)
- Bash — Linux host daemon (`daemon/claude-usage-daemon.sh`)

**Secondary:**
- Python 3 — macOS host daemon (`daemon/claude_usage_daemon.py`)
- JavaScript (Node.js) — asset pipeline tools (`tools/*.js`)

## Runtime

**Firmware:**
- ESP32-S3 (Xtensa dual-core LX7, 240 MHz) — primary target
- ESP32-C6 (RISC-V single-core) — supported via separate env `waveshare_amoled_216_c6`
- Arduino Core 3.x via pioarduino (ESP-IDF 5.x underneath)

**Host daemon (Linux):**
- Bash shell with `bluetoothctl`, `busctl`, `dbus-monitor`, `curl`

**Host daemon (macOS):**
- Python 3 (venv at `daemon/.venv`)
- Packages: `bleak>=0.22`, `httpx>=0.27`

**Asset tools:**
- Node.js (no version pinned; no `.nvmrc`)

## Package Manager / Build System

**Firmware:**
- PlatformIO (CLI: `pio`) — manages library fetching and build
- Build platform: `pioarduino/platform-espressif32` pinned at `55.03.38-1`
  (required for Arduino Core 3.x; standard `espressif32` ships only 2.x)
- Config: `firmware/platformio.ini`
- Lockfile: `firmware/.pio/libdeps/` (fetched artifacts present, not a lockfile per se)

**macOS daemon:**
- `pip` inside virtualenv (`daemon/.venv`)
- No `requirements.txt` — install script calls `pip install "bleak>=0.22" "httpx>=0.27"` directly

**Tools:**
- No `package.json` — Node scripts are standalone, only use built-ins except `pngjs` (ad-hoc install)

## Frameworks

**Core (firmware):**
- Arduino framework (via pioarduino ESP32 3.x core) — `setup()` / `loop()` lifecycle

**UI (firmware):**
- LVGL 9.x (`lvgl/lvgl@^9.2.0`, installed 9.5.0) — widget library, RGB565 partial render mode
  - Config: entirely via `build_flags` in `platformio.ini` (no `lv_conf.h` file; `LV_CONF_SKIP` set)
  - Fonts: pre-compiled LVGL bitmap C arrays in `firmware/src/font_*.c` (Tiempos, Styrene, Mono)
  - Note: fonts require manual patching from `lv_font_conv` LVGL-8 output to LVGL-9 format

**BLE (firmware):**
- NimBLE-Arduino `h2zero/NimBLE-Arduino@^2.1.1` (installed 2.5.0) — BLE peripheral stack
  - Exposes custom GATT data service + HID keyboard service simultaneously
  - Max 2 connections: one for OS HID link, one for host daemon

**Display drivers (firmware):**
- GFX Library for Arduino `moononournation/GFX Library for Arduino` (1.5.6 on 2.16, 1.6.4+ on 1.8 and C6, installed 1.6.5)
  - 2.16 board: `Arduino_CO5300` over QSPI
  - 1.8 and C6 boards: `Arduino_SH8601` (requires >=1.6.4)
  - CPU rotation for CO5300 done in `boards/waveshare_amoled_216/display.cpp`

**Sensor/power (firmware):**
- SensorLib `lewisxhe/SensorLib@^0.2.6` (installed 0.2.6) — QMI8658 IMU (accelerometer, auto-rotation on 2.16)
- XPowersLib `lewisxhe/XPowersLib@^0.2.7` (installed 0.2.9) — AXP2101 PMU (battery %, charging, power button IRQ)

**JSON (firmware):**
- ArduinoJson `bblanchon/ArduinoJson@^7.0.0` (installed 7.4.3) — parse incoming BLE JSON payload

## Key Dependencies

**Critical:**
- `lvgl 9.5.0` — entire UI rendering layer; version matters for font format compatibility
- `NimBLE-Arduino 2.5.0` — BLE peripheral with dual-connection (HID + data) support
- `pioarduino platform-espressif32 55.03.38-1` — mandatory for Arduino Core 3.x; older platform breaks build
- `GFX Library for Arduino 1.6.5` — display driver; 1.6.4+ required for SH8601 panels

**Infrastructure:**
- `ArduinoJson 7.4.3` — parses `{"s":N,"sr":N,"w":N,"wr":N,"st":"...","ok":true}` payload
- `XPowersLib 0.2.9` — AXP2101 PMU: battery %, charging state, PWR button edge detection
- `SensorLib 0.2.6` — QMI8658 IMU: rotation quadrant on 2.16; I2C bus health on 1.8
- `bleak>=0.22` (Python, macOS) — CoreBluetooth wrapper; uses `retrieveConnectedPeripheralsWithServices_` to reach HID-held device
- `httpx>=0.27` (Python, macOS) — async HTTP for Anthropic API polling

## Configuration

**Firmware build:**
- All LVGL config via `-D` build flags in `firmware/platformio.ini` (no lv_conf.h)
- Board selection via `build_src_filter` — one env per board, shared code + one board folder
- PSRAM required for S3 boards: `board_build.arduino.memory_type = qio_opi`
- Flash size: 16 MB partitions for 1.8 and C6 boards (`default_16MB.csv`)

**Runtime (firmware):**
- No env vars; all config is compile-time (`board.h`) or HAL runtime (`BoardCaps`)
- BLE device name hardcoded: `"Claude Controller"` (`firmware/src/ble.cpp`)
- GATT service UUID hardcoded: `4c41555a-4465-7669-6365-000000000001`

**Runtime (daemon):**
- OAuth token: Linux reads `~/.claude/.credentials.json`; macOS reads macOS Keychain service `"Claude Code-credentials"`
- BLE address cache: `~/.config/claude-usage-monitor/ble-address` (Linux: MAC; macOS: CoreBluetooth UUID)
- Poll interval: `POLL_INTERVAL=60` seconds, inner tick `TICK=5` seconds
- Systemd user unit: `daemon/claude-usage-daemon.service` (Linux)
- LaunchAgent plist: `daemon/com.user.claude-usage-daemon.plist` (macOS)

## Platform Requirements

**Development:**
- PlatformIO CLI (`pio`) for firmware build and flash
- ESP32-S3 connected via USB-JTAG (no boot-mode dance required)
- Device ports: `/dev/cu.usbmodem*` (macOS), `/dev/ttyACM0` (Linux)
- Screenshot capture: `./screenshot.sh out.png [port]` (requires `pyserial` or falls back to pio's bundled Python)

**Production (firmware targets):**
- Waveshare ESP32-S3-Touch-AMOLED-2.16 (CO5300, 480x480, env: `waveshare_amoled_216`)
- Waveshare ESP32-S3-Touch-AMOLED-1.8 (SH8601, 368x448, env: `waveshare_amoled_18`)
- Waveshare ESP32-C6-AMOLED-2.16 (SH8601 variant, no PSRAM, env: `waveshare_amoled_216_c6`)

**Production (host daemon):**
- Linux: systemd user service, requires `curl`, `bluetoothctl`, `busctl`, `dbus-monitor`
- macOS: launchd LaunchAgent, requires Python 3, `bleak`, `httpx`, Bluetooth permission grant

---

*Stack analysis: 2026-06-01*
