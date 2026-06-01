# Codebase Concerns

**Analysis Date:** 2026-06-01

## Tech Debt

**Unguarded LVGL render buffers on PSRAM failure:**
- Issue: `buf1` and `buf2` are allocated via `heap_caps_malloc` in `firmware/src/main.cpp` (lines 201–202) but there is no null check before they are passed to `lv_display_set_buffers` (line 207). If PSRAM is misconfigured (e.g., missing `board_build.arduino.memory_type = qio_opi`), both return NULL and LVGL gets a null buffer with no error halt or log.
- Files: `firmware/src/main.cpp`
- Impact: Silent black screen that looks identical to a library or display failure. Already documented in CLAUDE.md as a known gotcha but no runtime guard exists.
- Fix approach: Add `if (!buf1 || !buf2) { Serial.println("FATAL: LVGL buffer alloc failed"); while(1); }` after allocation.

**`make_pill` and reset label use hardcoded `font_styrene_28` regardless of layout:**
- Issue: `make_pill()` at `firmware/src/ui.cpp:259` always uses `&font_styrene_28`. On the compact layout (AMOLED-1.8, 368×448), the usage panel inherits `lbl_session_reset` and `lbl_weekly_reset` also at `font_styrene_28` (line 299), while the panel height is shrunk to 130 px. The pill text ("Current", "Weekly") overflows or clips against the 48pt percentage label.
- Files: `firmware/src/ui.cpp`
- Impact: Possible visual overlap of "Current"/"Weekly" pill and the percentage label on the 1.8" board in certain font metric combinations. Not yet caught because `make_pill` is not driven by `L.bt_device_font` or equivalent.
- Fix approach: Pass a font pointer argument to `make_pill()` (or a `Layout` reference), use `L.bt_device_font` as the font for the pill in `make_usage_panel`.

**`rot_buf` allocation not guarded for failure in 216 display:**
- Issue: In `firmware/src/boards/waveshare_amoled_216/display.cpp:32`, `rot_buf` is allocated with `heap_caps_malloc` from SPIRAM. It is already guarded at use-time (`if (r == 0 || !rot_buf)`), so a failure gracefully falls back to unrotated rendering. However, no log/warning is emitted if the allocation fails, making it silent.
- Files: `firmware/src/boards/waveshare_amoled_216/display.cpp`
- Impact: IMU rotation silently disabled with no diagnostic; hard to distinguish from PSRAM being absent vs. not enough contiguous memory.
- Fix approach: Add `if (!rot_buf) Serial.println("WARN: rot_buf alloc failed, rotation disabled");` after allocation.

**Stale "SC01 Plus" references in Linux install script:**
- Issue: `install.sh` lines 35 and 38 refer to "SC01 Plus" — the original panel that was replaced by the AMOLED boards. Instructions tell users to power on "the SC01 Plus" and scan for it.
- Files: `install.sh`
- Impact: New users following the script see wrong device names and incorrect pairing instructions.
- Fix approach: Replace "SC01 Plus" with "Waveshare AMOLED" (or "Claude Controller") throughout `install.sh`.

**Two daemon implementations diverge over time:**
- Issue: `daemon/claude-usage-daemon.sh` (Linux/bash) and `daemon/claude_usage_daemon.py` (macOS/Python) duplicate API call logic, header strings, model selection, and backoff logic. Currently in sync (both use `anthropic-beta: oauth-2025-04-20`, `claude-haiku-4-5-20251001`, `User-Agent: claude-code/2.1.5`) but the pattern guarantees drift.
- Files: `daemon/claude-usage-daemon.sh`, `daemon/claude_usage_daemon.py`
- Impact: API token expiry, header changes, or model deprecation will need coordinated updates to both files. A missed update in either file silently breaks that platform.
- Fix approach: Consolidate to a single Python daemon (already more featureful: CoreBluetooth macOS support, async polling, refresh subscriptions via bleak). The bash daemon is already superseded in capability.

