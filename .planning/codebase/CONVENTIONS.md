# Coding Conventions

**Analysis Date:** 2026-06-01

## Naming Patterns

**Files:**
- C++ implementation files use `snake_case.cpp` — e.g. `board_init.cpp`, `io_expander.cpp`, `usage_rate.cpp`
- C++ headers use `snake_case.h` — e.g. `board_caps.h`, `display_hal.h`, `idle_cfg.h`
- HAL headers are named `<subsystem>_hal.h` — e.g. `display_hal.h`, `touch_hal.h`
- Board-private headers follow `<subsystem>.h` within the board folder — e.g. `io_expander.h`
- Generated files are explicitly labelled — e.g. `splash_animations.h` has a "do not hand-edit" comment in CLAUDE.md
- Bash daemon: `claude-usage-daemon.sh`, `claude_usage_daemon.py` (hyphen for shell, underscore for Python)
- Node tools: `snake_case.js` — e.g. `png_to_lvgl.js`, `convert_to_c.js`

**Functions (C++):**
- Public HAL functions: `<module>_hal_<action>` — e.g. `display_hal_init`, `touch_hal_read`, `power_hal_battery_pct`
- Public module functions: `<module>_<action>` — e.g. `ble_init`, `ble_has_data`, `ui_update`, `splash_tick`
- Private / static helper functions: `snake_case` without a module prefix — e.g. `rotate_strip`, `compute_layout`, `start_advertising`, `format_reset_time`
- LVGL callback functions: `<purpose>_cb` — e.g. `my_flush_cb`, `my_touch_cb`, `rounder_cb`, `global_click_cb`, `ble_reset_click_cb`
- ISR functions: `<purpose>_isr` — e.g. `touch_isr`; always marked `static void IRAM_ATTR`
- `board_init()` is declared `extern "C"` so C and C++ translation units agree on the symbol without mangling

**Variables (C++):**
- Module-level statics: `snake_case` — e.g. `state`, `data_ready`, `cached_pct`, `last_poll_ms`
- ISR-shared state: `volatile` keyword always applied — e.g. `volatile bool data_ready`, `volatile bool touch_pressed`
- LVGL widget pointers: `lv_obj_t*` with descriptive prefix — e.g. `lbl_title`, `bar_session`, `lbl_ble_status`, `battery_img`
- Layout struct fields: short `snake_case` — e.g. `scr_w`, `content_y`, `usage_bar_y`
- Constants / compile-time thresholds: `UPPER_SNAKE_CASE` macros — e.g. `BUF_LINES`, `RATE_THRESH_NORMAL`, `IDLE_TIMEOUT_MS`
- nullptr is preferred over NULL for C++ pointer nullability

**Types (C++):**
- Structs: `PascalCase` — e.g. `BoardCaps`, `UsageData`, `Layout`, `Sample`
- Enums: `snake_case_t` suffix — e.g. `ble_state_t`, `screen_t`, `InputButton`
- Enum values: `UPPER_SNAKE_CASE` — e.g. `BLE_STATE_INIT`, `SCREEN_SPLASH`, `INPUT_BTN_PRIMARY`
- Private state enums scoped to the `.cpp` — e.g. `IdleState` in `idle.cpp`
- Callback wrapper classes (NimBLE): `PascalCase` with descriptive name — e.g. `ServerCallbacks`, `RxCallbacks`, `ReqCallbacks`

**Macros:**
- Capability flags: `BOARD_HAS_<FEATURE>` — e.g. `BOARD_HAS_PSRAM`, `BOARD_HAS_ROTATION`, `BOARD_HAS_IO_EXPANDER`
- Board identity: `BOARD_<NAME>` — e.g. `BOARD_AMOLED_216`, `BOARD_AMOLED_18` (set via PlatformIO `build_flags`)
- Pin names: `LCD_CS`, `IIC_SDA`, `TP_INT`, `BTN_BACK_GPIO` — hardware-signal names in UPPER_SNAKE_CASE
- Config tunables: `IDLE_TIMEOUT_MS`, `DISPLAY_DEFAULT_BRIGHTNESS` — in `idle_cfg.h` so nothing is hard-coded in logic files
- LVGL widget counts and array sizes: `SPINNER_COUNT`, `ANIM_MSG_COUNT`, `GROUP_COUNT`

**Bash (daemon):**
- Global constants / config: `UPPER_SNAKE_CASE` — e.g. `DEVICE_NAME`, `POLL_INTERVAL`, `SAVED_MAC_FILE`
- Functions: `snake_case` — e.g. `log`, `read_token`, `scan_for_device`, `connect_device`, `write_gatt`, `start_notify_subscriber`
- Local variables: `snake_case` — e.g. `adapter`, `scan_pid`, `found`

