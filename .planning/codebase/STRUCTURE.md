# Codebase Structure

**Analysis Date:** 2026-06-01

## Directory Layout

```
Clawdmeter/
├── firmware/                   # ESP32 firmware (PlatformIO project)
│   ├── platformio.ini          # Build environments (one per board)
│   └── src/
│       ├── main.cpp            # setup() + loop() — shared, board-agnostic
│       ├── ble.cpp / ble.h     # NimBLE GATT peripheral + HID keyboard
│       ├── ui.cpp / ui.h       # LVGL 3-screen UI + responsive layout
│       ├── splash.cpp / splash.h  # 20×20 pixel-art animation engine
│       ├── idle.cpp / idle.h   # Auto-sleep / brightness fade state machine
│       ├── idle_cfg.h          # Tunables: timeout, fade durations, brightness
│       ├── usage_rate.cpp / .h # Session pct rate-of-change → 4 group index
│       ├── data.h              # UsageData struct (BLE payload shape)
│       ├── theme.h             # Design tokens (LVGL color macros)
│       ├── icons.h             # Icon pixel arrays (RGB565A8 battery, RGB565 rest)
│       ├── logo.h              # 80×80 RGB565 Anthropic logo
│       ├── splash_animations.h # Generated: 13 pixel-art animation catalogs
│       ├── font_tiempos_56.c   # Pre-compiled LVGL 9 bitmap fonts
│       ├── font_tiempos_34.c
│       ├── font_styrene_48.c   # Styrene family: 48/28/24/20/16/14/12
│       ├── font_styrene_*.c
│       ├── font_mono_32.c      # Mono: 32/18
│       ├── font_mono_18.c
│       ├── hal/                # Board-agnostic HAL interface headers
│       │   ├── board_caps.h    # BoardCaps struct + board_caps() declaration
│       │   ├── display_hal.h   # init/begin/set_brightness/draw_bitmap/tick/round_area
│       │   ├── touch_hal.h     # init/read(x,y,pressed)
│       │   ├── input_hal.h     # init/is_held(PRIMARY|SECONDARY)
│       │   ├── power_hal.h     # init/tick/battery_pct/is_charging/pwr_pressed
│       │   └── imu_hal.h       # init/tick/rotation_quadrant
│       └── boards/             # One subfolder per supported board
│           ├── template/       # Copy-and-fill scaffolding for new ports
│           ├── waveshare_amoled_216/   # CO5300 480×480, CST9220, QMI8658 rotation
│           ├── waveshare_amoled_18/    # SH8601 368×448, FT3168, XCA9554 expander
│           └── waveshare_amoled_216_c6/ # CO5300 480×480 on ESP32-C6 (no PSRAM)
├── daemon/                     # Host-side BLE daemon
│   ├── claude-usage-daemon.sh  # Linux (bluetoothctl + D-Bus)
│   ├── claude_usage_daemon.py  # macOS (CoreBluetooth via bleak)
│   ├── claude-usage-daemon.service  # systemd user unit
│   ├── com.user.claude-usage-daemon.plist  # launchd plist (macOS)
│   └── test_macos_connect.py   # macOS BLE connection smoke test
├── tools/                      # Asset pipeline scripts (Node.js)
│   ├── png_to_lvgl.js          # PNG → RGB565A8 C array for icons.h
│   ├── scrape_claudepix.js     # Fetch pixel-art JSONs from claudepix.vercel.app
│   ├── convert_to_c.js         # JSON animations → splash_animations.h
│   └── claudepix_data/         # Cached scrape output (JSON per animation)
├── docs/
│   └── porting/
│       ├── adding-a-board.md   # Step-by-step porting guide
│       ├── hal-contract.md     # HAL function contracts and invariants
│       └── capability-flags.md # When to use BoardCaps vs BOARD_HAS_*
├── assets/                     # Source PNGs for icons (before conversion)
├── screenshots/                # Captured framebuffer screenshots
│   └── amoled_18/
├── screenshot.sh               # Serial capture tool → PNG (uses pio Python)
├── flash.sh                    # Linux flash helper
├── flash-mac.sh                # macOS flash helper
├── install.sh                  # Linux daemon install + systemd enable
├── install-mac.sh              # macOS daemon install + launchd load
├── CLAUDE.md                   # Project context for Claude Code sessions
└── README.md
```

