# Phase 4: Tray & Autostart - Pattern Map

**Mapped:** 2026-06-01
**Files analyzed:** 9 (7 new, 2 modified)
**Analogs found:** 9 / 9 (every new file maps to an existing daemon/test convention; the *tray runtime* itself has no analog — see No Analog Found)

This phase is entirely Python daemon-side under `daemon/`. It is **strictly additive** — no firmware, no macOS/Linux daemon edits (PROJECT.md lock). The substrate being wrapped is `daemon/claude_usage_daemon_windows.py`, which stays **unchanged in logic**; new code reads its `read_token()`/`write_payload()`/`stop_event`/`main()` surface and mirrors its stdlib-lean, `log()`-style, pytest-mock conventions.

The macOS daemon (`daemon/claude_usage_daemon.py`) has **no tray/autostart code** — it is a spirit-only reference, never an analog to copy from for the tray runtime.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `daemon/tray_windows.py` | provider (tray entry + state bridge) | event-driven | `daemon/claude_usage_daemon_windows.py` (`main()` / `log()`) | role-match (lifecycle/entry conventions only; tray API net-new) |
| `daemon/autostart_windows.py` | utility (winreg HKCU\Run toggle) | CRUD (registry key) | `_windows_credential_candidates()` / `read_token()` in daemon (env-driven path + stdlib + idempotent OSError swallow) | role-match |
| `daemon/icon_assets.py` | utility (logo.h → PNG + bubble) | transform | `firmware/src/logo.h` (RGB565A8 layout) + RESEARCH Code Example (verified pipeline) | partial (pure transform; no in-repo Python analog) |
| `daemon/tests/test_windows_autostart.py` | test | request-response (mocked) | `daemon/tests/test_windows_reconnect.py` (mock+patch style) + `test_windows_token.py` (monkeypatch/tmp_path) | exact |
| `daemon/tests/test_windows_icon.py` | test | transform assertion | `daemon/tests/test_windows_token.py` (FIXTURES + direct-import + assert) | exact |
| `daemon/tests/test_windows_no_wsl.py` | test | static (file read + regex) | `daemon/tests/test_windows_token.py` (Path-based, no mock) + RESEARCH guard example | exact |
| `daemon/requirements-windows.txt` | config | — | itself (current `bleak`+`httpx` + comment header) | exact (extend) |
| `daemon/README-windows.md` | doc | — | itself (`## What is NOT covered here` § promising Phase 4) | exact (extend) |
| `install-windows.ps1` (repo root) | config (bootstrap script) | batch | `daemon/claude-usage-daemon.sh` (macOS/Linux bootstrap — *spirit only*, different shell/OS) | partial |

## Pattern Assignments

### `daemon/tray_windows.py` (provider, event-driven)

**Analog:** `daemon/claude_usage_daemon_windows.py` — only for entry/lifecycle/log conventions. The pystray runtime and the asyncio↔main-thread split are net-new (RESEARCH Pattern 1 is the authority, not the codebase).

**`log()` style to reuse verbatim** (daemon L53-54):
```python
def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)
```
All new tray/install log lines MUST use this `[HH:MM:SS]` `flush=True` form (CONTEXT.md D-discretion note, RESEARCH "Project Constraints"). Import it from the daemon rather than re-defining if practical (`from daemon.claude_usage_daemon_windows import log`).

**Clean-shutdown hook — the Quit target** (daemon L342-356): `main()` already owns `stop_event = asyncio.Event()` and captures `loop = asyncio.get_running_loop()`, with SIGINT/SIGTERM wired through `_stop()` → `stop_event.set()`:
```python
async def main() -> None:
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    def _stop(*_args: object) -> None:
        log("Daemon stopping")
        stop_event.set()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop)
        except NotImplementedError:
            signal.signal(sig, _stop)
    ...
```
Quit is a **third trigger** alongside SIGINT/SIGTERM. Per RESEARCH Pitfall 2 / Anti-Patterns: the tray thread must NOT call `stop_event.set()` directly (asyncio.Event is not thread-safe). Route it as `loop.call_soon_threadsafe(stop_event.set)` then `icon.stop()`. The planner's A4 recommendation: have `main()` accept/populate a shared `TrayState` so the tray can read back `loop` + `stop_event` (additive — leaves the existing `stop_event = asyncio.Event()` line intact).

