<!-- refreshed: 2026-06-01 -->
# Architecture

**Analysis Date:** 2026-06-01

## System Overview

```text
┌──────────────────────────────────────────────────────────────────┐
│                        Host Side (Daemon)                        │
│   daemon/claude-usage-daemon.sh  /  daemon/claude_usage_daemon.py│
│   Polls Anthropic API → JSON payload → BLE GATT write            │
└─────────────────────────────┬────────────────────────────────────┘
                              │ BLE GATT (custom service 4c41555a-…0001)
                              │ RX char (…0002): daemon writes JSON
                              │ REQ char (…0004): device notifies refresh req
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                   firmware/src/main.cpp                          │
│   setup() + loop() — HAL calls only, zero #ifdef BOARD_*         │
│   Orchestrates: BLE → JSON parse → UsageData → UI update         │
│   Physical buttons → HID keyboard events via ble_keyboard_press  │
│   Idle/sleep state machine via idle.h                            │
└────┬───────────────┬──────────────┬──────────────┬───────────────┘
     │               │              │              │
     ▼               ▼              ▼              ▼
┌─────────┐   ┌───────────┐  ┌──────────┐  ┌──────────────────┐
│  ble.h  │   │   ui.h    │  │ splash.h │  │    idle.h        │
│ ble.cpp │   │  ui.cpp   │  │splash.cpp│  │    idle.cpp      │
│ NimBLE  │   │ LVGL 9    │  │pixel-art │  │ brightness fade  │
│ custom  │   │ 3-screen  │  │ 20×20    │  │ 30min timeout    │
│ GATT +  │   │ responsive│  │ engine   │  │ wake-press gate  │
│ HID kbd │   │ layout    │  │          │  │                  │
└─────────┘   └───────────┘  └──────────┘  └──────────────────┘
     │               │              │
     │        ┌──────┴──────┐       │
     │        │ usage_rate.h│       │
     │        │ 4-group rate│       │
     │        │ tracker     │       │
     │        └─────────────┘       │
     │                              │
     └──────────────────────────────┘
     All shared code calls into →
┌──────────────────────────────────────────────────────────────────┐
│                   firmware/src/hal/                              │
│  board_caps.h  display_hal.h  touch_hal.h  input_hal.h           │
│  power_hal.h   imu_hal.h                                         │
│  (pure C++ interfaces — no implementations here)                 │
└─────────────────────────────────────────────────────────────────-┘
     ↑ implemented by exactly one of:
┌──────────────────────────────────────────────────────────────────┐
│  firmware/src/boards/<name>/     (one compiled per PlatformIO env)│
│                                                                   │
│  waveshare_amoled_216/  — CO5300 480×480, CST9220, GPIO18 btn,   │
│                           QMI8658 CPU-rotation, AXP PKEY         │
│  waveshare_amoled_18/   — SH8601 368×448, FT3168, XCA9554 expander│
│                           AXP PMU+battery, no rotation           │
│  waveshare_amoled_216_c6/ — CO5300 480×480 on ESP32-C6, no PSRAM │
│  template/              — empty stubs, copy to bootstrap a port  │
└──────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| `main.cpp` | Arduino setup()/loop(), LVGL glue, JSON parse, button dispatch, idle policy | `firmware/src/main.cpp` |
| `ble.cpp` | NimBLE GATT peripheral + HID keyboard; owns connect/advertise state machine | `firmware/src/ble.cpp` |
| `ui.cpp` | 3-screen LVGL UI (splash, usage, bluetooth); `compute_layout()` responsive sizing | `firmware/src/ui.cpp` |
| `splash.cpp` | 20×20 pixel-art animation engine on an LVGL canvas; usage-rate-driven group picker | `firmware/src/splash.cpp` |
| `idle.cpp` | Screen auto-sleep state machine; brightness fade in/out; wake-press consumption | `firmware/src/idle.cpp` |
| `usage_rate.cpp` | Sliding-window rate-of-change tracker → 4-group index for splash selection | `firmware/src/usage_rate.cpp` |
| `hal/board_caps.h` | Runtime `BoardCaps` struct; each board's `caps.cpp` returns a const reference | `firmware/src/hal/board_caps.h` |
| `hal/display_hal.h` | init/begin/set_brightness/draw_bitmap/tick/round_area interface | `firmware/src/hal/display_hal.h` |
| `hal/touch_hal.h` | init/read(x,y,pressed) interface | `firmware/src/hal/touch_hal.h` |
| `hal/input_hal.h` | init/is_held(PRIMARY\|SECONDARY) interface | `firmware/src/hal/input_hal.h` |
| `hal/power_hal.h` | init/tick/battery_pct/is_charging/pwr_pressed interface | `firmware/src/hal/power_hal.h` |
| `hal/imu_hal.h` | init/tick/rotation_quadrant interface | `firmware/src/hal/imu_hal.h` |
| boards/`<name>`/board.h | Compile-time pin constants + `BOARD_HAS_*` flags for one board | `firmware/src/boards/<name>/board.h` |
| boards/`<name>`/caps.cpp | Returns `const BoardCaps&`; runtime dimensions/feature flags | `firmware/src/boards/<name>/caps.cpp` |
| boards/`<name>`/board_init.cpp | Wire.begin + optional IO expander; called first in setup() | `firmware/src/boards/<name>/board_init.cpp` |
| `daemon/claude-usage-daemon.sh` | Linux BLE daemon; Anthropic API polling; GATT write | `daemon/claude-usage-daemon.sh` |
| `daemon/claude_usage_daemon.py` | macOS BLE daemon; same logic via CoreBluetooth | `daemon/claude_usage_daemon.py` |

## Pattern Overview

**Overall:** Hardware Abstraction Layer (HAL) with compile-time board selection via PlatformIO `build_src_filter`. Shared firmware code never sees board-specific symbols.

**Key Characteristics:**
- Zero `#ifdef BOARD_*` in shared code (`main.cpp`, `ui.cpp`, `splash.cpp`, `ble.cpp`, `idle.cpp`). Board variation is resolved entirely through the HAL interfaces and `BoardCaps`.
- Exactly one board folder is compiled per PlatformIO env (`-<boards/>` then `+<boards/<name>/>` in `build_src_filter`). All other board folders are excluded at the file system level — the linker never sees them.
- Runtime feature gating uses `board_caps()` (e.g., `board_caps().button_count >= 2`). Compile-time dead-stripping uses `BOARD_HAS_*` flags in individual board sources only.
- LVGL 9 partial render mode: two PSRAM-backed strip buffers (`BUF_LINES` rows × display width). `my_flush_cb` → `display_hal_draw_bitmap` → board's panel push.
- BLE exposes two independent GATT roles simultaneously: custom data service (usage JSON) + HID keyboard (Space / Shift+Tab). `CONFIG_BT_NIMBLE_MAX_CONNECTIONS=2` enables both in parallel.