**Python (daemon):**
- Module-level constants: `UPPER_SNAKE_CASE` — e.g. `DEVICE_NAME`, `RX_CHAR_UUID`, `POLL_INTERVAL`
- Functions: `snake_case` — e.g. `log`, `discover_target`, `_extract_access_token`
- Private helpers: `_underscore_prefix` — e.g. `_extract_access_token`
- Type annotations used throughout

**Node (tools):**
- Functions: `camelCase` — e.g. `rgb565`, `hexToRgb565`, `paletteToRgb565`, `safeIdent`
- Constants: `UPPER_SNAKE_CASE` — e.g. `PALETTE_SIZE`, `IN_DIR`, `OUT_FILE`

## Code Style

**Formatting:**
- No dedicated formatter config (`.clang-format`, `.prettierrc`, `biome.json` absent)
- 4-space indentation used consistently throughout C++, Bash, Python, and Node.js
- Single-space alignment in struct initializer lists where fields are multi-line (e.g. `caps.cpp` designated initializer syntax)
- Opening braces on the same line as the function/control statement (`K&R` style)
- Short one-liner functions keep brace on same line — e.g. `const BoardCaps& board_caps(void) { return caps; }`
- Pointer/reference qualifier adjacent to the type: `uint16_t* x`, `const BoardCaps&`
- `(void)` explicit empty parameter lists on functions that take no arguments — enforced for HAL function signatures

**Linting:**
- No `.eslintrc` or equivalent configured
- PlatformIO compiler flags enforce warnings by default
- No static analysis tool detected

## Import / Include Organization

**C++ order:**
1. HAL implementation header (relative, `../../hal/<name>.h`) as the first include in any HAL implementation file
2. Board-private header (`board.h`) second
3. Arduino standard libraries (`<Arduino.h>`, `<Wire.h>`)
4. Third-party vendor libraries (`<lvgl.h>`, `<NimBLEDevice.h>`, `<XPowersLib.h>`)
5. Project headers (`"data.h"`, `"ui.h"`, `"splash.h"`)

```cpp
// Example from boards/waveshare_amoled_216/display.cpp:
#include "../../hal/display_hal.h"   // HAL contract first
#include "../../hal/imu_hal.h"
#include "board.h"                   // board-private constants
#include <Arduino.h>                 // Arduino core
#include <Arduino_GFX_Library.h>    // vendor library
#include <esp_heap_caps.h>
#include <lvgl.h>
```

**Path aliases:** None — relative paths (`../../hal/`) used directly.

## Preprocessor / Conditional Compilation

**Policy: no `#ifdef BOARD_*` in shared code** (`main.cpp`, `ui.cpp`, `splash.cpp`, HAL headers). This is a hard rule; the entire device-abstraction refactor removed ~30 such blocks.

**Legitimate uses:**
- `#ifdef BOARD_HAS_PSRAM` in `main.cpp` for LVGL buffer sizing — capability-based, not board-identity based
- `#ifndef BOARD_HAS_PSRAM` in `main.cpp`'s `send_screenshot()` — guards an operation that physically cannot work without PSRAM
- `BOARD_AMOLED_18` / `BOARD_AMOLED_216` set in PlatformIO `build_flags` but consumed only inside board-specific `.cpp` files when truly necessary
- `#pragma once` used universally in all header files (no traditional include guards)

**Capability checks in shared code use `board_caps()`:**
```cpp
// Correct — runtime capability gate:
if (board_caps().button_count >= 2) { /* secondary button logic */ }

// Wrong — never do this in shared code:
// #ifdef BOARD_AMOLED_216
```

## Error Handling

**Firmware strategy:** Log to `Serial` and return early / degrade gracefully. No exceptions (bare-metal C++). No assert-style crashes.

**Patterns:**
- Init failures: print diagnostic to `Serial` and return (hardware continues without the subsystem)
  ```cpp
  if (!pmu.begin(Wire, AXP2101_ADDR, IIC_SDA, IIC_SCL)) {
      Serial.println("AXP2101 init failed");
      return;
  }
  ```
- Null-pointer guards before any driver call: `if (gfx) gfx->setBrightness(level);`
- I2C read failures: set `touch_pressed = false` and return — caller gets last known state
- JSON parse errors: `Serial.printf("JSON parse error: %s\n", err.c_str()); return false;`
- Memory allocation failures: check `nullptr` after `heap_caps_malloc`, print `SCREENSHOT_ERR`, return
- BLE write failures: `ble_send_nack()` — daemon retries on next tick