## Board Folder Contents

Every board folder under `firmware/src/boards/<name>/` contains exactly these files:

| File | Purpose |
|------|---------|
| `board.h` | Compile-time pin constants, I2C addresses, `BOARD_HAS_*` flags. Never included by shared code. |
| `board_init.cpp` | `extern "C" void board_init()` — Wire.begin + optional IO expander init. Called first in `setup()`. |
| `display.cpp` | Implements `display_hal.h` — constructs GFX driver, handles QSPI push, optional CPU rotation. |
| `touch.cpp` | Implements `touch_hal.h` — driver init, ISR or polling, latches state for `touch_hal_read()`. |
| `input.cpp` | Implements `input_hal.h` — GPIO read for PRIMARY/SECONDARY buttons. |
| `power.cpp` | Implements `power_hal.h` — AXP2101 via XPowersLib; edge-detects PWR button. |
| `imu.cpp` | Implements `imu_hal.h` — QMI8658 init + rotation quadrant; no-op stub if rotation disabled. |
| `caps.cpp` | Returns `const BoardCaps&` for this board — dimensions, button_count, has_* flags. |
| `io_expander.cpp/.h` | Board-private (AMOLED-1.8 only) — XCA9554/PCA9554 I2C IO expander driver. |

## Key File Locations

**Entry Points:**
- `firmware/src/main.cpp`: `setup()` (line 179) and `loop()` (line 229)
- `firmware/platformio.ini`: build env definitions — one `[env:...]` block per board

**HAL Interfaces (read these to understand contracts):**
- `firmware/src/hal/board_caps.h`: `BoardCaps` struct fields
- `firmware/src/hal/display_hal.h`: display contract
- `firmware/src/hal/power_hal.h`: power/button contract

**Board Implementations (read for reference when porting):**
- `firmware/src/boards/waveshare_amoled_216/display.cpp`: CPU rotation strip algorithm
- `firmware/src/boards/waveshare_amoled_18/touch.cpp`: minimal vendored FT3168 I2C reader
- `firmware/src/boards/waveshare_amoled_18/io_expander.cpp`: XCA9554 driver pattern
- `firmware/src/boards/template/board.h`: canonical TODO template for new ports

**UI & Layout:**
- `firmware/src/ui.cpp`: `compute_layout()` at line 51 — breakpoint logic (H >= 460 → large, else compact)
- `firmware/src/theme.h`: all LVGL color macros
- `firmware/src/data.h`: `UsageData` struct fields

**Splash Animations:**
- `firmware/src/splash_animations.h`: generated — do not hand-edit (run `tools/convert_to_c.js`)
- `firmware/src/splash.cpp`: group assignment table at line 46 (`GROUP_NAMES`)

**Configuration:**
- `firmware/src/idle_cfg.h`: idle timeout, fade durations, brightness, sleep-on-charge policy

**Host Daemon:**
- `daemon/claude-usage-daemon.sh`: Linux main daemon
- `daemon/claude_usage_daemon.py`: macOS main daemon

## Naming Conventions

**Files:**
- Shared firmware modules: `snake_case.cpp` / `snake_case.h` (e.g., `usage_rate.cpp`)
- HAL headers: `<subsystem>_hal.h` pattern (e.g., `display_hal.h`, `power_hal.h`)
- Board headers: `board.h` (identical name in every board folder — disambiguated by path)
- Font files: `font_<family>_<size>.c` (e.g., `font_styrene_28.c`, `font_mono_18.c`)
- Generated assets: `splash_animations.h`, `icons.h`, `logo.h` — header-only C arrays