## Layers

**Board Port Layer:**
- Purpose: Translate HAL contracts to specific hardware chips and GPIO topology
- Location: `firmware/src/boards/<name>/`
- Contains: `board.h` (pins, addresses, `BOARD_HAS_*`), `display.cpp`, `touch.cpp`, `input.cpp`, `power.cpp`, `imu.cpp`, `caps.cpp`, `board_init.cpp`, optional private drivers (e.g. `io_expander.cpp`)
- Depends on: Arduino BSP, vendor libraries (Arduino_GFX, XPowersLib, SensorLib, touch drivers)
- Used by: HAL interfaces resolved at link time

**HAL Interface Layer:**
- Purpose: Define the contracts shared code compiles against; board implementations satisfy them
- Location: `firmware/src/hal/`
- Contains: Six pure header files (`board_caps.h`, `display_hal.h`, `touch_hal.h`, `input_hal.h`, `power_hal.h`, `imu_hal.h`)
- Depends on: nothing (pure declarations, `<stdint.h>` only)
- Used by: `main.cpp`, `ui.cpp`, `splash.cpp`, `idle.cpp`

**Application Layer:**
- Purpose: Device logic — BLE comms, UI rendering, splash animations, sleep/wake
- Location: `firmware/src/` (shared `.cpp` files)
- Contains: `main.cpp`, `ble.cpp`, `ui.cpp`, `splash.cpp`, `idle.cpp`, `usage_rate.cpp`
- Depends on: HAL interfaces, LVGL 9, NimBLE, ArduinoJson
- Used by: Nothing (top of the firmware stack)

**Asset Layer:**
- Purpose: Pre-compiled fonts, icon bitmaps, logo, generated animation catalog
- Location: `firmware/src/` (header-only data files)
- Contains: `font_*.c`, `icons.h`, `logo.h`, `splash_animations.h`, `theme.h`
- Depends on: nothing (static arrays)
- Used by: `ui.cpp`, `splash.cpp`

**Host Daemon Layer:**
- Purpose: Bridge Anthropic API data to the device over BLE GATT
- Location: `daemon/`
- Contains: `claude-usage-daemon.sh` (Linux/bluetoothctl/D-Bus), `claude_usage_daemon.py` (macOS/CoreBluetooth), systemd unit, launchd plist
- Depends on: OS BLE stack (bluez / CoreBluetooth), curl, Anthropic API OAuth token at `~/.claude/.credentials.json`
- Used by: Nothing (external process)

## Data Flow

### Primary Request Path (BLE data → display update)