**`BOARD_HAS_PSRAM` is a compile-time flag but `BOARD_HAS_*` pattern violates HAL contract:**
- Issue: The refactor removed `#ifdef BOARD_*` from shared code but two `#ifdef BOARD_HAS_PSRAM` guards remain in shared files (`firmware/src/main.cpp:28,123` and `firmware/src/splash.cpp:107`). These are justified (PSRAM governs memory allocation strategy, not board identity) but represent the beginning of feature-flag creep back into shared code.
- Files: `firmware/src/main.cpp`, `firmware/src/splash.cpp`
- Impact: Low — these are currently appropriate uses. Risk is that future ports add new `BOARD_HAS_*` guards to shared files instead of using `BoardCaps`.
- Fix approach: Document explicitly in `docs/porting/capability-flags.md` that `BOARD_HAS_PSRAM` is the only compile-time flag permitted in shared code. All others use `BoardCaps` runtime fields.

**Unused compiled font files in build (`font_mono_18.c`, `font_styrene_12.c`):**
- Issue: `firmware/src/font_mono_18.c` and `firmware/src/font_styrene_12.c` are compiled into every build target but `LV_FONT_DECLARE(font_mono_18)` and `LV_FONT_DECLARE(font_styrene_12)` never appear in any `.cpp` file. The font data is linked but dead.
- Files: `firmware/src/font_mono_18.c`, `firmware/src/font_styrene_12.c`
- Impact: Binary bloat — each LVGL font file is ~10–80 KB of bitmap glyph data. On the PSRAM-less C6 build, flash is more constrained (~1.43 MB firmware vs ~6.5 MB partition).
- Fix approach: Either declare and use them (e.g., `font_mono_18` for a compact BT screen on the 1.8" board) or remove the `.c` files and their `lv_font_conv` sources.

---

## Known Bugs

**`ble_clear_bonds` disconnects only the first peer (index 0):**
- Symptoms: When "Reset Bluetooth" is tapped on the BT screen and two clients are connected (OS HID + daemon), only `getPeerInfo(0)` is disconnected.
- Files: `firmware/src/ble.cpp:234`
- Trigger: Tap "Reset Bluetooth" while both the OS keyboard HID link and the daemon's data connection are active.
- Workaround: The second client will eventually time out or the user can manually disconnect.

**`data_ready` / `rx_buf` race between NimBLE callback thread and Arduino loop:**
- Symptoms: `data_ready` is `volatile bool` and `rx_buf` is a plain `char[]`. NimBLE's `onWrite` callback runs on the BT stack task (a separate FreeRTOS task), while `ble_has_data()` / `ble_get_data()` are called from the Arduino `loop()` task. The `volatile` on `data_ready` provides visibility but not atomicity, and no memory barrier prevents the compiler or CPU from reordering the `memcpy` into `rx_buf` ahead of `data_ready = true`.
- Files: `firmware/src/ble.cpp:126–135`, `firmware/src/ble.cpp:239–246`
- Trigger: Unlikely under typical 60s polling, but theoretically a partial/stale buffer could be parsed during a write. ESP32 is dual-core — if loop() and the BT task run simultaneously on different cores, the race is real.
- Workaround: None currently. A proper fix uses a NimBLE-task-to-loop notification via a FreeRTOS queue, or a mutex around `rx_buf` + `data_ready`.

**`touch_data_ready` ISR flag non-atomic on boards with touch ISR:**
- Symptoms: `touch_data_ready` is set to `true` in an IRAM_ATTR ISR and cleared in `touch_hal_read()` on the Arduino loop task, both sides single-byte boolean. On single-core ESP32-S3, ISRs are atomic wrt the main task when no FreeRTOS task switch occurs mid-read, but the gap between `touch_data_ready = false` and re-reading the I2C transaction leaves a window where a new interrupt fires and sets `data_ready` again, causing the previous read to be discarded.
- Files: `firmware/src/boards/waveshare_amoled_216/touch.cpp:17–34`, `firmware/src/boards/waveshare_amoled_18/touch.cpp:17–65`, `firmware/src/boards/waveshare_amoled_216_c6/touch.cpp`
- Trigger: Fast repeated touch at the same time as the poll interval.
- Workaround: In practice the touch read loop runs on every `loop()` iteration (5ms tick) and finger contact dwell time is many milliseconds, so dropped single events are not perceptible.

---

## Security Considerations

**OAuth token stored in plaintext file on Linux:**
- Risk: The bash daemon reads `$HOME/.claude/.credentials.json` directly via `grep` (line 24 of `claude-usage-daemon.sh`). Any process running as the user can read this token.
- Files: `daemon/claude-usage-daemon.sh:24`
- Current mitigation: Token is stored in user home directory with default file permissions. macOS version correctly uses the system Keychain.
- Recommendations: Linux should ideally use the GNOME Keyring or `secret-tool` for token storage rather than plaintext file access. At minimum, document the exposure.

**BLE bonding uses "SC" (Secure Connections) without MITM — accepts any bond:**
- Risk: `NimBLEDevice::setSecurityAuth(true, false, true)` enables bonding and SC but disables MITM protection. Any device that initiates pairing can bond without user confirmation (no pin, no numeric comparison).
- Files: `firmware/src/ble.cpp:151`
- Current mitigation: The device name `"Claude Controller"` and custom service UUID are not widely known. The data channel carries only rate-limit utilization percentages (no private content).
- Recommendations: For a desk device, this is an acceptable tradeoff — the payload is non-sensitive. If used in a shared or public space, enabling MITM and displaying a confirm pin would be appropriate.

---

## Performance Bottlenecks

**CPU pixel-remapping rotation is O(w×h) per LVGL strip flush:**
- Problem: On the AMOLED-2.16 with rotation enabled, every 480×40 partial strip is remapped pixel-by-pixel in `rotate_strip()` before being sent to the panel.
- Files: `firmware/src/boards/waveshare_amoled_216/display.cpp:45–98`
- Cause: CO5300 MADCTL does not support column/row swap, so software rotation on the ESP32-S3 is required. At 480×40 × 3 rotation variants, that's ~19 200 pixel operations per strip.
- Improvement path: LVGL partial mode already limits the work to dirty strips. On S3 with dual-core, moving rotation into a secondary core (Task) could pipeline with LVGL rendering. Current approach is functional and fast enough in practice (no observed jitter).

**`find_char_path_by_uuid` in the bash daemon is O(n×characteristics) via D-Bus tree walk:**
- Problem: Every connection cycle the bash daemon calls `busctl tree` and then queries each characteristic's UUID property individually. On a crowded GATT server this is slow (~1–2 seconds with 20+ characteristics).
- Files: `daemon/claude-usage-daemon.sh:116–129`
- Cause: BlueZ D-Bus API doesn't support filtering by UUID in the tree walk; the daemon does a linear scan.
- Improvement path: The Python daemon does not have this problem (bleak handles characteristic discovery natively). Switching to the Python daemon eliminates this.

---

## Fragile Areas

**`board_init.cpp` init order constraint (XCA9554 / ALDO3 must precede display):**
- Files: `firmware/src/boards/waveshare_amoled_18/board_init.cpp`, `firmware/src/boards/waveshare_amoled_216_c6/board_init.cpp`
- Why fragile: If a new port's `board_init()` forgets to release the IO expander reset lines (AMOLED-1.8) or pulse the ALDO3 LCD reset (C6), `gfx->begin()` succeeds but the display stays black. The failure is silent — no error return from the GFX library.
- Safe modification: Always verify with a screenshot after changing `board_init.cpp`. The documented constraint is in CLAUDE.md critical gotchas §9 but easy to miss when porting.
- Test coverage: No automated test; relies on visual inspection via `screenshot.sh`.

**`resolve_group_lists()` in `splash.cpp` depends on string-matching animation names:**
- Files: `firmware/src/splash.cpp:57–72`
- Why fragile: `GROUP_NAMES` hardcodes animation names like `"expression sleep"`, `"dance bounce dj"`. If `tools/convert_to_c.js` regenerates `splash_animations.h` and any animation is renamed or removed, the group silently drops to 0 members (`group_size[g] == 0`) and `splash_pick_for_current_rate()` silently no-ops for that usage tier (no animal shown, no error).
- Safe modification: After regenerating `splash_animations.h`, verify that all 12 named animations still exist in the generated file.
- Test coverage: None. A build-time check (static_assert on SPLASH_ANIM_COUNT ranges or a post-build validator) would catch regressions.

**`compute_layout()` breakpoints cover only two known display heights:**
- Files: `firmware/src/ui.cpp:51–88`
- Why fragile: The layout has exactly two branches: `c.height >= 460` (large, tuned for 480×480) and the `else` (compact, tuned for 368×448). A new board with height 400 px or 320 px falls into the compact branch without pixel-perfect validation. Labels and panels may overflow or leave awkward gaps.
- Safe modification: After porting, always use `screenshot.sh` to visually inspect all three screens. Add a new breakpoint in `compute_layout()` for significantly different geometries rather than relying on the fallback.
- Test coverage: Manual screenshot only.

**`splat_next()` / `splash_pick_for_current_rate()` can produce a cast to int8_t overflow if `SPLASH_ANIM_COUNT > 127`:**
- Files: `firmware/src/splash.cpp:42`, `firmware/src/splash.cpp:205`
- Why fragile: `group_lists[GROUP_COUNT][GROUP_MAX]` stores animation indices as `int8_t`, capped at 127. With 13 current animations this is fine. If the animation library grows past 127 entries, indices silently wrap negative.
- Safe modification: Change `int8_t` to `int16_t` (or `uint8_t` with 255 as sentinel) before adding more than ~120 animations.

---

## Scaling Limits

**BLE payload size (512 bytes) is undocumented on daemon side:**
- Current capacity: `BLE_BUF_SIZE 512` in `firmware/src/ble.cpp:14`. The daemon sends compact JSON (~60–80 bytes). The BLE GATT max write without response is typically 247 bytes (ATT_MTU 251 − 3 header − 1 opcode), negotiable to 512 with MTU exchange.
- Limit: If the Anthropic API response headers grow (new rate-limit fields, longer status strings), the daemon-side JSON payload could exceed 512 bytes and be silently truncated at `std::min(val.length(), BLE_BUF_SIZE-1)`.
- Scaling path: `BLE_BUF_SIZE` can be increased; ensure the daemon and firmware values are kept in sync. Add a daemon-side assertion that the serialized payload is under the limit.

**LVGL canvas buffer for splash is uncapped on PSRAM boards (up to 480×480 = ~460 KB):**
- Current capacity: PSRAM boards allocate the full `canvas_w × canvas_h × 2` bytes from SPIRAM. 480×480×2 = ~460 KB.
- Limit: On an 8 MB SPIRAM S3, this is ~5.6% of available SPIRAM alongside the LVGL draw buffers (~38 KB), rot_buf (~38 KB), screenshot buffer (another ~460 KB when active), and NimBLE stack. No total SPIRAM budget is tracked.
- Scaling path: A memory budget comment in `main.cpp` listing all large SPIRAM allocations would prevent accidental OOM as new features are added.

---

## Dependencies at Risk

**Hardcoded Anthropic API beta header (`anthropic-beta: oauth-2025-04-20`):**
- Risk: The `oauth-2025-04-20` beta feature flag may be retired by Anthropic, renamed, or changed to a new date string. Both daemons hardcode it in two places.
- Impact: If the flag is retired and required, API calls return 400/422 and the device shows stale data indefinitely.
- Files: `daemon/claude-usage-daemon.sh:205`, `daemon/claude_usage_daemon.py:42`
- Migration plan: Track Anthropic API changelogs. The flag is currently needed for OAuth token auth; if OAuth becomes stable API, the beta header can be dropped. Extract to a named constant in both daemons.

**Hardcoded `claude-haiku-4-5-20251001` model name:**
- Risk: Model names at Anthropic include date suffixes that are deprecated on a 6–12 month cycle. The model is used only to trigger a 1-token API call for rate-limit header extraction — any available model works.
- Impact: When this model is deprecated, the API returns a 404/400 and the device stops updating.
- Files: `daemon/claude-usage-daemon.sh:208`, `daemon/claude_usage_daemon.py:47`
- Migration plan: Change to the then-current cheapest available model (e.g., `claude-haiku-3-5-20241022` or newer). Consider using a well-known stable alias if Anthropic introduces one.

**Pinned `pioarduino/platform-espressif32` at version `55.03.38-1`:**
- Risk: The platform is pinned by download URL in `firmware/platformio.ini`. If the GitHub release is deleted or moved, a clean build fails with a 404. Newer versions of the platform may include bug fixes needed for future Arduino Core 3.x support.
- Impact: `pio run` fails on a clean machine if the release URL is unavailable.
- Files: `firmware/platformio.ini` (all three `[env:...]` blocks)
- Migration plan: Once a newer pioarduino release validates against all three boards, update the URL. Keep a local `.pio/` cache committed or use PlatformIO Registry packages when they become available.

---

## Missing Critical Features

**No error display when BLE write fails after successful parse:**
- Problem: If `write_gatt` in the bash daemon fails (e.g., mid-connection drop), `poll()` returns 1 (failure) but `LAST_POLL` is not updated, causing an immediate retry on the next 5s tick. The device UI has no "data stale" indicator — it shows the last received values indefinitely with no timeout.
- Blocks: Users have no way to distinguish "connected and up to date" from "connected but stale for 10 minutes."

**No firmware OTA update mechanism:**
- Problem: Firmware updates require a physical USB cable and `pio run -t upload`. There is no BLE DFU or USB-triggered OTA path.
- Blocks: Remote update for deployed devices; any fix or feature requires physical access.

---

## Test Coverage Gaps

**Zero automated tests for any firmware logic:**
- What's not tested: `usage_rate_group()` ring-buffer logic, `parse_json()` edge cases (malformed JSON, truncated payload, missing fields), idle state machine transitions in `idle.cpp`, `format_reset_time()` boundary cases.
- Files: `firmware/src/usage_rate.cpp`, `firmware/src/main.cpp:99–115`, `firmware/src/idle.cpp`
- Risk: Regressions in ring-buffer math or JSON parsing are only caught at runtime on physical hardware.
- Priority: High for `usage_rate.cpp` (pure C++ logic, easily unit-testable in a native env). Medium for `idle.cpp` and `parse_json`.

**No CI pipeline — build correctness is manually verified:**
- What's not tested: Whether any of the three PlatformIO environments compile cleanly after a change.
- Files: All firmware source; no `.github/workflows/` or equivalent exists.
- Risk: A change to a shared header can silently break one of the three board builds without the author noticing.
- Priority: Medium. A GitHub Actions job running `pio run -e waveshare_amoled_216 -e waveshare_amoled_18 -e waveshare_amoled_216_c6` on every PR would catch most regressions.

**`daemon/test_macos_connect.py` is a one-off script, not an automated test:**
- What's not tested: The macOS Python daemon's connection and polling flow are only exercised by manual testing.
- Files: `daemon/test_macos_connect.py`
- Risk: Changes to the Python daemon's `retrieve_connected_macos()` or `poll_api()` logic aren't caught until runtime.
- Priority: Low — the daemon is straightforward async code that's difficult to test without hardware.

---

*Concerns audit: 2026-06-01*