**Success/state signals to hook (additive setter injection, no logic change)** — the existing decision points in `connect_and_run()` (daemon L294-330) and `main()`'s D-05 backoff (L360-387):
- `write_payload()` returns `True` (daemon L130-138, called at L306) → `set_connected(time.time())` + last-sync timestamp.
- scan/slow-search branch (L364-373) and fast-reconnect branch (L375-383) → `set_scanning()` (both collapse to "Scanning" per D-01).
- `read_token()` → `None` (L201-208, called L300) / API HTTP ≥400 (L66-68) → `set_error("token expired — run claude login")` + D-04 toast on entry.

**Headless `__main__` convention** (daemon L390-399): the existing entry guards platform and runs `asyncio.run(main())`. The tray entry inverts this per RESEARCH Pattern 1 — `asyncio.run(main(...))` goes in a `threading.Thread(daemon=True)`, `pystray.Icon.run(setup=...)` owns the main thread. Keep `import pystray` **inside** the function (RESEARCH Wave-0 gap), not at module top, so the GTK-less dev/CI box can still import the module's pure helpers.

---

### `daemon/autostart_windows.py` (utility, CRUD on registry)

**Analog:** `_windows_credential_candidates()` (daemon L176-198) + `read_token()` (L201-208) — same shape: stdlib-only, env/`sys`-derived paths, OSError swallowed for idempotency, small pure functions that the tests monkeypatch.

**Idempotent-on-missing pattern to mirror** (daemon `read_token`, L201-208):
```python
def read_token() -> str | None:
    for path in _windows_credential_candidates():
        try:
            return _extract_access_token(path.read_text(encoding="utf-8"))
        except OSError:
            continue
    return None
```
Mirror this `try/except → continue/pass`, return-`None`/`False`-on-absent style for `disable()` (swallow `FileNotFoundError`) and `is_enabled()` (return `False` on `FileNotFoundError`). See RESEARCH "winreg autostart toggle" Code Example for the exact `enable()`/`disable()`/`is_enabled()` bodies. Key locks: **HKCU only** (no admin — D-07, ASVS V4), **`pythonw.exe`** derived from `sys.executable` dir (D-08, no console; RESEARCH Pitfall 3 — never `python.exe`), path derived at install time not hard-coded (RESEARCH Anti-Pattern; mirrors CLAUDE.md "repoint ExecStart" lesson).

---

### `daemon/icon_assets.py` (utility, transform)

**Analog:** `firmware/src/logo.h` for the binary layout (read-only, do not edit) + RESEARCH "logo.h → RGBA PNG" Code Example (verified end-to-end on this machine).