1. Daemon polls Anthropic API → sends JSON to GATT RX characteristic (`…0002`) (`daemon/claude-usage-daemon.sh`)
2. `ble_has_data()` returns true in `loop()` (`firmware/src/main.cpp:307`)
3. `parse_json()` deserializes JSON into `UsageData` struct (`firmware/src/main.cpp:99-115`)
4. `usage_rate_sample(usage.session_pct)` updates short-term rate tracker; may trigger `splash_pick_for_current_rate()` (`firmware/src/main.cpp:309-315`)
5. `ui_update(&usage)` pushes new percentages/status to LVGL widgets (`firmware/src/ui.cpp`)
6. LVGL marks dirty widgets → calls `my_flush_cb` → `display_hal_draw_bitmap` → board's QSPI panel push

### Physical Button → HID Keypress

1. `input_hal_is_held(INPUT_BTN_PRIMARY)` polled every loop iteration (`firmware/src/main.cpp:253`)
2. Press edge detected → `idle_consume_wake_press()` decides wake-only or action
3. Action: `ble_keyboard_press(0x2C, 0)` sends HID Space over NimBLE HID characteristic
4. Release edge: `ble_keyboard_release()` clears the report

### PWR Button → Screen Cycle

1. `power_hal_pwr_pressed()` returns edge-triggered true (once per short press) (`firmware/src/main.cpp:281`)
2. If on SCREEN_SPLASH: `splash_next()` cycles pixel-art animation
3. Otherwise: `ui_cycle_screen()` advances through SCREEN_USAGE → SCREEN_BLUETOOTH → SCREEN_SPLASH

### Idle/Sleep Transition

1. No activity for `IDLE_TIMEOUT_MS` (30 min) → `idle_tick()` transitions STATE_AWAKE → STATE_FADING_OUT
2. `display_hal_set_brightness()` called with decreasing values over `IDLE_FADE_OUT_MS` (400ms)
3. STATE_ASLEEP: `display_hal_tick()` skipped, touch events masked in `my_touch_cb`
4. Button press → `idle_consume_wake_press()` returns true (press consumed), STATE_FADING_IN begins
5. Brightness ramps back up over `IDLE_FADE_IN_MS` (180ms); second press acts normally

**State Management:**
- `UsageData usage` — static in `main.cpp`; updated each BLE receive cycle
- `BoardCaps` — static const in each board's `caps.cpp`; accessed via `board_caps()` reference
- BLE state — module-private in `ble.cpp`; polled via `ble_get_state()`
- LVGL widget tree — allocated on heap in `ui_init()`; updated via `ui_update*()` functions
- Idle state machine — module-private in `idle.cpp`; driven by `idle_tick()` each loop

## Key Abstractions

**BoardCaps:**
- Purpose: Runtime board description consumed by UI and main loop — display size, button count, optional feature presence
- Examples: `firmware/src/boards/waveshare_amoled_216/caps.cpp`, `firmware/src/boards/waveshare_amoled_18/caps.cpp`
- Pattern: Each board defines `static const BoardCaps caps = { … }` and `const BoardCaps& board_caps() { return caps; }`. Shared code calls `board_caps().width`, `board_caps().button_count`, etc.

**HAL Functions:**
- Purpose: One-to-one hardware operations that boards implement and shared code calls by name
- Examples: `display_hal_draw_bitmap()`, `touch_hal_read()`, `power_hal_pwr_pressed()`
- Pattern: Pure function declarations in `firmware/src/hal/*.h`; each board provides matching `.cpp`. No virtual dispatch — resolved at link time.

**Layout struct:**
- Purpose: Computed once at `ui_init()` from `board_caps()` dimensions; drives all pixel positions and font choices in the UI without any runtime branching
- Examples: `firmware/src/ui.cpp:23-88` (`struct Layout`, `compute_layout()`)
- Pattern: `if (c.height >= 460)` selects large vs compact breakpoint; all widget builders read from the global `L` struct

**UsageData:**
- Purpose: Normalized usage payload from the Anthropic API; passed through BLE JSON → `parse_json()` → `ui_update()`
- File: `firmware/src/data.h`
- Fields: `session_pct`, `session_reset_mins`, `weekly_pct`, `weekly_reset_mins`, `status[16]`, `ok`, `valid`

## Entry Points

**`setup()` — firmware init:**
- Location: `firmware/src/main.cpp:179`
- Triggers: Arduino framework on boot
- Responsibilities: `board_init()` → HAL inits in dependency order → LVGL init + buffer alloc → `ble_init()` → `ui_init()` → show SCREEN_SPLASH

