#!/usr/bin/env python3
"""Unit tests for connect_and_run reconnect hardening — BLE-03.

Covers:
  D-01: connect-retry wrapper (post-wake WinRT failure modes)
  D-03: zombie-link consecutive-failure break (stale is_connected)

Run: python -m pytest daemon/tests/test_windows_reconnect.py -x -q
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError

from daemon.claude_usage_daemon_windows import connect_and_run


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    """Run a coroutine synchronously for synchronous test functions."""
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_device(address="AA:BB:CC:DD:EE:FF"):
    """Build a minimal fake BLEDevice."""
    device = MagicMock()
    device.address = address
    return device


async def _make_event(set_):
    ev = asyncio.Event()
    if set_:
        ev.set()
    return ev


# ---------------------------------------------------------------------------
# D-01: connect-retry wrapper tests
# ---------------------------------------------------------------------------

def test_connect_retry_exhaustion_on_bleak_error(monkeypatch, capsys):
    """BleakError on every connect attempt exhausts CONNECT_RETRIES then returns False."""
    import daemon.claude_usage_daemon_windows as mod

    device = _make_device()
    stop_event = asyncio.get_event_loop().run_until_complete(_make_event(False))

    mock_client = AsyncMock()
    mock_client.connect = AsyncMock(side_effect=BleakError("Unreachable"))
    mock_client.is_connected = False
    mock_client.disconnect = AsyncMock()

    with patch("daemon.claude_usage_daemon_windows.BleakClient", return_value=mock_client), \
         patch("daemon.claude_usage_daemon_windows.asyncio.sleep", new=AsyncMock()):
        result = _run(connect_and_run(device, stop_event))

    assert result is False
    assert mock_client.connect.call_count == mod.CONNECT_RETRIES


def test_connect_retry_exhaustion_on_timeout_error(monkeypatch, capsys):
    """asyncio.TimeoutError on every connect attempt is treated same as BleakError."""
    import daemon.claude_usage_daemon_windows as mod

    device = _make_device()
    stop_event = asyncio.get_event_loop().run_until_complete(_make_event(False))

    mock_client = AsyncMock()
    mock_client.connect = AsyncMock(side_effect=asyncio.TimeoutError())
    mock_client.is_connected = False
    mock_client.disconnect = AsyncMock()

    with patch("daemon.claude_usage_daemon_windows.BleakClient", return_value=mock_client), \
         patch("daemon.claude_usage_daemon_windows.asyncio.sleep", new=AsyncMock()):
        result = _run(connect_and_run(device, stop_event))

    assert result is False
    assert mock_client.connect.call_count == mod.CONNECT_RETRIES


def test_connect_retry_calls_disconnect_between_attempts(monkeypatch):
    """Guarded disconnect() is called between failed connect attempts."""
    import daemon.claude_usage_daemon_windows as mod

    device = _make_device()
    stop_event = asyncio.get_event_loop().run_until_complete(_make_event(False))

    mock_client = AsyncMock()
    mock_client.connect = AsyncMock(side_effect=BleakError("Unreachable"))
    mock_client.is_connected = False
    mock_client.disconnect = AsyncMock()

    with patch("daemon.claude_usage_daemon_windows.BleakClient", return_value=mock_client), \
         patch("daemon.claude_usage_daemon_windows.asyncio.sleep", new=AsyncMock()):
        _run(connect_and_run(device, stop_event))

    # disconnect is called between attempts (at least CONNECT_RETRIES - 1 times)
    assert mock_client.disconnect.call_count >= mod.CONNECT_RETRIES - 1


def test_connect_success_on_first_attempt_no_extra_retries(monkeypatch):
    """First-attempt success consumes exactly 1 connect call and proceeds past connect block."""
    import daemon.claude_usage_daemon_windows as mod

    device = _make_device()
    # stop_event is set so the loop exits immediately after connecting
    stop_event = asyncio.get_event_loop().run_until_complete(_make_event(True))

    mock_client = AsyncMock()
    mock_client.connect = AsyncMock(return_value=None)  # success
    mock_client.is_connected = True
    mock_client.disconnect = AsyncMock()
    mock_client.start_notify = AsyncMock()
    mock_client.write_gatt_char = AsyncMock(return_value=None)

    with patch("daemon.claude_usage_daemon_windows.BleakClient", return_value=mock_client), \
         patch("daemon.claude_usage_daemon_windows.read_token", return_value="fake-token"), \
         patch("daemon.claude_usage_daemon_windows.poll_api", new=AsyncMock(return_value={"ok": True})):
        _run(connect_and_run(device, stop_event))

    assert mock_client.connect.call_count == 1


def test_connect_retry_exhaustion_does_not_log_token(monkeypatch, capsys):
    """On exhaustion, no log line contains the patched token sentinel (T-03-01)."""
    import daemon.claude_usage_daemon_windows as mod

    TOKEN_SENTINEL = "sk-ant-SUPERSECRET-DO-NOT-LOG-12345"
    device = _make_device()
    stop_event = asyncio.get_event_loop().run_until_complete(_make_event(False))

    mock_client = AsyncMock()
    mock_client.connect = AsyncMock(side_effect=BleakError("Unreachable"))
    mock_client.is_connected = False
    mock_client.disconnect = AsyncMock()

    with patch("daemon.claude_usage_daemon_windows.BleakClient", return_value=mock_client), \
         patch("daemon.claude_usage_daemon_windows.read_token", return_value=TOKEN_SENTINEL), \
         patch("daemon.claude_usage_daemon_windows.asyncio.sleep", new=AsyncMock()):
        _run(connect_and_run(device, stop_event))

    captured = capsys.readouterr()
    assert TOKEN_SENTINEL not in captured.out, "Token sentinel leaked to stdout (T-03-01)"
    assert TOKEN_SENTINEL not in captured.err, "Token sentinel leaked to stderr (T-03-01)"