**logo.h layout contract** (header, L1-8):
```c
#define LOGO_WIDTH 80
#define LOGO_HEIGHT 80
// RGB565A8: 6400 RGB565 pixels (little-endian) followed by 6400 alpha bytes
static const uint8_t logo_data[19200] = {
```
So `data_size = 80*80*3 = 19200`; first `6400*2` bytes are little-endian RGB565, last `6400` are alpha (matches CLAUDE.md gotcha #8 planar RGB565A8). Use **proper RGB565→RGB888 rounding** `(v*255 + max//2)//max`, NOT a `*8` bit-shift (RESEARCH "Don't Hand-Roll"). Bound-check `len == w*h*3` before indexing (ASVS V5). Brand hex derived from the asset itself = **#DE7552** (RESEARCH A1; D-03 — do not invent art). Build the three state images **once** at startup, swap `icon.icon`, never recompute per tick (RESEARCH Anti-Pattern). Bubble colors locked by RESEARCH Code Example: connected `(60,200,90)`, scanning `(240,180,40)`, error `(220,60,60)`.

---

### `daemon/tests/test_windows_autostart.py` (test) — APP-01

**Analog:** `daemon/tests/test_windows_reconnect.py` for the `mock`/`patch` style; `test_windows_token.py` for `monkeypatch`/`tmp_path`/direct-import structure.

**Module docstring + run-line header** (every existing test file, e.g. token L1-5):
```python
#!/usr/bin/env python3
"""Unit tests for ... — <REQ-ID>.

Run: python -m pytest daemon/tests/test_windows_autostart.py -x -q
"""
```

**Direct-import + monkeypatch.setattr pattern** (token test L13, L48-50): import the unit under test directly, monkeypatch internals by module reference:
```python
import daemon.claude_usage_daemon_windows as mod
monkeypatch.setattr(mod, "_windows_credential_candidates", lambda: [creds])
```
`winreg` is **not importable off-Windows** (RESEARCH Environment table) — tests MUST mock it. Mirror the reconnect test's `patch(...)` style (test_windows_reconnect L57-58):
```python
with patch("daemon.claude_usage_daemon_windows.BleakClient", return_value=mock_client), \
     patch("daemon.claude_usage_daemon_windows.asyncio.sleep", new=AsyncMock()):
```
Apply the same to `winreg` (`patch("daemon.autostart_windows.winreg", ...)` or inject). Required cases per RESEARCH test map: `test_enable_writes_pythonw_command`, `test_disable_idempotent`, `test_is_enabled`, `test_command_uses_pythonw` (assert the command string ends in `pythonw.exe`, D-08).

---

### `daemon/tests/test_windows_icon.py` (test) — APP-01

**Analog:** `daemon/tests/test_windows_token.py` — FIXTURES path + direct-import + plain `assert`.

**FIXTURES constant pattern** (token test L16):
```python
FIXTURES = Path(__file__).parent / "fixtures"
```
For icon tests the "fixture" is the real in-repo `firmware/src/logo.h` (trusted asset). Required cases: `test_logo_parse` (80×80 RGBA, dominant color `#DE7552`), `test_rgb565_expand` (`0xDBAA → (222,117,82)`), `test_state_icon_bubble` (distinct image per state, bubble color matches). Import only the pure helpers (`load_logo_rgba`, `_expand565`, `state_icon`) so the GTK-less `pystray` top-level import never loads (RESEARCH Wave-0 gap). Pillow 11.2.1 is available on the dev box.

---

### `daemon/tests/test_windows_no_wsl.py` (test) — APP-02 / D-10

**Analog:** `daemon/tests/test_windows_token.py` (Path-based file read, no mocks) + RESEARCH "Static no-WSL-paths guard" Code Example.

```python
import re
from pathlib import Path

FORBIDDEN = [r"\\wsl\$", r"wsl\.exe", r"/home/", r"/mnt/"]

def test_daemon_has_no_wsl_paths():
    src = Path("daemon/claude_usage_daemon_windows.py").read_text()
    for pat in FORBIDDEN:
        assert not re.search(pat, src), f"WSL path leaked into daemon: {pat}"
```
**Confirmed clean today** — grep of the daemon for `\\wsl$|wsl.exe|/home/|/mnt/` returned no matches (re-verified during this mapping). Extend the guard to cover `tray_windows.py` + `autostart_windows.py` once they exist.

---

### `daemon/requirements-windows.txt` (config) — extend

**Analog:** itself. Current content (comment header + two deps):
```
# Windows-only dependency manifest for claude_usage_daemon_windows.py
# The macOS/Linux daemons manage their own dependencies separately.
bleak
httpx
```
Add `pystray` and `Pillow` (D-11; RESEARCH Standard Stack). `winreg` is stdlib — do NOT add it. `winotify` only if the Error toast needs a clickable action (otherwise `pystray.Icon.notify()` covers D-04 with zero new dep).

---

### `daemon/README-windows.md` (doc) — extend, don't duplicate

**Analog:** itself. The `## What is NOT covered here` section (L117-121) already names this phase's deliverables:
```
## What is NOT covered here

- Tray icon, login autostart, `install-windows.ps1` script — Phase 4
- PyInstaller / one-file `.exe` packaging — v2
- MAC-address cache / sleep-wake reconnect hardening — Phase 3
```
The scope line at L4-5 ("no tray icon, no autostart … those come in a later phase") and this list are the promises to fulfil. Move the tray/autostart/install bullet out of "NOT covered" into new documented steps; keep PyInstaller + (resolved) MAC-cache notes accurate.

---

### `install-windows.ps1` (config / bootstrap) — new (repo root per RESEARCH structure)

**Analog:** `daemon/claude-usage-daemon.sh` — spirit only (different OS/shell). No PowerShell precedent in-repo; RESEARCH "Recommended Project Structure" + D-09 are the spec. Sequence (D-09): create venv → `pip install -r requirements-windows.txt` → `autostart_windows.enable()` (or invoke the toggle) → launch the tray app, one turnkey run. Derive `pythonw.exe` from the just-created venv `Scripts/` dir at install time (RESEARCH Anti-Pattern + CLAUDE.md repoint lesson). Reuse the `[HH:MM:SS]` log shape for any echoed progress lines.

## Shared Patterns

### Logging
**Source:** `daemon/claude_usage_daemon_windows.py` L53-54 (`log()`)
**Apply to:** `tray_windows.py`, `autostart_windows.py`, `install-windows.ps1` (echo equivalent)
```python
def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)
```
Never log the token (ASVS V7; RESEARCH — the D-10 "log resolved token path" idea was explicitly NOT adopted).

### Stdlib-lean / idempotent-on-missing
**Source:** `read_token()` L201-208, `_windows_credential_candidates()` L176-198
**Apply to:** `autostart_windows.py` (winreg toggle — swallow `FileNotFoundError`, return `None`/`False` on absent, derive paths from `sys.executable`/env, no new dep where stdlib suffices). Inherits Phase 3 D-08 stdlib lean; D-07 picks `winreg` Run-key over a `.lnk`-that-needs-a-dependency.

### Test conventions
**Source:** `daemon/tests/test_windows_token.py` (FIXTURES, monkeypatch, tmp_path, direct import, `#!/usr/bin/env python3` + `Run:` docstring) and `daemon/tests/test_windows_reconnect.py` (`unittest.mock` `AsyncMock`/`MagicMock`/`patch`, `_make_*` helpers).
**Apply to:** all three new `daemon/tests/test_windows_*.py` files.
- Repo-root `sys.path` injection is already handled by root `conftest.py` so `import daemon.*` resolves — no per-test sys.path hacks needed:
```python
# /home/kevin/repos/Clawdmeter/conftest.py
sys.path.insert(0, os.path.dirname(__file__))
```
- `daemon/__init__.py` and `daemon/tests/__init__.py` already exist (empty); `daemon/tests/fixtures/` exists (`credentials_direct.json`, `credentials_nested.json`).
- Quick run: `python -m pytest daemon/tests/test_windows_autostart.py daemon/tests/test_windows_icon.py daemon/tests/test_windows_no_wsl.py -x -q`. Full suite (`python -m pytest daemon/tests/ -q`) is currently 47 passing.

### Mock-the-platform-binding discipline
**Source:** `test_windows_reconnect.py` patches `BleakClient`/`asyncio.sleep` because bleak's WinRT backend isn't on the dev box.
**Apply to:** `winreg` (not importable off-Windows) and `pystray` (GTK-less top-level import fails on Linux). Mock `winreg`; keep `import pystray` inside `tray_windows.main()` and test only pure helpers (icon math, state→image, command-string construction).

## No Analog Found

Files/concerns with no close match in the codebase — the planner should follow RESEARCH (which verified them locally) rather than search the codebase:

| Concern | Role | Data Flow | Reason |
|---------|------|-----------|--------|
| pystray tray runtime (icon, menu, `notify()`, click dispatch) in `tray_windows.py` | provider | event-driven | No tray code anywhere in repo (macOS daemon has none — confirmed). Follow RESEARCH Pattern 1 + Code Examples. |
| asyncio-loop-in-bg-thread ↔ pystray-on-main-thread coexistence + `call_soon_threadsafe` Quit join | provider | event-driven | Net-new architecture (D-11 discretion). RESEARCH Patterns 1-3 are the authority. |
| logo.h C-array → Pillow RGBA parse + corner-bubble compositor | utility | transform | No Python image code in repo; logo.h is only consumed by firmware C. RESEARCH "Code Examples" verified the exact pipeline. |
| `install-windows.ps1` PowerShell bootstrap | config | batch | No `.ps1` in repo; `claude-usage-daemon.sh` is bash for a different OS. D-09 is the spec. |

## Metadata

**Analog search scope:** `daemon/` (daemon source, tests, requirements, README, macOS reference), `firmware/src/logo.h`, repo-root `conftest.py` and `install-*.ps1` (none found).
**Files scanned:** `claude_usage_daemon_windows.py`, `claude_usage_daemon.py` (macOS, confirmed no tray), `tests/test_windows_token.py`, `tests/test_windows_reconnect.py` (head), `tests/test_windows_poll.py` (listing), `conftest.py`, `requirements-windows.txt`, `README-windows.md`, `firmware/src/logo.h` (header).
**Pattern extraction date:** 2026-06-01