**Directories:**
- Board folders: `<vendor>_<product>_<size>` (e.g., `waveshare_amoled_216`)
- PlatformIO env names match board folder names exactly (e.g., `[env:waveshare_amoled_216]`)

**Symbols:**
- HAL functions: `<subsystem>_hal_<verb>()` (e.g., `display_hal_draw_bitmap`, `power_hal_pwr_pressed`)
- Board caps accessor: `board_caps()` — returns `const BoardCaps&`
- Board init: `board_init()` — declared `extern "C"` in `main.cpp`, defined in each `board_init.cpp`
- Compile-time flags: `BOARD_HAS_<FEATURE>` (e.g., `BOARD_HAS_ROTATION`, `BOARD_HAS_PSRAM`)
- Build identity flags: `BOARD_AMOLED_216`, `BOARD_AMOLED_18`, `BOARD_AMOLED_216_C6` — set in `platformio.ini`; only used inside board-private code, never in shared code

## Where to Add New Code

**New board port:**
1. Copy `firmware/src/boards/template/` to `firmware/src/boards/<your_board>/`
2. Fill `board.h` (pins, addresses, `BOARD_HAS_*` flags)
3. Implement all seven `.cpp` files (display, touch, input, power, imu, caps, board_init)
4. Add `[env:<your_board>]` block to `firmware/platformio.ini` with matching `build_src_filter`
5. Never edit `main.cpp`, `ui.cpp`, or any `hal/` header

**New UI screen:**
- Add enum value to `screen_t` in `firmware/src/ui.h`
- Add widget construction in `firmware/src/ui.cpp`; extend `compute_layout()` if new layout values are needed
- Add case to `ui_cycle_screen()` and `ui_show_screen()` in `firmware/src/ui.cpp`

**New board capability flag:**
- Add `bool has_<feature>` to `BoardCaps` in `firmware/src/hal/board_caps.h`
- Update all `caps.cpp` files with the new field
- Add `BOARD_HAS_<FEATURE>` compile-time define to affected `board.h` files
- See `docs/porting/capability-flags.md` for the decision guide

**New icon:**
- Convert source PNG: `node tools/png_to_lvgl.js <input.png> ICON_<NAME> [W] [H] [--tint=RRGGBB]`
- Splice output into `firmware/src/icons.h`
- Use `init_icon_dsc_rgb565a8()` in `ui.cpp` for icons over non-uniform backgrounds

**New splash animation:**
1. Run `node tools/scrape_claudepix.js` to refresh `tools/claudepix_data/`
2. Run `node tools/convert_to_c.js` to regenerate `firmware/src/splash_animations.h`
3. Assign to a usage-rate group in `GROUP_NAMES` in `firmware/src/splash.cpp:46`

**Shared utility/helper:**
- Place in `firmware/src/` as a new `<name>.cpp` + `<name>.h` pair
- Keep it board-agnostic; if it needs board info, call `board_caps()`

## Special Directories

**`firmware/.pio/`:**
- Purpose: PlatformIO build cache, downloaded libraries, compiled objects
- Generated: Yes
- Committed: No (in `.gitignore`)

**`tools/claudepix_data/`:**
- Purpose: Cached JSON from claudepix.vercel.app scraper; intermediate step before C generation
- Generated: Yes (by `tools/scrape_claudepix.js`)
- Committed: Yes (avoids re-scraping on every build)

**`.planning/codebase/`:**
- Purpose: Codebase analysis documents for GSD planning tools
- Generated: Yes (by `/gsd:map-codebase`)
- Committed: Yes

**`screenshots/`:**
- Purpose: Captured framebuffer PNGs from `screenshot.sh` for UI iteration QA
- Generated: Yes
- Committed: Selectively (reference screenshots for documentation)

---

*Structure analysis: 2026-06-01*
