# Phase 1: Foundation - Pattern Map

**Mapped:** 2026-06-01
**Files analyzed:** 4 (2 new Python files, 1 new test file, 1 modified note)
**Analogs found:** 2 / 4 (the test file and fixtures have no analog — no pytest infrastructure exists)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `daemon/claude_usage_daemon_windows.py` | service | file-I/O → transform | `daemon/claude_usage_daemon.py` | exact (copy-source) |
| `daemon/tests/test_windows_token.py` | test | — | `daemon/test_macos_connect.py` | style-reference only (integration, not unit) |
| `daemon/tests/fixtures/*.json` | config | — | none | no analog |
| `.planning/notes/windows-daemon-port.md` | — | — | itself (append only) | n/a |

## Pattern Assignments

### `daemon/claude_usage_daemon_windows.py` (service, file-I/O → transform)

**Analog:** `daemon/claude_usage_daemon.py`

**Imports pattern** (lines 1–19 of analog):
```python
#!/usr/bin/env python3
"""Claude Usage Tracker Daemon (BLE) — macOS port..."""

import asyncio
import getpass
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path
```

For the Windows scaffold (D-05 minimal scope), the import block shrinks to stdlib-only — no `asyncio`, `bleak`, `httpx`. Only what `_extract_access_token()`, `read_token()`, and `__main__` actually use:

```python
#!/usr/bin/env python3
"""Claude Usage Tracker Daemon — Windows scaffold (Phase 1).

Reads the Claude OAuth token from the native-Windows credentials path.
Phase 1: token read + redacted verification only. BLE/API in later phases.
"""

import datetime
import json
import os
import re
import sys
from pathlib import Path
```

**Core extract pattern — copy verbatim** (analog lines 57–86):
```python
def _extract_access_token(blob: str) -> str | None:
    """Pull the accessToken out of a credentials blob.

    Claude Code stores credentials as a JSON object; the blob may also be
    nested ({"claudeAiOauth": {"accessToken": "..."}}). Fall back to a
    regex match so unexpected shapes still work, and finally treat the
    blob as a raw token if nothing else matches.
    """
    blob = blob.strip()
    if not blob:
        return None
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict):
        # direct: {"accessToken": "..."}
        if isinstance(data.get("accessToken"), str):
            return data["accessToken"]
        # nested: {"claudeAiOauth": {"accessToken": "..."}}
        for v in data.values():
            if isinstance(v, dict) and isinstance(v.get("accessToken"), str):
                return v["accessToken"]
    m = re.search(r'"accessToken"\s*:\s*"([^"]+)"', blob)
    if m:
        return m.group(1)
    # Raw token (no JSON wrapper) — must look plausible (sk-ant-... etc.)
    if re.fullmatch(r"[A-Za-z0-9_\-.~+/=]{20,}", blob):
        return blob
    return None
```

D-08 is explicit: copy this function body exactly. Do not import from `claude_usage_daemon.py`.

**read_token() structural reference** (analog lines 115–127):
```python
# macOS analog — shows the pattern; Windows version replaces the platform branch
# with a flat candidate-path loop (D-04: file-search only, no Keychain).

def _read_token_file() -> str | None:       # analog's Linux-path branch
    try:
        raw = CREDENTIALS_PATH.read_text()
    except OSError as e:
        log(f"Error reading credentials: {e}")
        return None
    return _extract_access_token(raw)

def read_token() -> str | None:             # analog's dispatch function
    if sys.platform == "darwin":
        return _read_token_keychain()
    return _read_token_file()
```

Windows replacement — candidate-path loop (no platform branch needed per D-04):
```python
def _windows_credential_candidates() -> list[Path]:
    # Priority 1: project-specific env override (D-03)
    if override := os.environ.get("CLAUDE_CREDENTIALS_PATH"):
        return [Path(override)]
    # Priority 2: official CLAUDE_CONFIG_DIR env override
    if config_dir := os.environ.get("CLAUDE_CONFIG_DIR"):
        return [Path(config_dir) / ".credentials.json"]
    # Priority 3: D-02 candidate list — first hit wins
    home = Path.home()
    local_appdata = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
    appdata = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
    return [
        home / ".claude" / ".credentials.json",         # primary (confirmed by docs)
        local_appdata / "Claude" / ".credentials.json",  # fallback 2
        appdata / "Claude" / ".credentials.json",        # fallback 3
    ]

def read_token() -> str | None:
    for path in _windows_credential_candidates():
        try:
            return _extract_access_token(path.read_text(encoding="utf-8"))
        except OSError:
            continue
    return None
```

Note: `PermissionError` is a subclass of `OSError` in Python 3, so `except OSError` covers Windows file-lock errors (Pitfall 3 from RESEARCH.md).

**`__main__` pattern** (analog lines 452–456):
```python
# Analog:
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
```

