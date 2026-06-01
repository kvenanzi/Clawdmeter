# Testing Patterns

**Analysis Date:** 2026-06-01

## Test Framework

**Runner:** None configured. No `jest.config.*`, `vitest.config.*`, `pytest.ini`, or PlatformIO `test/` directory exists. There is no automated test suite.

**Manual / Integration testing only.** Verification is done through two mechanisms:
1. **Screenshot capture** — `screenshot.sh` dumps the LVGL framebuffer over serial and produces a PNG for visual inspection
2. **End-to-end connection test** — `daemon/test_macos_connect.py` connects over BLE and writes a test payload to verify the full BLE→firmware path

---

## Screenshot-Based UI Verification

**Script:** `./screenshot.sh [out.png] [port]` (repo root)

**Mechanism:**
- Sends `screenshot` command over the serial connection to the device
- Firmware's `send_screenshot()` in `firmware/src/main.cpp` (lines 122–158) allocates a full-frame RGB565 buffer from PSRAM, calls `lv_snapshot_take_to_draw_buf()`, and writes the raw bytes preceded by a `SCREENSHOT_START W H BYTES` sentinel
- Script decodes the binary stream into a PNG sized to the active display (480×480 for AMOLED-2.16, 368×448 for AMOLED-1.8)
- The script auto-detects the OS default port (`/dev/cu.usbmodem*` on macOS, `/dev/ttyACM0` on Linux)

**Constraint:** Screenshot capture requires PSRAM (`BOARD_HAS_PSRAM`). On the C6 variant the firmware prints `SCREENSHOT_UNSUPPORTED` instead.

**How to iterate on UI changes:**
1. Flash the firmware
2. Temporarily change the default boot screen in `firmware/src/main.cpp` from `SCREEN_SPLASH` to `SCREEN_USAGE` or `SCREEN_BLUETOOTH` (search for `ui_show_screen(SCREEN_SPLASH)`)
3. Run `./screenshot.sh out.png` after each build+flash
4. Inspect the PNG with the Read tool
5. Iterate until correct, then revert the default screen before committing

**Do not skip this step for UI changes.** Per project convention: "Use this on every UI iteration."

---

## BLE Integration Test (macOS)

**File:** `daemon/test_macos_connect.py`

**Framework:** Python `asyncio` + `bleak` (CoreBluetooth backend)

**What it tests:**
- macOS connected-peripheral discovery path (no scan, uses `retrieveConnected` API)
- BLE connection succeeds and `client.is_connected` is `True`
- Custom GATT service is reachable and RX characteristic (`RX_CHAR_UUID`) is discoverable
- Write of a JSON test payload to `RX_CHAR_UUID` completes without error
- Device screen visually confirms received data (manual verification step)

**How to run:**
```bash
cd daemon && ./.venv/bin/python ./test_macos_connect.py
```

**Dependencies:** Requires Bleak installed in a virtualenv (`daemon/.venv`). Must run from Terminal.app on macOS for Bluetooth permission.

**Test structure:**
```python
async def main() -> None:
    target = await d.discover_target()      # find device
    client = BleakClient(target)
    await client.connect()                  # connect
    # check RX characteristic is visible
    # write test payload
    await client.disconnect()
```

Output is `PASS:` / `FAIL:` prefixed lines to stdout.

---

## Manual Hardware Verification Checklist

No automated assertions exist for hardware behaviour. The following are verified manually during development:

**Display:**
- Visual inspection via screenshot tool
- Rotation transitions on AMOLED-2.16 (IMU tilt test)
- Brightness ramp after rotation

**Touch:**
- Tap events propagate to LVGL (screen switch on tap)
- Touch wake-up swallows first press correctly

**BLE:**
- `daemon/test_macos_connect.py` for macOS GATT write path
- `claude-usage-daemon.sh` / `claude_usage_daemon.py` for full daemon loop
- Serial output (`BLE: connected from ...`, `BLE: advertising start=OK`) provides runtime state

**Power / Battery:**
- Battery icon updates visually on the Usage screen
- Idle fade to black after `IDLE_TIMEOUT_MS` (30 min default)
- USB-present keeps display awake when `IDLE_SLEEP_WHEN_CHARGING=false`

---

## Serial Command Interface

The firmware exposes a serial command interface used during development:

| Command | Response | Purpose |
|---------|----------|---------|
| `screenshot` | Binary frame + sentinels | Captures LVGL framebuffer |

Previous debug commands (e.g. `iox`) have been removed. Adding new serial commands follows the pattern in `check_serial_cmd()` in `firmware/src/main.cpp` (lines 160–171).

---

## Asset Pipeline Tests (Node.js tools)

**`tools/png_to_lvgl.js`:** No test suite. The output is visually verified by splicing into `firmware/src/icons.h` and running a screenshot capture.

**`tools/convert_to_c.js`:** No test suite. Output is `firmware/src/splash_animations.h`; correctness is confirmed visually by running the splash screen on hardware.

**`tools/scrape_claudepix.js`:** No test suite. Correctness verified by checking `tools/claudepix_data/_index.json` after scraping and running `convert_to_c.js`.

---

## Adding Tests (Guidance for Future Work)

If automated tests are added, the natural points of attachment are:

**Firmware unit tests (PlatformIO `test/` directory):**
- `usage_rate.cpp` is pure logic (no hardware calls) — easiest to test. `usage_rate_sample()` / `usage_rate_group()` can be compiled natively and covered with Google Test or Unity
- `parse_json()` in `main.cpp` is testable standalone (ArduinoJson + a stub `Serial`)
- `format_reset_time()` in `ui.cpp` has no hardware dependency

**Node.js tools (Jest or Node's built-in test runner):**
- `rgb565()` in `png_to_lvgl.js` is a pure function
- `hexToRgb565()` / `paletteToRgb565()` in `convert_to_c.js` are pure functions

**Python daemon:**
- `_extract_access_token()` in `claude_usage_daemon.py` is a pure function
- The `poll()` logic can be tested against recorded HTTP header fixtures with `httpx`'s mock transport

---

*Testing analysis: 2026-06-01*
