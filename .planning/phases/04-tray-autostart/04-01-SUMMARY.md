---
phase: 04-tray-autostart
plan: 01
subsystem: daemon/icon-assets
tags: [tdd, pillow, icon, rgb565, tray, python]
requirements: [APP-01]
dependency_graph:
  requires: []
  provides: [daemon/icon_assets.py]
  affects: [daemon/tray_windows.py (04-03 consumes build_state_icons)]
tech_stack:
  added: [Pillow (PIL.Image, PIL.ImageDraw)]
  patterns: [TDD RED/GREEN, RGB565->RGB888 rounding, RGBA planar parse, corner-bubble compositor]
key_files:
  created:
    - daemon/icon_assets.py
    - daemon/tests/test_windows_icon.py
  modified: []
decisions:
  - "BRAND_HEX=#DE7552 derived from logo.h dominant opaque pixel (0xDBAA), not invented"
  - "RGB565->RGB888 uses (c*255 + max//2)//max per channel — NOT *8 bit-shift (matches firmware rendering)"
  - "BUBBLE dict uses locked colors from RESEARCH: connected (60,200,90,255), scanning (240,180,40,255), error (220,60,60,255)"
  - "state_icon raises KeyError on unknown state — no silent fallback per plan anti-pattern"
  - "No pystray or winreg imports in icon_assets.py — fully off-Windows importable"
  - "All three state images built once via build_state_icons; never recomposite per tick"
metrics:
  duration: 12min
  completed: 2026-06-01
  tasks_completed: 2
  files_created: 2
---

# Phase 4 Plan 1: Icon Asset Layer (logo.h parse + state-bubble compositor) Summary

**One-liner:** Pillow-based pure icon layer: logo.h RGB565A8 -> 80x80 RGBA + per-state corner-bubble compositor building three distinct 32x32 tray icons.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 (RED) | Add failing tests for logo parse + RGB565 expand | b6a98ae | daemon/tests/test_windows_icon.py |
| 1 (GREEN) | Implement _expand565 + load_logo_rgba | b6da724 | daemon/icon_assets.py |
| 2 (GREEN) | Implement state_icon + build_state_icons (same feat commit) | b6da724 | daemon/icon_assets.py |

## What Was Built

`daemon/icon_assets.py` — pure, off-Windows-importable helper module with:

- `_expand565(v: int) -> tuple[int,int,int]`: expands 16-bit RGB565 to RGB888 with proper per-channel rounding `(c*255 + max//2)//max`. Correctly handles all edge cases: 0x0000->(0,0,0), 0xFFFF->(255,255,255), 0xDBAA->(222,117,82).
- `load_logo_rgba(header_path: str) -> Image.Image`: regex-parses the `logo_data[19200]` C array from `firmware/src/logo.h`, asserts `len == W*H*3` before indexing (ASVS V5 bound-check), splits the RGB565/alpha planes, returns an 80x80 RGBA Pillow Image.
- `state_icon(base, state, size=32) -> Image.Image`: resizes base with LANCZOS, composites a `size//3`-radius filled circle in the bottom-right corner using `BUBBLE[state]` (KeyError on unknown state — no silent fallback).
- `build_state_icons(base, size=32) -> dict`: returns all three state images pre-built (build once at startup, never recomposite per tick).
- Module-level constants: `W=80`, `H=80`, `BRAND_HEX="#DE7552"`, `BUBBLE` dict.

`daemon/tests/test_windows_icon.py` — 6 TDD tests:
- `test_logo_parse`: 80x80 RGBA, dominant opaque color (222,117,82)
- `test_rgb565_expand`: correct rounding for 0xDBAA/0x0000/0xFFFF
- `test_logo_parse_bounds_check`: ValueError on malformed header length
- `test_state_icon_bubble`: distinct 32x32 images per state; bottom-right corner nearest correct bubble color
- `test_build_icons_once`: dict with connected/scanning/error keys, all distinct
- `test_state_icon_unknown_state`: KeyError/ValueError on unknown state

## TDD Gate Compliance

| Gate | Commit | Status |
|------|--------|--------|
| RED (test commit) | b6a98ae | PASS — tests imported non-existent module, confirmed ImportError |
| GREEN (feat commit) | b6da724 | PASS — all 6 tests pass after implementation |
| REFACTOR | N/A | No refactor needed — code was clean |

## Deviations from Plan

None — plan executed exactly as written.

The test file was written to cover both Task 1 and Task 2 behaviors in a single RED commit (per standard TDD at the plan level for a `type: tdd` plan), and the implementation satisfied all tests in a single GREEN commit.

## Verification

```
python -m pytest daemon/tests/test_windows_icon.py::test_logo_parse daemon/tests/test_windows_icon.py::test_rgb565_expand -x -q
# 2 passed

python -m pytest daemon/tests/test_windows_icon.py -x -q
# 6 passed

python -m pytest daemon/tests/ -q
# 53 passed (47 prior + 6 new)

grep -E "import (pystray|winreg)" daemon/icon_assets.py
# (no output — PASS)
```

## Self-Check: PASSED

- [x] `daemon/icon_assets.py` exists with `def load_logo_rgba(`, `def _expand565(`, `def state_icon(`, `def build_state_icons(`, `BRAND_HEX = "#DE7552"`, `BUBBLE` dict
- [x] No pystray/winreg imports in icon_assets.py
- [x] RED commit b6a98ae exists in git log
- [x] GREEN commit b6da724 exists in git log
- [x] 6 new tests pass; full suite 53 passed

## Known Stubs

None — all functions are fully implemented and wired to the real logo.h asset. The dominant opaque color test verifies the actual pixel data is read correctly.

## Threat Flags

None — module handles only image bytes (no token, no credentials, no network). ASVS V5 bound-check is implemented in `load_logo_rgba`.