Windows scaffold replaces `asyncio.run(main())` with synchronous read + redacted print (D-05/D-06/D-07):
```python
if __name__ == "__main__":
    if sys.platform != "win32":
        print(
            "Warning: running under Linux/WSL — Windows credential paths will "
            "not resolve correctly.",
            file=sys.stderr,
        )
    token = read_token()
    if token is None:
        print(
            "No Windows token found — install Claude Code natively on Windows "
            "and run 'claude login'."
        )
        sys.exit(1)
    expiry_str = _read_expiry()  # separate pass over raw dict for expiresAt
    print(f"Token OK (sk-ant-…{token[-4:]}), expires {expiry_str}")
```

**Expiry helper pattern** (no analog — new for Windows, see RESEARCH.md Pattern 2):
```python
def _read_expiry() -> str:
    """Return human-readable expiry from the first-hit credentials file."""
    for path in _windows_credential_candidates():
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            data = json.loads(raw)
            oauth = data.get("claudeAiOauth", {})
            expires_ms = oauth.get("expiresAt")
            if expires_ms is None:
                return "expiry unknown"
            dt = datetime.datetime.fromtimestamp(
                expires_ms / 1000, tz=datetime.timezone.utc
            )
            return dt.strftime("%Y-%m-%d %H:%M UTC")
        except (TypeError, ValueError, OSError, json.JSONDecodeError):
            return "expiry unknown"
    return "expiry unknown"
```

Key: divide `expiresAt` by 1000 before passing to `fromtimestamp` — the field is epoch milliseconds (JavaScript Date.now() convention). Raw value yields year ~57000.

---

### `daemon/tests/test_windows_token.py` (test, unit)

**Analog:** `daemon/test_macos_connect.py` — style reference only.

The analog is an **integration test** (requires live hardware, macOS Bluetooth, the `bleak` library, and the macOS daemon module). It does NOT use pytest: it is a plain `asyncio.run(main())` script. This means there is **no pytest-style unit test in the repo to mirror** — Phase 1 must establish the convention from scratch.

**Analog file structure** (lines 1–14):
```python
#!/usr/bin/env python3
"""Quick end-to-end test of the macOS connected-peripheral path.
...
"""
import asyncio

from bleak import BleakClient
import claude_usage_daemon as d

async def main() -> None:
    ...

if __name__ == "__main__":
    asyncio.run(main())
```

Observations from the analog:
- Module-level docstring describes what the test does and how to run it.
- Imports the daemon module directly (`import claude_usage_daemon as d`).
- No pytest, no fixtures, no assertions — integration-only.

**Convention to establish for Phase 1 (no analog exists — planner must define):**

The test file must be a proper pytest module. Conventions to adopt:
- Module-level docstring naming what requirement it covers (`TOKEN-01`).
- Import the new module directly: `from daemon.claude_usage_daemon_windows import _extract_access_token, read_token`.
- Use `tmp_path` (pytest built-in fixture) to write credential fixture files at runtime rather than loading from `fixtures/` — simpler and avoids path-resolution issues when running from different working directories.
- Alternatively, load from `fixtures/` via `Path(__file__).parent / "fixtures" / "credentials_nested.json"` — explicit, readable.
- Each test function name maps 1-to-1 to a TOKEN-01 sub-case (names given in RESEARCH.md validation table).
- Use `monkeypatch` (pytest built-in) to set env vars for D-03 override tests and to mock `_windows_credential_candidates` to return a known path.

```python
#!/usr/bin/env python3
"""Unit tests for daemon/claude_usage_daemon_windows.py — TOKEN-01.

Run: python -m pytest daemon/tests/test_windows_token.py -x -q
"""
import json
from pathlib import Path
import pytest

from daemon.claude_usage_daemon_windows import _extract_access_token, read_token


FIXTURES = Path(__file__).parent / "fixtures"


def test_extract_nested_shape():
    blob = (FIXTURES / "credentials_nested.json").read_text()
    assert _extract_access_token(blob) == "sk-ant-test-1234"


def test_extract_direct_shape():
    blob = (FIXTURES / "credentials_direct.json").read_text()
    assert _extract_access_token(blob) == "sk-ant-test-5678"


def test_read_token_primary_path(tmp_path, monkeypatch):
    creds = tmp_path / ".claude" / ".credentials.json"
    creds.parent.mkdir(parents=True)
    creds.write_text(json.dumps({"claudeAiOauth": {"accessToken": "sk-ant-test-AAAA"}}))
    monkeypatch.setenv("CLAUDE_CREDENTIALS_PATH", str(creds))
    assert read_token() == "sk-ant-test-AAAA"


def test_read_token_no_file(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CREDENTIALS_PATH", str(tmp_path / "nonexistent.json"))
    assert read_token() is None
```

---

### `daemon/tests/fixtures/*.json` (config, static)