**Daemon (Bash) strategy:** Functions return non-zero on failure; callers use `||` patterns:
```bash
scan_for_device || { log "Device not found, retrying..."; sleep "$BACKOFF"; continue; }
```

**Python daemon:** Exceptions caught at the `asyncio` task level; logged via `log()` and retried.

## Logging

**Firmware:** `Serial.printf` / `Serial.println` throughout. No structured logging framework.

**Patterns:**
- Init success/failure: `Serial.println("AXP2101 init OK")` / `Serial.println("AXP2101 init failed")`
- Module prefix in message string: `Serial.printf("BLE: advertising start=%s\n", ...)`
- Numeric state changes logged: `Serial.printf("Rotation: %d\n", current_rotation)`
- Boot readiness signaled as JSON: `Serial.println("{\"ready\":true}")` — consumed by `screenshot.sh`
- Screenshot protocol uses `Serial.printf("SCREENSHOT_START %lu %lu %lu\n", ...)` / `SCREENSHOT_END` sentinels

**Bash daemon:** `log()` function with timestamp: `echo "[$(date '+%H:%M:%S')] $1"` — always to stdout.

**Python daemon:** `log()` mirrors Bash: `print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)` — `flush=True` ensures output is visible in systemd journals.

## Comments

**When to comment:**
- Non-obvious hardware behaviour: always. Comments explain *why*, not *what* — e.g. why `SCLK=11` differs on the 1.8 board, why `io_expander_init()` must run before `gfx->begin()`
- Register addresses and bit layouts in low-level drivers: inline with each value
- HID descriptor bytes: every byte commented with its meaning
- Algorithm intent: e.g. rotation math in `rotate_strip()`, ring buffer wraparound in `usage_rate.cpp`
- "No-op on boards without X" notes in HAL implementations to confirm intent

**Header file comments:**
- Each HAL header has a module-level doc comment explaining ownership model and non-functional requirements (latency, ordering)
- `board.h` files open with a one-line board description comment
- `idle_cfg.h` explains each tunable with a short rationale comment

**Inline comments:**
- HEX values with semantic meaning always get a trailing comment: `0x2C, 0  // HID Space, no mods`
- Magic thresholds documented inline: `#define RATE_THRESH_HEAVY  0.33f  // ≤5h, matching or beating the session reset`
- `(void)e;` in unused-parameter suppression is never commented — understood C idiom

**Do not comment:**
- Self-explanatory getter implementations
- Standard Arduino setup boilerplate

## Function Design

**Size:** Functions stay focused — `init_*` functions build one screen or one subsystem. Shared helpers are extracted when a pattern appears twice (e.g. `make_panel()`, `make_bar()`, `format_reset_time()`).

**Parameters:** Output parameters use pointer (`uint16_t* x`) rather than C++ references in HAL interfaces — keeps the ABI consistent and makes mutation visible at call sites (`touch_hal_read(&x, &y, &pressed)`).

**Return values:**
- `bool` for success/failure: `bool io_expander_init(void)`, `bool ble_has_data(void)`
- `-1` as a sentinel for "not available": `power_hal_battery_pct()` returns `-1` when battery info is meaningless
- Edge-triggered flags cleared on read: `power_hal_pwr_pressed()` returns `true` once per press, then resets

**`extern "C"` boundary:** `board_init()` is declared `extern "C"` in `main.cpp` to avoid C++ name mangling when linking the board-specific translation unit.

## Module Design

**Exports:** Each module (`.h` + `.cpp` pair) exposes only what callers need. All internal state is `static` file-scope. No global variables.

**HAL modules (`hal/*.h`):** Pure interface headers — function declarations only, no implementation, no board-specific includes. All state lives in the per-board `boards/<name>/*.cpp` implementations.

**Board modules:** Each board folder is self-contained. Board-private drivers (e.g. `io_expander.h/.cpp`) are not exposed in `hal/` and are not visible to shared code.

**Configuration separation:** All tunables for a subsystem live in a dedicated `_cfg.h` file (`idle_cfg.h`). Logic files (`idle.cpp`) include the cfg header but never hard-code values.

**Splash animations:** `splash_animations.h` is generated by `tools/convert_to_c.js` and is never hand-edited. The pipeline comment at the top of the file serves as the regeneration recipe.

---

*Convention analysis: 2026-06-01*