**`loop()` — firmware main loop:**
- Location: `firmware/src/main.cpp:229`
- Triggers: Arduino framework, runs continuously
- Responsibilities: `idle_tick()`, `lv_timer_handler()`, `ui_tick_anim()`, `ble_tick()`, `power_hal_tick()`, `imu_hal_tick()`, `splash_tick()`, `display_hal_tick()`, button polling, BLE data dispatch. One `delay(5)` at end.

**`board_init()` — board early init:**
- Location: `firmware/src/boards/<name>/board_init.cpp`
- Triggers: Called first inside `setup()`
- Responsibilities: `Wire.begin(SDA, SCL)` + optional `io_expander_init()` to release display/touch from reset before any HAL calls

## Architectural Constraints

- **Threading:** Single-threaded Arduino loop. `touch_isr()` on AMOLED-1.8 is an IRAM_ATTR ISR that sets a volatile flag; actual I2C read happens synchronously in `touch_hal_read()` called from the loop.
- **Global state:** `static UsageData usage` in `main.cpp`; `static Layout L` in `ui.cpp`; per-module static state in `ble.cpp`, `idle.cpp`, `splash.cpp`, `usage_rate.cpp`. All accessed single-threaded.
- **PSRAM dependency:** LVGL strip buffers (`buf1`, `buf2`) and splash canvas buffer require `MALLOC_CAP_SPIRAM`. On `waveshare_amoled_216_c6` (no PSRAM), `BOARD_HAS_PSRAM` is not defined, buffer sizes shrink (`BUF_LINES 20`) and screenshot capture is disabled.
- **Build-time board exclusion:** Only one board folder is compiled per env. `build_src_filter = +<*> -<boards/> +<boards/<name>/>` in `firmware/platformio.ini`. All other board symbol definitions are absent from the build.
- **Circular imports:** None. HAL headers depend only on `<stdint.h>`. Shared code depends on HAL headers and LVGL. Board code depends on HAL headers and board-private vendor libs.
- **LVGL tick source:** `lv_tick_set_cb(my_tick)` uses `millis()` — no FreeRTOS timer dependency.

## Anti-Patterns

### `#ifdef BOARD_*` in shared code

**What happens:** Compiler guards that branch on which board is being built, scattered through `main.cpp`, `ui.cpp`, or other shared files.
**Why it's wrong:** It couples all boards together in one translation unit, defeats the HAL abstraction, and makes every new port require editing shared files.
**Do this instead:** Add a `BoardCaps` field for runtime decisions, or add a `BOARD_HAS_*` flag that is only branched on inside the relevant board's own `.cpp`. See `docs/porting/capability-flags.md`.

### Calling touch controller directly from outside touch.cpp

**What happens:** Calling `CST9220::getPoint()` or equivalent from `main.cpp` or `ui.cpp` rather than through `touch_hal_read()`.
**Why it's wrong:** The controller's I2C transaction is stateful; concurrent callers consume each other's data. Only the board's `touch.cpp` owns the latched state.
**Do this instead:** Always call `touch_hal_read(&x, &y, &pressed)` — the HAL is the single point of access.

### Allocating frame buffers from internal SRAM on PSRAM boards

**What happens:** Using `malloc()` or `MALLOC_CAP_INTERNAL` for LVGL strip buffers or the splash canvas on S3 boards.
**Why it's wrong:** The splash canvas alone is 480×480×2 = ~460 KB; internal SRAM is ~512 KB total. Shared with stack and other allocations, this causes NULL returns and a black screen.
**Do this instead:** Use `heap_caps_malloc(size, MALLOC_CAP_SPIRAM)` on PSRAM-equipped boards. The `#ifdef BOARD_HAS_PSRAM` guard in `main.cpp:28-34` shows the correct pattern.

## Error Handling

**Strategy:** Fail-loud via `Serial.printf` / `Serial.println`; continue running with degraded state where safe (e.g., missing IMU → rotation stays 0, AXP2101 init failure → battery shows -1).

**Patterns:**
- HAL init functions print OK/failure messages over Serial at 115200 baud
- `parse_json()` returns bool; `ble_send_nack()` is called on failure so the daemon can retry
- BLE state is polled each loop and UI updates on state changes (no crash on disconnect)
- Touch ISR sets a volatile flag only; actual I2C failure in `ft3168_read_into_shared_state()` sets `touch_pressed = false` and returns cleanly

## Cross-Cutting Concerns

**Logging:** `Serial.printf` / `Serial.println` at 115200 baud. No structured logging framework. Init messages use `"Foo init OK"` / `"Foo init failed"` convention.
**Validation:** JSON validation handled by ArduinoJson `DeserializationError`; `UsageData.valid` flag gates first-render guard.
**Authentication:** Anthropic API OAuth token read from `~/.claude/.credentials.json` on the host; never transmitted to device. Device BLE is unauthenticated peripheral (bonds via NimBLE pairing).

---

*Architecture analysis: 2026-06-01*