**Analog:** None — no fixture files exist in the repo.

Two files to create; contents are small and fully specified:

**`fixtures/credentials_nested.json`** — real Windows on-disk shape:
```json
{
  "claudeAiOauth": {
    "accessToken": "sk-ant-test-1234",
    "refreshToken": "sk-ant-ort-test-5678",
    "expiresAt": 9999999999000,
    "scopes": ["user:inference", "user:profile"]
  }
}
```

**`fixtures/credentials_direct.json`** — legacy direct shape (still handled by `_extract_access_token`):
```json
{
  "accessToken": "sk-ant-test-5678"
}
```

Note: `expiresAt: 9999999999000` is a far-future millisecond epoch (~year 2286) so expiry-display tests never produce stale output.

---

### `.planning/notes/windows-daemon-port.md` (modified — append only)

**Analog:** The file itself (lines 1–73, already read).

Append a new top-level section recording the D-01 verdict. Match the existing heading style (H2 `##` sections, plain prose, bullet points, code block for the flags). The existing file uses:
- `---` front-matter block at top (do not repeat)
- `## Problem` / `## Decisions` / `## BLE research findings` / `## Open questions` H2 sections
- Numbered lists for multi-point findings

Append after line 73 (end of file):
```markdown
## GATT encryption gate — verdict (D-01)

**Status: CONFIRMED UNENCRYPTED** — verified 2026-06-01 by reading
`firmware/src/ble.cpp` lines 185–199 directly.

The custom data-service characteristics (service UUID `4c41555a-…0001`) are
created with plain NimBLE property flags:

- **RX** (`…0002`): `NIMBLE_PROPERTY::WRITE | WRITE_NR` — no `_ENC` / `_AUTHEN` / `_AUTHOR`
- **TX** (`…0003`): `NIMBLE_PROPERTY::READ | NOTIFY` — plain
- **REQ** (`…0004`): `NIMBLE_PROPERTY::NOTIFY` — plain

The NimBLE library does define encrypted variants (`READ_ENC`, `WRITE_ENC`,
`READ_AUTHEN`, `WRITE_AUTHEN`, etc.) — they are used on the HID keyboard
characteristics but are absent from the custom data service.

**Consequence:** The Windows daemon needs no manual Bluetooth pairing and no
firmware change. The "encrypted characteristics" contingency from the BLE
research section above is closed.

*Satisfies Phase 1 Success Criterion #1.*
```

---

## Shared Patterns

### File-read with OSError catch
**Source:** `daemon/claude_usage_daemon.py` lines 115–121
**Apply to:** `read_token()` and `_read_expiry()` in `claude_usage_daemon_windows.py`
```python
try:
    raw = CREDENTIALS_PATH.read_text()
except OSError as e:
    log(f"Error reading credentials: {e}")
    return None
```

Windows note: `PermissionError` is a subclass of `OSError` in Python 3 — `except OSError` covers Windows file-lock errors without a separate clause.

### Shebang + module docstring convention
**Source:** `daemon/claude_usage_daemon.py` lines 1–7
**Apply to:** `claude_usage_daemon_windows.py` and `test_windows_token.py`
```python
#!/usr/bin/env python3
"""One-line summary.

Extended description of purpose and usage.
"""
```

### Non-zero exit on failure
**Source:** `daemon/test_macos_connect.py` (implicit — returns from main on failure)
**Apply to:** `__main__` block of `claude_usage_daemon_windows.py`
```python
sys.exit(1)   # on any failure path (D-07)
```

---

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `daemon/tests/test_windows_token.py` | test | — | No pytest-style unit test exists in the repo. Only `test_macos_connect.py` exists; it is a plain asyncio integration script with no pytest structure. Phase 1 must establish the pytest convention. |
| `daemon/tests/__init__.py` | config | — | `daemon/tests/` directory does not exist. Wave 0 creates it. |
| `daemon/tests/fixtures/credentials_nested.json` | config | — | No fixture files exist anywhere in the repo. |
| `daemon/tests/fixtures/credentials_direct.json` | config | — | Same as above. |

**No pytest config exists** (`pytest.ini`, `pyproject.toml` with `[tool.pytest]`, `conftest.py`) — Wave 0 must create `daemon/tests/__init__.py` and install pytest (`pip install pytest`). A `conftest.py` is not required for Phase 1's flat test structure but is recommended if test count grows.

---

## Metadata

**Analog search scope:** `/home/kevin/repos/Clawdmeter/daemon/` (all files), repo-wide search for `pytest.ini`, `pyproject.toml`, `conftest.py`
**Files scanned:** `daemon/claude_usage_daemon.py` (457 lines, full read), `daemon/test_macos_connect.py` (57 lines, full read), `.planning/notes/windows-daemon-port.md` (73 lines, full read)
**Pattern extraction date:** 2026-06-01
